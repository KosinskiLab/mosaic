"""
Dialog functions used throughout the GUI.

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

from ..widgets import DialogFooter
from ..widgets.settings import create_setting_widget, get_widget_value, set_widget_value
from ..stylesheets import QPushButton_style, QScrollArea_style


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
        self.resize(600, 500)

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
        self.setStyleSheet(QPushButton_style + QScrollArea_style)

    def _setup_ui(self):
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
        self.mode_selector.currentTextChanged.connect(self._toggle_mode)
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

        # Create edge length widget (index 0)
        basic_layout.addWidget(self._create_labeled_widget(self._settings[0]), 0, 0)
        self._widgets["average_edge_length"].valueChanged.connect(self._update_bounds)

        # Add steps widget (index 3)
        basic_layout.addWidget(self._create_labeled_widget(self._settings[3]), 0, 1)

        # Add bounds widgets (indices 1, 2)
        basic_layout.addWidget(self._create_labeled_widget(self._settings[1]), 1, 0)
        basic_layout.addWidget(self._create_labeled_widget(self._settings[2]), 1, 1)

        content_layout.addWidget(basic_settings)

        # Advanced settings - Energy coefficients
        self.advanced_group = QGroupBox("Energy Coefficients")
        advanced_layout = QGridLayout(self.advanced_group)
        advanced_layout.setColumnStretch(0, 1)
        advanced_layout.setColumnStretch(1, 1)

        row, col = 0, 0
        for i in range(4, 10):
            advanced_layout.addWidget(
                self._create_labeled_widget(self._settings[i]), row, col
            )
            col = (col + 1) % 2
            if col == 0:
                row += 1

        content_layout.addWidget(self.advanced_group)

        # Constraints
        self.constraints_group = QGroupBox("Additional Constraints")
        constraints_layout = QGridLayout(self.constraints_group)

        for i in range(10, len(self._settings)):
            constraints_layout.addWidget(
                self._create_labeled_widget(self._settings[i]),
                (i - 10) // 2,
                (i - 10) % 2,
            )

        content_layout.addWidget(self.constraints_group)
        content_layout.addStretch()

        main_layout.addWidget(scroll_area)

        footer = DialogFooter(dialog=self, margin=(0, 15, 0, 0))
        main_layout.addWidget(footer)
        self._toggle_mode("Default")

    def _create_labeled_widget(self, setting):
        """Create a widget with label for a setting."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        label = QLabel(setting["label"])
        label.setToolTip(setting.get("description", ""))
        layout.addWidget(label)

        widget = create_setting_widget(setting)
        layout.addWidget(widget)

        self._widgets[setting["parameter"]] = widget
        return container

    def _toggle_mode(self, mode):
        """Toggle between Default and Advanced modes."""
        is_advanced = mode == "Advanced"
        self.advanced_group.setVisible(is_advanced)
        self.constraints_group.setVisible(is_advanced)

    def _update_bounds(self, value):
        """Update lower and upper bounds when edge length changes."""
        try:
            val = float(value)
            set_widget_value(self._widgets["lower_bound"], val * 0.75)
            set_widget_value(self._widgets["upper_bound"], val * 1.25)
        except (ValueError, KeyError):
            pass

    def get_parameters(self):
        """Get the current parameters."""
        return {
            param: get_widget_value(widget) for param, widget in self._widgets.items()
        }
