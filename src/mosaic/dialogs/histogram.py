from qtpy.QtWidgets import QDialog, QVBoxLayout

from ..widgets import HistogramWidget


class HistogramDialog(QDialog):
    def __init__(self, cdata, parent=None):
        super().__init__(parent)
        self.cdata = cdata

        self.setWindowTitle("Select Clusters by Size")

        layout = QVBoxLayout(self)
        self._histogram_widget = HistogramWidget()
        layout.addWidget(self._histogram_widget)

        self.cdata.data.data_changed.connect(self.update_histogram)
        self.histogram_widget.cutoff_changed.connect(self._on_cutoff_changed)
        self.update_histogram()

    def update_histogram(self, data=None):
        if data is None:
            data = self.cdata._data.get_cluster_size()
        self.histogram_widget.update_histogram(data)

    def _on_cutoff_changed(self, lower_cutoff, upper_cutoff=None):
        cluster_sizes = self.cdata._data.get_cluster_size()
        if upper_cutoff is None:
            upper_cutoff = max(cluster_sizes) + 1

        indices = []
        for i in range(len(self.cdata._data)):
            if (cluster_sizes[i] > lower_cutoff) & (cluster_sizes[i] < upper_cutoff):
                indices.append(i)
        self.cdata.data.set_selection(indices)

    @property
    def histogram_widget(self):
        return self._histogram_widget

    def closeEvent(self, event):
        """Disconnect when dialog closes"""
        try:
            self.cdata.data.data_changed.disconnect(self.update_histogram)
            self.histogram_widget.cutoff_changed.disconnect(self._on_cutoff_changed)
        except (TypeError, RuntimeError):
            pass  # Already disconnected
        super().closeEvent(event)
