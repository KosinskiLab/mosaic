"""
Slider widgets for the GUI.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

__all__ = ["DualHandleSlider", "SliderRow", "HistogramRangeSlider"]

import numpy as np
from qtpy.QtGui import QColor
from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
    QWidget,
    QSlider,
    QSizePolicy,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
)

from ..stylesheets import Colors


class SliderRow(QWidget):
    """A row with label, slider, and value display."""

    valueChanged = Signal(float)

    def __init__(
        self,
        label: str,
        min_val: float = 0.0,
        max_val: float = 1.0,
        default: float = 0.5,
        decimals: int = 2,
        suffix: str = "",
        label_position: str = "left",
        steps: int = 100,
        exponent: float = 1.0,
        parent=None,
    ):
        super().__init__(parent)
        self.min_val = min_val
        self.max_val = max_val
        self.decimals = decimals
        self.suffix = suffix
        self.steps = steps
        self.exponent = exponent
        self._setup_ui(label, default, label_position)

    def _setup_ui(self, label: str, default: float, label_position: str = "left"):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.label_widget = QLabel(f"{label}:")

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(self.steps)
        self.slider.setValue(self._value_to_slider(default))
        self.slider.valueChanged.connect(self._on_slider_changed)

        self.value_label = QLabel()
        self.value_label.setStyleSheet("QLabel { min-width: 45px; text-align: right;}")

        self.value_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._update_value_label(default)

        if label_position == "left":
            layout.addWidget(self.label_widget, 0, Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(self.slider, 1, Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(self.value_label, 0, Qt.AlignmentFlag.AlignVCenter)
        else:
            layout.addWidget(self.slider, 1, Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(self.label_widget, 0, Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(self.value_label, 0, Qt.AlignmentFlag.AlignVCenter)

    def _value_to_slider(self, value: float) -> int:
        """Convert actual value to slider position (0-steps)."""
        ratio = (value - self.min_val) / (self.max_val - self.min_val)
        if self.exponent != 1.0:
            # Inverse of the non-linear scaling: more precision at high end
            ratio = 1.0 - (1.0 - ratio) ** (1.0 / self.exponent)
        return int(ratio * self.steps)

    def _slider_to_value(self, pos: int) -> float:
        """Convert slider position to actual value."""
        ratio = pos / self.steps
        if self.exponent != 1.0:
            # Non-linear scaling: more precision at high end when exponent > 1
            ratio = 1.0 - (1.0 - ratio) ** self.exponent
        return self.min_val + ratio * (self.max_val - self.min_val)

    def _update_value_label(self, value: float):
        """Update the value label display."""
        if self.decimals == 0:
            text = f"{int(value)}{self.suffix}"
        else:
            text = f"{value:.{self.decimals}f}{self.suffix}"
        self.value_label.setText(text)

    def _on_slider_changed(self, pos: int):
        """Handle slider value change."""
        value = self._slider_to_value(pos)
        self._update_value_label(value)
        self.valueChanged.emit(value)

    def value(self) -> float:
        """Get the current value."""
        return self._slider_to_value(self.slider.value())

    def setValue(self, value: float):
        """Set the current value."""
        self.slider.setValue(self._value_to_slider(value))
        self._update_value_label(value)

    def setRange(self, min_val: float, max_val: float):
        """Set the value range."""
        self.min_val = min_val
        self.max_val = max_val
        self._update_value_label(self.value())

    def setEnabled(self, enabled: bool):
        """Enable or disable the widget."""
        super().setEnabled(enabled)
        self.label_widget.setEnabled(enabled)
        self.slider.setEnabled(enabled)
        self.value_label.setEnabled(enabled)


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
        self.handle_size = 16

        # Colors matching QSlider_style from stylesheets.py
        self.groove_color = QColor("#e2e8f0")
        self.active_color = QColor(Colors.BORDER_HOVER)
        self.handle_color = QColor("#ffffff")
        self.border_color = QColor(Colors.BORDER_DARK)
        # Disabled colors
        self.groove_disabled = QColor(Colors.BG_TERTIARY)
        self.active_disabled = QColor(Colors.BORDER_DARK)
        self.handle_disabled = QColor(Colors.BG_SECONDARY)
        self.border_disabled = QColor("#e2e8f0")

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
            return self.handle_size
        margin = self.handle_size
        width = self.width() - margin * 2
        normalized = (value - self.min_val) / (self.max_val - self.min_val)
        return margin + normalized * width

    def _pixel_to_value(self, pixel):
        """Convert pixel position to value."""
        margin = self.handle_size
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

        # Use disabled colors when widget is disabled
        if not self.isEnabled():
            groove = self.groove_disabled
            active = self.active_disabled
            handle = self.handle_disabled
            border = self.border_disabled
        else:
            groove = self.groove_color
            active = self.active_color
            handle = self.handle_color
            border = self.border_color

        # Draw track/groove
        track_y = self.height() // 2
        margin = self.handle_size
        track_width = self.width() - margin * 2

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(groove))
        painter.drawRoundedRect(margin, track_y - 2, track_width, 4, 2, 2)

        # Draw active range
        lower_x = self._value_to_pixel(self.lower_pos)
        upper_x = self._value_to_pixel(self.upper_pos)
        range_width = upper_x - lower_x

        painter.setBrush(QBrush(active))
        painter.drawRoundedRect(int(lower_x), track_y - 2, int(range_width), 4, 2, 2)

        # Draw handles (circular, matching QSlider style)
        for pos in [self.lower_pos, self.upper_pos]:
            x = self._value_to_pixel(pos)
            handle_x = int(x - self.handle_size // 2)
            handle_y = track_y - self.handle_size // 2

            painter.setBrush(QBrush(handle))
            painter.setPen(QPen(border, 1))
            painter.drawEllipse(handle_x, handle_y, self.handle_size, self.handle_size)

    def mousePressEvent(self, event):
        """Start dragging a handle."""
        if not self.isEnabled() or event.button() != Qt.LeftButton:
            return

        x = event.pos().x()
        lower_x = self._value_to_pixel(self.lower_pos)
        upper_x = self._value_to_pixel(self.upper_pos)

        # Check which handle is closer
        dist_to_lower = abs(x - lower_x)
        dist_to_upper = abs(x - upper_x)

        if dist_to_lower < self.handle_size:
            self.dragging_handle = "lower"
        elif dist_to_upper < self.handle_size:
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
        if not self.isEnabled() or self.dragging_handle is None:
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
        was_dragging = self.dragging_handle is not None
        if event.button() == Qt.LeftButton:
            self.dragging_handle = None
            if was_dragging:
                self.rangeReleased.emit(self.lower_pos, self.upper_pos)

    rangeReleased = Signal(float, float)


class MiniHistogram(QWidget):
    """A compact histogram display widget."""

    def __init__(self, parent=None, n_bins: int = 50, margin: int = 16):
        super().__init__(parent)
        self.n_bins = n_bins
        self.margin = margin  # Match DualHandleSlider handle_size for alignment
        self._hist = None
        self._bin_edges = None
        self._lower = 0.0
        self._upper = 1.0
        self._min_val = 0.0
        self._max_val = 1.0

        self.hist_color = QColor(Colors.BORDER_HOVER)
        self.hist_color.setAlpha(100)
        self.selected_color = QColor(Colors.PRIMARY)
        self.selected_color.setAlpha(160)
        self.placeholder_color = QColor(Colors.BORDER_DARK)
        self.placeholder_color.setAlpha(30)

    def setData(self, values):
        """Compute histogram from values."""
        if values is None or len(values) == 0:
            self._hist = None
            self.update()
            return

        values = np.asarray(values).flatten()
        values = values[np.isfinite(values)]
        if len(values) == 0:
            self._hist = None
            return

        self._min_val = float(np.min(values))
        self._max_val = float(np.max(values))
        if self._min_val == self._max_val:
            self._max_val = self._min_val + 1.0

        self._hist, self._bin_edges = np.histogram(values, bins=self.n_bins)
        self._lower = self._min_val
        self._upper = self._max_val
        self.update()

    def setSelection(self, lower, upper):
        """Update the highlighted range."""
        self._lower = lower
        self._upper = upper
        self.update()

    def paintEvent(self, event):
        """Draw the histogram bars or placeholder."""
        from qtpy.QtGui import QPainter, QBrush, QPen

        painter = QPainter(self)
        width = self.width()
        height = self.height()
        draw_width = width - 2 * self.margin

        if self._hist is None or len(self._hist) == 0:
            # Draw placeholder
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(self.placeholder_color))
            painter.drawRect(self.margin, 0, draw_width, height)

            painter.setPen(QPen(QColor(Colors.TEXT_SECONDARY)))
            painter.drawText(
                self.margin, 0, draw_width, height, Qt.AlignCenter, "No data"
            )
            return

        max_count = np.max(self._hist)
        if max_count == 0:
            return

        bar_width = draw_width / len(self._hist)
        for i, count in enumerate(self._hist):
            bar_height = int((count / max_count) * (height - 2))
            x = self.margin + i * bar_width
            y = height - bar_height

            bin_center = (self._bin_edges[i] + self._bin_edges[i + 1]) / 2
            if self._lower <= bin_center <= self._upper:
                painter.setBrush(QBrush(self.selected_color))
            else:
                painter.setBrush(QBrush(self.hist_color))

            painter.setPen(Qt.NoPen)
            painter.drawRect(int(x), int(y), int(bar_width - 1), bar_height)


class HistogramRangeSlider(QWidget):
    """A histogram with an integrated range slider for filtering."""

    rangeChanged = Signal(float, float)
    rangeReleased = Signal(float, float)

    def __init__(self, parent=None, n_bins: int = 50):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._histogram = MiniHistogram(n_bins=n_bins)
        self._slider = DualHandleSlider()

        layout.addWidget(self._histogram)
        layout.addWidget(self._slider)

        self._slider.rangeChanged.connect(self._on_range_changed)
        self._slider.rangeReleased.connect(self.rangeReleased)

    def _on_range_changed(self, lower, upper):
        self._histogram.setSelection(lower, upper)
        self.rangeChanged.emit(lower, upper)

    def setData(self, values):
        """Set data and update histogram and slider range."""
        self._histogram.setData(values)
        if values is not None and len(values) > 0:
            min_val = self._histogram._min_val
            max_val = self._histogram._max_val
            self._slider.setRange(min_val, max_val)
            self._slider.setValues(min_val, max_val)

    def getRange(self):
        """Get the current selected range."""
        return self._slider.lower_pos, self._slider.upper_pos
