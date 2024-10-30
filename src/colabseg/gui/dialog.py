from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QDialog,
    QLabel,
    QPushButton,
    QDialogButtonBox,
    QSpinBox,
    QDoubleSpinBox,
    QGridLayout,
    QComboBox,
)


class KeybindsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keybinds")

        layout = QVBoxLayout()

        keybinds = [
            ("z", "Set camera view along Z-axis"),
            ("x", "Set camera view along X-axis"),
            ("c", "Set camera view along Y-axis"),
            ("d", "Toggle renderer background color"),
            ("h", "Toggle visibility of selected clusters"),
            ("Delete", "Remove selected cluster or points"),
            ("R", "Bring up point selector"),
            ("Right Mouse", "Deselect cluster or points"),
            ("Left Mouse Drag", "Rotate scene"),
            ("Shift Left Mouse Drag", "Translate scene"),
            ("Ctrl+O", "Open file"),
            ("Ctrl+S", "Save file"),
            ("Ctrl+H", "Show this keybinds popup"),
        ]

        for key, description in keybinds:
            key_label = QLabel(f"<b>{key}</b>: {description}")
            layout.addWidget(key_label)

        close_button = QPushButton("Close")
        close_button.setFixedSize(100, 30)
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setLayout(layout)

    def show_keybinds(parent):
        dialog = KeybindsDialog(parent)
        dialog.setStyleSheet(
            """
            QDialog {
                background-color: #f0f0f0;
            }
            QLabel {
                color: #333333;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 5px 10px;
                text-align: center;
                text-decoration: none;
                font-size: 14px;
                margin: 4px 2px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """
        )
        dialog.exec()


def format_tooltip(title, description, default_value=None, notes=None):
    """Create a formatted HTML tooltip with consistent styling."""
    tooltip = f"""
    <div style='font-family: Arial, sans-serif;'>
        <b style='color: #2c3e50; font-size: 11pt;'>{title}</b>
        <p style='margin: 5px 0; color: #34495e;'>{description}</p>
    """

    if default_value is not None:
        tooltip += f"""
        <p style='margin: 5px 0;'>
            <span style='color: #7f8c8d;'>Default:</span>
            <span style='color: #2980b9;'>{default_value}</span>
        </p>
        """

    if notes:
        tooltip += f"""
        <p style='margin: 5px 0; font-style: italic; color: #95a5a6;'>
            Note: {notes}
        </p>
        """

    tooltip += "</div>"
    return tooltip


class OperationDialog(QDialog):
    def __init__(self, operation_type, parameters, parent=None):
        super().__init__(parent)
        self.operation_type = operation_type
        self.parameters = parameters
        self.parameter_widgets = {}
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle(self.operation_type)
        layout = QVBoxLayout(self)

        params_layout = QGridLayout()
        for row, param_info in enumerate(self.parameters):
            label, value, min_value, tooltip_info = param_info
            tooltip = format_tooltip(**tooltip_info)

            label_widget = QLabel(f"{tooltip_info['title']}:")
            label_widget.setToolTip(tooltip)
            params_layout.addWidget(label_widget, row, 0)

            if isinstance(value, list):
                widget = QComboBox()
                widget.addItems(value)
                widget.setCurrentText(value[0])
            elif isinstance(value, float):
                widget = QDoubleSpinBox()
                widget.setMinimum(min_value)
                widget.setMaximum(float("inf"))
                widget.setDecimals(4)
                widget.setValue(value)
            else:
                widget = QSpinBox()
                widget.setMinimum(min_value)
                widget.setMaximum(2147483647)
                widget.setValue(value)

            widget.setToolTip(tooltip)
            self.parameter_widgets[label] = widget
            params_layout.addWidget(widget, row, 1)

        layout.addLayout(params_layout)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
