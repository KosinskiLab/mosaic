""" Dialog functions used throughout the GUI.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from PyQt6.QtCore import QLocale
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QDialog,
    QLabel,
    QDialogButtonBox,
    QSpinBox,
    QComboBox,
    QFormLayout,
    QCheckBox,
    QLineEdit,
)
from PyQt6.QtGui import QDoubleValidator


def format_tooltip(title, description, default_value=None, notes=None):
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
        self.label_widgets = {}
        self.is_hierarchical = isinstance(parameters, dict)

        self.setWindowTitle(self.operation_type)
        self.main_layout = QVBoxLayout(self)
        self.params_layout = QFormLayout()

        if self.is_hierarchical:
            self.type_selector = QComboBox()
            self.type_selector.addItems(list(self.parameters.keys()))
            self.type_selector.currentIndexChanged.connect(
                self.update_operation_options
            )
            self.params_layout.addRow("Option:", self.type_selector)

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
        while self.params_layout.rowCount() > (1 if self.is_hierarchical else 0):
            self.params_layout.removeRow(self.params_layout.rowCount() - 1)
        self.parameter_widgets.clear()
        self.label_widgets.clear()

        for param_info in parameters:
            label, value, min_value, tooltip_info = param_info
            tooltip = format_tooltip(**tooltip_info)
            label_widget = QLabel(f"{tooltip_info['title']}:")
            label_widget.setToolTip(tooltip)

            if isinstance(value, bool):
                widget = QCheckBox()
                widget.setChecked(value)
            elif isinstance(min_value, list):
                widget = QComboBox()
                widget.addItems(min_value)
                widget.setCurrentText(value)
            elif isinstance(value, float):
                widget = QLineEdit()
                if isinstance(min_value, float):
                    validator = QDoubleValidator()
                    validator.setLocale(QLocale.c())
                    validator.setNotation(QDoubleValidator.Notation.StandardNotation)
                    validator.setBottom(min_value)
                    widget.setValidator(validator)
                widget.setText(str(value))
            else:
                widget = QSpinBox()
                widget.setMinimum(int(min_value))
                widget.setMaximum(2147483647)
                widget.setValue(value)

            widget.setToolTip(tooltip)
            self.label_widgets[label] = label_widget
            self.parameter_widgets[label] = widget
            self.params_layout.addRow(label_widget, widget)

    def get_parameters(self):
        ret = {}
        for param_name, widget in self.parameter_widgets.items():
            if isinstance(widget, QCheckBox):
                ret[param_name] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                ret[param_name] = widget.currentText()
            elif isinstance(widget, QLineEdit):
                validator = widget.validator()
                if validator:
                    ret[param_name] = float(widget.text())
                else:
                    ret[param_name] = widget.text()
            else:
                ret[param_name] = widget.value()
        return ret


class ParameterHandler:
    def __init__(self, operation_dict, settings_button, selector):
        self.operation_dict = operation_dict
        self.settings_button = settings_button
        self.selector = selector
        self.parameters_store = {}

        self.update_button(self.selector.currentText())
        for op_type, params in self.operation_dict.items():
            if not params:
                continue
            self.parameters_store[op_type] = {x[0]: x[1] for x in params}

    def get(self, key, default=None):
        return self.parameters_store.get(key, default)

    def update_button(self, current_type):
        has_params = len(self.operation_dict[current_type]) > 0
        self.settings_button.setEnabled(has_params)

    def show_dialog(self):
        current_type = self.selector.currentText()
        params = []
        custom_parameters = self.parameters_store.get(current_type, {})

        for param in self.operation_dict[current_type].copy():
            default = custom_parameters.get(param[0], param[1])
            params.append(tuple(x if i != 1 else default for i, x in enumerate(param)))

        def _ident(**kwargs):
            return kwargs

        kwargs = show_parameter_dialog(
            current_type,
            params,
            self.settings_button.parent(),
            {current_type: _ident},
            self.settings_button,
        )

        if isinstance(kwargs, dict):
            self.parameters_store[current_type] = kwargs


def show_parameter_dialog(
    operation_type, parameters, obj, mapping={}, source_widget=None
):
    dialog = OperationDialog(operation_type, parameters, obj)
    if source_widget:
        pos = source_widget.mapToGlobal(source_widget.rect().bottomLeft())
        dialog.move(pos)

    if dialog.exec() == QDialog.DialogCode.Rejected:
        return -1

    params = dialog.get_parameters()
    if dialog.is_hierarchical:
        params["method"] = dialog.type_selector.currentText()

    func = mapping.get(operation_type)
    if func is None:
        print(f"{operation_type} is unknown - Supported are {mapping.keys()}.")
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
