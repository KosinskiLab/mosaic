"""
Slider widgets for the GUI.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

__all__ = ["DualHandleSlider", "SliderRow"]

import numpy as np
from qtpy.QtGui import QColor
from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import QWidget, QSlider, QSizePolicy, QHBoxLayout, QLabel

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

        # Label
        self.label_widget = QLabel(f"{label}:")
        self.label_widget.setStyleSheet(
            f"""
            QLabel {{
                font-size: 13px;
                color: {Colors.TEXT_PRIMARY};
            }}
        """
        )

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(self.steps)
        self.slider.setValue(self._value_to_slider(default))
        self.slider.valueChanged.connect(self._on_slider_changed)

        self.value_label = QLabel()
        self.value_label.setStyleSheet(
            f"""
            QLabel {{
                font-size: 13px;
                font-weight: 500;
                color: {Colors.TEXT_PRIMARY};
                min-width: 45px;
                text-align: right;
            }}
        """
        )
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
        if event.button() == Qt.LeftButton:
            self.dragging_handle = None
