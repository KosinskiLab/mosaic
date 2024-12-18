""" Dialog functions used throughout the GUI.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from os.path import exists

import qtawesome as qta
from PyQt6.QtWidgets import (
    QLabel,
    QHBoxLayout,
    QPushButton,
    QFileDialog,
    QMessageBox,
)

from .operation import OperationDialog, make_param


class HMFFDialog(OperationDialog):
    def __init__(self, parent=None, mesh_options=[""]):
        self._operations = [
            make_param("mesh", mesh_options[0], mesh_options, "Mesh to simulate."),
            make_param("volume_path", 0.0, "", "Path to HMFF potential file."),
            make_param(
                "lowpass_cutoff", 140.0, 0.0, "Resolution to lowpass filter to [Å]."
            ),
            make_param(
                "highpass_cutoff", 900.0, 0.0, "Resolution to highpass filter to [Å]."
            ),
            make_param(
                "invert_contrast",
                True,
                [False, True],
                "Invert data, i.e. switch from Black-White to White-Black contrast.",
            ),
            make_param("xi", 5.0, 0.0, "Weighting factor of HMFF potential."),
            make_param(
                "gradient_step_size",
                0.0,
                0.0,
                "Gradient step size along HMFF potential.",
            ),
            make_param("kappa", 25.0, 0.0, "Membrane rigidity."),
            make_param("steps", 50000, 0.0, "Simulation steps."),
            make_param("threads", 1, 0, "Simulation threads."),
        ]
        super().__init__("Setup HMFF", self._operations, parent)
        self.setup_custom_ui()

    def setup_custom_ui(self):
        self.volume_input = self.parameter_widgets["volume_path"]
        self.volume_input.setText("")
        self.select_volume_button = QPushButton()
        self.select_volume_button.setIcon(
            qta.icon("fa5s.folder-open", opacity=0.7, color="gray")
        )
        self.select_volume_button.clicked.connect(self.browse_volume)

        volume_layout = QHBoxLayout()
        label = QLabel("Volume path:")
        volume_layout.addWidget(self.volume_input)
        volume_layout.addWidget(self.select_volume_button)

        row_index = 0
        for i, k in enumerate(self._operations):
            if k[0] == "volume_path":
                row_index = i

        self.params_layout.removeRow(row_index)
        self.params_layout.insertRow(row_index, label, volume_layout)

        self.lowpass_input = self.parameter_widgets["lowpass_cutoff"]
        self.highpass_input = self.parameter_widgets["highpass_cutoff"]

        self.lowpass_input.textChanged.connect(self.validate_filters)
        self.highpass_input.textChanged.connect(self.validate_filters)

        self.volume_input.textChanged.connect(self.validate_volume)

    def browse_volume(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Volume File",
            "",
            "Volume Files (*.mrc *.map *.em);;All Files (*.*)",
        )
        if file_path:
            self.volume_input.setText(file_path)

    def validate_filters(self):
        lowpass = float(self.lowpass_input.text())
        highpass = float(self.highpass_input.text())

        valid_range = all([highpass >= lowpass])
        style = "" if valid_range else "background-color: #d32f2f;"
        self.lowpass_input.setStyleSheet(style)
        self.highpass_input.setStyleSheet(style)

        return valid_range

    def validate_volume(self):
        vol_path = self.volume_input.text()
        if not vol_path:
            return False

        if not exists(vol_path):
            self.volume_input.setStyleSheet("background-color: #d32f2f;")
            return False

        self.volume_input.setStyleSheet("")
        return True

    def accept(self):
        if not self.validate_volume():
            QMessageBox.warning(
                self, "Invalid Input", "Please select a valid volume file."
            )
            return

        if not self.validate_filters():
            QMessageBox.warning(
                self, "Invalid Input", "Please provide a valid filter specification."
            )
            return

        super().accept()
