"""
Modulate visual properties of Geometry objects.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from os.path import exists

from qtpy.QtCore import Signal, Qt
from qtpy.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QDialog,
    QPushButton,
    QFileDialog,
    QRadioButton,
    QWidget,
    QLabel,
    QGroupBox,
    QApplication,
)
import qtawesome as qta

from ..stylesheets import (
    QPushButton_style,
    QSpinBox_style,
    QLineEdit_style,
    QGroupBox_style,
    Colors,
)
from ..widgets import (
    DialogFooter,
    create_setting_widget,
    get_widget_value,
    ColorPickerRow,
    SliderRow,
)


class GeometryPropertiesDialog(QDialog):
    parametersChanged = Signal(dict)

    def __init__(self, initial_properties=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Properties")
        self.setFixedWidth(400)
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

    def showEvent(self, event):
        """Position the dialog on the left side of the parent window."""
        super().showEvent(event)

        # Find the main window
        main_window = self.parent().window() if self.parent() else None
        if main_window is None:
            main_window = QApplication.activeWindow()
        if main_window is None or main_window is self:
            return

        parent_geo = main_window.geometry()

        # Position on the left side, vertically centered
        x = parent_geo.left() + 20
        y = parent_geo.top() + (parent_geo.height() - self.height()) // 2

        self.move(x, y)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 8)
        main_layout.setSpacing(12)

        # === APPEARANCE SECTION ===
        appearance_group = QGroupBox("Appearance")
        appearance_group.setStyleSheet(QGroupBox_style)
        appearance_layout = QVBoxLayout(appearance_group)
        appearance_layout.setSpacing(12)

        point_size_row = QWidget()
        point_size_layout = QHBoxLayout(point_size_row)
        point_size_layout.setContentsMargins(0, 0, 0, 0)
        point_size_layout.setSpacing(12)

        point_size_label = QLabel("Point Size")
        point_size_layout.addWidget(point_size_label)
        point_size_layout.addStretch()

        self.size_spin = create_setting_widget(
            {
                "type": "number",
                "min": 0,
                "max": 50,
                "default": self.initial_properties.get("size", 8),
            }
        )
        self.size_spin.setStyleSheet(QSpinBox_style)
        self.size_spin.setFixedWidth(80)
        self.size_spin.setToolTip("Size of points in the representation")
        point_size_layout.addWidget(self.size_spin)

        appearance_layout.addWidget(point_size_row)

        self.opacity_slider = SliderRow(
            "Opacity",
            min_val=0.0,
            max_val=1.0,
            default=self.initial_properties.get("opacity", 0.3),
            decimals=2,
        )
        self.opacity_slider.setToolTip(
            "Transparency of the geometry (0 = invisible, 1 = solid)"
        )
        appearance_layout.addWidget(self.opacity_slider)

        self.base_color_picker = ColorPickerRow("Base Color", self.base_color)
        self.base_color_picker.setToolTip("Default color for the geometry")
        appearance_layout.addWidget(self.base_color_picker)

        self.highlight_color_picker = ColorPickerRow(
            "Highlight Color", self.highlight_color
        )
        self.highlight_color_picker.setToolTip("Color when geometry is selected")
        appearance_layout.addWidget(self.highlight_color_picker)

        main_layout.addWidget(appearance_group)

        # === LIGHTING SECTION ===
        lighting_group = QGroupBox("Lighting")
        lighting_group.setStyleSheet(QGroupBox_style)
        lighting_layout = QVBoxLayout(lighting_group)
        lighting_layout.setSpacing(12)

        self.ambient_slider = SliderRow(
            "Ambient",
            min_val=0.0,
            max_val=1.0,
            default=self.initial_properties.get("ambient", 0.3),
            decimals=2,
        )
        self.ambient_slider.setToolTip(
            "Base illumination independent of light direction"
        )
        lighting_layout.addWidget(self.ambient_slider)

        self.diffuse_slider = SliderRow(
            "Diffuse",
            min_val=0.0,
            max_val=1.0,
            default=self.initial_properties.get("diffuse", 0.3),
            decimals=2,
        )
        self.diffuse_slider.setToolTip(
            "Scattered light reflection for a matte appearance"
        )
        lighting_layout.addWidget(self.diffuse_slider)

        self.specular_slider = SliderRow(
            "Specular",
            min_val=0.0,
            max_val=1.0,
            default=self.initial_properties.get("specular", 0.3),
            decimals=2,
        )
        self.specular_slider.setToolTip("Sharp highlights for a shiny appearance")
        lighting_layout.addWidget(self.specular_slider)

        main_layout.addWidget(lighting_group)

        # === MODEL SECTION ===
        model_group = QGroupBox("Model")
        model_group.setStyleSheet(QGroupBox_style)
        model_layout = QVBoxLayout(model_group)
        model_layout.setSpacing(12)

        browse_row = QWidget()
        browse_layout = QHBoxLayout(browse_row)
        browse_layout.setContentsMargins(0, 0, 0, 0)
        browse_layout.setSpacing(8)

        browse_label = QLabel("Map File")
        browse_label.setToolTip("Density map in MRC or CCP4 format")
        browse_layout.addWidget(browse_label)
        browse_layout.addStretch()

        self.browse_button = QPushButton("Browse...")
        self.browse_button.setIcon(qta.icon("ph.folder-open", color=Colors.ICON))
        self.browse_button.setStyleSheet(QPushButton_style)
        self.browse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_button.setToolTip("Select a density map file")
        self.browse_button.clicked.connect(self.browse_volume)
        browse_layout.addWidget(self.browse_button)

        self.attach_button = QPushButton("Reattach")
        self.attach_button.setIcon(qta.icon("ph.link", color=Colors.ICON))
        self.attach_button.setStyleSheet(QPushButton_style)
        self.attach_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.attach_button.setEnabled(self.volume_path is not None)
        self.attach_button.setToolTip("Recompute isosurface from the density map")
        browse_layout.addWidget(self.attach_button)

        model_layout.addWidget(browse_row)

        scale_row = QWidget()
        scale_layout = QHBoxLayout(scale_row)
        scale_layout.setContentsMargins(0, 0, 0, 0)
        scale_layout.setSpacing(12)

        scale_label = QLabel("Scale")
        scale_layout.addWidget(scale_label)
        scale_layout.addStretch()

        self.scale_positive = QRadioButton("+1")
        self.scale_positive.setToolTip("Use positive density values")
        self.scale_negative = QRadioButton("-1")
        self.scale_negative.setToolTip("Invert density (for negative stain maps)")
        if self.initial_properties.get("scale", 0) >= 0:
            self.scale_positive.setChecked(True)
        else:
            self.scale_negative.setChecked(True)

        scale_layout.addWidget(self.scale_positive)
        scale_layout.addWidget(self.scale_negative)

        self.scale_positive.setEnabled(self.volume_path is not None)
        self.scale_negative.setEnabled(self.volume_path is not None)

        model_layout.addWidget(scale_row)

        self.isovalue_slider = SliderRow(
            "Isovalue",
            min_val=0.0,
            max_val=100.0,
            default=self.initial_properties.get("isovalue_percentile", 99.5),
            decimals=1,
            suffix="%",
            steps=1000,
            exponent=2.0,
        )
        self.isovalue_slider.setToolTip(
            "Density threshold percentile for isosurface extraction"
        )
        self.isovalue_slider.setEnabled(self.volume_path is not None)
        model_layout.addWidget(self.isovalue_slider)

        main_layout.addWidget(model_group)

        # === SAMPLING SECTION ===
        sampling_group = QGroupBox("Sampling")
        sampling_group.setStyleSheet(QGroupBox_style)
        sampling_rate = self.initial_properties.get("sampling_rate", (1.0, 1.0, 1.0))

        sampling_layout = QHBoxLayout(sampling_group)
        sampling_layout.setSpacing(8)

        base = {"type": "text", "min": 0}

        sampling_tooltip = "Voxel size in Ångström for this axis"

        min_width = 50
        sampling_layout.addWidget(QLabel("X"))
        self.sampling_x = create_setting_widget(base | {"default": sampling_rate[0]})
        self.sampling_x.setMinimumWidth(min_width)
        self.sampling_x.setStyleSheet(QLineEdit_style)
        self.sampling_x.setToolTip(sampling_tooltip)
        sampling_layout.addWidget(self.sampling_x)

        sampling_layout.addWidget(QLabel("Y"))
        self.sampling_y = create_setting_widget(base | {"default": sampling_rate[1]})
        self.sampling_y.setMinimumWidth(min_width)
        self.sampling_y.setStyleSheet(QLineEdit_style)
        self.sampling_y.setToolTip(sampling_tooltip)
        sampling_layout.addWidget(self.sampling_y)

        sampling_layout.addWidget(QLabel("Z"))
        self.sampling_z = create_setting_widget(base | {"default": sampling_rate[2]})
        self.sampling_z.setMinimumWidth(min_width)
        self.sampling_z.setStyleSheet(QLineEdit_style)
        self.sampling_z.setToolTip(sampling_tooltip)
        sampling_layout.addWidget(self.sampling_z)

        main_layout.addWidget(sampling_group)

        # Footer: Reset | [stretch] | Cancel | Done
        footer = DialogFooter(dialog=self, margin=(0, 0, 0, 0))

        self.reset_button = QPushButton("Reset")
        self.reset_button.setIcon(
            qta.icon("ph.arrow-counter-clockwise", color=Colors.ICON)
        )
        self.reset_button.setStyleSheet(QPushButton_style)
        self.reset_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_button.clicked.connect(self._reset_to_defaults)
        footer.layout().insertWidget(0, self.reset_button)
        footer.layout().insertStretch(1)

        main_layout.addWidget(footer)

    def connect_signals(self):
        """Connect all widget signals to update parameters."""
        self.size_spin.valueChanged.connect(self.emit_parameters)
        self.opacity_slider.valueChanged.connect(self.emit_parameters)
        self.ambient_slider.valueChanged.connect(self.emit_parameters)
        self.diffuse_slider.valueChanged.connect(self.emit_parameters)
        self.specular_slider.valueChanged.connect(self.emit_parameters)
        self.isovalue_slider.valueChanged.connect(self.emit_parameters)
        self.scale_positive.toggled.connect(self.emit_parameters)
        self.scale_negative.toggled.connect(self.emit_parameters)
        self.sampling_x.textChanged.connect(self.emit_parameters)
        self.sampling_y.textChanged.connect(self.emit_parameters)
        self.sampling_z.textChanged.connect(self.emit_parameters)
        self.base_color_picker.colorChanged.connect(self.emit_parameters)
        self.highlight_color_picker.colorChanged.connect(self.emit_parameters)
        self.attach_button.clicked.connect(self.emit_parameters)

    def emit_parameters(self):
        parameters = self.get_parameters()
        self.parametersChanged.emit(parameters)

    def _reset_to_defaults(self):
        """Reset all values to initial properties."""
        self.size_spin.setValue(self.initial_properties.get("size", 8))
        self.opacity_slider.setValue(self.initial_properties.get("opacity", 0.3))
        self.ambient_slider.setValue(self.initial_properties.get("ambient", 0.3))
        self.diffuse_slider.setValue(self.initial_properties.get("diffuse", 0.3))
        self.specular_slider.setValue(self.initial_properties.get("specular", 0.3))

        self.base_color_picker.set_color(
            self.initial_properties.get("base_color", (0.7, 0.7, 0.7))
        )
        self.highlight_color_picker.set_color(
            self.initial_properties.get("highlight_color", (0.8, 0.2, 0.2))
        )

        sampling_rate = self.initial_properties.get("sampling_rate", (1.0, 1.0, 1.0))
        self.sampling_x.setText(str(sampling_rate[0]))
        self.sampling_y.setText(str(sampling_rate[1]))
        self.sampling_z.setText(str(sampling_rate[2]))

        self.emit_parameters()

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

        # Enable volume controls
        self.scale_positive.setEnabled(True)
        self.scale_negative.setEnabled(True)
        self.isovalue_slider.setEnabled(True)
        self.attach_button.setEnabled(True)

        self.emit_parameters()

    def get_parameters(self) -> dict:
        """Return current parameters."""
        return {
            "size": get_widget_value(self.size_spin),
            "opacity": self.opacity_slider.value(),
            "ambient": self.ambient_slider.value(),
            "diffuse": self.diffuse_slider.value(),
            "specular": self.specular_slider.value(),
            "base_color": self.base_color_picker.get_color(),
            "highlight_color": self.highlight_color_picker.get_color(),
            "scale": -1 if self.scale_negative.isChecked() else 1,
            "isovalue_percentile": self.isovalue_slider.value(),
            "volume_path": self.volume_path,
            "sampling_rate": (
                float(get_widget_value(self.sampling_x)),
                float(get_widget_value(self.sampling_y)),
                float(get_widget_value(self.sampling_z)),
            ),
        }
