""" Variety of widgets used throughout the GUI.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np
import pyqtgraph as pg
from qtpy.QtCore import Qt, Signal, QLocale
from qtpy.QtGui import QColor, QDoubleValidator
from qtpy.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QSlider,
    QLineEdit,
    QLabel,
    QSpinBox,
    QSizePolicy,
    QComboBox,
)


class RangeSlider(QWidget):
    """A custom slider that allows selecting a range with two handles."""

    rangeChanged = Signal(float, float)

    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(parent)
        self.orientation = orientation
        self.lower_value = 0
        self.upper_value = 100

        layout = (
            QHBoxLayout() if orientation == Qt.Orientation.Horizontal else QVBoxLayout()
        )
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.lower_slider = QSlider(orientation)
        self.upper_slider = QSlider(orientation)
        for slider, value, callback in [
            (self.lower_slider, 0, self._lower_slider_changed),
            (self.upper_slider, 100, self._upper_slider_changed),
        ]:
            slider.setRange(0, 100)
            slider.setValue(value)
            slider.valueChanged.connect(callback)
            layout.addWidget(slider)

    def _lower_slider_changed(self, value):
        if value > self.upper_slider.value():
            self.lower_slider.setValue(self.upper_slider.value())
            return

        self.lower_value = value
        self.rangeChanged.emit(self.lower_value, self.upper_value)

    def _upper_slider_changed(self, value):
        if value < self.lower_slider.value():
            self.upper_slider.setValue(self.lower_slider.value())
            return

        self.upper_value = value
        self.rangeChanged.emit(self.lower_value, self.upper_value)

    def setRange(self, minimum, maximum):
        self.lower_slider.setRange(minimum, maximum)
        self.upper_slider.setRange(minimum, maximum)

    def setValues(self, lower, upper):
        # Block signals to avoid triggering callbacks
        for slider, value in [(self.lower_slider, lower), (self.upper_slider, upper)]:
            slider.blockSignals(True)
            slider.setValue(value)
            slider.blockSignals(False)

        self.lower_value = lower
        self.upper_value = upper


class HistogramWidget(QWidget):
    cutoff_changed = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.data = []
        self.min_value = 0
        self.max_value = 1
        self.bin_count = 20

        self.setup_ui()
        self.resize(800, 400)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)

        self.histogram_plot = pg.PlotWidget()
        self.histogram_plot.setBackground(None)
        self.histogram_plot.getAxis("left").setPen(pg.mkPen(color=(0, 0, 0)))
        self.histogram_plot.getAxis("bottom").setPen(pg.mkPen(color=(0, 0, 0)))
        self.histogram_plot.setLabel("left", "Count")
        self.histogram_plot.setLabel("bottom", "Cluster Size")
        self.histogram_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        controls_layout = self._create_controls()
        self.lower_cutoff_line, self.upper_cutoff_line = self._create_cutoff_lines()

        self.range_slider = RangeSlider(Qt.Orientation.Horizontal)
        self.range_slider.rangeChanged.connect(self._on_slider_range_changed)
        self.range_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.range_slider.setMinimumHeight(30)

        main_layout.addWidget(self.histogram_plot)
        main_layout.addLayout(controls_layout)
        main_layout.addWidget(self.range_slider)

    def _create_cutoff_lines(self):
        line_configs = [
            {
                "color": QColor(70, 130, 180),
                "callback": lambda: self._handle_cutoff_drag(is_lower=True),
            },
            {
                "color": QColor(220, 70, 70),
                "callback": lambda: self._handle_cutoff_drag(is_lower=False),
            },
        ]

        lines = []
        for config in line_configs:
            line = pg.InfiniteLine(
                angle=90,
                movable=True,
                pen=pg.mkPen(config["color"], width=2, style=Qt.PenStyle.DotLine),
            )
            line.sigDragged.connect(config["callback"])
            self.histogram_plot.addItem(line)
            lines.append(line)

        return lines

    def _create_controls(self):
        """Create all control widgets and layouts"""
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)

        cutoff_layout = QHBoxLayout()
        cutoff_layout.setSpacing(10)
        self.min_value_input = QLineEdit()
        self.max_value_input = QLineEdit()

        # Configure both inputs
        for widget, label_text, callback in [
            (
                self.min_value_input,
                "Min Value:",
                lambda: self._handle_input_change(is_lower=True),
            ),
            (
                self.max_value_input,
                "Max Value:",
                lambda: self._handle_input_change(is_lower=False),
            ),
        ]:
            label = QLabel(label_text)
            widget.setValidator(QDoubleValidator())
            widget.setMinimumWidth(80)
            widget.editingFinished.connect(callback)

            cutoff_layout.addWidget(label)
            cutoff_layout.addWidget(widget)

        # Transform controls
        transform_layout = QHBoxLayout()
        transform_layout.setSpacing(6)

        transform_label = QLabel("Transform:")
        self.transform_combo = QComboBox()
        self.transform_combo.addItems(["Linear", "Log"])
        self.transform_combo.setMinimumWidth(100)
        self.transform_combo.currentTextChanged.connect(self._draw_histogram)

        transform_layout.addWidget(transform_label)
        transform_layout.addWidget(self.transform_combo)

        # Bin size controls
        bin_layout = QHBoxLayout()
        bin_layout.setSpacing(6)

        bin_label = QLabel("Bins:")
        self.bin_count_spinner = QSpinBox()
        self.bin_count_spinner.setRange(5, 100)
        self.bin_count_spinner.setValue(self.bin_count)
        self.bin_count_spinner.setMinimumWidth(60)
        self.bin_count_spinner.valueChanged.connect(self._on_bin_count_changed)

        bin_layout.addWidget(bin_label)
        bin_layout.addWidget(self.bin_count_spinner)

        controls_layout.addLayout(cutoff_layout)
        controls_layout.addStretch(1)
        controls_layout.addLayout(transform_layout)
        controls_layout.addStretch(1)
        controls_layout.addLayout(bin_layout)

        return controls_layout

    def update_histogram(self, data):
        """Update the histogram with new data"""
        data = np.asarray(data)
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

        self.min_value = data.min() - 1
        self.max_value = data.max() + 1

        self.min_value_input.setText(str(self.min_value))
        self.max_value_input.setText(str(self.max_value))

        self._update_cutoff_positions(self.min_value, self.max_value)

        y, x = np.histogram(data, bins=self.bin_count)
        bar_graph = pg.BarGraphItem(
            x=x[:-1],
            height=y,
            width=(x[1] - x[0]) * 0.8,
            brush=QColor(70, 130, 180),
        )
        self.histogram_plot.addItem(bar_graph)

        self.histogram_plot.addItem(self.lower_cutoff_line)
        self.histogram_plot.addItem(self.upper_cutoff_line)

        label = "Cluster Size" + (" (log scale)" if log_scale else "")
        self.histogram_plot.setLabel("bottom", label)
        self.range_slider.setRange(0, 100)

    def _update_cutoff_values(self, lower_value=None, upper_value=None):
        """Central method to update cutoff values and propagate changes to all UI elements."""

        if lower_value is None:
            lower_value = self.lower_cutoff_line.value()
        if upper_value is None:
            upper_value = self.upper_cutoff_line.value()

        range_span = self.max_value - self.min_value
        if range_span <= 0:
            return None

        lower_value = min(lower_value, upper_value)
        upper_value = max(lower_value, upper_value)
        lower_value = max(self.min_value, lower_value)
        upper_value = min(self.max_value, upper_value)

        lower_percent = int(((lower_value - self.min_value) / range_span) * 100)
        upper_percent = int(((upper_value - self.min_value) / range_span) * 100)
        for element in [
            self.lower_cutoff_line,
            self.upper_cutoff_line,
            self.range_slider,
        ]:
            element.blockSignals(True)

        self.lower_cutoff_line.setValue(lower_value)
        self.upper_cutoff_line.setValue(upper_value)

        self.min_value_input.setText(str(round(lower_value, 4)))
        self.max_value_input.setText(str(round(upper_value, 4)))
        self.range_slider.setValues(lower_percent, upper_percent)
        for element in [
            self.lower_cutoff_line,
            self.upper_cutoff_line,
            self.range_slider,
        ]:
            element.blockSignals(False)

        self.cutoff_changed.emit(
            self._invert_scaling(lower_value), self._invert_scaling(upper_value)
        )

    def _update_cutoff_positions(self, lower_value, upper_value):
        """Update the positions of both cutoff lines."""
        self._update_cutoff_values(lower_value, upper_value)

    def _on_slider_range_changed(self, lower_percent, upper_percent):
        """Handle range slider value changes."""
        range_span = self.max_value - self.min_value
        lower_value = self.min_value + (lower_percent / 100.0) * range_span
        upper_value = self.min_value + (upper_percent / 100.0) * range_span
        self._update_cutoff_values(lower_value, upper_value)

    def _handle_cutoff_drag(self, is_lower):
        """Handle dragging of cutoff lines."""
        line = self.lower_cutoff_line if is_lower else self.upper_cutoff_line
        if is_lower:
            self._update_cutoff_values(lower_value=line.value())
        else:
            self._update_cutoff_values(upper_value=line.value())

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
