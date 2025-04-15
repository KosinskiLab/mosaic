from qtpy.QtWidgets import QWidget, QSlider, QDoubleSpinBox, QVBoxLayout
from qtpy.QtCore import Qt, Signal


class SliderWithInput(QWidget):
    valueChanged = Signal(int)

    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(parent)
        self.initUI(orientation)

    def initUI(self, orientation):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.slider = QSlider(orientation)
        self.spinbox = QDoubleSpinBox()
        self.spinbox.setRange(0, 100)
        self.spinbox.setDecimals(4)
        self.spinbox.setSingleStep(0.01)

        self.slider.valueChanged.connect(self.valueChanged.emit)

        self.slider.valueChanged.connect(
            lambda: self.spinbox.setValue(self._value_to_quantile(self.slider.value()))
        )
        self.spinbox.valueChanged.connect(
            lambda: self.slider.setValue(self._quantile_to_value(self.spinbox.value()))
        )

        main_layout.addWidget(self.slider)
        main_layout.addWidget(self.spinbox)

        self.setLayout(main_layout)

    def _quantile_to_value(self, value) -> int:
        return int(value * (self.maximum() - self.minimum()) / 100 + self.minimum())

    def _value_to_quantile(self, value) -> float:
        return 100 * (value - self.minimum()) / (self.maximum() - self.minimum())

    def setRange(self, minimum, maximum):
        self.slider.setRange(minimum, maximum)

    def setValue(self, value):
        self.slider.setValue(value)

    def value(self):
        return self.slider.value()

    def setOrientation(self, orientation):
        self.slider.setOrientation(orientation)

    def minimum(self):
        return self.slider.minimum()

    def maximum(self):
        return self.slider.maximum()
