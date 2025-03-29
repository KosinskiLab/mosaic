from qtpy.QtCore import Signal
from qtpy.QtWidgets import (
    QVBoxLayout,
    QLabel,
    QDoubleSpinBox,
    QSpinBox,
    QWidget,
)

from ..stylesheets import HelpLabel_style


class ParameterWidget(QWidget):
    """A widget that displays a parameter with a label and input field."""

    valueChanged = Signal(str, object)

    def __init__(
        self, param_name, param_value, param_min, param_description, parent=None
    ):
        super().__init__(parent)
        self.param_name = param_name

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Label with description tooltip
        label = QLabel(param_description.get("title", param_name))
        label.setToolTip(param_description.get("description", ""))
        layout.addWidget(label)

        # Help text
        if "description" in param_description:
            help_label = QLabel(param_description["description"])
            help_label.setStyleSheet(HelpLabel_style)
            help_label.setWordWrap(True)
            layout.addWidget(help_label)

        # Input field based on type
        if isinstance(param_value, float):
            self.input = QDoubleSpinBox()
            self.input.setDecimals(2)
            self.input.setRange(param_min, 1e10)
            self.input.setValue(param_value)
            self.input.setSingleStep(1.0 if param_value > 10 else 0.1)
            self.input.valueChanged.connect(
                lambda value: self.valueChanged.emit(param_name, value)
            )
        elif isinstance(param_value, int):
            self.input = QSpinBox()
            self.input.setRange(param_min, 1000000)
            self.input.setValue(param_value)
            self.input.valueChanged.connect(
                lambda value: self.valueChanged.emit(param_name, value)
            )
        else:
            self.input = QLabel(str(param_value))

        layout.addWidget(self.input)

    def getValue(self):
        if isinstance(self.input, (QDoubleSpinBox, QSpinBox)):
            return self.input.value()
        return None

    def setValue(self, value):
        if isinstance(self.input, (QDoubleSpinBox, QSpinBox)):
            self.input.setValue(value)

    def setVisible(self, visible):
        super().setVisible(visible)
        self.input.setVisible(visible)
