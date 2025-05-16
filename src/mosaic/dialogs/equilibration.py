""" Dialog functions used throughout the GUI.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGridLayout,
    QComboBox,
    QFrame,
    QScrollArea,
    QWidget,
    QGroupBox,
)

from .operation import make_param
from ..widgets import ParameterWidget, DialogFooter
from ..stylesheets import QGroupBox_style, QPushButton_style, QScrollArea_style


class MeshEquilibrationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Mesh Equilibration")
        self.resize(600, 500)

        self._operations = [
            make_param("average_edge_length", 40.0, 0, "Average edge length of mesh."),
            make_param("lower_bound", 35.0, 0, "Minimum edge length of mesh (lc1)."),
            make_param("upper_bound", 45.0, 0, "Maximumg edge length of mesh (lc0)."),
            make_param("steps", 5000, 0, "Number of minimization steps."),
            make_param("kappa_b", 300.0, 0, "Bending energy coefficient (kappa_b)."),
            make_param("kappa_a", 1e6, 0, "Area conservation coefficient (kappa_a)."),
            make_param("kappa_v", 1e6, 0, "Volume conservation coefficient (kappa_v)."),
            make_param("kappa_c", 0.0, 0, "Curvature energy coefficient (kappa_c)."),
            make_param("kappa_t", 1e5, 0, "Edge tension coefficient (kappa_t)."),
            make_param("kappa_r", 1e3, 0, "Surface repulsion coefficient (kappa_r)."),
            make_param("volume_fraction", 1.1, 0, "Fraction VN/V0."),
            make_param("area_fraction", 1.1, 0, "Fraction AN/A0."),
            make_param(
                "scaling_lower", 1.0, 0, "Lower bound for rescaled mesh edge length."
            ),
        ]

        self.parameter_widgets = {}
        self.current_values = {op[0]: op[1] for op in self._operations}

        self.setup_ui()
        self.setStyleSheet(QGroupBox_style + QPushButton_style + QScrollArea_style)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        header_layout = QHBoxLayout()

        title_label = QLabel("Mesh Equilibration Settings")
        title_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        mode_label = QLabel("Settings Mode:")
        header_layout.addWidget(mode_label)

        self.mode_selector = QComboBox()
        self.mode_selector.addItems(["Default", "Advanced"])
        self.mode_selector.currentTextChanged.connect(self.toggle_mode)
        header_layout.addWidget(self.mode_selector)

        main_layout.addLayout(header_layout)

        # Scroll area for content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        content_widget = QWidget()
        scroll_area.setWidget(content_widget)
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(15)

        # Basic settings
        basic_settings = QGroupBox("Basic Settings")
        basic_layout = QGridLayout(basic_settings)
        basic_layout.setColumnStretch(0, 1)
        basic_layout.setColumnStretch(1, 1)

        # Create edge length widget
        self.edge_length_widget = self.create_parameter_widget(self._operations[0])
        self.edge_length_widget.valueChanged.connect(self.update_bounds)
        basic_layout.addWidget(self.edge_length_widget, 0, 0)

        # Add steps widget
        self.steps_widget = self.create_parameter_widget(self._operations[3])
        basic_layout.addWidget(self.steps_widget, 0, 1)

        # Add parameters visible in both modes
        self.lower_bound_widget = self.create_parameter_widget(self._operations[1])
        self.upper_bound_widget = self.create_parameter_widget(self._operations[2])
        basic_layout.addWidget(self.lower_bound_widget, 1, 0)
        basic_layout.addWidget(self.upper_bound_widget, 1, 1)

        content_layout.addWidget(basic_settings)

        # Advanced settings
        self.advanced_group = QGroupBox("Energy Coefficients")
        advanced_layout = QGridLayout(self.advanced_group)
        advanced_layout.setColumnStretch(0, 1)
        advanced_layout.setColumnStretch(1, 1)

        # Energy coefficients (kappa)
        row, col = 0, 0
        for i in range(4, 10):
            widget = self.create_parameter_widget(self._operations[i])
            advanced_layout.addWidget(widget, row, col)
            col = (col + 1) % 2
            if col == 0:
                row += 1

        content_layout.addWidget(self.advanced_group)

        # Constraints
        self.constraints_group = QGroupBox("Additional Constraints")
        constraints_layout = QGridLayout(self.constraints_group)

        for i in range(10, len(self._operations)):
            widget = self.create_parameter_widget(self._operations[i])
            constraints_layout.addWidget(widget, (i - 10) // 2, (i - 10) % 2)

        content_layout.addWidget(self.constraints_group)
        content_layout.addStretch()

        main_layout.addWidget(scroll_area)

        footer = DialogFooter(dialog=self, margin=(0, 15, 0, 0))
        main_layout.addWidget(footer)
        self.toggle_mode("Default")

    def create_parameter_widget(self, param_data):
        """Create a parameter widget from parameter data."""
        param_name, param_value, param_min, param_info = param_data

        widget = ParameterWidget(param_name, param_value, param_min, param_info, self)
        widget.valueChanged.connect(self._on_value_changed)

        self.parameter_widgets[param_name] = widget
        return widget

    def toggle_mode(self, mode):
        """Toggle between Default and Advanced modes."""
        is_advanced = mode == "Advanced"
        self.advanced_group.setVisible(is_advanced)
        self.constraints_group.setVisible(is_advanced)

    def update_bounds(self, param_name, value):
        """Update lower and upper bounds when edge length changes."""
        if param_name != "average_edge_length":
            return

        try:
            val = float(value)
            self.lower_bound_widget.setValue(val * 0.75)
            self.upper_bound_widget.setValue(val * 1.25)

            self.current_values["lower_bound"] = val * 0.75
            self.current_values["upper_bound"] = val * 1.25
        except ValueError:
            pass

    def _on_value_changed(self, param_name, value):
        self.current_values[param_name] = value

    def get_parameters(self):
        """Get the current parameters."""
        return self.current_values
