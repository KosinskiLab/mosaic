"""
App settings panel for the Mosaic application.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

__all__ = ["AppSettingsPanel"]

from collections import OrderedDict

import qtawesome as qta
from qtpy.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath
from qtpy.QtCore import Qt, Signal, QRectF, QThread
from qtpy.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QLabel,
    QPushButton,
    QCheckBox,
    QScrollArea,
)

from mosaic.settings import Settings
from mosaic.actor import QUALITY_PRESETS
from mosaic.stylesheets import Colors, QPushButton_style, QScrollArea_style
from mosaic.widgets.sliders import SliderRow
from mosaic.widgets.colors import ColorPickerRow
from mosaic.widgets.segmented_control import SegmentedControl

THEME_PAIRINGS = OrderedDict(
    [
        ("Slate", ((0.09, 0.10, 0.12), (0.97, 0.97, 0.96))),
        ("Midnight", ((0.02, 0.02, 0.05), (1.00, 1.00, 1.00))),
        ("Steel", ((0.18, 0.20, 0.25), (0.90, 0.92, 0.94))),
        ("Ocean", ((0.10, 0.18, 0.28), (0.88, 0.93, 0.97))),
        ("Ember", ((0.22, 0.12, 0.08), (0.98, 0.95, 0.92))),
    ]
)

LIGHTING_MODES = [
    ("simple", "Simple", "Single headlight — default lighting"),
    ("soft", "Soft", "Ambient occlusion (SSAO) — subtle depth shading"),
    ("full", "Full", "Multi-light setup — three-point lighting"),
    ("flat", "Flat", "No shading — uniform flat colors"),
    ("shadow", "Shadow", "Shadow mapping — cast shadows from a light source"),
    ("silhouettes", "Silhouettes", "Edge outlines via Sobel gradient detection"),
]


class ThemeCard(QWidget):
    """A clickable card showing a dark/light color pairing side by side."""

    clicked = Signal()

    def __init__(self, name: str, dark: tuple, light: tuple, parent=None):
        super().__init__(parent)
        self.name = name
        self.dark = dark
        self.light = light
        self._selected = False
        self.setMinimumSize(40, 36)
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(name)

    def set_selected(self, selected: bool):
        self._selected = selected
        self.update()

    def mousePressEvent(self, event):
        self.clicked.emit()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        radius = 5.0
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        mid_x = rect.center().x()

        # Left half (dark)
        left_path = QPainterPath()
        left_path.moveTo(rect.left() + radius, rect.top())
        left_path.lineTo(mid_x, rect.top())
        left_path.lineTo(mid_x, rect.bottom())
        left_path.lineTo(rect.left() + radius, rect.bottom())
        left_path.arcTo(
            QRectF(rect.left(), rect.bottom() - 2 * radius, 2 * radius, 2 * radius),
            -90,
            -90,
        )
        left_path.lineTo(rect.left(), rect.top() + radius)
        left_path.arcTo(
            QRectF(rect.left(), rect.top(), 2 * radius, 2 * radius), 180, -90
        )
        left_path.closeSubpath()

        dr, dg, db = [int(c * 255) for c in self.dark]
        p.fillPath(left_path, QBrush(QColor(dr, dg, db)))

        # Right half (light)
        right_path = QPainterPath()
        right_path.moveTo(mid_x, rect.top())
        right_path.lineTo(rect.right() - radius, rect.top())
        right_path.arcTo(
            QRectF(rect.right() - 2 * radius, rect.top(), 2 * radius, 2 * radius),
            90,
            -90,
        )
        right_path.lineTo(rect.right(), rect.bottom() - radius)
        right_path.arcTo(
            QRectF(
                rect.right() - 2 * radius,
                rect.bottom() - 2 * radius,
                2 * radius,
                2 * radius,
            ),
            0,
            -90,
        )
        right_path.lineTo(mid_x, rect.bottom())
        right_path.closeSubpath()

        lr, lg, lb = [int(c * 255) for c in self.light]
        p.fillPath(right_path, QBrush(QColor(lr, lg, lb)))

        # Border
        full_path = QPainterPath()
        full_path.addRoundedRect(rect, radius, radius)

        if self._selected:
            pen = QPen(QColor(Colors.PRIMARY), 1.5)
        else:
            pen = QPen(QColor(Colors.BORDER_DARK), 1.0)
        p.setPen(pen)
        p.drawPath(full_path)

        p.end()


class CollapsibleSection(QWidget):
    """A section with a clickable header that toggles content visibility."""

    def __init__(self, title: str, expanded: bool = True, parent=None):
        super().__init__(parent)
        self._expanded = expanded

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._header = QPushButton()
        self._header.setFlat(True)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setFixedHeight(28)
        self._header.clicked.connect(self._toggle)
        self._title = title
        self._update_header()
        self._header.setStyleSheet(
            f"""
            QPushButton {{
                font-weight: 500;
                text-align: left;
                padding: 0;
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background: {Colors.BG_HOVER};
            }}
            QPushButton:focus {{ outline: none; }}
        """
        )
        layout.addWidget(self._header)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 6, 0, 0)
        self._content_layout.setSpacing(4)
        self._content.setVisible(expanded)
        layout.addWidget(self._content)

    @property
    def content_layout(self):
        return self._content_layout

    def addWidget(self, widget):
        self._content_layout.addWidget(widget)

    def addLayout(self, layout):
        self._content_layout.addLayout(layout)

    def setExpanded(self, expanded: bool):
        self._expanded = expanded
        self._content.setVisible(expanded)
        self._update_header()

    def _toggle(self):
        self.setExpanded(not self._expanded)

    def _update_header(self):
        icon_name = "ph.caret-down" if self._expanded else "ph.caret-right"
        self._header.setIcon(qta.icon(icon_name, color=Colors.TEXT_SECONDARY))
        self._header.setText(f" {self._title}")


def _checkbox_row(label_text: str, checked: bool, tooltip: str = ""):
    """Create a label + checkbox row matching SliderRow alignment.

    Returns (container_widget, checkbox).
    """
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)

    label = QLabel(f"{label_text}:")
    label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
    cb = QCheckBox()
    cb.setChecked(checked)

    if tooltip:
        row.setToolTip(tooltip)

    right_col = QWidget()
    right_col.setFixedWidth(45)
    right_layout = QHBoxLayout(right_col)
    right_layout.setContentsMargins(0, 0, 0, 0)
    right_layout.addStretch()
    right_layout.addWidget(cb)

    layout.addWidget(label, 0, Qt.AlignmentFlag.AlignVCenter)
    layout.addStretch(1)
    layout.addWidget(right_col, 0, Qt.AlignmentFlag.AlignVCenter)

    return row, cb


def _section_label(text):
    """Create a section label for grouping related controls."""
    lbl = QLabel(text)
    lbl.setStyleSheet("QLabel { font-weight: 500; }")
    return lbl


class AppSettingsPanel(QFrame):
    """Floating appearance settings panel anchored to the status bar."""

    settingsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumSize(420, 300)
        self.resize(420, 520)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        header = QWidget()
        header.setStyleSheet(f"border-bottom: 1px solid {Colors.BORDER_DARK};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 6, 8, 6)

        title = QLabel("Settings")
        title.setStyleSheet("QLabel { font-size: 13px; border: none; }")
        header_layout.addWidget(title)
        header_layout.addStretch()

        reset_btn = QPushButton()
        reset_btn.setIcon(
            qta.icon("ph.arrow-counter-clockwise", color=Colors.ICON_MUTED)
        )
        reset_btn.setToolTip("Reset all appearance settings to defaults")
        reset_btn.setFixedSize(Colors.WIDGET_HEIGHT, Colors.WIDGET_HEIGHT)
        reset_btn.clicked.connect(self._reset_settings)
        header_layout.addWidget(reset_btn)

        close_btn = QPushButton()
        close_btn.setIcon(qta.icon("ph.x", color=Colors.TEXT_MUTED))
        close_btn.setToolTip("Close panel")
        close_btn.setFixedSize(Colors.WIDGET_HEIGHT, Colors.WIDGET_HEIGHT)
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(close_btn)

        root.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(QScrollArea_style)

        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(12, 8, 12, 12)
        self._body_layout.setSpacing(12)

        self._build_theme_section()
        self._build_rendering_section()
        self._build_quality_section()

        self._body_layout.addStretch()
        scroll.setWidget(self._body)
        root.addWidget(scroll, 1)

        self.setStyleSheet(
            f"""AppearancePanel {{
                border: 1px solid {Colors.BORDER_DARK};
                border-bottom: none;
            }}"""
            + QPushButton_style
        )

    def _build_theme_section(self):
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(_section_label("Background"))

        cards_row = QHBoxLayout()
        cards_row.setSpacing(6)
        self._theme_cards = {}

        for name, (dark, light) in THEME_PAIRINGS.items():
            card = ThemeCard(name, dark, light)
            card.clicked.connect(lambda n=name: self._on_theme_selected(n))
            self._theme_cards[name] = card
            cards_row.addWidget(card)

        self._custom_btn = QPushButton()
        self._custom_btn.setCheckable(True)
        self._custom_btn.setIcon(qta.icon("ph.eyedropper", color=Colors.ICON))
        self._custom_btn.setFixedHeight(36)
        self._custom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._custom_btn.setToolTip("Choose custom dark and light background colors")
        self._custom_btn.clicked.connect(self._toggle_custom_colors)
        cards_row.addWidget(self._custom_btn)

        layout.addLayout(cards_row)

        self._custom_container = QWidget()
        custom_layout = QVBoxLayout(self._custom_container)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(8)

        dark_presets = [v[0] for v in THEME_PAIRINGS.values()]
        light_presets = [v[1] for v in THEME_PAIRINGS.values()]

        self._dark_picker = ColorPickerRow(
            "Dark Background",
            default_color=Settings.rendering.background_color,
            preset_colors=dark_presets,
        )
        self._dark_picker.colorChanged.connect(
            lambda c: self._update_setting(Settings.rendering, "background_color", c)
        )
        custom_layout.addWidget(self._dark_picker)

        self._light_picker = ColorPickerRow(
            "Light Background",
            default_color=Settings.rendering.background_color_alt,
            preset_colors=light_presets,
        )
        self._light_picker.colorChanged.connect(
            lambda c: self._update_setting(
                Settings.rendering, "background_color_alt", c
            )
        )
        custom_layout.addWidget(self._light_picker)

        self._custom_container.setVisible(False)
        layout.addWidget(self._custom_container)

        grad_row = QWidget()
        grad_row.setToolTip(
            "Blend dark and light background colors as a vertical gradient"
        )
        grad_layout = QHBoxLayout(grad_row)
        grad_layout.setContentsMargins(0, 0, 0, 0)
        grad_layout.setSpacing(12)
        grad_label = QLabel("Gradient:")
        grad_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        grad_layout.addWidget(grad_label, 0, Qt.AlignmentFlag.AlignVCenter)
        grad_layout.addStretch(1)
        self._gradient_check = QCheckBox()
        self._gradient_check.setChecked(Settings.rendering.use_gradient_background)
        self._gradient_check.toggled.connect(
            lambda v: self._update_setting(
                Settings.rendering, "use_gradient_background", v
            )
        )
        grad_layout.addWidget(self._gradient_check, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(grad_row)

        layout.addWidget(_section_label("Lighting"))

        lighting_labels = [lbl for _, lbl, _ in LIGHTING_MODES]
        lighting_tooltips = {lbl: tip for _, lbl, tip in LIGHTING_MODES}
        current_mode = Settings.rendering.lighting_mode
        current_idx = next(
            (i for i, (m, _, _) in enumerate(LIGHTING_MODES) if m == current_mode), 0
        )
        self._lighting_control = SegmentedControl(lighting_labels, default=current_idx)
        for btn in self._lighting_control._buttons:
            tip = lighting_tooltips.get(btn.text(), "")
            if tip:
                btn.setToolTip(tip)
        self._lighting_control.selectionChanged.connect(self._on_lighting_changed)
        layout.addWidget(self._lighting_control)

        layout.addWidget(_section_label("Computation"))

        max_workers = QThread.idealThreadCount()
        self._workers_slider = SliderRow(
            "Workers",
            min_val=1,
            max_val=max_workers,
            default=Settings.rendering.parallel_worker,
            decimals=0,
        )
        self._workers_slider.setToolTip("Maximum number of parallel background tasks")
        self._connect_slider(
            self._workers_slider, Settings.rendering, "parallel_worker", int
        )
        layout.addWidget(self._workers_slider)

        self._body_layout.addWidget(section)

        self._update_theme_selection()

    def _on_theme_selected(self, name: str):
        dark, light = THEME_PAIRINGS[name]
        Settings.rendering.background_color = dark
        Settings.rendering.background_color_alt = light

        self._dark_picker.set_color(dark)
        self._light_picker.set_color(light)

        self._custom_btn.setChecked(False)
        self._custom_container.setVisible(False)

        self._update_theme_selection()
        self.settingsChanged.emit()

    def _update_theme_selection(self):
        current_dark = Settings.rendering.background_color
        current_light = Settings.rendering.background_color_alt

        matched = False
        for name, (dark, light) in THEME_PAIRINGS.items():
            is_match = _colors_match(dark, current_dark) and _colors_match(
                light, current_light
            )
            self._theme_cards[name].set_selected(is_match)
            if is_match:
                matched = True

        if not matched:
            self._custom_btn.setChecked(True)
            self._custom_container.setVisible(True)

    def _toggle_custom_colors(self):
        show = self._custom_btn.isChecked()
        self._custom_container.setVisible(show)

    def _on_lighting_changed(self, label: str):
        mode_map = {lbl: key for key, lbl, _ in LIGHTING_MODES}
        mode = mode_map.get(label, "simple")
        Settings.rendering.lighting_mode = mode
        self.settingsChanged.emit()

    def _build_rendering_section(self):
        section = CollapsibleSection("Rendering", expanded=False)

        preset_labels = [name.title() for name in QUALITY_PRESETS]
        current_preset = Settings.vtk.preset
        current_idx = next(
            (i for i, name in enumerate(QUALITY_PRESETS) if name == current_preset), 0
        )
        self._preset_control = SegmentedControl(preset_labels, default=current_idx)
        self._preset_control.setToolTip(
            "Point rendering quality — higher uses more memory"
        )
        self._preset_control.selectionChanged.connect(self._on_preset_changed)
        section.addWidget(self._preset_control)

        self._lod_container = QWidget()
        lod_layout = QVBoxLayout(self._lod_container)
        lod_layout.setContentsMargins(0, 2, 0, 0)
        lod_layout.setSpacing(2)

        self._lod_points_slider = SliderRow(
            "LOD Points",
            min_val=100000,
            max_val=50000000,
            default=int(Settings.vtk.lod_points),
            decimals=0,
            exponent=2.0,
        )
        self._lod_points_slider.setToolTip(
            "Number of points in the level-of-detail cloud"
        )
        self._connect_slider(self._lod_points_slider, Settings.vtk, "lod_points", int)
        lod_layout.addWidget(self._lod_points_slider)

        self._lod_size_slider = SliderRow(
            "Point Size",
            min_val=1,
            max_val=20,
            default=Settings.vtk.lod_points_size,
            decimals=0,
        )
        self._lod_size_slider.setToolTip(
            "Pixel size of points in the level-of-detail cloud"
        )
        self._connect_slider(
            self._lod_size_slider, Settings.vtk, "lod_points_size", int
        )
        lod_layout.addWidget(self._lod_size_slider)

        quality_type = QUALITY_PRESETS.get(current_preset, {}).get("quality", "full")
        self._lod_container.setVisible(quality_type == "lod")
        section.addWidget(self._lod_container)

        self._fps_slider = SliderRow(
            "Target Frame Rate",
            min_val=1,
            max_val=144,
            default=Settings.rendering.target_fps,
            decimals=0,
            suffix=" fps",
        )
        self._fps_slider.setToolTip("Target rendering frame rate for the VTK viewport")
        self._connect_slider(self._fps_slider, Settings.rendering, "target_fps", float)
        section.addWidget(self._fps_slider)

        self._body_layout.addWidget(section)

    def _on_preset_changed(self, label: str):
        preset_name = label.lower()
        if preset_name not in QUALITY_PRESETS:
            return

        Settings.vtk.preset = preset_name
        preset_config = QUALITY_PRESETS.get(preset_name, {})

        quality_type = preset_config.get("quality", "full")
        Settings.vtk.quality = quality_type

        self._lod_points_slider.blockSignals(True)
        self._lod_size_slider.blockSignals(True)

        if "lod_points" in preset_config:
            Settings.vtk.lod_points = int(preset_config["lod_points"])
            self._lod_points_slider.setValue(int(preset_config["lod_points"]))
        if "lod_points_size" in preset_config:
            Settings.vtk.lod_points_size = preset_config["lod_points_size"]
            self._lod_size_slider.setValue(preset_config["lod_points_size"])

        self._lod_points_slider.blockSignals(False)
        self._lod_size_slider.blockSignals(False)

        self._lod_container.setVisible(quality_type == "lod")
        self.settingsChanged.emit()

    def _build_quality_section(self):
        section = CollapsibleSection("Quality", expanded=False)

        fxaa_row, self._fxaa_check = _checkbox_row(
            "FXAA",
            Settings.rendering.enable_fxaa,
            tooltip="Fast approximate anti-aliasing — smooths jagged edges",
        )
        self._fxaa_check.toggled.connect(
            lambda v: self._update_setting(Settings.rendering, "enable_fxaa", v)
        )
        section.addWidget(fxaa_row)

        self._multisamples_slider = SliderRow(
            "Multisamples",
            min_val=0,
            max_val=16,
            default=Settings.rendering.multisamples,
            decimals=0,
        )
        self._multisamples_slider.setToolTip(
            "Hardware multi-sample anti-aliasing (0 = disabled)"
        )
        self._connect_slider(
            self._multisamples_slider, Settings.rendering, "multisamples", int
        )
        section.addWidget(self._multisamples_slider)

        smooth_row = QWidget()
        smooth_row.setToolTip("Enable hardware smoothing for geometry edges")
        smooth_layout = QHBoxLayout(smooth_row)
        smooth_layout.setContentsMargins(0, 0, 0, 0)
        smooth_layout.setSpacing(12)

        smooth_label = QLabel("Smoothing:")
        smooth_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        smooth_layout.addWidget(smooth_label, 0, Qt.AlignmentFlag.AlignVCenter)
        smooth_layout.addStretch(1)

        for attr, label_text in [
            ("point_smoothing", "Point"),
            ("line_smoothing", "Line"),
            ("polygon_smoothing", "Polygon"),
        ]:
            cb = QCheckBox(label_text)
            cb.setChecked(getattr(Settings.rendering, attr))
            cb.toggled.connect(
                lambda v, a=attr: self._update_setting(Settings.rendering, a, v)
            )
            smooth_layout.addWidget(cb, 0, Qt.AlignmentFlag.AlignVCenter)
            setattr(self, f"_{attr}_check", cb)

        section.addWidget(smooth_row)

        dp_row, self._depth_peeling_check = _checkbox_row(
            "Depth Peeling",
            Settings.rendering.use_depth_peeling,
            tooltip="Order-independent transparency rendering",
        )
        section.addWidget(dp_row)

        self._dp_detail_container = QWidget()
        dp_detail_layout = QVBoxLayout(self._dp_detail_container)
        dp_detail_layout.setContentsMargins(0, 2, 0, 0)
        dp_detail_layout.setSpacing(2)

        self._max_peels_slider = SliderRow(
            "Max Peels",
            min_val=1,
            max_val=20,
            default=Settings.rendering.max_depth_peels,
            decimals=0,
        )
        self._max_peels_slider.setToolTip(
            "Maximum number of transparency layers to resolve"
        )
        self._connect_slider(
            self._max_peels_slider, Settings.rendering, "max_depth_peels", int
        )
        dp_detail_layout.addWidget(self._max_peels_slider)

        self._occlusion_slider = SliderRow(
            "Occlusion",
            min_val=0.0,
            max_val=1.0,
            default=Settings.rendering.occlusion_ratio,
            decimals=2,
        )
        self._occlusion_slider.setToolTip(
            "Allowed occlusion ratio before stopping depth peeling"
        )
        self._connect_slider(
            self._occlusion_slider, Settings.rendering, "occlusion_ratio", float
        )
        dp_detail_layout.addWidget(self._occlusion_slider)

        self._dp_detail_container.setVisible(Settings.rendering.use_depth_peeling)
        section.addWidget(self._dp_detail_container)

        self._depth_peeling_check.toggled.connect(self._on_depth_peeling_toggled)

        self._body_layout.addWidget(section)

    def _on_depth_peeling_toggled(self, checked: bool):
        self._dp_detail_container.setVisible(checked)
        self._update_setting(Settings.rendering, "use_depth_peeling", checked)

    def _set_setting(self, category, attr, value):
        """Update a setting value without emitting settingsChanged."""
        setattr(category, attr, value)

    def _update_setting(self, category, attr, value):
        self._set_setting(category, attr, value)
        self.settingsChanged.emit()

    def _connect_slider(self, slider, category, attr, cast=float):
        """Connect a SliderRow: live updates on drag, signal on release."""
        slider.label_widget.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        slider.valueChanged.connect(
            lambda v: self._set_setting(category, attr, cast(v))
        )
        slider.valueCommitted.connect(lambda _: self.settingsChanged.emit())

    def _reset_settings(self):
        Settings.reset_to_defaults("vtk")
        Settings.reset_to_defaults("rendering")
        self._rebuild_contents()
        self.settingsChanged.emit()

    def _rebuild_contents(self):
        """Tear down and rebuild all panel contents from current settings."""
        old_body = self._body
        scroll = old_body.parent()

        new_body = QWidget()
        new_layout = QVBoxLayout(new_body)
        new_layout.setContentsMargins(12, 8, 12, 12)
        new_layout.setSpacing(12)

        self._body = new_body
        self._body_layout = new_layout

        self._build_theme_section()
        self._build_rendering_section()
        self._build_quality_section()

        self._body_layout.addStretch()
        scroll.setWidget(new_body)
        old_body.deleteLater()


def _colors_match(a: tuple, b: tuple) -> bool:
    """Check if two RGB tuples are approximately equal."""
    return all(abs(x - y) < 0.015 for x, y in zip(a, b))
