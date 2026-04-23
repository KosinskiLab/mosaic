"""
App settings panel for the Mosaic application.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

__all__ = ["AppSettingsPanel"]

from collections import OrderedDict

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
from mosaic.settings import QUALITY_PRESETS
from mosaic.lod import LOD_DISABLED
from mosaic.stylesheets import Colors, Typography
from mosaic.icons import icon
from mosaic.widgets.sliders import SliderRow
from mosaic.widgets.colors import ColorPickerRow
from mosaic.widgets.segmented_control import SegmentedControl


def _rgb(hex_str: str) -> tuple:
    """Convert a ``#rrggbb`` string to a normalized ``(r, g, b)`` tuple."""
    return QColor(hex_str).getRgbF()[:3]


THEME_PAIRINGS = OrderedDict(
    [
        ("Zinc", (_rgb(Colors.DARK["SURFACE"]), _rgb(Colors.LIGHT["SURFACE"]))),
        ("Slate", ((0.09, 0.10, 0.12), (0.97, 0.97, 0.96))),
        ("Steel", ((0.18, 0.20, 0.25), (0.90, 0.92, 0.94))),
        ("Ocean", ((0.10, 0.18, 0.28), (0.88, 0.93, 0.97))),
        ("Ember", ((0.22, 0.12, 0.08), (0.98, 0.95, 0.92))),
    ]
)

LIGHTING_MODES = [
    ("simple", "Simple", "Single headlight"),
    ("soft", "Soft", "Ambient lighting with SSAO depth shading"),
    ("full", "Full", "Multi-light setup with three-point lighting"),
    ("flat", "Flat", "No shading with uniform flat colors"),
    ("poster", "Poster", "Light background with edge outlines"),
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
        self._apply_style()
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

    def _apply_style(self):
        self._header.setStyleSheet(
            f"""
            QPushButton {{
                font-weight: 600;
                text-align: left;
                padding: 0;
                border: none;
                border-bottom: 1px solid {Colors.BORDER_DARK};
                border-radius: 0px;
                color: {Colors.TEXT_MUTED};
                background: transparent;
            }}
            QPushButton:hover {{ background: transparent; }}
            QPushButton:pressed {{ background: transparent; }}
            QPushButton:focus {{ outline: none; }}
        """
        )

    def _on_theme_changed(self):
        self._apply_style()

    def _update_header(self):
        icon_name = "ph.caret-down" if self._expanded else "ph.caret-right"
        self._header.setIcon(icon(icon_name, role="muted"))
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


class AppSettingsPanel(QFrame):
    """Floating appearance settings panel anchored to the status bar."""

    _MARGIN = 8
    _RADIUS = float(Colors.RADIUS)

    settingsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(420, 200)
        self.resize(420, 380)
        self._build_ui()

    def _build_ui(self):
        m = self._MARGIN
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(m, m, m, m)

        header = QWidget()
        header.setObjectName("panelHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 6, 8, 6)

        title = QLabel("Settings")
        title.setStyleSheet(
            f"QLabel {{ font-size: {Typography.BODY}px; border: none; }}"
        )
        header_layout.addWidget(title)
        header_layout.addStretch()

        reset_btn = QPushButton()
        reset_btn.setIcon(icon("ph.arrow-counter-clockwise", role="muted"))
        reset_btn.setToolTip("Reset all appearance settings to defaults")
        reset_btn.setFixedSize(Colors.WIDGET_HEIGHT, Colors.WIDGET_HEIGHT)
        reset_btn.clicked.connect(self._reset_settings)
        header_layout.addWidget(reset_btn)

        close_btn = QPushButton()
        close_btn.setIcon(icon("ph.x", role="muted"))
        close_btn.setToolTip("Close panel")
        close_btn.setFixedSize(Colors.WIDGET_HEIGHT, Colors.WIDGET_HEIGHT)
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(close_btn)

        root.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

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

        self._apply_panel_style()

    def _apply_panel_style(self):
        self.setStyleSheet(
            f"""
            AppSettingsPanel {{ background: transparent; border: none; }}
            AppSettingsPanel > QWidget {{ background: transparent; }}
            #panelHeader {{ border: none; border-bottom: 1px solid {Colors.BORDER_DARK}; }}
            QScrollArea {{ background: transparent; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
        """
        )
        self.update()

    def _on_theme_changed(self):
        self._apply_panel_style()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        m = self._MARGIN
        rf = QRectF(
            m + 0.5, m + 0.5, self.width() - 2 * m - 1, self.height() - 2 * m - 1
        )

        path = QPainterPath()
        path.addRoundedRect(rf, self._RADIUS, self._RADIUS)

        p.setPen(QPen(QColor(Colors.BORDER_DARK), 1.0))
        p.setBrush(QColor(Colors.SURFACE))
        p.drawPath(path)

        p.end()

    def _build_theme_section(self):
        layout = self._body_layout

        bg_label = QLabel("Background:")
        layout.addWidget(bg_label)

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
        self._custom_btn.setIcon(icon("ph.eyedropper", role="muted"))
        self._custom_btn.setFixedHeight(36)
        self._custom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._custom_btn.setToolTip("Choose custom dark and light background colors")
        self._custom_btn.clicked.connect(self._toggle_custom_colors)
        cards_row.addWidget(self._custom_btn)

        layout.addLayout(cards_row)

        comment_label = QLabel("Use 'd' to toggle between dark and light background.")
        comment_label.setStyleSheet(
            f"font-size: {Typography.CAPTION}; color: {Colors.TEXT_MUTED}"
        )
        layout.addWidget(comment_label)

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

        grad_row, self._gradient_check = _checkbox_row(
            "Gradient Background",
            Settings.rendering.use_gradient_background,
            tooltip="Blend dark and light background colors as a vertical gradient",
        )
        self._gradient_check.toggled.connect(
            lambda v: self._update_setting(
                Settings.rendering, "use_gradient_background", v
            )
        )
        layout.addWidget(grad_row)

        layout.addWidget(QLabel("Lighting:"))

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
        def _fmt_budget(v):
            v = int(v)
            if v >= 1_000_000:
                return f"{v / 1_000_000:.1f}M".replace(".0M", "M")
            return f"{v // 1000}K"

        preset_labels = [name.title() for name in QUALITY_PRESETS]
        current_preset = Settings.vtk.preset
        current_idx = next(
            (i for i, name in enumerate(QUALITY_PRESETS) if name == current_preset), 0
        )

        self._preset_control = SegmentedControl(preset_labels, default=current_idx)
        self._preset_control.setToolTip(
            "Ultra renders everything, Balanced only a given point budget. \n"
            "Balanced is recommended for laptop users"
        )
        self._preset_control.selectionChanged.connect(self._on_preset_changed)

        preset_row = QHBoxLayout()
        preset_row.setContentsMargins(0, 0, 0, 0)
        preset_row.setSpacing(12)
        preset_row.addWidget(QLabel("Rendering:"))
        preset_row.addWidget(self._preset_control, 1)
        self._body_layout.addLayout(preset_row)

        budget_stops = [
            100_000,
            250_000,
            500_000,
            1_000_000,
            2_000_000,
            5_000_000,
            10_000_000,
            20_000_000,
        ]
        self._budget_slider = SliderRow(
            "Point Budget",
            default=int(Settings.vtk.point_budget),
            values=budget_stops,
            formatter=_fmt_budget,
        )
        self._budget_slider.setToolTip(
            "Maximum points rendered during camera interaction"
        )
        self._connect_slider(self._budget_slider, Settings.vtk, "point_budget", int)
        is_balanced = current_preset == "balanced"
        self._budget_slider.setVisible(is_balanced)
        self._body_layout.addWidget(self._budget_slider)

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
        self._body_layout.addWidget(self._fps_slider)

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
        self._body_layout.addWidget(self._workers_slider)

    def _on_preset_changed(self, label: str):
        preset_name = label.lower()
        if preset_name not in QUALITY_PRESETS:
            return

        Settings.vtk.preset = preset_name
        preset_config = QUALITY_PRESETS.get(preset_name, {})

        budget = int(preset_config.get("point_budget", LOD_DISABLED))
        Settings.vtk.point_budget = budget

        self._budget_slider.blockSignals(True)
        if budget > 0:
            self._budget_slider.setValue(budget)
        self._budget_slider.blockSignals(False)

        self._budget_slider.setVisible(preset_name == "balanced")
        self.settingsChanged.emit()

    def _build_quality_section(self):
        section = CollapsibleSection("Quality", expanded=False)

        fxaa_row, self._fxaa_check = _checkbox_row(
            "FXAA",
            Settings.rendering.enable_fxaa,
            tooltip="Fast approximate anti-aliasing, smooths jagged edges",
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
        scroll = self.findChild(QScrollArea)

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


def _colors_match(a: tuple, b: tuple) -> bool:
    """Check if two RGB tuples are approximately equal."""
    return all(abs(x - y) < 0.015 for x, y in zip(a, b))
