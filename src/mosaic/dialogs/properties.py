""" Modulate visual properties of Geometry objects.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtGui import QColor
from qtpy.QtCore import Signal
from qtpy.QtWidgets import (
    QVBoxLayout,
    QDialog,
    QFormLayout,
    QPushButton,
    QGroupBox,
    QFileDialog,
    QColorDialog,
    QRadioButton,
    QHBoxLayout,
    QWidget,
    QStackedWidget,
)
import qtawesome as qta

from ..stylesheets import QPushButton_style, QGroupBox_style
from ..widgets import (
    DialogFooter,
    RibbonToolBar,
    create_button,
    create_setting_widget,
    get_widget_value,
)


class GeometryPropertiesDialog(QDialog):
    parametersChanged = Signal(dict)

    def __init__(self, initial_properties=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Properties")
        self.parameters = {}

        self.base_color = initial_properties.get("base_color", (0.7, 0.7, 0.7))
        self.highlight_color = initial_properties.get(
            "highlight_color", (0.8, 0.2, 0.2)
        )
        self.initial_properties = initial_properties or {}
        self.volume_path = self.initial_properties.get("volume_path", None)

        self.setup_ui()
        self.connect_signals()
        self.setStyleSheet(QPushButton_style + QGroupBox_style)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 8, 0)

        ribbon = RibbonToolBar()
        pages = (
            self.setup_appearance_page(),
            self.setup_volume_page(),
            self.setup_sampling_page(),
        )
        self.stacked_widget = QStackedWidget()
        for page in pages:
            self.stacked_widget.addWidget(page)

        appearance_btn = create_button(
            "Appearance",
            "fa5s.palette",
            callback=lambda: self.stacked_widget.setCurrentIndex(0),
        )
        volume_btn = create_button(
            "Model",
            "fa5s.cube",
            callback=lambda: self.stacked_widget.setCurrentIndex(1),
        )
        sampling_btn = create_button(
            "Sampling",
            "fa5s.compress-arrows-alt",
            callback=lambda: self.stacked_widget.setCurrentIndex(2),
        )

        ribbon.add_section("Properties", [appearance_btn])
        ribbon.add_section("", [volume_btn])
        ribbon.add_section("", [sampling_btn])

        main_layout.addWidget(ribbon)
        main_layout.addWidget(self.stacked_widget)

        footer = DialogFooter(dialog=self)
        main_layout.addWidget(footer)

    def setup_appearance_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        appearance_group = QGroupBox("Display")
        appearance_layout = QFormLayout(appearance_group)

        self.size_spin = create_setting_widget(
            {
                "type": "number",
                "min": 0,
                "max": 50,
                "default": self.initial_properties.get("size", 8),
            }
        )
        appearance_layout.addRow("Point Size:", self.size_spin)

        base_settings = {"type": "float", "min": 0.0, "max": 1.0, "step": 0.1}
        self.opacity_spin = create_setting_widget(
            base_settings | {"default": self.initial_properties.get("opacity", 0.3)}
        )
        appearance_layout.addRow("Opacity:", self.opacity_spin)
        layout.addWidget(appearance_group)

        # Colors Group
        colors_group = QGroupBox("Colors")
        colors_layout = QFormLayout()

        self.base_color_button = QPushButton()
        self.update_color_button(self.base_color_button, self.base_color)
        self.base_color_button.clicked.connect(lambda: self.choose_color("base"))
        colors_layout.addRow("Base Color:", self.base_color_button)

        self.highlight_color_button = QPushButton()
        self.update_color_button(self.highlight_color_button, self.highlight_color)
        self.highlight_color_button.clicked.connect(
            lambda: self.choose_color("highlight")
        )
        colors_layout.addRow("Highlight Color:", self.highlight_color_button)

        colors_group.setLayout(colors_layout)
        layout.addWidget(colors_group)

        # Lighting Group
        lighting_group = QGroupBox("Lighting")
        lighting_layout = QFormLayout()

        self.ambient_spin = create_setting_widget(
            base_settings | {"default": self.initial_properties.get("ambient", 0.3)}
        )
        lighting_layout.addRow("Ambient:", self.ambient_spin)

        self.diffuse_spin = create_setting_widget(
            base_settings | {"default": self.initial_properties.get("diffuse", 0.3)}
        )
        lighting_layout.addRow("Diffuse:", self.diffuse_spin)

        self.specular_spin = create_setting_widget(
            base_settings | {"default": self.initial_properties.get("specular", 0.3)}
        )
        lighting_layout.addRow("Specular:", self.specular_spin)

        lighting_group.setLayout(lighting_layout)
        layout.addWidget(lighting_group)

        layout.addStretch()
        return page

    def setup_volume_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        # Volume Group
        volume_group = QGroupBox("Volume Settings")
        volume_layout = QFormLayout()

        self.browse_button = QPushButton()
        self.browse_button.setIcon(qta.icon("fa5s.folder-open"))
        self.browse_button.clicked.connect(self.browse_volume)
        volume_layout.addRow("Volume:", self.browse_button)

        self.scale_widget = QWidget()
        scale_layout = QHBoxLayout(self.scale_widget)
        scale_layout.setContentsMargins(0, 0, 0, 0)
        self.scale_positive = QRadioButton("1")
        self.scale_negative = QRadioButton("-1")
        self.scale_positive.setChecked(True)
        scale_layout.addWidget(self.scale_positive)
        scale_layout.addWidget(self.scale_negative)
        self.scale_widget.setEnabled(False)
        volume_layout.addRow("Scaling:", self.scale_widget)

        self.isovalue_spin = create_setting_widget(
            {
                "type": "slider",
                "min": 0.0,
                "max": 10000.0,
                "step": 1.0,
                "default": self.initial_properties.get("isovalue_percentile", 0.995)
                * 10000,
            }
        )
        self.isovalue_spin.setEnabled(False)
        volume_layout.addRow("Isovalue:", self.isovalue_spin)

        volume_path = self.initial_properties.get("volume_path", None)
        if volume_path is not None:
            self.scale_widget.setEnabled(True)
            self.isovalue_spin.setEnabled(True)

        volume_group.setLayout(volume_layout)
        layout.addWidget(volume_group)
        layout.addStretch()
        return page

    def setup_sampling_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        sampling_rate = self.initial_properties.get("sampling_rate", (1.0, 1.0, 1.0))

        # Sampling Group
        sampling_group = QGroupBox("Sampling Rates")
        sampling_layout = QFormLayout()

        base = {"type": "text", "min": 0}
        self.sampling_x = create_setting_widget(base | {"default": sampling_rate[0]})
        sampling_layout.addRow("X Sampling:", self.sampling_x)

        self.sampling_y = create_setting_widget(base | {"default": sampling_rate[1]})
        sampling_layout.addRow("Y Sampling:", self.sampling_y)

        self.sampling_z = create_setting_widget(base | {"default": sampling_rate[2]})
        sampling_layout.addRow("Z Sampling:", self.sampling_z)

        sampling_group.setLayout(sampling_layout)
        layout.addWidget(sampling_group)
        layout.addStretch()
        return page

    def connect_signals(self):
        """Connect all widget signals to update parameters"""
        self.size_spin.valueChanged.connect(self.emit_parameters)
        self.opacity_spin.valueChanged.connect(self.emit_parameters)
        self.ambient_spin.valueChanged.connect(self.emit_parameters)
        self.diffuse_spin.valueChanged.connect(self.emit_parameters)
        self.specular_spin.valueChanged.connect(self.emit_parameters)
        self.isovalue_spin.valueChanged.connect(self.emit_parameters)
        self.scale_positive.toggled.connect(self.emit_parameters)
        self.scale_negative.toggled.connect(self.emit_parameters)
        self.sampling_x.textChanged.connect(self.emit_parameters)
        self.sampling_y.textChanged.connect(self.emit_parameters)
        self.sampling_z.textChanged.connect(self.emit_parameters)

    def emit_parameters(self):
        parameters = self.get_parameters()
        self.parametersChanged.emit(parameters)

    def browse_volume(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select Volume File", "", "MRC Files (*.mrc);;All Files (*.*)"
        )
        if not file_name:
            return
        self.scale_widget.setEnabled(True)
        self.isovalue_spin.setEnabled(True)
        self.volume_path = file_name
        self.emit_parameters()

    def update_color_button(self, button, color):
        rgb = [int(c * 255) for c in color]
        button.setStyleSheet(f"background-color: rgb({rgb[0]}, {rgb[1]}, {rgb[2]})")

    def choose_color(self, color_type):
        current_color = (
            self.base_color if color_type == "base" else self.highlight_color
        )
        button = (
            self.base_color_button
            if color_type == "base"
            else self.highlight_color_button
        )

        initial_color = QColor(
            int(current_color[0] * 255),
            int(current_color[1] * 255),
            int(current_color[2] * 255),
        )

        color = QColorDialog.getColor(initial=initial_color, parent=self)
        if color.isValid():
            new_color = (
                color.red() / 255,
                color.green() / 255,
                color.blue() / 255,
            )
            if color_type == "base":
                self.base_color = new_color
            else:
                self.highlight_color = new_color
            self.update_color_button(button, new_color)
            self.emit_parameters()

    def get_parameters(self) -> dict:
        """Return current parameters"""
        return {
            "size": get_widget_value(self.size_spin),
            "opacity": get_widget_value(self.opacity_spin),
            "ambient": get_widget_value(self.ambient_spin),
            "diffuse": get_widget_value(self.diffuse_spin),
            "specular": get_widget_value(self.specular_spin),
            "base_color": self.base_color,
            "highlight_color": self.highlight_color,
            "scale": -1 if self.scale_negative.isChecked() else 1,
            "isovalue_percentile": get_widget_value(self.isovalue_spin) / 100,
            "volume_path": self.volume_path,
            "sampling_rate": (
                float(get_widget_value(self.sampling_x)),
                float(get_widget_value(self.sampling_y)),
                float(get_widget_value(self.sampling_z)),
            ),
        }
