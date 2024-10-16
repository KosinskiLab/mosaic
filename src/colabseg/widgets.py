from typing import Tuple

import vtk
import numpy as np
import pyqtgraph as pg

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QSlider,
    QDialog,
    QLabel,
    QPushButton,
)
from PyQt6.QtGui import QColor


class HistogramWidget(QWidget):
    cutoff_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        layout = QHBoxLayout(self)

        # Histogram plotter
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

        self.max_cluster_size = 1  # Default value to avoid division by zero

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


class KeybindsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keybinds")
        # self.setFixedSize(400, 450)

        layout = QVBoxLayout()

        keybinds = [
            ("z", "Set camera view along Z-axis"),
            ("x", "Set camera view along X-axis"),
            ("c", "Set camera view along Y-axis"),
            ("d", "Toggle renderer background color"),
            ("Delete", "Remove selected cluster or points"),
            ("R", "Bring up point selector"),
            ("Right Mouse", "Deselect cluster or points"),
            ("Left Mouse Drag", "Rotate scene"),
            ("Shift Left Mouse Drag", "Translate scene"),
            ("Ctrl+O", "Open file"),
            ("Ctrl+S", "Save file"),
            ("Ctrl+H", "Show this keybinds popup"),
        ]

        for key, description in keybinds:
            key_label = QLabel(f"<b>{key}</b>: {description}")
            layout.addWidget(key_label)

        close_button = QPushButton("Close")
        close_button.setFixedSize(100, 30)
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setLayout(layout)

    def show_keybinds(parent):
        dialog = KeybindsDialog(parent)
        dialog.setStyleSheet(
            """
            QDialog {
                background-color: #f0f0f0;
            }
            QLabel {
                color: #333333;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 5px 10px;
                text-align: center;
                text-decoration: none;
                font-size: 14px;
                margin: 4px 2px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """
        )
        dialog.exec()
