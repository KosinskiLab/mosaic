"""
Modulate visual properties of Geometry objects.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from os.path import exists

from qtpy.QtCore import Signal
from qtpy.QtWidgets import (
    QVBoxLayout,
    QDialog,
    QFormLayout,
    QPushButton,
    QGroupBox,
    QFileDialog,
    QRadioButton,
    QHBoxLayout,
    QWidget,
    QStackedWidget,
    QScrollArea,
)
import qtawesome as qta

from ..stylesheets import QPushButton_style, QGroupBox_style
from ..widgets import (
    DialogFooter,
    RibbonToolBar,
    create_button,
    create_setting_widget,
    get_widget_value,
    ColorButton,
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
        try:
            if not exists(self.volume_path):
                self.volume_path = None
        except Exception:
            pass

        self.setup_ui()
        self.connect_signals()
        self.setStyleSheet(QPushButton_style + QGroupBox_style)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        container = QWidget()
        content_layout = QVBoxLayout(container)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(16)

        content_layout.addWidget(self.create_display_group())
        content_layout.addWidget(self.create_colors_group())
        content_layout.addWidget(self.create_lighting_group())
        content_layout.addWidget(self.create_volume_group())
        content_layout.addWidget(self.create_sampling_group())
        content_layout.addStretch()

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        footer = DialogFooter(dialog=self)
        main_layout.addWidget(footer)

        self.setMinimumWidth(250)

    def create_display_group(self):
        group = QGroupBox("Display")
        layout = QFormLayout(group)

        self.size_spin = create_setting_widget(
            {
                "type": "number",
                "min": 0,
                "max": 50,
                "default": self.initial_properties.get("size", 8),
            }
        )
        layout.addRow("Point Size:", self.size_spin)

        base_settings = {"type": "float", "min": 0.0, "max": 1.0, "step": 0.1}
        self.opacity_spin = create_setting_widget(
            base_settings | {"default": self.initial_properties.get("opacity", 0.3)}
        )
        layout.addRow("Opacity:", self.opacity_spin)

        return group

    def create_colors_group(self):
        group = QGroupBox("Colors")
        layout = QFormLayout(group)

        self.base_color_button = ColorButton()
        self.base_color_button.update_color(self.base_color)
        layout.addRow("Base Color:", self.base_color_button)

        self.highlight_color_button = ColorButton()
        self.highlight_color_button.update_color(self.highlight_color)
        layout.addRow("Highlight Color:", self.highlight_color_button)

        return group

    def create_lighting_group(self):
        group = QGroupBox("Lighting")
        layout = QFormLayout(group)

        base_settings = {"type": "float", "min": 0.0, "max": 1.0, "step": 0.1}

        self.ambient_spin = create_setting_widget(
            base_settings | {"default": self.initial_properties.get("ambient", 0.3)}
        )
        layout.addRow("Ambient:", self.ambient_spin)

        self.diffuse_spin = create_setting_widget(
            base_settings | {"default": self.initial_properties.get("diffuse", 0.3)}
        )
        layout.addRow("Diffuse:", self.diffuse_spin)

        self.specular_spin = create_setting_widget(
            base_settings | {"default": self.initial_properties.get("specular", 0.3)}
        )
        layout.addRow("Specular:", self.specular_spin)

        return group

    def create_volume_group(self):
        group = QGroupBox("Volume")
        layout = QFormLayout(group)

        self.browse_button = QPushButton()
        self.browse_button.setIcon(qta.icon("fa5s.folder-open"))
        self.browse_button.clicked.connect(self.browse_volume)
        layout.addRow("Volume:", self.browse_button)

        self.scale_widget = QWidget()
        scale_layout = QHBoxLayout(self.scale_widget)
        scale_layout.setContentsMargins(0, 0, 0, 0)
        self.scale_positive = QRadioButton("1")
        self.scale_negative = QRadioButton("-1")
        if self.initial_properties.get("scale", 0) >= 0:
            self.scale_positive.setChecked(True)
        else:
            self.scale_negative.setChecked(True)

        scale_layout.addWidget(self.scale_positive)
        scale_layout.addWidget(self.scale_negative)
        self.scale_widget.setEnabled(False)
        layout.addRow("Scaling:", self.scale_widget)

        self.isovalue_spin = create_setting_widget(
            {
                "type": "slider",
                "min": 0.0,
                "max": 10000.0,
                "step": 1.0,
                "default": self.initial_properties.get("isovalue_percentile", 99.5)
                * 100,
            }
        )
        self.isovalue_spin.setEnabled(False)
        layout.addRow("Isovalue:", self.isovalue_spin)

        self.attach_button = QPushButton("Reattach")
        self.attach_button.setEnabled(False)
        self.attach_button.setToolTip("Reattach volume after representation change.")
        layout.addRow("", self.attach_button)

        volume_path = self.initial_properties.get("volume_path", None)
        if volume_path is not None:
            self.scale_widget.setEnabled(True)
            self.isovalue_spin.setEnabled(True)
            self.attach_button.setEnabled(True)

        return group

    def create_sampling_group(self):
        group = QGroupBox("Sampling")
        layout = QFormLayout(group)

        sampling_rate = self.initial_properties.get("sampling_rate", (1.0, 1.0, 1.0))

        base = {"type": "text", "min": 0}
        self.sampling_x = create_setting_widget(base | {"default": sampling_rate[0]})
        layout.addRow("X:", self.sampling_x)

        self.sampling_y = create_setting_widget(base | {"default": sampling_rate[1]})
        layout.addRow("Y:", self.sampling_y)

        self.sampling_z = create_setting_widget(base | {"default": sampling_rate[2]})
        layout.addRow("Z:", self.sampling_z)

        return group

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
        self.base_color_button.colorChanged.connect(self.emit_parameters)
        self.highlight_color_button.colorChanged.connect(self.emit_parameters)
        self.attach_button.clicked.connect(self.emit_parameters)

    def emit_parameters(self):
        parameters = self.get_parameters()
        self.parametersChanged.emit(parameters)

    def browse_volume(self):
        from ..formats.parser import load_density

        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select Volume File", "", "MRC Files (*.mrc);;All Files (*.*)"
        )
        if not file_name:
            return

        # Auto determine scale
        self.volume_path = file_name
        volume = load_density(self.volume_path)
        non_negative = (volume.data > 0).sum()
        if non_negative < volume.data.size // 2:
            self.scale_negative.setChecked(True)

        self.scale_widget.setEnabled(True)
        self.isovalue_spin.setEnabled(True)
        self.attach_button.setEnabled(True)

        self.emit_parameters()

    def get_parameters(self) -> dict:
        """Return current parameters"""
        return {
            "size": get_widget_value(self.size_spin),
            "opacity": get_widget_value(self.opacity_spin),
            "ambient": get_widget_value(self.ambient_spin),
            "diffuse": get_widget_value(self.diffuse_spin),
            "specular": get_widget_value(self.specular_spin),
            "base_color": self.base_color_button.get_color(uint8=False),
            "highlight_color": self.highlight_color_button.get_color(uint8=False),
            "scale": -1 if self.scale_negative.isChecked() else 1,
            "isovalue_percentile": get_widget_value(self.isovalue_spin) / 100,
            "volume_path": self.volume_path,
            "sampling_rate": (
                float(get_widget_value(self.sampling_x)),
                float(get_widget_value(self.sampling_y)),
                float(get_widget_value(self.sampling_z)),
            ),
        }
