"""
Floating camera angle HUD anchored to the top-left of the viewport.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np
from qtpy.QtCore import Qt, QEvent, QPoint, QCoreApplication
from qtpy.QtGui import QColor, QPen, QPainter
from qtpy.QtWidgets import QVBoxLayout, QWidget

from ..stylesheets import Typography
from ..utils import Throttle
from .sliders import SliderRow

_STYLE = f"""
QSlider {{
    height: 24px;
}}
QSlider::groove:horizontal {{
    background: rgba(255, 255, 255, 0.10);
    height: 3px;
    border-radius: 1px;
}}
QSlider::handle:horizontal {{
    background: rgba(255, 255, 255, 0.85);
    width: 10px;
    height: 10px;
    margin: -4px 0;
    border-radius: 5px;
    border: none;
}}
QSlider::handle:horizontal:hover {{
    background: #ffffff;
}}
QSlider::sub-page:horizontal {{
    background: rgba(255, 255, 255, 0.22);
    border-radius: 1px;
}}
QLabel {{
    color: rgba(255, 255, 255, 0.55);
    font-size: {Typography.SMALL}px;
    background: transparent;
}}
"""

_REF_DIRECTIONS = {
    "z": np.array([0.0, 0.0, 1.0]),
    "c": np.array([0.0, 1.0, 0.0]),
    "x": np.array([1.0, 0.0, 0.0]),
}

_REF_VIEW_UPS = {
    "z": np.array([1.0, 0.0, 1.0]),
    "c": np.array([1.0, 0.0, 0.0]),
    "x": np.array([0.0, 1.0, 0.0]),
}


def _decompose_angles(camera, view_key, aligned_direction):
    """Compute (elevation, azimuth, pitch) from camera state."""
    position = np.array(camera.GetPosition())
    focal = np.array(camera.GetFocalPoint())
    direction = position - focal
    norm = np.linalg.norm(direction)
    if norm < 1e-12:
        return 0, 0, 0
    direction /= norm
    if not aligned_direction:
        direction = -direction

    ref = _REF_DIRECTIONS.get(view_key)
    if ref is None:
        return 0, 0, 0

    # Compute azimuth from the Y component relative to reference
    # For the ZYX Euler decomposition of the rotation R that maps ref to direction,
    # we use spherical-like decomposition relative to the reference frame.
    # Build an orthonormal reference frame from ref direction.
    ref_n = ref / np.linalg.norm(ref)
    ref_up = _REF_VIEW_UPS[view_key].copy()
    ref_up = ref_up - np.dot(ref_up, ref_n) * ref_n
    ref_up /= np.linalg.norm(ref_up)
    ref_right = np.cross(ref_up, ref_n)

    # Project current direction into reference frame
    dx = np.dot(direction, ref_right)
    dy = np.dot(direction, ref_up)
    dz = np.dot(direction, ref_n)

    # Azimut is rotation in right-forward, elevation in up-forward plane
    azimuth = np.degrees(np.arctan2(dx, dz))
    elevation = np.degrees(np.arctan2(dy, np.sqrt(dx * dx + dz * dz)))
    view_up = np.array(camera.GetViewUp())
    fwd = direction

    right = np.cross(fwd, ref_up)
    right_norm = np.linalg.norm(right)
    if right_norm < 1e-12:
        right = ref_right
    else:
        right /= right_norm

    expected_up = np.cross(right, fwd)
    expected_up_norm = np.linalg.norm(expected_up)
    if expected_up_norm < 1e-12:
        return elevation, azimuth, 0
    expected_up /= expected_up_norm

    # Pitch is the angle between expected_up and actual view_up around fwd
    cos_pitch = np.clip(np.dot(view_up, expected_up), -1, 1)
    sin_pitch = np.dot(np.cross(expected_up, view_up), fwd)
    pitch = np.degrees(np.arctan2(sin_pitch, cos_pitch))

    return (
        int(np.clip(round(elevation), -180, 180)),
        int(np.clip(round(azimuth), -180, 180)),
        int(np.clip(round(pitch), -180, 180)),
    )


class CameraHUD(QWidget):
    """Floating HUD displaying camera elevation, azimuth, and pitch.

    Parameters
    ----------
    parent : QWidget, optional
        Transient parent (the main window).
    """

    _BG_IDLE = QColor(30, 32, 38, 160)
    _BG_HOVER = QColor(36, 38, 46, 235)
    _BORDER = QColor(255, 255, 255, 25)
    _RADIUS = 6
    _MARGIN = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)

        self._viewport_parent = None
        self._top_window = None
        self._hovered = False
        self._app = None
        self._updating_from_camera = False

        self._throttle_camera = Throttle(self._push_to_camera, interval_ms=30)

        self._build_ui()
        self.hide()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(4)

        self._rows = {}
        for axis, label in [("elevation", "E"), ("azimuth", "A"), ("pitch", "P")]:
            row = SliderRow(
                label,
                min_val=-180,
                max_val=180,
                default=0,
                decimals=0,
                suffix="\u00b0",
            )
            row.slider.setMinimumWidth(120)
            row.valueChanged.connect(self._on_slider_changed)
            self._rows[axis] = row
            main.addWidget(row)

        self.setStyleSheet(_STYLE)

    def _on_slider_changed(self):
        if self._updating_from_camera:
            return
        self._throttle_camera()

    def _push_to_camera(self):
        if self._app is None:
            return
        view = getattr(self._app, "_camera_view", None)
        if view is None:
            return
        direction = getattr(self._app, "_camera_direction", True)
        self._app.set_camera_view(
            view,
            direction,
            int(self._rows["elevation"].value()),
            int(self._rows["azimuth"].value()),
            int(self._rows["pitch"].value()),
        )

    def set_angles(self, elevation=0, azimuth=0, pitch=0):
        """Update displayed angles (called from camera observer)."""
        self._updating_from_camera = True
        self._rows["elevation"].setValue(int(elevation))
        self._rows["azimuth"].setValue(int(azimuth))
        self._rows["pitch"].setValue(int(pitch))
        self._updating_from_camera = False

    def attach(self, app):
        """Attach HUD to the application and its viewport.

        Parameters
        ----------
        app : App
            The main application window (provides viewport_container,
            renderer, interactor, and set_camera_view).
        """
        self._app = app
        self._viewport_parent = app.viewport_container
        self._viewport_parent.installEventFilter(self)

        # self.parent() is the main window (passed in __init__); tracking
        # it keeps the floating HUD anchored as the window moves, resizes,
        # or hides.
        self._top_window = self.parent()
        if self._top_window is not None:
            self._top_window.installEventFilter(self)

        self._install_camera_observer()
        self._reposition()

    def _install_camera_observer(self):
        """Observe interactor events to sync HUD when user drags camera."""
        interactor = self._app.interactor
        self._throttle_sync = Throttle(self._sync_from_camera, interval_ms=50)
        self._observer_id = interactor.AddObserver(
            "InteractionEvent", self._on_camera_interaction
        )

    def _on_camera_interaction(self, obj, event):
        self._throttle_sync()

    def _sync_from_camera(self):
        """Reverse-compute angles from the VTK camera and update sliders."""
        if self._app is None:
            return
        view_key = getattr(self._app, "_camera_view", None)
        if view_key is None:
            return
        aligned = getattr(self._app, "_camera_direction", True)
        camera = self._app.renderer.GetActiveCamera()
        elevation, azimuth, pitch = _decompose_angles(camera, view_key, aligned)
        self._app._camera_elevation = elevation
        self._app._camera_azimuth = azimuth
        self._app._camera_pitch = pitch
        self.set_angles(elevation, azimuth, pitch)

    def eventFilter(self, obj, event):
        etype = event.type()
        if obj is self._viewport_parent and etype == QEvent.Type.Resize:
            self._reposition()
        elif obj is self._top_window:
            if etype in (
                QEvent.Type.Move,
                QEvent.Type.Resize,
                QEvent.Type.WindowStateChange,
            ):
                self._reposition()
            elif etype == QEvent.Type.Hide and self.isVisible():
                self._was_visible = True
                self.hide()
            elif etype == QEvent.Type.Show and getattr(self, "_was_visible", False):
                self._was_visible = False
                self.show()
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_from_camera()
        self._reposition()

    def _reposition(self):
        if self._viewport_parent is None or not self.isVisible():
            return
        vp = self._viewport_parent
        if vp.width() <= 0 or vp.height() <= 0:
            return

        layout = self.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)

        hint = self.sizeHint()
        w = hint.width()
        h = hint.height()
        self.setMinimumSize(self.minimumSizeHint())

        top_left = vp.mapToGlobal(QPoint(0, 0))
        x = top_left.x() + self._MARGIN
        y = top_left.y() + self._MARGIN
        self.setGeometry(x, y, w, h)

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        bg = self._BG_HOVER if self._hovered else self._BG_IDLE
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, self._RADIUS, self._RADIUS)
        p.setPen(QPen(self._BORDER, 0.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, self._RADIUS, self._RADIUS)
        p.end()
