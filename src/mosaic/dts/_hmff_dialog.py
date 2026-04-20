"""
Dialog functions used throughout the GUI.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from os.path import join, exists
from typing import Dict, List, Optional

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QVBoxLayout,
    QMessageBox,
    QDialog,
    QGroupBox,
    QFormLayout,
    QLabel,
)

from ..widgets import PathSelector, DialogFooter
from ..stylesheets import Colors, Typography
from ..widgets.settings import get_widget_value, create_setting_widget


class HMFFDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("HMFF Configuration")
        self.setMinimumWidth(400)

        self.parameter_widgets = {}
        self._mesh_conf: Optional[Dict[str, List[str]]] = None
        self._gated_groups: List[QGroupBox] = []
        self.setup_ui()
        self.setup_connections()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)

        input_group = QGroupBox("Input Configuration")
        input_layout = QFormLayout(input_group)

        self.directory_selector = PathSelector(
            placeholder="Directory created by Mesh Equilibration (contains mesh.txt)",
            mode="directory",
        )
        input_layout.addRow("Working directory:", self.directory_selector)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            f"color: {Colors.ERROR}; font-size: {Typography.SMALL}px;"
        )
        self.status_label.setVisible(False)
        input_layout.addRow("", self.status_label)

        self.parameter_widgets["mesh"] = create_setting_widget(
            {
                "type": "select",
                "options": [""],
                "default": "",
            }
        )
        input_layout.addRow("Mesh:", self.parameter_widgets["mesh"])

        volume_input = PathSelector()
        input_layout.addRow("Volume:", volume_input)
        self.parameter_widgets["volume_path"] = volume_input
        main_layout.addWidget(input_group)

        # Filter Options Group
        filter_group = QGroupBox("Filter Options")
        filter_layout = QFormLayout(filter_group)

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
        main_layout.addWidget(filter_group)

        # Simulation Parameters Group
        sim_group = QGroupBox("Simulation Parameters")
        sim_layout = QFormLayout(sim_group)

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
        main_layout.addWidget(sim_group)

        self.footer = DialogFooter(dialog=self, margin=(0, 10, 0, 0))
        self.footer.accept_button.setEnabled(False)
        main_layout.addWidget(self.footer)

        # Groups whose contents are only meaningful once the working directory is set.
        self._gated_groups = [filter_group, sim_group]
        # Mesh and volume live in input_group alongside the directory selector,
        # so gate them individually rather than disabling the whole group.
        self._gated_widgets = [
            self.parameter_widgets["mesh"],
            self.parameter_widgets["volume_path"],
        ]
        self._set_downstream_enabled(False)

    def setup_connections(self):
        self.parameter_widgets["use_filters"].stateChanged.connect(
            self.toggle_filter_inputs
        )
        self.parameter_widgets["lowpass_cutoff"].valueChanged.connect(
            self.validate_filters
        )
        self.parameter_widgets["highpass_cutoff"].valueChanged.connect(
            self.validate_filters
        )
        self.directory_selector.path_input.textChanged.connect(
            self._on_directory_changed
        )

    def _set_downstream_enabled(self, enabled: bool):
        """Enable or disable everything that depends on a valid working directory.

        Qt propagates disabled state through parent groups without overriding
        individual child states, so the filter fields preserve whatever state
        the 'Enable Filters' checkbox last set when the group is re-enabled.
        """
        for group in self._gated_groups:
            group.setEnabled(enabled)
        for widget in self._gated_widgets:
            widget.setEnabled(enabled)
        self.footer.accept_button.setEnabled(enabled)

    def _show_status(self, message: str):
        self.status_label.setText(message)
        self.status_label.setVisible(bool(message))

    def _on_directory_changed(self, text: str):
        """Parse mesh.txt from the selected directory and update dependent widgets."""
        directory = text.strip()
        self._mesh_conf = None

        if not directory:
            self._show_status("")
            self._set_downstream_enabled(False)
            self._set_mesh_options([""])
            return

        if not exists(directory):
            self._show_status("Directory does not exist.")
            self._set_downstream_enabled(False)
            self._set_mesh_options([""])
            return

        mesh_config = join(directory, "mesh.txt")
        if not exists(mesh_config):
            self._show_status(
                "Missing mesh.txt — pick a directory created by Mesh Equilibration."
            )
            self._set_downstream_enabled(False)
            self._set_mesh_options([""])
            return

        try:
            with open(mesh_config, mode="r", encoding="utf-8") as infile:
                data = [x.strip() for x in infile.read().split("\n")]
                data = [x.split("\t") for x in data if len(x)]
            headers = data.pop(0)
            ret = {header: list(column) for header, column in zip(headers, zip(*data))}
        except (OSError, ValueError, IndexError) as exc:
            self._show_status(f"Could not parse mesh.txt: {exc}")
            self._set_downstream_enabled(False)
            self._set_mesh_options([""])
            return

        required = ("file", "scale_factor", "offset")
        if not all(col in ret for col in required):
            self._show_status(
                "mesh.txt is malformed (expected file, scale_factor, offset columns)."
            )
            self._set_downstream_enabled(False)
            self._set_mesh_options([""])
            return

        self._mesh_conf = ret
        self._show_status("")
        self._set_mesh_options(ret["file"])
        self._set_downstream_enabled(True)

    def _set_mesh_options(self, options: List[str]):
        mesh_widget = self.parameter_widgets["mesh"]
        mesh_widget.blockSignals(True)
        mesh_widget.clear()
        mesh_widget.addItems(options)
        mesh_widget.blockSignals(False)

    def toggle_filter_inputs(self, state):
        enabled = state == Qt.CheckState.Checked.value
        self.parameter_widgets["lowpass_cutoff"].setEnabled(enabled)
        self.parameter_widgets["highpass_cutoff"].setEnabled(enabled)
        self.parameter_widgets["plane_norm"].setEnabled(enabled)

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
        if self._mesh_conf is None:
            QMessageBox.warning(
                self, "Invalid Input", "Please select a valid working directory."
            )
            return

        if not self.validate_filters():
            QMessageBox.warning(
                self, "Invalid Input", "Please provide a valid filter specification."
            )
            return

        return super().accept()

    def get_mesh_conf(self) -> Dict[str, List[str]]:
        """Return the parsed mesh.txt contents for the selected working directory."""
        return self._mesh_conf or {}

    def get_parameters(self):
        params = {
            name: get_widget_value(widget)
            for name, widget in self.parameter_widgets.items()
        }
        params["directory"] = self.directory_selector.get_path().strip()
        return params
