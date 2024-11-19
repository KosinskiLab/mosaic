from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QDialog,
    QLabel,
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
            ("a", "Toggle draawing mode"),
            ("d", "Toggle renderer background color"),
            ("h", "Toggle visibility of selected clusters"),
            ("m", "Merge selected cluster or points"),
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

        close_button = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        close_button.accepted.connect(self.accept)
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

        self.is_hierarchical = isinstance(parameters, dict)

        self.setWindowTitle(self.operation_type)

        self.main_layout = QVBoxLayout(self)
        self.params_layout = QGridLayout()

        if self.is_hierarchical:
            label = QLabel("Method:")
            self.type_selector = QComboBox()
            self.type_selector.addItems(list(self.parameters.keys()))
            self.type_selector.currentIndexChanged.connect(
                self.update_operation_options
            )
            self.params_layout.addWidget(label, 0, 0)
            self.params_layout.addWidget(self.type_selector, 0, 1)

        self.main_layout.addLayout(self.params_layout)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.main_layout.addWidget(button_box)

        if self.is_hierarchical:
            return self.update_operation_options(0)
        return self.update_parameters(self.parameters)

    def update_operation_options(self, index):
        current_type = list(self.parameters.keys())[index]
        self.update_parameters(self.parameters[current_type])

    def update_parameters(self, parameters):
        for i in reversed(range(self.params_layout.count())):
            widget = self.params_layout.itemAt(i).widget()
            if widget is not None:
                widget.deleteLater()

        self.parameter_widgets.clear()
        for row, param_info in enumerate(parameters):
            row_index = row + int(self.is_hierarchical)

            label, value, min_value, tooltip_info = param_info
            tooltip = format_tooltip(**tooltip_info)

            label_widget = QLabel(f"{tooltip_info['title']}:")
            label_widget.setToolTip(tooltip)
            self.params_layout.addWidget(label_widget, row_index, 0)

            if isinstance(min_value, list):
                widget = QComboBox()
                widget.addItems(min_value)
                widget.setCurrentText(value)
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
            self.params_layout.addWidget(widget, row_index, 1)


def show_parameter_dialog(operation_type, parameters, obj, operation_mapping):
    dialog = OperationDialog(operation_type, parameters, obj)

    if dialog.exec() == QDialog.DialogCode.Rejected:
        return -1

    params = {
        label: (
            widget.currentText() if isinstance(widget, QComboBox) else widget.value()
        )
        for label, widget in dialog.parameter_widgets.items()
    }
    if dialog.is_hierarchical:
        params["method"] = dialog.type_selector.currentText()

    func = operation_mapping.get(operation_type)
    if func is None:
        print(
            f"{operation_type} is unknown - Supported are {operation_mapping.keys()}."
        )
    return func(**params)


def make_param(param, default, min_val=0, description=None, notes=None):
    return (
        param,
        default,
        min_val,
        {
            "title": param.lower().replace("_", " ").capitalize(),
            "description": description or param,
            "default_value": str(default),
            "notes": notes if notes else None,
        },
    )
