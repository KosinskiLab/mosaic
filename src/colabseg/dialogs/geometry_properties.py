from PyQt6.QtWidgets import (
    QVBoxLayout,
    QDialog,
    QDialogButtonBox,
    QSpinBox,
    QDoubleSpinBox,
    QFormLayout,
    QPushButton,
    QGroupBox,
    QFileDialog,
    QColorDialog,
    QRadioButton,
    QHBoxLayout,
    QWidget,
)
from PyQt6.QtGui import QColor
import qtawesome as qta


class GeometryPropertiesDialog(QDialog):
    def __init__(self, initial_properties=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Geometry Properties")
        self.parameters = {}

        # Set default colors if not provided
        self.base_color = initial_properties.get("base_color", (0.7, 0.7, 0.7))
        self.highlight_color = initial_properties.get(
            "highlight_color", (0.8, 0.2, 0.2)
        )
        self.initial_properties = initial_properties or {}
        self.volume_path = self.initial_properties.get("volume_path", None)

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Appearance Group
        appearance_group = QGroupBox("Appearance")
        appearance_layout = QFormLayout()

        # Point Size
        self.size_spin = QSpinBox()
        self.size_spin.setRange(1, 50)
        self.size_spin.setValue(self.initial_properties.get("size", 8))
        appearance_layout.addRow("Point Size:", self.size_spin)

        # Opacity
        self.opacity_spin = QDoubleSpinBox()
        self.opacity_spin.setRange(0.0, 1.0)
        self.opacity_spin.setSingleStep(0.1)
        self.opacity_spin.setValue(self.initial_properties.get("opacity", 1.0))
        appearance_layout.addRow("Opacity:", self.opacity_spin)

        # Colors Group
        colors_group = QGroupBox("Colors")
        colors_layout = QFormLayout()

        # Base Color
        self.base_color_button = QPushButton()
        self.update_color_button(self.base_color_button, self.base_color)
        self.base_color_button.clicked.connect(lambda: self.choose_color("base"))
        colors_layout.addRow("Base Color:", self.base_color_button)

        # Highlight Color
        self.highlight_color_button = QPushButton()
        self.update_color_button(self.highlight_color_button, self.highlight_color)
        self.highlight_color_button.clicked.connect(
            lambda: self.choose_color("highlight")
        )
        colors_layout.addRow("Highlight Color:", self.highlight_color_button)

        colors_group.setLayout(colors_layout)

        # Lighting properties
        self.ambient_spin = QDoubleSpinBox()
        self.ambient_spin.setRange(0.0, 1.0)
        self.ambient_spin.setSingleStep(0.1)
        self.ambient_spin.setValue(self.initial_properties.get("ambient", 0.3))
        appearance_layout.addRow("Ambient:", self.ambient_spin)

        self.diffuse_spin = QDoubleSpinBox()
        self.diffuse_spin.setRange(0.0, 1.0)
        self.diffuse_spin.setSingleStep(0.1)
        self.diffuse_spin.setValue(self.initial_properties.get("diffuse", 0.7))
        appearance_layout.addRow("Diffuse:", self.diffuse_spin)

        self.specular_spin = QDoubleSpinBox()
        self.specular_spin.setRange(0.0, 1.0)
        self.specular_spin.setSingleStep(0.1)
        self.specular_spin.setValue(self.initial_properties.get("specular", 0.2))
        appearance_layout.addRow("Specular:", self.specular_spin)

        appearance_group.setLayout(appearance_layout)

        # Render points as glyphs
        model_group = QGroupBox("Model")
        model_layout = QFormLayout()

        self.browse_button = QPushButton()
        self.browse_button.setIcon(qta.icon("fa5s.folder-open"))
        self.browse_button.clicked.connect(self.browse_volume)
        model_layout.addRow("Volume:", self.browse_button)

        self.scale_widget = QWidget()
        scale_layout = QHBoxLayout(self.scale_widget)
        scale_layout.setContentsMargins(0, 0, 0, 0)
        self.scale_positive = QRadioButton("1")
        self.scale_negative = QRadioButton("-1")
        self.scale_positive.setChecked(True)
        scale_layout.addWidget(self.scale_positive)
        scale_layout.addWidget(self.scale_negative)
        self.scale_widget.setEnabled(False)
        model_layout.addRow("Scaling:", self.scale_widget)

        self.isovalue_spin = QDoubleSpinBox()
        self.isovalue_spin.setRange(0.0, 100.0)
        self.isovalue_spin.setSingleStep(1.0)
        self.isovalue_spin.setDecimals(1)
        default_percentile = self.initial_properties.get("isovalue_percentile", 99.5)
        self.isovalue_spin.setValue(default_percentile)
        self.isovalue_spin.setEnabled(False)
        model_layout.addRow("Isovalue:", self.isovalue_spin)

        model_group.setLayout(model_layout)

        layout.addWidget(appearance_group)
        layout.addWidget(colors_group)
        layout.addWidget(model_group)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def browse_volume(self):
        """Open file dialog to select volume file"""
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select Volume File", "", "MRC Files (*.mrc);;All Files (*.*)"
        )
        if not file_name:
            return -1
        self.scale_widget.setEnabled(True)
        self.isovalue_spin.setEnabled(True)
        self.volume_path = file_name

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

    def exec(self) -> dict:
        """Execute the dialog and return the parameters if accepted"""
        result = super().exec()
        if result == QDialog.DialogCode.Accepted:
            self.parameters = {
                "size": self.size_spin.value(),
                "opacity": self.opacity_spin.value(),
                "ambient": self.ambient_spin.value(),
                "diffuse": self.diffuse_spin.value(),
                "specular": self.specular_spin.value(),
                "base_color": self.base_color,
                "highlight_color": self.highlight_color,
                "scale": -1 if self.scale_negative.isChecked() else 1,
                "isovalue_percentile": self.isovalue_spin.value(),
                "volume_path": self.volume_path,
            }
            return self.parameters
        return None
