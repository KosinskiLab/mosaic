from qtpy.QtWidgets import QDialog, QVBoxLayout, QGroupBox

from ..widgets import HistogramWidget


class HistogramDialog(QDialog):
    def __init__(self, cdata, parent=None):
        super().__init__(parent)
        self.cdata = cdata

        layout = QVBoxLayout(self)
        group = QGroupBox("Select")
        group_layout = QVBoxLayout(group)

        self.histogram_widget = HistogramWidget()
        group_layout.addWidget(self.histogram_widget)
        layout.addWidget(group)

        self.cdata.data.render_update.connect(self.update_histogram)
        self.histogram_widget.cutoff_changed.connect(self._on_cutoff_changed)
        self.update_histogram()

    def get_cluster_size(self):
        return [x.get_number_of_points() for x in self.cdata._data.data]

    def update_histogram(self, data=None):
        self.histogram_widget.update_histogram(self.get_cluster_size())

    def _on_cutoff_changed(self, lower_cutoff, upper_cutoff=None):
        cluster_sizes = self.get_cluster_size()
        if upper_cutoff is None:
            upper_cutoff = max(cluster_sizes) + 1

        uuids = []
        for geometry in self.cdata._data.data:
            n_points = geometry.get_number_of_points()
            if (n_points > lower_cutoff) & (n_points < upper_cutoff):
                uuids.append(geometry.uuid)
        self.cdata.data.set_selection_by_uuid(uuids)

    def closeEvent(self, event):
        """Disconnect when dialog closes"""
        try:
            self.cdata.data.render_update.disconnect(self.update_histogram)
            self.histogram_widget.cutoff_changed.disconnect(self._on_cutoff_changed)
        except (TypeError, RuntimeError):
            pass  # Already disconnected
        super().closeEvent(event)
