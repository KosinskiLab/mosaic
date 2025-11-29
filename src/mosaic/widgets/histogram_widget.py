"""
Variety of widgets used throughout the GUI.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np
import pyqtgraph as pg
from qtpy.QtGui import QColor, QDoubleValidator
from qtpy.QtCore import Qt, Signal, QLocale, QSize
from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLineEdit,
    QLabel,
    QSpinBox,
    QSizePolicy,
    QComboBox,
    QGridLayout,
)


class DualHandleSlider(QWidget):
    """A slider with two handles for selecting a range, with visual feedback."""

    rangeChanged = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.min_val = 0.0
        self.max_val = 100.0
        self.lower_pos = 0.0
        self.upper_pos = 100.0

        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Track which handle is being dragged
        self.dragging_handle = None
        self.handle_radius = 8

        self.inactive_color = QColor(226, 232, 240)
        self.active_color = QColor(148, 163, 184)
        self.handle_color = QColor(255, 255, 255)
        self.border_color = QColor(79, 70, 229)

    def setRange(self, minimum, maximum):
        """Set the range of values the slider represents."""
        self.min_val = minimum
        self.max_val = maximum
        self.update()

    def setValues(self, lower, upper):
        """Set both handle positions."""
        self.lower_pos = np.clip(lower, self.min_val, self.max_val)
        self.upper_pos = np.clip(upper, self.min_val, self.max_val)
        if self.lower_pos > self.upper_pos:
            self.lower_pos, self.upper_pos = self.upper_pos, self.lower_pos
        self.update()

    def _value_to_pixel(self, value):
        """Convert a value to pixel position."""
        if self.max_val == self.min_val:
            return self.handle_radius
        margin = self.handle_radius * 2
        width = self.width() - margin * 2
        normalized = (value - self.min_val) / (self.max_val - self.min_val)
        return margin + normalized * width

    def _pixel_to_value(self, pixel):
        """Convert pixel position to value."""
        margin = self.handle_radius * 2
        width = self.width() - margin * 2
        if width <= 0:
            return self.min_val
        normalized = (pixel - margin) / width
        normalized = np.clip(normalized, 0, 1)
        return self.min_val + normalized * (self.max_val - self.min_val)

    def paintEvent(self, event):
        """Draw the slider with range visualization."""
        from qtpy.QtGui import QPainter, QPen, QBrush

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw track
        track_y = self.height() // 2
        margin = self.handle_radius * 2
        track_width = self.width() - margin * 2

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self.inactive_color))
        painter.drawRoundedRect(margin, track_y - 2, track_width, 4, 2, 2)

        lower_x = self._value_to_pixel(self.lower_pos)
        upper_x = self._value_to_pixel(self.upper_pos)
        range_width = upper_x - lower_x

        painter.setBrush(QBrush(self.active_color))
        painter.drawRoundedRect(int(lower_x), track_y - 2, int(range_width), 4, 2, 2)

        for pos in [self.lower_pos, self.upper_pos]:
            x = self._value_to_pixel(pos)

            painter.setBrush(QBrush(self.handle_color))
            painter.drawEllipse(
                int(x - self.handle_radius),
                track_y - self.handle_radius,
                self.handle_radius * 2,
                self.handle_radius * 2,
            )

            painter.setPen(QPen(self.border_color, 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(
                int(x - self.handle_radius),
                track_y - self.handle_radius,
                self.handle_radius * 2,
                self.handle_radius * 2,
            )

    def mousePressEvent(self, event):
        """Start dragging a handle."""
        if event.button() != Qt.LeftButton:
            return

        x = event.pos().x()
        lower_x = self._value_to_pixel(self.lower_pos)
        upper_x = self._value_to_pixel(self.upper_pos)

        # Check which handle is closer
        dist_to_lower = abs(x - lower_x)
        dist_to_upper = abs(x - upper_x)

        if dist_to_lower < self.handle_radius * 2:
            self.dragging_handle = "lower"
        elif dist_to_upper < self.handle_radius * 2:
            self.dragging_handle = "upper"
        else:
            # Click on track - move nearest handle
            if dist_to_lower < dist_to_upper:
                self.dragging_handle = "lower"
                self.lower_pos = self._pixel_to_value(x)
            else:
                self.dragging_handle = "upper"
                self.upper_pos = self._pixel_to_value(x)
            self.update()
            self.rangeChanged.emit(self.lower_pos, self.upper_pos)

    def mouseMoveEvent(self, event):
        """Drag the active handle."""
        if self.dragging_handle is None:
            return

        value = self._pixel_to_value(event.pos().x())

        if self.dragging_handle == "lower":
            self.lower_pos = min(value, self.upper_pos)
        else:
            self.upper_pos = max(value, self.lower_pos)

        self.update()
        self.rangeChanged.emit(self.lower_pos, self.upper_pos)

    def mouseReleaseEvent(self, event):
        """Stop dragging."""
        if event.button() == Qt.LeftButton:
            self.dragging_handle = None


class HistogramWidget(QWidget):
    cutoff_changed = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.data = []
        self.min_value = 0
        self.max_value = 1
        self.bin_count = 20

        self.setup_ui()

    def setup_ui(self):
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
