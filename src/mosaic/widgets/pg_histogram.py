""" Variety of widgets used throughout the GUI.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np
import pyqtgraph as pg
from qtpy.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QSlider,
)
from qtpy.QtGui import QColor
from qtpy.QtCore import Qt, Signal


class HistogramWidget(QWidget):
    cutoff_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        layout = QHBoxLayout(self)

        self.histogram_plot = pg.PlotWidget()
        self.histogram_plot.setBackground(None)
        self.histogram_plot.getAxis("left").setPen(pg.mkPen(color=(0, 0, 0)))
        self.histogram_plot.getAxis("bottom").setPen(pg.mkPen(color=(0, 0, 0)))
        self.histogram_plot.setLabel("left", "Count")
        self.histogram_plot.setLabel("bottom", "Cluster Size")
        layout.addWidget(self.histogram_plot)

        # Cutoff line
        self.cutoff_line = pg.InfiniteLine(
            angle=90,
            movable=False,
            pen=pg.mkPen(QColor(70, 130, 180), width=2, style=Qt.PenStyle.DotLine),
        )
        self.histogram_plot.addItem(self.cutoff_line)

        # Slider
        slider_layout = QVBoxLayout()
        self.slider = QSlider(Qt.Orientation.Vertical)
        self.slider.setMinimum(0)
        self.slider.setMaximum(100)
        self.slider.setValue(50)
        self.slider.valueChanged.connect(self.update_cutoff_line)
        slider_layout.addWidget(self.slider)
        layout.addLayout(slider_layout)

        self.max_cluster_size = 1

    def update_histogram(self, cluster_sizes):
        if cluster_sizes:
            y, x = np.histogram(cluster_sizes, bins=max(10, len(set(cluster_sizes))))
            self.histogram_plot.clear()
            bar_graph = pg.BarGraphItem(
                x=x[:-1],
                height=y,
                width=(x[1] - x[0]) * 0.8,
                brush=QColor(70, 130, 180),
            )
            self.histogram_plot.addItem(bar_graph)
            self.histogram_plot.addItem(self.cutoff_line)
            self.max_cluster_size = max(cluster_sizes) + 1
            self.update_cutoff_line(emit=False)

    def update_cutoff_line(self, emit: bool = True):
        cutoff_value = (self.slider.value() / 100.0) * self.max_cluster_size
        self.cutoff_line.setValue(cutoff_value)
        if emit:
            self.cutoff_changed.emit(cutoff_value)
