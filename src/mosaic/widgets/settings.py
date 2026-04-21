from typing import Dict

from qtpy.QtCore import QLocale
from qtpy.QtGui import QDoubleValidator
from qtpy.QtWidgets import (
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QCheckBox,
    QFormLayout,
    QLineEdit,
)

from ..stylesheets import Colors, Typography

__all__ = [
    "format_tooltip",
    "create_setting_widget",
    "get_widget_value",
    "set_widget_value",
    "get_layout_widget_value",
]


def format_tooltip(description=None, default=None, notes=None, **kwargs):
    if description is None and default is None and notes is None:
        return ""

    lines = []
    if description is not None:
        lines.append(
            f"<span style='font-size: {Typography.SMALL}px;'>{description}</span>"
        )
    if default is not None and lines:
        lines.append(
            f"<br><br><span style='font-size: {Typography.CAPTION}px;'>Default: </span>"
            f"<span style='font-size: {Typography.CAPTION}px; color: {Colors.PRIMARY};'>{default}</span>"
        )
    if notes:
        sep = "<br><br>" if lines else ""
        lines.append(
            f"{sep}<span style='font-size: {Typography.CAPTION}px;'>Note: {notes}</span>"
        )
    return "".join(lines)


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
        if setting.get("min", 0.0) < 0:
            widget.setSpecialValueText(setting.get("special_text", "Auto"))
    elif setting["type"] == "select":
        widget = QComboBox()
        option_values = setting.get("option_values")
        if option_values is not None:
            for text, value in zip(setting["options"], option_values):
                widget.addItem(text, userData=value)
        else:
            widget.addItems(setting["options"])
        if "default" in setting:
            set_widget_value(widget, setting["default"])
    elif setting["type"] == "PathSelector":
        from . import PathSelector

        mode = setting.get("mode", "file")
        if "file_mode" in setting and "mode" not in setting:
            mode = "file" if setting["file_mode"] else "directory"
        widget = PathSelector(
            placeholder=setting.get("placeholder", None),
            mode=mode,
        )
        if "default" in setting:
            set_widget_value(widget, setting["default"])
        widget.setMinimumWidth(200)

    elif setting["type"] == "boolean":
        widget = QCheckBox()
        set_widget_value(widget, setting.get("default", False))
        widget.setMinimumHeight(Colors.WIDGET_HEIGHT)
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
        data = widget.currentData()
        if data is not None:
            return data
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
        # Try matching by item data first (e.g. UUID-backed combo boxes)
        for i in range(widget.count()):
            if widget.itemData(i) == value:
                widget.setCurrentIndex(i)
                return
        widget.setCurrentText(str(value))
    elif isinstance(widget, QCheckBox):
        widget.setChecked(bool(value))
    elif isinstance(widget, QLineEdit):
        if widget.property("setting_type") == "float_list":
            if isinstance(value, (list, tuple)):
                value = ",".join([str(x) for x in value])
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
