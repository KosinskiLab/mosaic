"""
Modulate visual properties of Geometry objects.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from os.path import exists

from qtpy.QtCore import Signal, Qt

from mosaic.geometry import BASE_COLOR
from mosaic.utils import Throttle
from qtpy.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QDialog,
    QPushButton,
    QFileDialog,
    QWidget,
    QLabel,
    QGroupBox,
    QApplication,
)
from ..icons import icon
from ..widgets import (
    DialogFooter,
    create_setting_widget,
    get_widget_value,
    ColorPickerRow,
    SliderRow,
)
from ..widgets.segmented_control import SegmentedControl


class GeometryPropertiesDialog(QDialog):
    parametersChanged = Signal(dict)

    def __init__(self, initial_properties=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Properties")
        self.setFixedWidth(400)
        self.parameters = {}

        self.base_color = initial_properties.get("base_color", BASE_COLOR)
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
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)

        appearance_group = QGroupBox("Appearance")
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

        interp_row = QWidget()
        interp_layout = QHBoxLayout(interp_row)
        interp_layout.setContentsMargins(0, 0, 0, 0)
        interp_layout.setSpacing(12)

        interp_label = QLabel("Shading")
        interp_layout.addWidget(interp_label)
        interp_layout.addStretch()

        interp_labels = ["Flat", "Gouraud", "Phong"]
        current_interp = self.initial_properties.get("interpolation", "gouraud")
        interp_idx = next(
            (i for i, l in enumerate(interp_labels) if l.lower() == current_interp), 1
        )
        self._interpolation_control = SegmentedControl(
            interp_labels, default=interp_idx
        )
        self._interpolation_control.setToolTip(
            "Surface shading. Flat for faceted, Gouraud for smooth, Phong \n"
            "for per-pixel smooth with sharper highlights on meshes."
        )
        interp_layout.addWidget(self._interpolation_control)
        appearance_layout.addWidget(interp_row)

        main_layout.addWidget(appearance_group)

        lighting_group = QGroupBox("Lighting")
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

        model_group = QGroupBox("Model")
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
        self.browse_button.setIcon(icon("ph.folder-open"))
        self.browse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_button.setToolTip("Select a density map file")
        self.browse_button.clicked.connect(self.browse_volume)
        browse_layout.addWidget(self.browse_button)

        self.attach_button = QPushButton("Reattach")
        self.attach_button.setIcon(icon("ph.link"))
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

        default_idx = 1 if self.initial_properties.get("volume_scale", 0) < 0 else 0
        self.scale_control = SegmentedControl(["Native", "Invert"], default=default_idx)
        self.scale_control.setToolTip("Keep original density contrast or invert it")
        self.scale_control.setEnabled(self.volume_path is not None)
        scale_layout.addWidget(self.scale_control)

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

        sampling_group = QGroupBox("Sampling")
        sampling_rate = self.initial_properties.get("sampling_rate", (1.0, 1.0, 1.0))

        sampling_layout = QHBoxLayout(sampling_group)
        sampling_layout.setSpacing(8)

        base = {"type": "text", "min": 0}

        sampling_tooltip = "Voxel size in Ångström for this axis"

        min_width = 50
        sampling_layout.addWidget(QLabel("X"))
        self.sampling_x = create_setting_widget(base | {"default": sampling_rate[0]})
        self.sampling_x.setMinimumWidth(min_width)
        self.sampling_x.setToolTip(sampling_tooltip)
        sampling_layout.addWidget(self.sampling_x)

        sampling_layout.addWidget(QLabel("Y"))
        self.sampling_y = create_setting_widget(base | {"default": sampling_rate[1]})
        self.sampling_y.setMinimumWidth(min_width)
        self.sampling_y.setToolTip(sampling_tooltip)
        sampling_layout.addWidget(self.sampling_y)

        sampling_layout.addWidget(QLabel("Z"))
        self.sampling_z = create_setting_widget(base | {"default": sampling_rate[2]})
        self.sampling_z.setMinimumWidth(min_width)
        self.sampling_z.setToolTip(sampling_tooltip)
        sampling_layout.addWidget(self.sampling_z)

        main_layout.addWidget(sampling_group)

        footer = DialogFooter(dialog=self, margin=(0, 0, 0, 0))

        self.reset_button = QPushButton("Reset")
        self.reset_button.setIcon(icon("ph.arrow-counter-clockwise"))
        self.reset_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_button.clicked.connect(self._reset_to_defaults)
        footer.layout().insertWidget(0, self.reset_button)
        footer.layout().insertStretch(1)

        main_layout.addWidget(footer)

    def connect_signals(self):
        """Connect all widget signals to update parameters."""
        self._emit_throttle = Throttle(
            lambda *args: self.emit_parameters(), interval_ms=150
        )
        self.size_spin.valueChanged.connect(self._emit_throttle)
        self.opacity_slider.valueChanged.connect(self._emit_throttle)
        self.ambient_slider.valueChanged.connect(self._emit_throttle)
        self.diffuse_slider.valueChanged.connect(self._emit_throttle)
        self.specular_slider.valueChanged.connect(self._emit_throttle)
        self._interpolation_control.selectionChanged.connect(
            lambda _: self.emit_parameters()
        )
        self.isovalue_slider.valueChanged.connect(self._emit_throttle)
        self.scale_control.selectionChanged.connect(lambda _: self.emit_parameters())
        self.sampling_x.textChanged.connect(self.emit_parameters)
        self.sampling_y.textChanged.connect(self.emit_parameters)
        self.sampling_z.textChanged.connect(self.emit_parameters)
        self.base_color_picker.colorChanged.connect(self.emit_parameters)
        self.highlight_color_picker.colorChanged.connect(self.emit_parameters)

        self.attach_button.clicked.connect(self.reattach_emit)

    def reattach_emit(self):
        parameters = self.get_parameters()
        parameters["reattach_volume"] = True
        self.parametersChanged.emit(parameters)

    def emit_parameters(self):
        parameters = self.get_parameters()
        self.parametersChanged.emit(parameters)

    def _reset_to_defaults(self):
        """Reset all values to initial properties."""
        self.size_spin.setValue(self.initial_properties.get("size", 8))
        self.opacity_slider.setValue(self.initial_properties.get("opacity", 1.0))
        self.ambient_slider.setValue(self.initial_properties.get("ambient", 0.3))
        self.diffuse_slider.setValue(self.initial_properties.get("diffuse", 0.7))
        self.specular_slider.setValue(self.initial_properties.get("specular", 0.2))

        interp = self.initial_properties.get("interpolation", "gouraud")
        interp_idx = next(
            (i for i, l in enumerate(["flat", "gouraud", "phong"]) if l == interp), 1
        )
        self._interpolation_control._select(interp_idx)

        self.base_color_picker.set_color(
            self.initial_properties.get("base_color", BASE_COLOR)
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

        self.volume_path = file_name
        volume = load_density(self.volume_path)
        non_negative = (volume.data > 0).sum()
        if non_negative < volume.data.size // 2:
            self.scale_control._select(1)

        self.scale_control.setEnabled(True)
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
            "interpolation": self._interpolation_control.currentText().lower(),
            "base_color": self.base_color_picker.get_color(),
            "highlight_color": self.highlight_color_picker.get_color(),
            "scale": -1 if self.scale_control.currentText() == "Invert" else 1,
            "isovalue_percentile": self.isovalue_slider.value(),
            "volume_path": self.volume_path,
            "reattach_volume": False,
            "sampling_rate": (
                float(get_widget_value(self.sampling_x)),
                float(get_widget_value(self.sampling_y)),
                float(get_widget_value(self.sampling_z)),
            ),
        }
