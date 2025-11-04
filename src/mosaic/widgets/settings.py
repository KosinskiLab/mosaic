from typing import Dict

import numpy as np
from qtpy.QtCore import Qt, QLocale
from qtpy.QtGui import QDoubleValidator
from qtpy.QtWidgets import (
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QCheckBox,
    QFormLayout,
    QLineEdit,
)


def format_tooltip(label=None, description="", default=None, notes=None, **kwargs):
    if label is None:
        return ""

    label = str(label).title().replace("_", " ")
    tooltip = f"""
    <div class="tooltip">
        <span style='font-size: 11pt; font-weight: 600; color: #2c3e50;'>{label}</span>
        <p style='margin: 6px 0; color: #34495e;'>{description}</p>
    """
    if default is not None:
        tooltip += f"""
        <p style='margin: 6px 0;'>
            <span style='color: #6b7280;'>Default:</span>
            <span style='color: rgba(99, 102, 241, 1.0);'>{default}</span>
        </p>
        """

    if notes:
        tooltip += f"""
        <p style='margin: 6px 0; color: #95a5a6; font-style: italic;'>
            Note: {notes}
        </p>
        """
    tooltip += "</div>"
    return tooltip


def create_setting_widget(setting: Dict):
    if setting["type"] == "number":
        widget = QSpinBox()
        widget.setRange(int(setting.get("min", 0)), int(setting.get("max", 1 << 30)))
        set_widget_value(widget, setting.get("default", 0))
    elif setting["type"] == "float":
        widget = QDoubleSpinBox()
        widget.setDecimals(setting.get("decimals", 4))
        widget.setRange(setting.get("min", 0.0), setting.get("max", 1e32))
        set_widget_value(widget, setting.get("default", 0.0))
        widget.setSingleStep(setting.get("step", 1.0))
    elif setting["type"] == "slider":
        from .input_slider import SliderWithInput

        widget = SliderWithInput(Qt.Orientation.Horizontal)
        widget.setRange(int(setting.get("min", 0)), int(setting.get("max", 1)))
        set_widget_value(widget, int(setting.get("default", 0)))
    elif setting["type"] == "select":
        widget = QComboBox()
        widget.addItems(setting["options"])
        if "default" in setting:
            set_widget_value(widget, setting["default"])
    elif setting["type"] == "MappedComboBox":
        from . import MappedComboBox

        widget = MappedComboBox(choices=setting["choices"])
        if "default" in setting:
            set_widget_value(widget, setting["default"])
    elif setting["type"] == "PathSelector":
        from . import PathSelector

        widget = PathSelector()
        if "default" in setting:
            set_widget_value(widget, setting["default"])
        widget.setMinimumWidth(200)

    elif setting["type"] == "boolean":
        widget = QCheckBox()
        set_widget_value(widget, setting.get("default", False))
        widget.setMinimumHeight(25)
    elif setting["type"] in ("text", "float_list"):
        widget = QLineEdit()
        default_value = setting.get("default", None)

        widget.setProperty("setting_type", setting["type"])
        if not isinstance(default_value, str) and setting["type"] != "float_list":
            validator = QDoubleValidator()
            validator.setLocale(QLocale.c())
            validator.setNotation(QDoubleValidator.Notation.StandardNotation)
            validator.setBottom(float(setting.get("min", 0.0)))
            widget.setValidator(validator)
        set_widget_value(widget, str(setting.get("default", 0)))
        widget.setMinimumWidth(100)
    else:
        raise ValueError(f"Could not create widget from {setting}.")

    widget.setToolTip(format_tooltip(**setting))
    widget.setProperty("parameter", setting.get("parameter", None))
    return widget


def get_widget_value(widget):
    from .path_selector import PathSelector

    if isinstance(widget, QSpinBox) or isinstance(widget, QDoubleSpinBox):
        return widget.value()
    elif isinstance(widget, QComboBox):
        return widget.currentText()
    elif isinstance(widget, QCheckBox):
        return widget.isChecked()
    elif isinstance(widget, QLineEdit):
        validator = widget.validator()
        value = widget.text().strip()
        if validator:
            return float(value.replace(",", "."))
        if widget.property("setting_type") == "float_list":
            return [float(x.strip().replace(",", ".")) for x in value.split(";")]
        return value
    elif isinstance(widget, PathSelector):
        return widget.get_path()

    try:
        return widget.value()
    except Exception:
        return None


def set_widget_value(widget, value):
    from .path_selector import PathSelector

    if isinstance(widget, QSpinBox) or isinstance(widget, QDoubleSpinBox):
        widget.setValue(value)
    elif isinstance(widget, QComboBox):
        widget.setCurrentText(str(value))
    elif isinstance(widget, QCheckBox):
        widget.setChecked(bool(value))
    elif isinstance(widget, QLineEdit):
        widget.setText(str(value))
    elif isinstance(widget, PathSelector):
        widget.set_path(value)
    else:
        try:
            widget.setValue(value)
        except Exception:
            pass


def get_layout_widget_value(layout):
    ret = {}
    for i in range(layout.rowCount()):
        field_item = layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
        if not (field_item and field_item.widget()):
            continue

        widget = field_item.widget()
        parameter = widget.property("parameter")
        if parameter is None:
            continue
        ret[parameter] = get_widget_value(widget)
    return ret
