from qtpy.QtWidgets import QDialog, QVBoxLayout

from ..widgets import HistogramWidget


class HistogramDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Clusters by Size")
        self.resize(800, 500)

        layout = QVBoxLayout(self)
        self._histogram_widget = HistogramWidget()
        layout.addWidget(self._histogram_widget)

    def update_histogram(self, data):
        self.histogram_widget.update_histogram(data)

    @property
    def histogram_widget(self):
        return self._histogram_widget
