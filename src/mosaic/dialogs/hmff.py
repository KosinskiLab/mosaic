""" Dialog functions used throughout the GUI.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from os.path import exists

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QDialog,
    QGroupBox,
    QFormLayout,
    QWidget,
    QLineEdit,
)
import qtawesome as qta

from mosaic.widgets.settings import get_widget_value, create_setting_widget


class HMFFDialog(QDialog):
    def __init__(self, parent=None, mesh_options=[""]):
        super().__init__(parent)
        self.setWindowTitle("HMFF Configuration")
        self.setMinimumWidth(400)

        self.parameter_widgets = {}
        self.mesh_options = mesh_options
        self.setup_ui()
        self.setup_connections()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)

        # Input Configuration
        input_group = QGroupBox("Input Configuration")
        input_layout = QFormLayout()

        self.parameter_widgets["mesh"] = create_setting_widget(
            {
                "type": "select",
                "options": self.mesh_options,
                "default": self.mesh_options[0],
            }
        )
        input_layout.addRow("Mesh:", self.parameter_widgets["mesh"])

        volume_widget = QWidget()
        volume_layout = QHBoxLayout(volume_widget)
        volume_layout.setContentsMargins(0, 0, 0, 0)

        self.volume_input = QLineEdit()
        self.parameter_widgets["volume_path"] = self.volume_input

        browse_button = QPushButton()
        browse_button.setIcon(qta.icon("fa5s.folder-open", opacity=0.7, color="gray"))
        browse_button.clicked.connect(self.browse_volume)

        volume_layout.addWidget(self.volume_input)
        volume_layout.addWidget(browse_button)
        input_layout.addRow("Volume:", volume_widget)
        input_group.setLayout(input_layout)
        main_layout.addWidget(input_group)

        # Filter Options Group
        filter_group = QGroupBox("Filter Options")
        filter_layout = QFormLayout()

        self.parameter_widgets["use_filters"] = create_setting_widget(
            {
                "type": "boolean",
                "default": False,
            }
        )
        filter_layout.addRow("Enable Filters", self.parameter_widgets["use_filters"])

        self.parameter_widgets["lowpass_cutoff"] = create_setting_widget(
            {
                "type": "float",
                "min": 0.0,
                "max": 1000.0,
                "default": 140.0,
                "step": 1.0,
                "description": "Filter cutoff in units of input volume sampling rate.",
            }
        )
        self.parameter_widgets["lowpass_cutoff"].setEnabled(False)
        filter_layout.addRow(
            "Lowpass cutoff:", self.parameter_widgets["lowpass_cutoff"]
        )

        self.parameter_widgets["highpass_cutoff"] = create_setting_widget(
            {
                "type": "float",
                "min": 0.0,
                "max": 1000.0,
                "default": 900.0,
                "step": 1.0,
                "description": "Filter cutoff in units of input volume sampling rate.",
            }
        )
        self.parameter_widgets["highpass_cutoff"].setEnabled(False)
        filter_layout.addRow(
            "Highpass cutoff:", self.parameter_widgets["highpass_cutoff"]
        )

        self.parameter_widgets["plane_norm"] = create_setting_widget(
            {
                "type": "select",
                "options": ["", "x", "y", "z"],
                "default": "",
                "description": "Scale maximum value along axis to one.",
            }
        )
        self.parameter_widgets["plane_norm"].setEnabled(False)
        filter_layout.addRow("Normalize axis:", self.parameter_widgets["plane_norm"])

        filter_group.setLayout(filter_layout)
        main_layout.addWidget(filter_group)

        # Simulation Parameters Group
        sim_group = QGroupBox("Simulation Parameters")
        sim_layout = QFormLayout()

        self.parameter_widgets["invert_contrast"] = create_setting_widget(
            {
                "type": "boolean",
                "default": True,
            }
        )
        sim_layout.addRow("Invert contrast:", self.parameter_widgets["invert_contrast"])

        sim_params = {
            "xi": {"min": 0, "max": 100, "default": 5.0, "step": 0.1},
            "gradient_step_size": {"min": 0, "max": 100, "default": 0.0, "step": 0.1},
            "kappa": {"min": 0, "max": 100, "default": 25.0, "step": 0.1},
            "steps": {"min": 0, "max": 1000000, "default": 50000},
            "threads": {"min": 1, "max": 32, "default": 1},
        }

        labels = {
            "xi": "HMFF weight (ξ):",
            "gradient_step_size": "Gradient step:",
            "kappa": "Rigidity (κ):",
            "steps": "Steps:",
            "threads": "Threads:",
        }

        for param, settings in sim_params.items():
            widget_type = "float" if "step" in settings else "number"
            self.parameter_widgets[param] = create_setting_widget(
                {"type": widget_type, **settings}
            )
            sim_layout.addRow(labels[param], self.parameter_widgets[param])

        sim_group.setLayout(sim_layout)
        main_layout.addWidget(sim_group)

        # Button layout
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        ok_btn.setDefault(True)

        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(ok_btn)
        main_layout.addLayout(button_layout)

    def setup_connections(self):
        self.parameter_widgets["use_filters"].stateChanged.connect(
            self.toggle_filter_inputs
        )
        self.volume_input.textChanged.connect(self.validate_volume)
        self.parameter_widgets["lowpass_cutoff"].valueChanged.connect(
            self.validate_filters
        )
        self.parameter_widgets["highpass_cutoff"].valueChanged.connect(
            self.validate_filters
        )

    def toggle_filter_inputs(self, state):
        enabled = state == Qt.CheckState.Checked.value
        self.parameter_widgets["lowpass_cutoff"].setEnabled(enabled)
        self.parameter_widgets["highpass_cutoff"].setEnabled(enabled)
        self.parameter_widgets["plane_norm"].setEnabled(enabled)

    def browse_volume(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Volume File",
            "",
            "Volume Files (*.mrc *.map *.em);;All Files (*.*)",
        )
        if file_path:
            self.volume_input.setText(file_path)

    def validate_volume(self):
        vol_path = self.volume_input.text()
        if not vol_path:
            return False

        if not exists(vol_path):
            self.volume_input.setStyleSheet("background-color: #d32f2f;")
            return False

        self.volume_input.setStyleSheet("")
        return True

    def validate_filters(self):
        if not self.parameter_widgets["use_filters"].isChecked():
            return True

        lowpass = get_widget_value(self.parameter_widgets["lowpass_cutoff"])
        highpass = get_widget_value(self.parameter_widgets["highpass_cutoff"])

        valid_range = highpass >= lowpass
        style = "" if valid_range else "background-color: #d32f2f;"
        self.parameter_widgets["lowpass_cutoff"].setStyleSheet(style)
        self.parameter_widgets["highpass_cutoff"].setStyleSheet(style)

        return valid_range

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

    def get_parameters(self):
        return {
            name: get_widget_value(widget)
            for name, widget in self.parameter_widgets.items()
        }
