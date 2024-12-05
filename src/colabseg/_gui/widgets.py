""" Variety of widgets used throughout the GUI.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import Tuple

import vtk
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QWidget,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QSlider,
)
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, pyqtProperty, pyqtSignal


class BoundingBoxWidget:
    def __init__(self, renderer, interactor):
        self.renderer = renderer
        self.interactor = interactor
        self.box_actor = None
        self.axes_actor = None
        self.orientation_marker = None
        self.setup()

    def setup(self, shape: Tuple[int] = None):
        box_mapper = vtk.vtkPolyDataMapper()
        if shape is not None:
            box_source = vtk.vtkCubeSource()
            box_source.SetXLength(shape[0])
            box_source.SetYLength(shape[1])
            box_source.SetZLength(shape[2])
            box_source.SetCenter(*(x // 2 for x in shape))
            box_mapper.SetInputConnection(box_source.GetOutputPort())

        self.box_actor = vtk.vtkActor()
        self.box_actor.SetMapper(box_mapper)
        self.box_actor.GetProperty().SetColor(0.5, 0.5, 0.5)
        self.box_actor.GetProperty().SetOpacity(0.3)
        self.box_actor.GetProperty().SetRepresentationToWireframe()

        # Create axes actor
        self.axes_actor = vtk.vtkAxesActor()
        self.axes_actor.SetTotalLength(20, 20, 20)
        self.axes_actor.SetShaftType(0)
        self.axes_actor.SetAxisLabels(1)
        self.axes_actor.SetCylinderRadius(0.01)
        self.axes_actor.SetPosition(0, 0, 0)

        # Adjust text properties for axis labels
        for axis in ["X", "Y", "Z"]:
            caption_actor = getattr(self.axes_actor, f"Get{axis}AxisCaptionActor2D")()
            text_actor = caption_actor.GetTextActor()
            text_actor.SetTextScaleModeToNone()
            text_actor.GetTextProperty().SetFontSize(12)

        # Create orientation marker widget
        self.orientation_marker = vtk.vtkOrientationMarkerWidget()
        self.orientation_marker.SetOrientationMarker(self.axes_actor)
        self.orientation_marker.SetInteractor(self.interactor)
        self.orientation_marker.SetViewport(0.0, 0.0, 0.2, 0.2)
        self.orientation_marker.SetEnabled(1)
        self.orientation_marker.InteractiveOff()
        self.orientation_marker.SetOutlineColor(0.93, 0.57, 0.13)

        self.renderer.AddActor(self.box_actor)


class ProgressButton(QPushButton):
    cancel = pyqtSignal()

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._progress = 0
        self._is_progressing = False
        self._original_text = text
        self._fade_opacity = 1.0

        # Re-clicking the progress button should allow cancelling the operation
        self._cancel_button = QPushButton(parent=self)
        self._cancel_button.setStyleSheet(
            """
            QPushButton {
                background-color: transparent;
                border: none;
            }
        """
        )

        self._cancel_button.clicked.connect(self._handle_cancel_click)
        self._cancel_button.setEnabled(False)
        self._cancel_button.hide()

        self._fade_animation = QPropertyAnimation(self, b"fadeOpacity")
        self._fade_animation.setDuration(200)
        self._fade_animation.finished.connect(self._cleanup)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._cancel_button:
            self._cancel_button.setGeometry(self.rect())

    @pyqtProperty(float)
    def fadeOpacity(self):
        return self._fade_opacity

    @fadeOpacity.setter
    def fadeOpacity(self, opacity):
        self._fade_opacity = max(0.0, min(1.0, opacity))
        if not self._is_progressing:
            return None
        self.update()

    def listen(self, signal):
        self.setEnabled(False)

        # self._cancel_button.setEnabled(True)
        # self._cancel_button.show()

        self.signal = signal
        self.signal.connect(self._update_progress)

        self._fade_opacity, self._is_progressing = 1.0, True
        self.update()

    def _update_progress(self, value):
        if not self._is_progressing:
            return None

        self._progress = max(0.0, min(1.0, value)) * 100

        self.update()
        if self._progress >= 100:
            QTimer.singleShot(200, self._exit)

    def _handle_cancel_click(self):
        if self._is_progressing:
            self.cancel.emit()
            self._exit()
            return None

    def _exit(self):
        self._fade_animation.stop()
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.start()

    def _cleanup(self):
        self._is_progressing = False
        self._fade_opacity = 0.0

        self.setEnabled(True)
        self._cancel_button.setEnabled(False)
        self._cancel_button.hide()

        if hasattr(self, "signal") and self.signal is not None:
            self.signal.disconnect(self._update_progress)
            self.signal = None

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        super().paintEvent(event)

        if not self._is_progressing:
            return None

        painter.save()
        painter.setOpacity(self._fade_opacity)

        bg_color = QColor(200, 200, 200)
        painter.fillRect(self.rect(), bg_color)
        if self._progress > 0:
            progress_width = int(self.width() * (self._progress / 100))
            progress_color = QColor(76, 175, 80)
            painter.fillRect(0, 0, progress_width, self.height(), progress_color)

        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(
            self.rect(), Qt.AlignmentFlag.AlignCenter, f"{int(self._progress)}%"
        )
        painter.restore()


class HistogramWidget(QWidget):
    cutoff_changed = pyqtSignal(float)

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
