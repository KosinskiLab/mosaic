""" Dialog functions used throughout the GUI.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""
from PyQt6.QtWidgets import QComboBox

from .operation import OperationDialog, make_param


class MeshEquilibrationDialog(OperationDialog):
    def __init__(self, parent=None):
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
                "scaling_lower", 1.0, 0, "Lower bound for rescalde mesh edge length."
            ),
        ]

        super().__init__("Mesh Equilibration", self._operations, parent)
        self.setup_custom_ui()

    def setup_custom_ui(self):
        # Hide all parameter widgets initially except edge length
        self.edge_length = self.parameter_widgets[self._operations[0][0]]
        self.edge_length.textChanged.connect(self.update_bounds)

        # Add parameter mode selection
        self.mode_selector = QComboBox()
        self.mode_selector.addItems(["Default", "Advanced"])
        self.mode_selector.currentTextChanged.connect(self.toggle_advanced)
        self.params_layout.insertRow(1, "Settings:", self.mode_selector)
        self.toggle_advanced("Default")

    def update_bounds(self, value):
        try:
            val = float(value)
            lower_bound = self.parameter_widgets["lower_bound"]
            upper_bound = self.parameter_widgets["upper_bound"]
            if lower_bound and upper_bound:
                lower_bound.setText(f"{val * 0.75}")
                upper_bound.setText(f"{val * 1.25}")
        except ValueError:
            pass

    def toggle_advanced(self, mode):
        for name, widget in self.parameter_widgets.items():
            if widget != self.edge_length:
                widget.setVisible(mode == "Advanced")

        for name, widget in self.label_widgets.items():
            if name != "average_edge_length":
                widget.setVisible(mode == "Advanced")
