"""
Dialog functions used throughout the GUI.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from pathlib import Path

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QGridLayout,
    QLabel,
    QGroupBox,
    QPushButton,
    QWidget,
)

from ..icons import icon
from ..stylesheets import Colors
from ..widgets import DialogFooter, PathSelector, MosaicMessageBox
from ..widgets.settings import create_setting_widget, get_widget_value, set_widget_value


def _make_setting(parameter, default, min_val=0, description=""):
    """Create a setting dict compatible with create_setting_widget."""
    setting_type = "float" if isinstance(default, float) else "number"
    return {
        "parameter": parameter,
        "label": parameter.replace("_", " ").title(),
        "type": setting_type,
        "default": default,
        "min": min_val,
        "description": description,
    }


class MeshEquilibrationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Mesh Equilibration")
        self.setMinimumWidth(350)

        self._settings = [
            _make_setting(
                "average_edge_length", 40.0, 0, "Average edge length of mesh."
            ),
            _make_setting("lower_bound", 35.0, 0, "Minimum edge length of mesh (lc1)."),
            _make_setting("upper_bound", 45.0, 0, "Maximum edge length of mesh (lc0)."),
            _make_setting("steps", 5000, 0, "Number of minimization steps."),
            _make_setting("kappa_b", 300.0, 0, "Bending energy coefficient (kappa_b)."),
            _make_setting(
                "kappa_a", 1e6, 0, "Area conservation coefficient (kappa_a)."
            ),
            _make_setting(
                "kappa_v", 1e6, 0, "Volume conservation coefficient (kappa_v)."
            ),
            _make_setting("kappa_c", 0.0, 0, "Curvature energy coefficient (kappa_c)."),
            _make_setting("kappa_t", 1e5, 0, "Edge tension coefficient (kappa_t)."),
            _make_setting(
                "kappa_r", 1e3, 0, "Surface repulsion coefficient (kappa_r)."
            ),
            _make_setting("volume_fraction", 1.1, 0, "Fraction VN/V0."),
            _make_setting("area_fraction", 1.1, 0, "Fraction AN/A0."),
            _make_setting(
                "scaling_lower", 1.0, 0, "Lower bound for rescaled mesh edge length."
            ),
        ]

        self._widgets = {}
        self._setup_ui()

    def _add_row(self, grid, row, left, right=None):
        """Add one or two label:widget pairs to a grid row."""
        label = QLabel(left["label"])
        label.setToolTip(left.get("description", ""))
        widget = create_setting_widget(left)
        self._widgets[left["parameter"]] = widget

        grid.addWidget(label, row, 0)
        grid.addWidget(widget, row, 1)

        if right is not None:
            label_r = QLabel(right["label"])
            label_r.setToolTip(right.get("description", ""))
            widget_r = create_setting_widget(right)
            self._widgets[right["parameter"]] = widget_r

            grid.addWidget(label_r, row, 2)
            grid.addWidget(widget_r, row, 3)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        basic_group = QGroupBox("Basic")
        basic = QGridLayout(basic_group)
        basic.setColumnStretch(1, 1)
        basic.setColumnStretch(3, 1)
        basic.setHorizontalSpacing(12)
        basic.setVerticalSpacing(8)

        out_label = QLabel("Output Directory")
        out_label.setToolTip("Directory where the equilibrated mesh will be written")
        self.output_selector = PathSelector(
            placeholder="Directory for equilibrated mesh",
            mode="directory",
        )
        basic.addWidget(out_label, 0, 0)
        basic.addWidget(self.output_selector, 0, 1, 1, 3)

        self._add_row(basic, 1, self._settings[0], self._settings[3])
        self._widgets["average_edge_length"].valueChanged.connect(self._update_bounds)
        self._add_row(basic, 2, self._settings[1], self._settings[2])

        layout.addWidget(basic_group)

        self._toggle_btn = QPushButton(" Advanced")
        self._toggle_btn.setIcon(icon("ph.caret-right", role="muted"))
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setAutoDefault(False)
        self._toggle_btn.setDefault(False)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-bottom: 1px solid {Colors.BORDER_DARK};
                border-radius: 0px;
                text-align: left;
                padding: 6px 0px;
                color: {Colors.TEXT_MUTED};
            }}
            QPushButton:hover {{
                color: {Colors.TEXT_SECONDARY};
            }}
        """
        )
        self._toggle_btn.toggled.connect(self._toggle_advanced)
        layout.addWidget(self._toggle_btn)

        self._advanced = QWidget()
        adv = QVBoxLayout(self._advanced)
        adv.setContentsMargins(0, 4, 0, 0)
        adv.setSpacing(10)

        energy_group = QGroupBox("Energy Coefficients")
        energy = QGridLayout(energy_group)
        energy.setColumnStretch(1, 1)
        energy.setColumnStretch(3, 1)
        energy.setHorizontalSpacing(12)
        energy.setVerticalSpacing(8)

        row = 0
        for i in range(4, 10, 2):
            self._add_row(energy, row, self._settings[i], self._settings[i + 1])
            row += 1
        adv.addWidget(energy_group)

        constraints_group = QGroupBox("Constraints")
        constraints = QGridLayout(constraints_group)
        constraints.setColumnStretch(1, 1)
        constraints.setColumnStretch(3, 1)
        constraints.setHorizontalSpacing(12)
        constraints.setVerticalSpacing(8)

        self._add_row(constraints, 0, self._settings[10], self._settings[11])
        self._add_row(constraints, 1, self._settings[12])
        adv.addWidget(constraints_group)

        self._advanced.setVisible(False)
        layout.addWidget(self._advanced)

        layout.addStretch()

        self.footer = DialogFooter(dialog=self, margin=(0, 12, 0, 0))
        self.footer.accept_button.setEnabled(False)
        layout.addWidget(self.footer)

        self.output_selector.path_input.textChanged.connect(self._update_accept_state)

    def _toggle_advanced(self, expanded):
        """Toggle visibility of advanced parameters."""
        icon_name = "ph.caret-down" if expanded else "ph.caret-right"
        self._toggle_btn.setIcon(icon(icon_name, role="muted"))
        self._advanced.setVisible(expanded)
        self.adjustSize()

    def _update_bounds(self, value):
        """Update lower and upper bounds when edge length changes."""
        try:
            val = float(value)
            set_widget_value(self._widgets["lower_bound"], val * 0.75)
            set_widget_value(self._widgets["upper_bound"], val * 1.25)
        except (ValueError, KeyError):
            pass

    def _update_accept_state(self, *_):
        """Enable the accept button only when a directory is set."""
        path = self.output_selector.get_path().strip()
        self.footer.accept_button.setEnabled(bool(path))

    def accept(self):
        """Ensure the output directory exists (creating it if needed)."""
        path = self.output_selector.get_path().strip()
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            MosaicMessageBox.warning(
                self,
                "Invalid Output Directory",
                f"Cannot use '{path}':\n{exc}",
            )
            return
        return super().accept()

    def get_output_directory(self) -> str:
        """Return the selected output directory."""
        return self.output_selector.get_path().strip()

    def get_parameters(self):
        """Get the current parameters."""
        return {
            param: get_widget_value(widget) for param, widget in self._widgets.items()
        }
