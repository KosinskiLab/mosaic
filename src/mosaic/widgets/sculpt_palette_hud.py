"""
Floating sculpt palette HUD anchored to the bottom-left of the viewport.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtCore import Qt, QEvent, QPoint, QCoreApplication, Signal
from qtpy.QtGui import QColor, QPainter, QPen
from qtpy.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..sculpt.session import TOOLS
from ..stylesheets import Colors, Typography
from .sliders import SliderRow

__all__ = ["SculptPaletteHUD"]


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
QPushButton {{
    color: rgba(255, 255, 255, 0.75);
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 4px;
    padding: 3px 8px;
    font-size: {Typography.SMALL}px;
}}
QPushButton:hover {{
    background: rgba(255, 255, 255, 0.12);
    color: rgba(255, 255, 255, 0.95);
}}
QPushButton:checked {{
    background: {Colors.alpha("PRIMARY", 0.28)};
    color: #ffffff;
    border: 1px solid {Colors.alpha("PRIMARY", 0.55)};
}}
"""


class SculptPaletteHUD(QWidget):
    """Floating palette providing sculpt tool selection and brush parameters."""

    toolChanged = Signal(str)
    radiusChanged = Signal(float)
    strengthChanged = Signal(float)

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
        self._app = None
        self._hovered = False
        self._suppress_tool_signal = False
        self._suppress_radius_signal = False
        self._suppress_strength_signal = False

        self._tool_buttons = {}
        self._build_ui()
        self.hide()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(4)

        button_row = QWidget(self)
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(4)

        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        for tool in TOOLS:
            btn = QPushButton(tool.label, button_row)
            btn.setCheckable(True)
            btn.setAutoDefault(False)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _checked, t=tool.id: self._on_tool_clicked(t))
            self._button_group.addButton(btn)
            self._tool_buttons[tool.id] = btn
            button_layout.addWidget(btn)

        self._tool_buttons[TOOLS[0].id].setChecked(True)
        main.addWidget(button_row)

        self._radius_row = SliderRow(
            "Radius",
            min_val=0.5,
            max_val=500.0,
            default=10.0,
            decimals=1,
            suffix=" A",
        )
        self._radius_row.slider.setMinimumWidth(140)
        self._radius_row.slider.setToolTip("Brush radius — adjust with [ and ]")
        self._radius_row.valueChanged.connect(self._on_radius_changed)
        main.addWidget(self._radius_row)

        self._strength_row = SliderRow(
            "Strength",
            min_val=0.0,
            max_val=1.0,
            default=0.25,
            decimals=2,
        )
        self._strength_row.slider.setMinimumWidth(140)
        self._strength_row.slider.setToolTip(
            "Smooth tool strength (per-stamp Laplacian step)"
        )
        self._strength_row.valueChanged.connect(self._on_strength_changed)
        main.addWidget(self._strength_row)

        self.setStyleSheet(_STYLE)

    def _on_tool_clicked(self, tool: str):
        if self._suppress_tool_signal:
            return
        self.toolChanged.emit(tool)

    def _on_radius_changed(self, value: float):
        if self._suppress_radius_signal:
            return
        self.radiusChanged.emit(float(value))

    def _on_strength_changed(self, value: float):
        if self._suppress_strength_signal:
            return
        self.strengthChanged.emit(float(value))

    def set_tool(self, tool: str):
        """Programmatically select a tool button without emitting ``toolChanged``."""
        btn = self._tool_buttons.get(tool)
        if btn is None:
            return None
        self._suppress_tool_signal = True
        try:
            btn.setChecked(True)
        finally:
            self._suppress_tool_signal = False
        return None

    def current_tool(self) -> str:
        """Return the currently checked tool id."""
        for tool_id, btn in self._tool_buttons.items():
            if btn.isChecked():
                return tool_id
        return "view"

    def set_radius(self, radius: float):
        """Update the radius slider without emitting ``radiusChanged``."""
        self._suppress_radius_signal = True
        try:
            self._radius_row.setValue(float(radius))
        finally:
            self._suppress_radius_signal = False
        return None

    def set_radius_range(self, min_val: float, max_val: float) -> None:
        """Rescale the radius slider to fit the currently bound mesh's scale."""
        if max_val <= min_val:
            return None
        current = self._radius_row.value()
        self._suppress_radius_signal = True
        try:
            self._radius_row.setRange(float(min_val), float(max_val))
            clamped = min(max(current, float(min_val)), float(max_val))
            self._radius_row.setValue(clamped)
        finally:
            self._suppress_radius_signal = False
        return None

    def set_strength(self, value: float) -> None:
        """Update the strength slider without emitting ``strengthChanged``."""
        self._suppress_strength_signal = True
        try:
            self._strength_row.setValue(float(value))
        finally:
            self._suppress_strength_signal = False
        return None

    def current_strength(self) -> float:
        return float(self._strength_row.value())

    def attach(self, app):
        """Attach the HUD to the application and its viewport container.

        Parameters
        ----------
        app : App
            The main application window (provides ``viewport_container``).
        """
        self._app = app
        self._viewport_parent = app.viewport_container
        self._viewport_parent.installEventFilter(self)

        self._top_window = self.parent()
        if self._top_window is not None:
            self._top_window.installEventFilter(self)

        self._reposition()

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
        y = top_left.y() + vp.height() - h - self._MARGIN
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
