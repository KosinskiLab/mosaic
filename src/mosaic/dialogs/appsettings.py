from qtpy.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QGroupBox,
    QComboBox,
    QWidget,
    QScrollArea,
    QTabWidget,
    QHBoxLayout,
    QPushButton,
    QFrame,
)
from qtpy.QtCore import Signal
import qtawesome as qta

from mosaic.settings import Settings
from mosaic.actor import QUALITY_PRESETS
from mosaic.stylesheets import (
    QPushButton_style,
    QScrollArea_style,
    QTabBar_style,
)

from mosaic.widgets import create_setting_widget, ColorButton


class AppSettingsDialog(QDialog):

    settingsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = Settings.rendering
        self.quality_kwargs = Settings.vtk.get_settings()

        self.setWindowTitle("Settings")

        self.layout = QVBoxLayout(self)
        self.resize(400, 550)

        self.tabs = QTabWidget()
        self.build_tabs()

        self.layout.addWidget(self.tabs)

        from ..icons import dialog_accept_icon, dialog_reject_icon, icon_color

        button_frame = QFrame()
        button_layout = QHBoxLayout(button_frame)
        button_layout.setContentsMargins(0, 10, 0, 0)
        reset_btn = QPushButton("Reset")
        reset_btn.setIcon(qta.icon("mdi6.undo-variant", color=icon_color))
        reset_btn.clicked.connect(self.reset_settings)
        button_layout.addWidget(reset_btn)
        button_layout.addStretch()

        reject_btn = QPushButton("Cancel")
        reject_btn.setIcon(dialog_reject_icon)
        reject_btn.clicked.connect(super().reject)

        accept_btn = QPushButton("Done")
        accept_btn.setIcon(dialog_accept_icon)
        accept_btn.clicked.connect(super().accept)
        button_layout.addWidget(reject_btn)
        button_layout.addWidget(accept_btn)

        self.layout.addWidget(button_frame)
        self.setStyleSheet(QTabBar_style + QPushButton_style + QScrollArea_style)

    def build_tabs(self):
        self.tabs.clear()

        self.tabs.addTab(
            self.setup_general_page(),
            qta.icon("fa5s.cog", color="#4f46e5"),
            "General",
        )
        self.tabs.addTab(
            self.setup_rendering_page(),
            qta.icon("fa5s.paint-brush", color="#4f46e5"),
            "Data",
        )
        self.connect_signals()

        # Correctly initialize quality presets
        self.on_preset_changed()

        # Propagate defaults to render window
        self.settingsChanged.emit()

    def setup_general_page(self):
        """General settings page with colors, quality presets, and target FPS."""
        rendering = Settings.rendering

        page = QWidget()
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)

        colors_group = QGroupBox("Background Colors")
        colors_layout = QFormLayout()
        self.bg_color_button = ColorButton()
        self.bg_color_button.update_color(rendering.background_color)
        colors_layout.addRow("Background Color", self.bg_color_button)

        self.bg_color_alt_button = ColorButton()
        self.bg_color_alt_button.update_color(rendering.background_color_alt)
        colors_layout.addRow("Alt Background Color", self.bg_color_alt_button)
        colors_group.setLayout(colors_layout)
        layout.addWidget(colors_group)

        perf_group = QGroupBox("Performance")
        perf_layout = QFormLayout()

        self.target_fps_spin = create_setting_widget(
            {
                "type": "float",
                "min": 1.0,
                "max": 144.0,
                "step": 1.0,
                "default": rendering.target_fps,
            }
        )
        perf_layout.addRow("Target Frame Rate", self.target_fps_spin)

        perf_group.setLayout(perf_layout)
        layout.addWidget(perf_group)

        # Quality Preset Group (combined with parameters)
        quality_group = QGroupBox("Point Rendering")
        quality_layout = QFormLayout()

        cur_index, self.preset_combo = 0, QComboBox()
        for index, (preset_name, config) in enumerate(QUALITY_PRESETS.items()):
            description = config.get("description", "")
            display_text = f"{preset_name.title()}"
            if description:
                display_text += f" - {description}"
            self.preset_combo.addItem(display_text, preset_name)
            if preset_name == Settings.vtk.preset:
                cur_index = index

        self.preset_combo.setCurrentIndex(cur_index)
        quality_layout.addRow("Preset", self.preset_combo)

        # LOD Parameters (shown conditionally within the same group)
        self.lod_points_spin = create_setting_widget(
            {"type": "number", "min": 100000, "max": 50000000, "default": 5000000}
        )
        self.lod_points_row = quality_layout.rowCount()
        quality_layout.addRow("LOD Points", self.lod_points_spin)

        self.lod_point_size_spin = create_setting_widget(
            {"type": "number", "min": 1, "max": 20, "default": 3}
        )
        self.lod_point_size_row = quality_layout.rowCount()
        quality_layout.addRow("Point Size", self.lod_point_size_spin)

        quality_group.setLayout(quality_layout)
        self.quality_group = quality_group
        layout.addWidget(quality_group)

        layout.addStretch()
        scroll_area.setWidget(scroll_widget)

        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll_area)

        return page

    def setup_rendering_page(self):
        """Rendering settings page."""
        page = QWidget()
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)

        rendering = Settings.rendering

        # Anti-aliasing Group
        aa_group = QGroupBox("Anti-aliasing")
        aa_layout = QFormLayout()

        self.fxaa_check = create_setting_widget(
            {"type": "boolean", "default": rendering.enable_fxaa}
        )
        aa_layout.addRow("Enable FXAA", self.fxaa_check)

        self.multisamples_spin = create_setting_widget(
            {
                "type": "number",
                "min": 0,
                "max": 16,
                "default": rendering.multisamples,
            }
        )
        aa_layout.addRow("Multisamples", self.multisamples_spin)

        aa_group.setLayout(aa_layout)
        layout.addWidget(aa_group)

        # Smoothing Group
        smoothing_group = QGroupBox("Smoothing")
        smoothing_layout = QFormLayout()

        self.point_smooth_check = create_setting_widget(
            {"type": "boolean", "default": rendering.point_smoothing}
        )
        smoothing_layout.addRow("Point Smoothing", self.point_smooth_check)

        self.line_smooth_check = create_setting_widget(
            {"type": "boolean", "default": rendering.line_smoothing}
        )
        smoothing_layout.addRow("Line Smoothing", self.line_smooth_check)

        self.polygon_smooth_check = create_setting_widget(
            {"type": "boolean", "default": rendering.polygon_smoothing}
        )
        smoothing_layout.addRow("Polygon Smoothing", self.polygon_smooth_check)

        smoothing_group.setLayout(smoothing_layout)
        layout.addWidget(smoothing_group)

        # Depth Peeling Group
        depth_group = QGroupBox("Depth Peeling")
        depth_layout = QFormLayout()

        self.depth_peeling_check = create_setting_widget(
            {"type": "boolean", "default": rendering.use_depth_peeling}
        )
        depth_layout.addRow("Use Depth Peeling", self.depth_peeling_check)

        self.max_peels_spin = create_setting_widget(
            {
                "type": "number",
                "min": 1,
                "max": 20,
                "default": rendering.max_depth_peels,
            }
        )
        depth_layout.addRow("Max Depth Peels", self.max_peels_spin)

        self.occlusion_spin = create_setting_widget(
            {
                "type": "float",
                "min": 0.0,
                "max": 1.0,
                "step": 0.01,
                "default": rendering.occlusion_ratio,
            }
        )
        depth_layout.addRow("Occlusion Ratio", self.occlusion_spin)

        depth_group.setLayout(depth_layout)
        layout.addWidget(depth_group)

        layout.addStretch()
        scroll_area.setWidget(scroll_widget)

        # Set up the page layout
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll_area)

        return page

    def reset_settings(self):
        Settings.reset_to_defaults("vtk")
        Settings.reset_to_defaults("rendering")
        self.build_tabs()

    def connect_signals(self):
        """Connect all widget signals to auto-save to Settings and emit change."""

        def _update_setting(clx, attribute_name: str, value):
            setattr(clx, attribute_name, value)
            self.emit_parameters()

        self.widget_settings_map = {
            # vtk rendering settings
            self.target_fps_spin: (Settings.rendering, "target_fps", float),
            self.fxaa_check: (Settings.rendering, "enable_fxaa", bool),
            self.multisamples_spin: (Settings.rendering, "multisamples", int),
            self.point_smooth_check: (Settings.rendering, "point_smoothing", bool),
            self.line_smooth_check: (Settings.rendering, "line_smoothing", bool),
            self.polygon_smooth_check: (Settings.rendering, "polygon_smoothing", bool),
            self.depth_peeling_check: (Settings.rendering, "use_depth_peeling", bool),
            self.max_peels_spin: (Settings.rendering, "max_depth_peels", int),
            self.occlusion_spin: (Settings.rendering, "occlusion_ratio", float),
            # vtk actor settings
            self.lod_points_spin: (Settings.vtk, "lod_points", int),
            self.lod_point_size_spin: (Settings.vtk, "lod_points_size", int),
        }

        for widget, (
            clx,
            attr_name,
            type_converter,
        ) in self.widget_settings_map.items():
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(
                    lambda v, clx=clx, attr=attr_name, conv=type_converter: _update_setting(
                        clx, attr, conv(v)
                    )
                )
            elif hasattr(widget, "toggled"):
                widget.toggled.connect(
                    lambda v, clx=clx, attr=attr_name: _update_setting(clx, attr, v)
                )

        self.preset_combo.currentTextChanged.connect(self.on_preset_changed)
        self.bg_color_button.colorChanged.connect(
            lambda: _update_setting(
                Settings.rendering,
                "background_color",
                self.bg_color_button.get_color(uint8=False),
            )
        )
        self.bg_color_alt_button.colorChanged.connect(
            lambda: _update_setting(
                Settings.rendering,
                "background_color_alt",
                self.bg_color_alt_button.get_color(uint8=False),
            )
        )

    def on_preset_changed(self):
        """Handle preset selection change."""
        preset_name = self.preset_combo.currentData()
        if not preset_name:
            return None

        Settings.vtk.preset = preset_name
        preset_config = QUALITY_PRESETS.get(preset_name, {})
        quality_layout = self.quality_group.layout()

        self.lod_points_spin.blockSignals(True)
        self.lod_point_size_spin.blockSignals(True)

        if "lod_points" in preset_config:
            self.lod_points_spin.setValue(int(preset_config["lod_points"]))
        if "lod_points_size" in preset_config:
            self.lod_point_size_spin.setValue(preset_config["lod_points_size"])

        self.lod_points_spin.blockSignals(False)
        self.lod_point_size_spin.blockSignals(False)

        quality_type = preset_config.get("quality", "full")
        Settings.vtk.quality = quality_type

        lod_visible = quality_type == "lod"
        quality_layout.setRowVisible(self.lod_points_row, lod_visible)
        quality_layout.setRowVisible(self.lod_point_size_row, lod_visible)

        return self.emit_parameters()

    def emit_parameters(self):
        """Emit parameters change signal (match GeometryPropertiesDialog pattern)."""
        self.settingsChanged.emit()
