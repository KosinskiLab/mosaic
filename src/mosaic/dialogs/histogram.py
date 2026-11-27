"""
Histogram dialog for cluster size filtering.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import ArrayLike
from qtpy.QtCore import QSize, Signal
from qtpy.QtGui import QCloseEvent, QIntValidator
from qtpy.QtWidgets import (
    QDialog,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..stylesheets import Colors
from ..utils import Throttle
from ..widgets.segmented_control import SegmentedControl
from ..widgets.sliders import HistogramRangeSlider

if TYPE_CHECKING:
    from ..data import MosaicData


class HistogramWidget(QWidget):
    """Cluster size histogram with a range selection.

    Only user input emits ``cutoff_changed``; redraws keep the bounds.
    """

    cutoff_changed = Signal(float, float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.data = np.zeros(0)
        self.bounds = None
        self._log = True

        self.histogram = HistogramRangeSlider()
        self.histogram.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._throttle = Throttle(self._on_slider, interval_ms=100)
        self.histogram.rangeChanged.connect(self._throttle)
        self.histogram.rangeReleased.connect(self._on_slider)

        self.scale = SegmentedControl(["Linear", "Log"], default=1)
        self.scale.selectionChanged.connect(self._on_scale)

        self.min_value_input, self.max_value_input = QLineEdit(), QLineEdit()
        for field, is_lower in (
            (self.min_value_input, True),
            (self.max_value_input, False),
        ):
            field.setValidator(QIntValidator(0, 2**31 - 1))
            field.setFixedHeight(Colors.WIDGET_HEIGHT)
            field.editingFinished.connect(
                lambda lower=is_lower: self._handle_input_change(is_lower=lower)
            )

        controls = QGridLayout()
        controls.setSpacing(8)
        controls.addWidget(QLabel("Scale"), 0, 0)
        controls.addWidget(self.scale, 0, 1, 1, 3)
        controls.addWidget(QLabel("Min"), 1, 0)
        controls.addWidget(self.min_value_input, 1, 1)
        controls.addWidget(QLabel("Max"), 1, 2)
        controls.addWidget(self.max_value_input, 1, 3)
        controls.setColumnStretch(1, 1)
        controls.setColumnStretch(3, 1)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(self.histogram, 1)
        layout.addLayout(controls)

    def update_histogram(self, data: ArrayLike) -> None:
        """Show new cluster sizes, keeping the chosen bounds.

        Parameters
        ----------
        data : array_like
            Cluster sizes.
        """
        previous, self.data = self.data, np.asarray(data)
        if self.data.size == 0:
            self.bounds = None
            self.histogram.setData([])
            self.min_value_input.clear()
            self.max_value_input.clear()
            return None

        low, high = self.data.min(), self.data.max()
        lower, upper = self.bounds or (low, high)
        # Bounds at the edge of the data follow it, e.g. a newly merged largest cluster.
        if previous.size and lower <= previous.min():
            lower = low
        if previous.size and upper >= previous.max():
            upper = high

        self.histogram.setData(self._to_axis(self.data))
        self._show(np.clip(lower, low, high), np.clip(upper, low, high))
        return None

    def _to_axis(self, values: ArrayLike) -> np.ndarray:
        values = np.asarray(values, dtype=float)
        return np.log10(np.maximum(values, 1)) if self._log else values

    def _from_axis(self, value: float) -> float:
        return 10**value if self._log else value

    def _show(self, lower: float, upper: float) -> None:
        self.bounds = (lower, upper)
        self.histogram.setSelection(*self._to_axis([lower, upper]))
        self.min_value_input.setText(f"{lower:g}")
        self.max_value_input.setText(f"{upper:g}")
        return None

    def _set_bounds(self, lower: float, upper: float) -> None:
        low, high = self.data.min(), self.data.max()
        lower, upper = sorted(
            np.clip(round(value), low, high) for value in (lower, upper)
        )
        self._show(lower, upper)
        self.cutoff_changed.emit(float(lower), float(upper))
        return None

    def _on_slider(self, lower: float, upper: float) -> None:
        if self.data.size:
            self._set_bounds(self._from_axis(lower), self._from_axis(upper))
        return None

    def _handle_input_change(self, is_lower: bool) -> None:
        """Apply a typed bound, or restore the field if it is not a number."""
        if not self.data.size:
            return None

        field = self.min_value_input if is_lower else self.max_value_input
        lower, upper = self.bounds
        try:
            value = float(field.text())
        except ValueError:
            return self._show(lower, upper)

        if is_lower:
            return self._set_bounds(value, upper)
        return self._set_bounds(lower, value)

    def _on_scale(self, text: str) -> None:
        self._log = text == "Log"
        if self.data.size:
            self.histogram.setData(self._to_axis(self.data))
            self._show(*self.bounds)
        return None


class HistogramDialog(QDialog):
    def __init__(self, cdata: "MosaicData", parent: QWidget | None = None):
        super().__init__(parent)
        self.cdata = cdata
        self.setWindowTitle("Histogram")

        layout = QVBoxLayout(self)
        group = QGroupBox("Select")
        group_layout = QVBoxLayout(group)

        self.histogram_widget = HistogramWidget()
        group_layout.addWidget(self.histogram_widget)
        layout.addWidget(group)

        self.cdata.data.data_changed.connect(self.update_histogram)
        self.histogram_widget.cutoff_changed.connect(self._on_cutoff_changed)
        self.update_histogram()

    def sizeHint(self):
        return QSize(350, 350)

    def get_cluster_size(self):
        return [x.get_number_of_points() for x in self.cdata.data.container.data]

    def update_histogram(self, data: ArrayLike | None = None):
        self.histogram_widget.update_histogram(self.get_cluster_size())

    def _on_cutoff_changed(
        self, lower_cutoff: float, upper_cutoff: float | None = None
    ):
        cluster_sizes = self.get_cluster_size()
        if upper_cutoff is None:
            upper_cutoff = max(cluster_sizes) + 1

        uuids = []
        for geometry in self.cdata.data.container.data:
            n_points = geometry.get_number_of_points()
            if (n_points >= lower_cutoff) & (n_points <= upper_cutoff):
                uuids.append(geometry.uuid)
        self.cdata.data.set_selection_by_uuid(uuids)

    def closeEvent(self, event: QCloseEvent):
        """Disconnect when dialog closes"""
        try:
            self.cdata.data.data_changed.disconnect(self.update_histogram)
            self.histogram_widget.cutoff_changed.disconnect(self._on_cutoff_changed)
        except (TypeError, RuntimeError):
            pass  # Already disconnected
        super().closeEvent(event)
