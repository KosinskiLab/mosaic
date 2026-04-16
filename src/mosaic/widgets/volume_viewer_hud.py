"""
Floating HUD overlay for the volume viewer.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtCore import Qt, QEvent, QTimer
from qtpy.QtGui import QPainter, QColor, QPen, QCursor, QFont
from qtpy.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QPushButton,
    QApplication,
)

from ..icons import icon
from .segmented_control import SegmentedControl
from .volume_viewer import VolumeViewer

_ICON = "#d4d4d8"
_BTN = 28

_MAX_PILL_WIDTH = 720

_STRIP_STYLE = f"""
QPushButton {{
    background: rgba(255, 255, 255, 0.07);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 4px;
    color: rgba(255, 255, 255, 0.82);
    padding: 2px 8px;
    font-size: 11px;
}}
QPushButton:hover {{
    background: rgba(255, 255, 255, 0.14);
    border-color: rgba(255, 255, 255, 0.10);
}}
QPushButton:pressed {{ background: rgba(255, 255, 255, 0.19); }}
QPushButton:checked {{
    border: 1px solid rgba(255, 255, 255, 0.35);
    background: rgba(255, 255, 255, 0.10);
}}
QPushButton:disabled {{
    color: rgba(255, 255, 255, 0.18);
    background: rgba(255, 255, 255, 0.03);
    border-color: transparent;
}}

QPushButton#loadClose {{
    padding: 3px 10px;
    border-top-right-radius: 0; border-bottom-right-radius: 0;
    border-right: none;
}}
QPushButton#recentDrop {{
    padding: 2px 4px;
    border-top-left-radius: 0; border-bottom-left-radius: 0;
    border-left: none;
    min-width: 18px; max-width: 18px;
}}

QComboBox {{
    background: rgba(255, 255, 255, 0.07);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 4px;
    color: rgba(255, 255, 255, 0.82);
    padding: 2px 18px 2px 6px;
    font-size: 11px;
    max-height: {_BTN - 4}px;
}}
QComboBox:hover {{ background: rgba(255, 255, 255, 0.14); }}
QComboBox:disabled {{
    color: rgba(255, 255, 255, 0.18);
    background: rgba(255, 255, 255, 0.03);
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 14px; border: none;
}}
QComboBox::down-arrow {{
    width: 0; height: 0;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-top: 4px solid rgba(255, 255, 255, 0.45);
}}
QComboBox QAbstractItemView {{
    background-color: #12121a;
    color: rgba(255, 255, 255, 0.85);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px; padding: 4px;
    selection-background-color: rgba(99, 102, 241, 0.35);
    selection-color: rgba(255, 255, 255, 0.95);
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    background: transparent;
    padding: 4px 8px;
    border-radius: 3px;
}}
QComboBox QAbstractItemView::item:selected {{
    background: rgba(99, 102, 241, 0.35);
}}
QComboBox QFrame {{
    background: transparent;
    border: none;
}}

QSlider {{ height: {_BTN}px; }}
QSlider::groove:horizontal {{
    background: rgba(255, 255, 255, 0.10);
    height: 3px; border-radius: 1px;
}}
QSlider::handle:horizontal {{
    background: rgba(255, 255, 255, 0.85);
    width: 12px; height: 12px;
    margin: -5px 0; border-radius: 6px; border: none;
}}
QSlider::handle:horizontal:hover {{ background: #ffffff; }}
QSlider::sub-page:horizontal {{
    background: rgba(255, 255, 255, 0.22);
    border-radius: 1px;
}}
QSlider::groove:horizontal:disabled {{ background: rgba(255, 255, 255, 0.04); }}
QSlider::handle:horizontal:disabled {{ background: rgba(255, 255, 255, 0.15); }}
QSlider::sub-page:horizontal:disabled {{ background: rgba(255, 255, 255, 0.06); }}

QLabel {{
    color: rgba(255, 255, 255, 0.60);
    font-size: 11px; background: transparent;
}}
QLabel:disabled {{ color: rgba(255, 255, 255, 0.18); }}
"""


def _icon_btn(name, tooltip, size=_BTN):
    btn = QPushButton()
    btn.setIcon(icon(name, color=_ICON))
    btn.setFixedSize(size, size)
    btn.setToolTip(tooltip)
    return btn


def _dark_dual_slider(slider):
    """Re-theme a :class:`DualHandleSlider` for the dark HUD."""
    slider.setMinimumHeight(_BTN)
    slider.handle_size = 12
    slider.groove_color = QColor(255, 255, 255, 25)
    slider.active_color = QColor(255, 255, 255, 80)
    slider.handle_color = QColor(255, 255, 255, 220)
    slider.border_color = QColor(255, 255, 255, 30)
    slider.groove_disabled = QColor(255, 255, 255, 10)
    slider.active_disabled = QColor(255, 255, 255, 20)
    slider.handle_disabled = QColor(255, 255, 255, 40)
    slider.border_disabled = QColor(255, 255, 255, 8)


class _ViewerStrip(QWidget):
    """A single volume viewer presented as a dark-glass pill."""

    _BG_IDLE = QColor(30, 32, 38, 160)
    _BG_HOVER = QColor(36, 38, 46, 235)
    _BORDER = QColor(255, 255, 255, 25)
    _RADIUS = 6

    def __init__(self, viewer, *, add_btn=False, remove_btn=False, parent=None):
        super().__init__(parent)
        self.viewer = viewer
        self._hovered = False
        self._overflow_open = False

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)

        self._restyle_viewer()
        self._build_layout(add_btn, remove_btn)

        self._leave_timer = QTimer(self)
        self._leave_timer.setSingleShot(True)
        self._leave_timer.setInterval(500)
        self._leave_timer.timeout.connect(self._check_leave)

        viewer.data_changed.connect(self._sync_state)

    def _restyle_viewer(self):
        v = self.viewer

        v.open_button.setStyleSheet("")
        v._path_combo.setStyleSheet("")
        v.slice_row.value_label.setStyleSheet("")
        v.gamma_row.value_label.setStyleSheet("")

        v.open_button.hide()
        v.close_button.hide()
        v.orientation_selector.hide()

        v.visibility_button.setIcon(icon("ph.eye", color=_ICON))
        v.visibility_button.setFixedSize(_BTN, _BTN)
        v.auto_contrast_button.setIcon(icon("ph.magic-wand", color=_ICON))
        v.auto_contrast_button.setFixedSize(_BTN, _BTN)

        v._path_combo.setToolTip("Recent volumes")
        v._path_combo.setObjectName("splitRight")
        v._path_combo.setFixedHeight(_BTN)

        mono = QFont()
        mono.setStyleHint(QFont.StyleHint.Monospace)
        v.slice_row.value_label.setFont(mono)

        _dark_dual_slider(v.contrast_slider)

        v.project_selector.currentTextChanged.connect(self._on_projection_changed)

        _orig = v.set_visibility

        def _patched(visible, _f=_orig):
            _f(visible)
            icon_name = "ph.eye" if visible else "ph.eye-slash"
            v.visibility_button.setIcon(icon(icon_name, color=_ICON))

        v.set_visibility = _patched

        v.orientation_selector.currentTextChanged.connect(self._on_orientation_changed)

    def _build_layout(self, add_btn, remove_btn):
        v = self.viewer
        main = QVBoxLayout(self)
        main.setContentsMargins(6, 6, 6, 6)
        main.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(3)

        self._load_close_btn = QPushButton("Load")
        self._load_close_btn.setObjectName("loadClose")
        self._load_close_btn.setFixedSize(50, _BTN)
        self._load_close_btn.setToolTip("Load volume")
        self._load_close_btn.clicked.connect(self._on_load_close)

        self._recent_btn = QPushButton()
        self._recent_btn.setObjectName("recentDrop")
        self._recent_btn.setIcon(icon("ph.caret-down", color=_ICON))
        self._recent_btn.setFixedSize(22, _BTN)
        self._recent_btn.setToolTip("Recent volumes")
        self._recent_btn.clicked.connect(self._show_recent_menu)
        v._path_combo.hide()

        split = QHBoxLayout()
        split.setSpacing(0)
        split.setContentsMargins(0, 0, 0, 0)
        split.addWidget(self._load_close_btn)
        split.addWidget(self._recent_btn)
        row.addLayout(split)

        self._ori_seg = SegmentedControl(["X", "Y", "Z"], default=2)
        self._ori_seg.selectionChanged.connect(self._set_orientation)
        self._ori_seg.setEnabled(False)
        self._restyle_segmented(self._ori_seg)
        row.addWidget(self._ori_seg)

        row.addWidget(v.visibility_button)
        row.addWidget(v.auto_contrast_button)

        row.addWidget(v.slice_row, 1)

        self._more_btn = _icon_btn("ph.sliders-horizontal", "Adjustments")
        self._more_btn.setCheckable(True)
        self._more_btn.clicked.connect(self._toggle_overflow)
        row.addWidget(self._more_btn)

        if add_btn:
            self._add_btn = _icon_btn("ph.plus", "Add viewer")
            row.addWidget(self._add_btn)

        if remove_btn:
            self._rm_btn = _icon_btn("ph.trash", "Remove viewer")
            row.addWidget(self._rm_btn)

        main.addLayout(row)

        self._overflow = QWidget()
        self._overflow.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        ov = QHBoxLayout(self._overflow)
        ov.setContentsMargins(0, 2, 0, 0)
        ov.setSpacing(6)
        ov.addWidget(v.color_selector)
        ov.addWidget(v.contrast_label)
        ov.addWidget(v.contrast_slider, 1)
        ov.addWidget(v.contrast_value_label)
        ov.addWidget(v.gamma_row, 1)

        v.project_selector.hide()
        self._proj_seg = SegmentedControl(["Off", "Clip +", "Clip −"], default=0)
        self._proj_seg.selectionChanged.connect(self._set_projection)
        self._restyle_segmented(self._proj_seg, square=False)
        ov.addWidget(self._proj_seg)

        self._overflow.hide()
        main.addWidget(self._overflow)

        self.setStyleSheet(_STRIP_STYLE)

    _PROJ_MAP = {"Off": "Off", "Clip +": "Project +", "Clip −": "Project -"}
    _PROJ_RMAP = {v: k for k, v in _PROJ_MAP.items()}

    def _set_projection(self, label):
        combo_val = self._PROJ_MAP.get(label, "Off")
        self.viewer.project_selector.setCurrentText(combo_val)

    def _on_projection_changed(self, text):
        seg_label = self._PROJ_RMAP.get(text, "Off")
        idx = ["Off", "Clip +", "Clip −"].index(seg_label)
        self._proj_seg._select(idx)

    @staticmethod
    def _restyle_segmented(seg, square=True):
        """Apply dark-HUD colours to a :class:`SegmentedControl`."""
        n = len(seg._buttons)
        for i, btn in enumerate(seg._buttons):
            rl = "4px" if i == 0 else "0px"
            rr = "4px" if i == n - 1 else "0px"
            ml = "0px" if i == 0 else "-1px"
            if square:
                btn.setFixedSize(_BTN, _BTN)
            else:
                btn.setFixedHeight(_BTN)
            pad = "0px" if square else "2px 8px"
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    border: 1px solid rgba(255, 255, 255, 0.06);
                    border-radius: 0px;
                    border-top-left-radius: {rl};
                    border-bottom-left-radius: {rl};
                    border-top-right-radius: {rr};
                    border-bottom-right-radius: {rr};
                    padding: {pad};
                    color: rgba(255, 255, 255, 0.50);
                    background: rgba(255, 255, 255, 0.04);
                    margin-left: {ml};
                    font-weight: 600; font-size: 11px;
                }}
                QPushButton:checked {{
                    background: rgba(255, 255, 255, 0.12);
                    color: rgba(255, 255, 255, 0.88);
                }}
                QPushButton:hover:!checked {{
                    background: rgba(255, 255, 255, 0.08);
                }}
                QPushButton:disabled {{
                    color: rgba(255, 255, 255, 0.15);
                    background: rgba(255, 255, 255, 0.02);
                }}
            """
            )

    def _on_load_close(self):
        if self.viewer.volume is not None:
            self.viewer.close_button.click()
        else:
            self.viewer.open_button.click()

    def _show_recent_menu(self):
        from qtpy.QtWidgets import QMenu

        combo = self.viewer._path_combo
        if combo.count() == 0:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            """
            QMenu {
                background: rgba(18, 18, 24, 0.96);
                color: rgba(255, 255, 255, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px; padding: 4px;
            }
            QMenu::item { padding: 4px 12px; border-radius: 3px; }
            QMenu::item:selected {
                background: rgba(99, 102, 241, 0.35);
            }
        """
        )
        for i in range(combo.count()):
            text = combo.itemText(i)
            data = combo.itemData(i)
            menu.addAction(text, lambda d=data: self.viewer._load_from_path(d))
        menu.exec(self._recent_btn.mapToGlobal(self._recent_btn.rect().bottomLeft()))

    def _set_orientation(self, axis):
        self.viewer.orientation_selector.setCurrentText(axis)

    def _on_orientation_changed(self, text):
        self._ori_seg._select(["X", "Y", "Z"].index(text))

    def enterEvent(self, event):
        self._leave_timer.stop()
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._leave_timer.start()
        super().leaveEvent(event)

    def _check_leave(self):
        app = QApplication.instance()
        if app and app.activePopupWidget():
            self._leave_timer.start(200)
            return
        local = self.mapFromGlobal(QCursor.pos())
        if self.rect().contains(local):
            return
        self._hovered = False
        self.update()

    def _toggle_overflow(self):
        self._overflow_open = not self._overflow_open
        self._overflow.setVisible(self._overflow_open)
        self._more_btn.setChecked(self._overflow_open)
        self._relayout()

    def _relayout(self):
        hud = self.parentWidget()
        if hud is None:
            return
        if hasattr(hud, "_layout_strips"):
            hud._layout_strips()
        if hasattr(hud, "_schedule_vtk_render"):
            hud._schedule_vtk_render()

    def _sync_state(self):
        has_vol = self.viewer.volume is not None
        self._more_btn.setEnabled(has_vol)
        self._ori_seg.setEnabled(has_vol)
        if has_vol:
            self._load_close_btn.setText("Close")
            self._load_close_btn.setToolTip("Close volume")
        else:
            self._load_close_btn.setText("Load")
            self._load_close_btn.setToolTip("Load volume")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        bg = self._BG_HOVER if self._hovered else self._BG_IDLE
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, self._RADIUS, self._RADIUS)
        p.setPen(QPen(self._BORDER, 0.5))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, self._RADIUS, self._RADIUS)
        p.end()


class VolumeViewerHUD(QWidget):
    """Viewport overlay managing one or more :class:`_ViewerStrip` pills.

    Covers the full VTK viewport.  Strips are positioned manually
    (no QLayout) to avoid compositing artefacts on the OpenGL surface.

    Parameters
    ----------
    vtk_widget : QVTKRenderWindowInteractor
        The VTK render widget this HUD overlays (used as Qt parent).
    legend : LegendWidget, optional
        Shared legend widget forwarded to each :class:`VolumeViewer`.
    """

    _MARGIN_X = 12
    _MARGIN_BOTTOM = 10
    _SPACING = 6

    def __init__(self, vtk_widget, legend=None):
        super().__init__(vtk_widget)
        self.vtk_widget = vtk_widget
        self.legend = legend

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.primary = VolumeViewer(vtk_widget, legend)
        self.primary.setVisible(False)
        self._primary_strip = _ViewerStrip(self.primary, add_btn=True, parent=self)
        self._primary_strip._add_btn.clicked.connect(self.add_viewer)

        self.primary.close_button.clicked.connect(self._promote_new_primary)
        self.primary.data_changed.connect(self._on_volume_changed)

        self._recent_paths = []
        self._strips = []

        vtk_widget.installEventFilter(self)
        self.hide()

    def eventFilter(self, obj, event):
        if obj is self.vtk_widget and event.type() == QEvent.Type.Resize:
            self._reposition()
        return super().eventFilter(obj, event)

    def _reposition(self):
        parent = self.parentWidget()
        if parent is None:
            return
        self.setGeometry(0, 0, parent.width(), parent.height())
        self._layout_strips()

    def _layout_strips(self):
        available = self.width() - 2 * self._MARGIN_X
        if available <= 0:
            return
        w = min(available, _MAX_PILL_WIDTH)
        x = (self.width() - w) // 2
        y = self.height() - self._MARGIN_BOTTOM

        all_strips = [self._primary_strip] + [s for s in self._strips if s.isVisible()]

        for strip in all_strips:
            strip.setFixedWidth(w)

        for strip in all_strips:
            h = strip.sizeHint().height()
            y -= h
            strip.setGeometry(x, y, w, h)
            y -= self._SPACING

    def showEvent(self, event):
        super().showEvent(event)
        self._reposition()
        self.raise_()

    def _schedule_vtk_render(self):
        if not hasattr(self, "_vtk_timer"):
            self._vtk_timer = QTimer(self)
            self._vtk_timer.setSingleShot(True)
            self._vtk_timer.setInterval(0)
            self._vtk_timer.timeout.connect(self._do_vtk_render)
        self._vtk_timer.start()

    def _do_vtk_render(self):
        try:
            self.vtk_widget.GetRenderWindow().Render()
        except AttributeError:
            self.vtk_widget.update()
        self.repaint()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.end()

    def mousePressEvent(self, event):
        event.ignore()

    def mouseReleaseEvent(self, event):
        event.ignore()

    def mouseMoveEvent(self, event):
        event.ignore()

    def mouseDoubleClickEvent(self, event):
        event.ignore()

    def wheelEvent(self, event):
        event.ignore()

    @property
    def recent_paths(self):
        return list(self._recent_paths)

    def set_recent_paths(self, paths):
        self._recent_paths = list(paths)[:5]
        self._update_all_menus()

    def _on_volume_changed(self, viewer=None):
        viewer = viewer or self.primary
        path = viewer.source_path
        if path and isinstance(path, str):
            self._track_path(path)

    def _track_path(self, path):
        if path in self._recent_paths:
            self._recent_paths.remove(path)
        self._recent_paths.insert(0, path)
        self._recent_paths = self._recent_paths[:5]
        self._update_all_menus()

    def _update_all_menus(self):
        self.primary._rebuild_load_menu(self._recent_paths)
        for strip in self._strips:
            strip.viewer._rebuild_load_menu(self._recent_paths)

    @property
    def additional_viewers(self):
        return [s.viewer for s in self._strips]

    def add_viewer(self):
        viewer = VolumeViewer(self.vtk_widget, self.legend)
        viewer.setVisible(False)
        strip = _ViewerStrip(viewer, remove_btn=True, parent=self)
        strip._rm_btn.clicked.connect(lambda _, _s=strip: self.remove_viewer(_s))

        if self.primary.volume is not None:
            viewer.swap_volume(self.primary.volume)

        viewer.data_changed.connect(lambda v=viewer: self._on_volume_changed(v))
        viewer._rebuild_load_menu(self._recent_paths)

        self._strips.append(strip)
        strip.show()
        strip.raise_()
        self._layout_strips()

    def remove_viewer(self, strip):
        if strip not in self._strips:
            return
        self._strips.remove(strip)
        strip.viewer.close_volume()
        strip.hide()
        strip.setParent(None)
        strip.viewer.deleteLater()
        strip.deleteLater()
        self._layout_strips()
        self._schedule_vtk_render()

    def close(self):
        for strip in list(self._strips):
            strip.viewer.close_volume()
        try:
            self.primary.close_button.clicked.disconnect(self._promote_new_primary)
        except TypeError:
            pass
        self.primary.close_volume()

    def _promote_new_primary(self):
        donors = [s for s in self._strips if s.viewer.volume is not None]
        if not donors:
            return

        src = donors[0].viewer
        self.primary._source_path = src._source_path
        self.primary.swap_volume(src.volume)
        self.primary.change_orientation(src.get_orientation())
        self.primary.update_slice(src.get_slice())
        self.primary.handle_projection_change(src.get_projection())

        self.primary.color_selector.setCurrentText(src.color_selector.currentText())
        self.primary.contrast_slider.setValues(
            src.contrast_slider.lower_pos,
            src.contrast_slider.upper_pos,
        )
        self.primary.contrast_value_label.setText(src.contrast_value_label.text())
        self.primary.gamma_row.setValue(src.gamma_row.value())

        if src.is_visible != self.primary.is_visible:
            self.primary.toggle_visibility()

        self.remove_viewer(donors[0])
