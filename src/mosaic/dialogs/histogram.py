"""
Histogram dialog for cluster size filtering.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np
import pyqtgraph as pg
from qtpy.QtGui import QColor, QDoubleValidator
from qtpy.QtCore import Qt, Signal, QLocale, QSize
from qtpy.QtWidgets import (
    QWidget,
    QDialog,
    QVBoxLayout,
    QLineEdit,
    QLabel,
    QSpinBox,
    QSizePolicy,
    QComboBox,
    QGridLayout,
    QGroupBox,
)

from ..widgets.sliders import DualHandleSlider


class HistogramWidget(QWidget):
    cutoff_changed = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.data = []
        self.min_value = 0
        self.max_value = 1
        self.bin_count = 20

        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        self.histogram_plot = pg.PlotWidget()
        self.histogram_plot.setBackground(None)
        self.histogram_plot.getAxis("left").setPen(pg.mkPen(color=(0, 0, 0)))
        self.histogram_plot.getAxis("bottom").setPen(pg.mkPen(color=(0, 0, 0)))
        self.histogram_plot.setLabel("left", "Count")
        self.histogram_plot.setLabel("bottom", "Cluster Size")
        self.histogram_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Visual reference but no longer moveable since v1.0.16
        self.lower_cutoff_line = pg.InfiniteLine(
            angle=90,
            movable=False,
            pen=pg.mkPen(QColor(70, 130, 180), width=2, style=Qt.PenStyle.DashLine),
        )
        self.upper_cutoff_line = pg.InfiniteLine(
            angle=90,
            movable=False,
            pen=pg.mkPen(QColor(220, 70, 70), width=2, style=Qt.PenStyle.DashLine),
        )
        self.histogram_plot.addItem(self.lower_cutoff_line)
        self.histogram_plot.addItem(self.upper_cutoff_line)

        controls_layout = self._create_controls()

        self.range_slider = DualHandleSlider()
        self.range_slider.rangeChanged.connect(self._update_cutoff_values)
        self.range_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        main_layout.addWidget(self.histogram_plot)
        main_layout.addLayout(controls_layout)
        main_layout.addWidget(self.range_slider)

    def _create_controls(self):
        """Create all control widgets and layouts"""
        controls_layout = QGridLayout()
        controls_layout.setSpacing(8)
        controls_layout.setContentsMargins(0, 0, 0, 0)

        self.min_value_input = QLineEdit()
        self.max_value_input = QLineEdit()
        self.transform_combo = QComboBox()
        self.bin_count_spinner = QSpinBox()

        widget_width = 80
        for widget in [
            self.min_value_input,
            self.max_value_input,
            self.transform_combo,
            self.bin_count_spinner,
        ]:
            widget.setMinimumWidth(widget_width)

        validator = QDoubleValidator()
        validator.setLocale(QLocale.c())
        self.min_value_input.setValidator(validator)
        self.max_value_input.setValidator(validator)

        self.transform_combo.addItems(["Linear", "Log"])
        self.transform_combo.currentTextChanged.connect(self._draw_histogram)

        self.bin_count_spinner.setRange(5, 100)
        self.bin_count_spinner.setValue(self.bin_count)
        self.bin_count_spinner.valueChanged.connect(self._on_bin_count_changed)

        self.min_value_input.editingFinished.connect(
            lambda: self._handle_input_change(is_lower=True)
        )
        self.max_value_input.editingFinished.connect(
            lambda: self._handle_input_change(is_lower=False)
        )

        controls_layout.addWidget(QLabel("Scale:"), 0, 0, Qt.AlignmentFlag.AlignRight)
        controls_layout.addWidget(self.transform_combo, 0, 1)
        controls_layout.addWidget(QLabel("Bins:"), 0, 3, Qt.AlignmentFlag.AlignRight)
        controls_layout.addWidget(self.bin_count_spinner, 0, 4)

        controls_layout.addWidget(QLabel("Min:"), 1, 0, Qt.AlignmentFlag.AlignRight)
        controls_layout.addWidget(self.min_value_input, 1, 1)
        controls_layout.addWidget(QLabel("Max:"), 1, 3, Qt.AlignmentFlag.AlignRight)
        controls_layout.addWidget(self.max_value_input, 1, 4)

        return controls_layout

    def update_histogram(self, data):
        """Update the histogram with new data"""
        self.data = np.asarray(data)

        if self.data.size == 0:
            try:
                return self.plot_widget.clear()
            except Exception:
                return None
        return self._draw_histogram()

    def _invert_scaling(self, value):
        if self.transform_combo.currentText().lower() == "log":
            return 10**value
        return value

    def _draw_histogram(self):
        self.histogram_plot.clear()

        data = self.data
        log_scale = self.transform_combo.currentText().lower() == "log"
        if log_scale:
            data = np.log10(self.data[self.data > 0])

        if data.size == 0:
            return None

        self.min_value = data.min() * 0.999
        self.max_value = data.max() * 1.001

        self._update_cutoff_values()
        y, x = np.histogram(data, bins=self.bin_count)

        bin_centers = (x[:-1] + x[1:]) / 2
        bar_graph = pg.BarGraphItem(
            x=bin_centers,
            height=y,
            width=(x[1] - x[0]) * 0.8,
            brush=QColor(148, 163, 184),
        )
        self.histogram_plot.addItem(bar_graph)

        self.histogram_plot.addItem(self.lower_cutoff_line)
        self.histogram_plot.addItem(self.upper_cutoff_line)

        label = "Cluster Size" + (" (log scale)" if log_scale else "")
        self.histogram_plot.setLabel("bottom", label)

    def _update_cutoff_values(self, lower_value=None, upper_value=None):
        """Update cutoff values and propagate changes to UI elements."""

        if lower_value is None:
            lower_value = self.range_slider.lower_pos
            if self.range_slider.min_val != self.min_value:
                lower_value = self.min_value

        if upper_value is None:
            upper_value = self.range_slider.upper_pos
            if self.range_slider.max_val != self.max_value:
                upper_value = self.max_value

        if lower_value > upper_value:
            lower_value, upper_value = upper_value, lower_value

        lower_value = max(lower_value, self.min_value)
        upper_value = min(upper_value, self.max_value)

        block = [self.range_slider, self.min_value_input, self.max_value_input]
        for element in block:
            element.blockSignals(True)

        self.range_slider.setRange(self.min_value, self.max_value)
        self.range_slider.setValues(lower_value, upper_value)

        self.lower_cutoff_line.setValue(lower_value)
        self.upper_cutoff_line.setValue(upper_value)

        locale = QLocale.c()
        self.min_value_input.setText(locale.toString(float(lower_value), "f", 2))
        self.max_value_input.setText(locale.toString(float(upper_value), "f", 2))

        for element in block:
            element.blockSignals(False)

        self.cutoff_changed.emit(
            self._invert_scaling(lower_value), self._invert_scaling(upper_value)
        )

    def _handle_input_change(self, is_lower):
        """Handle changes to either min/max input field."""
        try:
            input_field = self.min_value_input if is_lower else self.max_value_input
            locale = QLocale.c()
            value = locale.toDouble(input_field.text())[0]

            if is_lower:
                return self._update_cutoff_values(lower_value=value)
            return self._update_cutoff_values(upper_value=value)

        except (ValueError, AttributeError):
            line = self.lower_cutoff_line if is_lower else self.upper_cutoff_line
            input_field.setText(str(int(line.value())))

    def _on_bin_count_changed(self, value):
        """Update the number of bins used in the histogram"""
        self.bin_count = value
        self._draw_histogram()


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

    def sizeHint(self):
        return QSize(350, 350)

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
            if (n_points >= lower_cutoff) & (n_points <= upper_cutoff):
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
