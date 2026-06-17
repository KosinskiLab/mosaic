from typing import Dict

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
    if setting["type"] in ("number", "float"):

        widget = QSpinBox()
        wrange = int(setting.get("min", 0)), int(setting.get("max", 1 << 30))
        if setting["type"] == "float":
            widget = QDoubleSpinBox()
            widget.setDecimals(setting.get("decimals", 6))
            wrange = setting.get("min", 0.0), setting.get("max", 1e32)
            widget.setSingleStep(setting.get("step", 1.0))

        default_value = setting.get("default")
        if default_value is None:
            # Reserve a sentinel slot one step below `min` for the
            # special-value marker. Without it the declared minimum
            # collides with the "Auto" slot and gets read back as None,
            # so e.g. typing 0 into a min=0 field silently means "unset".
            marker = setting.get("special_text", "Auto")
            widget.setRange(wrange[0] - widget.singleStep(), wrange[1])
            widget.setSpecialValueText(marker)
            widget.setProperty("none_marker", marker)
            widget.setValue(widget.minimum())
        else:
            widget.setRange(*wrange)
            widget.setValue(default_value)

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
            placeholder=setting.get("description", None),
            mode=mode,
        )
        if "default" in setting:
            set_widget_value(widget, setting["default"])
        widget.setMinimumWidth(200)

    elif setting["type"] == "boolean":
        widget = QCheckBox()
        set_widget_value(widget, setting.get("default", False))
        widget.setMinimumHeight(Colors.WIDGET_HEIGHT)

    elif setting["type"] == "text":
        widget = QLineEdit()
        default_value = setting.get("default", None)

        is_numeric = (
            default_value is not None and not isinstance(default_value, str)
        ) or ("min" in setting or "max" in setting)
        if is_numeric:
            validator = QDoubleValidator()
            validator.setNotation(QDoubleValidator.Notation.StandardNotation)
            validator.setBottom(float(setting.get("min", 0.0)))
            widget.setValidator(validator)

        text = "" if default_value is None else str(default_value)
        if default_value is None and (marker := setting.get("special_text")):
            text = str(marker)
            widget.setProperty("none_marker", text)
        set_widget_value(widget, text)
        widget.setMinimumWidth(100)
    else:
        raise ValueError(f"Could not create widget from {setting}.")

    widget.setFixedHeight(Colors.WIDGET_HEIGHT)
    widget.setToolTip(format_tooltip(**setting))
    widget.setProperty("parameter", setting.get("parameter", None))
    return widget


def get_widget_value(widget):
    from .path_selector import PathSelector

    if isinstance(widget, QSpinBox) or isinstance(widget, QDoubleSpinBox):
        marker = widget.property("none_marker")
        if marker and widget.text() == marker:
            return None
        return widget.value()
    elif isinstance(widget, QComboBox):
        data = widget.currentData()
        if data is not None:
            return data
        return widget.currentText()
    elif isinstance(widget, QCheckBox):
        return widget.isChecked()
    elif isinstance(widget, QLineEdit):
        value = widget.text().strip()
        marker = widget.property("none_marker")
        if not value or (marker and value == marker):
            return None
        validator = widget.validator()
        if validator:
            return float(value)
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
        if value is None:
            widget.setText(widget.property("none_marker") or "")
        else:
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
