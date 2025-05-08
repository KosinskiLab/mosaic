""" Implements VolumeViewer, which provides overlays volumeetric data with
    the corresponding point cloud segmentations.

    Copyright (c) 2023-2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import vtk
from qtpy.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QSlider,
    QComboBox,
    QPushButton,
    QFileDialog,
    QLabel,
)
import qtawesome as qta

from qtpy.QtCore import Qt, Signal
from vtkmodules.util import numpy_support

from ..stylesheets import QPushButton_style

_colormaps = [
    "gray",
    "gray_r",
    "viridis",
    "magma",
    "twilight_shifted",
    "coolwarm",
    "none",
]


class VolumeViewer(QWidget):
    data_changed = Signal()

    def __init__(self, vtk_widget, legend=None, parent=None):
        super().__init__(parent)
        self.vtk_widget = vtk_widget
        self.legend = legend

        self.renderer = (
            self.vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer()
        )

        self.slice_mapper = vtk.vtkImageSliceMapper()
        self.slice = vtk.vtkImageSlice()
        self.volume = None

        self.label = QLabel("Volume")
        self.open_button = QPushButton("Open")
        self.open_button.clicked.connect(self.open_volume)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close_volume)

        self.slice_slider = QSlider(Qt.Orientation.Horizontal)
        self.slice_slider.setEnabled(False)
        self.slice_slider.valueChanged.connect(self.update_slice)

        self.orientation_selector = QComboBox()
        self.orientation_selector.addItems(["X", "Y", "Z"])
        self._orientation_mapping = {"X": 0, "Y": 1, "Z": 2}
        self.orientation_selector.currentTextChanged.connect(self.change_orientation)
        self.orientation_selector.setEnabled(False)

        self.color_selector = QComboBox()
        self.color_selector.addItems(_colormaps)
        self.color_selector.currentTextChanged.connect(self.change_color_palette)
        self.color_selector.setEnabled(False)

        self.contrast_label = QLabel("Contrast:")
        self.min_contrast_slider = QSlider(Qt.Orientation.Horizontal)
        self.min_contrast_slider.setRange(0, 100)
        self.min_contrast_slider.setValue(0)
        self.min_contrast_slider.valueChanged.connect(self.update_contrast_and_gamma)
        self.min_contrast_slider.setEnabled(False)
        self.max_contrast_slider = QSlider(Qt.Orientation.Horizontal)
        self.max_contrast_slider.setRange(0, 100)
        self.max_contrast_slider.setValue(100)
        self.max_contrast_slider.valueChanged.connect(self.update_contrast_and_gamma)
        self.max_contrast_slider.setEnabled(False)

        self.gamma_label = QLabel("Gamma:")
        self.gamma_slider = QSlider(Qt.Orientation.Horizontal)
        self.gamma_slider.setRange(1, 300)
        self.gamma_slider.setValue(100)
        self.gamma_slider.valueChanged.connect(self.update_contrast_and_gamma)
        self.gamma_slider.setEnabled(False)

        # Create labels for current values
        self.slice_label = QLabel("Slice:")
        self.slice_value_label = QLabel("0")
        self.contrast_value_label = QLabel("0 - 100")
        self.gamma_value_label = QLabel("1.00")

        self.slice_value_label.setFixedWidth(30)
        self.contrast_value_label.setFixedWidth(80)
        self.gamma_value_label.setFixedWidth(40)

        # Project 3D geometries on 2D slice
        self.project_selector = QComboBox()
        self.project_selector.addItems(["Off", "Project +", "Project -"])
        self.project_selector.setEnabled(False)
        self.project_selector.currentTextChanged.connect(self.handle_projection_change)
        self.clipping_plane = vtk.vtkPlane()
        self.clipping_direction = 1

        # Create layout
        self.controls_layout = QHBoxLayout()
        self.controls_layout.addWidget(self.label)
        self.controls_layout.addWidget(self.open_button)
        self.controls_layout.addWidget(self.close_button)
        self.controls_layout.addWidget(self.orientation_selector)
        self.controls_layout.addWidget(self.color_selector)
        self.controls_layout.addWidget(self.slice_label)
        self.controls_layout.addWidget(self.slice_slider)
        self.controls_layout.addWidget(self.slice_value_label)
        self.controls_layout.addWidget(self.contrast_label)
        self.controls_layout.addWidget(self.min_contrast_slider)
        self.controls_layout.addWidget(self.max_contrast_slider)
        self.controls_layout.addWidget(self.contrast_value_label)
        self.controls_layout.addWidget(self.gamma_label)
        self.controls_layout.addWidget(self.gamma_slider)
        self.controls_layout.addWidget(self.gamma_value_label)
        self.controls_layout.addWidget(self.project_selector)

        self.editable_widgets = [
            self.slice_slider,
            self.orientation_selector,
            self.color_selector,
            self.min_contrast_slider,
            self.max_contrast_slider,
            self.gamma_slider,
            self.close_button,
            self.project_selector,
            self.contrast_value_label,
            self.slice_value_label,
            self.gamma_value_label,
            self.slice_label,
            self.contrast_label,
            self.gamma_label,
        ]
        self.change_widget_state(False)

        layout = QVBoxLayout(self)
        layout.addLayout(self.controls_layout)
        self.setLayout(layout)
        self.setStyleSheet(
            """
            QLabel:disabled {
                opacity: 0.1;
            }
        """
            + QPushButton_style
        )

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, volume):
        self._volume = volume
        self.data_changed.emit()

    def open_volume(self):
        if self.volume is not None:
            self.close_volume()

        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Open Volume")
        if not file_path:
            return -1

        try:
            self.load_volume(file_path)
        except Exception as e:
            print(f"Error opening volume: {e}")

    def close_volume(self):
        if self.volume is None:
            return -1

        self.min_contrast_slider.setValue(0)
        self.max_contrast_slider.setValue(100)
        self.gamma_slider.setValue(100)
        self.orientation_selector.setCurrentIndex(0)
        self.color_selector.setCurrentText("gray")

        if self.project_selector.currentText() != "Off":
            self.handle_projection_change("Off")

        self.volume = None
        self.renderer.RemoveViewProp(self.slice)
        self.slice_mapper = vtk.vtkImageSliceMapper()
        self.slice = vtk.vtkImageSlice()

        self.change_widget_state(is_enabled=False)
        self.vtk_widget.GetRenderWindow().Render()

    def change_widget_state(self, is_enabled: bool = False):
        for widget in self.editable_widgets:
            widget.setEnabled(is_enabled)

    def load_volume(self, file_path):
        from ..formats.parser import load_density

        volume = load_density(file_path)

        self.volume = vtk.vtkImageData()
        self.volume.SetDimensions(volume.shape)
        self.volume.SetSpacing(volume.sampling_rate)
        self.volume.AllocateScalars(vtk.VTK_FLOAT, 1)

        # if volume.shape[1] == 20:
        #     print("Change this back")

        #     self.volume.SetOrigin(
        #         -2 * 4.0,
        #         (1320 -2) * volume.sampling_rate[1],
        #         -1 * 5.24
        #     )

        volume = numpy_support.numpy_to_vtk(
            volume.data.ravel(order="F"), deep=True, array_type=vtk.VTK_FLOAT
        )
        self.volume.GetPointData().SetScalars(volume)
        self.swap_volume(self.volume)

    def swap_volume(self, new_volume):
        self.volume = new_volume
        self.slice_mapper.SetInputData(self.volume)
        self.slice_mapper.SetOrientationToX()
        self.slice_mapper.SetSliceNumber(0)

        self.slice.SetMapper(self.slice_mapper)
        self.renderer.AddViewProp(self.slice)

        self.change_color_palette("gray")
        self.update_contrast_and_gamma()

        dimensions = self.get_dimensions()
        self.slice_slider.setRange(0, dimensions[0] - 1)
        self.slice_slider.setValue(0)

        self.change_widget_state(is_enabled=True)

        self.renderer.ResetCamera()
        self.vtk_widget.GetRenderWindow().Render()

    def update_slice(self, slice_number):
        self.slice_mapper.SetSliceNumber(slice_number)
        self.slice_value_label.setText(str(slice_number))
        self.update_clipping_plane()
        self.vtk_widget.GetRenderWindow().Render()

    def change_orientation(self, orientation):
        dimensions = self.get_dimensions()

        if orientation == "X":
            self.slice_mapper.SetOrientationToX()
        elif orientation == "Y":
            self.slice_mapper.SetOrientationToY()
        elif orientation == "Z":
            self.slice_mapper.SetOrientationToZ()

        dim = self._orientation_mapping.get(orientation, 0)
        self.slice_slider.setRange(*(0, dimensions[dim] - 1))

        self.slice_slider.setValue(0)
        self.slice_mapper.SetSliceNumber(0)
        self.update_clipping_plane()

        self.renderer.ResetCamera()
        self.vtk_widget.GetRenderWindow().Render()

    def get_dimensions(self):
        return self.volume.GetDimensions()

    def change_color_palette(self, palette_name):
        self.current_palette = palette_name

        self.slice.SetVisibility(self.current_palette != "none")
        if self.current_palette != "none":
            self.update_contrast_and_gamma()
        self.vtk_widget.GetRenderWindow().Render()

    def update_contrast_and_gamma(self):
        from ..utils import cmap_to_vtkctf

        scalar_range = self.volume.GetScalarRange()
        min_value, max_value = scalar_range
        value_range = max_value - min_value

        min_contrast = self.min_contrast_slider.value() / 100.0
        max_contrast = self.max_contrast_slider.value() / 100.0
        gamma = self.gamma_slider.value() / 100.0

        if min_contrast >= max_contrast:
            min_contrast = max_contrast - 0.01

        self.gamma_value_label.setText(f"{gamma:.2f}")
        self.contrast_value_label.setText(f"{min_contrast:.2f} - {max_contrast:.2f}")
        adjusted_min = min_value + min_contrast * value_range
        adjusted_max = min_value + max_contrast * value_range

        if self.current_palette == "none":
            return None

        ctf, _ = cmap_to_vtkctf(
            self.current_palette, adjusted_max, adjusted_min, gamma=gamma
        )
        if self.legend is not None:
            self.legend.set_lookup_table(ctf, "Volume")

        self.slice.GetProperty().SetLookupTable(ctf)
        self.slice.GetProperty().SetUseLookupTableScalarRange(True)

        self.slice.GetProperty().SetColorWindow(value_range)
        self.slice.GetProperty().SetColorLevel(min_value + value_range / 2)

        self.vtk_widget.GetRenderWindow().Render()

    def update_clipping_plane(self):
        if self.volume is None or self.project_selector.currentText() == "Off":
            return None

        dim = self._orientation_mapping.get(self.orientation_selector.currentText(), 0)

        pos = self.slice_slider.value()
        origin, spacing = self.volume.GetOrigin()[dim], self.volume.GetSpacing()[dim]
        normal = [0 if i != dim else self.clipping_direction for i in range(3)]
        self.clipping_plane.SetNormal(*normal)
        self.clipping_plane.SetOrigin(
            *[0 if i != dim else origin + pos * spacing for i in range(3)]
        )

        return None

    def handle_projection_change(self, state):
        if self.volume is None:
            return

        actors = self.renderer.GetActors()
        actors.InitTraversal()

        for i in range(actors.GetNumberOfItems()):
            actor = actors.GetNextActor()
            actor.GetMapper().RemoveAllClippingPlanes()
            if state == "Off":
                continue

            self.clipping_direction = 1 if state == "Project +" else -1
            self.update_clipping_plane()
            actor.GetMapper().AddClippingPlane(self.clipping_plane)

        self.vtk_widget.GetRenderWindow().Render()


class MultiVolumeViewer(QWidget):
    """Container widget for managing multiple VolumeViewer instances"""

    def __init__(self, vtk_widget, legend=None, parent=None):
        super().__init__(parent)

        self.vtk_widget = vtk_widget
        self.legend = legend

        self.setStyleSheet(
            """
            QPushButton:hover {
                background-color: #f3f4f6;
            }
        """
        )

        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(5)
        self.layout.setContentsMargins(0, 0, 0, 5)

        self.primary = VolumeViewer(self.vtk_widget, self.legend)
        current_margins = self.primary.layout().contentsMargins()
        self.primary.layout().setContentsMargins(
            current_margins.left(), 0, current_margins.right(), 0
        )
        self.primary_margins = self.primary.layout().contentsMargins()
        self.layout.addWidget(self.primary)

        add_button = QPushButton()
        add_button.setIcon(qta.icon("fa5s.plus", color="#696c6f"))
        add_button.setFixedWidth(20)
        add_button.clicked.connect(self.add_viewer)
        self.primary.controls_layout.addWidget(add_button)

        self.additional_viewers = []
        self.primary.data_changed.connect(self._changed_primary)

    def add_viewer(self):
        """Add a new VolumeViewer instance"""
        new_viewer = VolumeViewer(self.vtk_widget, self.legend)
        new_viewer.layout().setContentsMargins(self.primary_margins)

        remove_button = QPushButton()
        remove_button.setIcon(qta.icon("fa5s.trash", color="#696c6f"))
        remove_button.setFixedWidth(20)
        remove_button.clicked.connect(lambda: self.remove_viewer(new_viewer))
        new_viewer.controls_layout.addWidget(remove_button)

        if self.primary.volume is not None:
            new_viewer.volume = self.primary.volume
            new_viewer.change_widget_state(True)
            new_viewer.change_color_palette("gray")
            new_viewer.update_contrast_and_gamma()

        self._copy_from_primary(new_viewer)
        self.additional_viewers.append(new_viewer)
        self.layout.addWidget(new_viewer)

    def remove_viewer(self, viewer):
        """Remove a specific viewer"""
        if viewer in self.additional_viewers:
            self.additional_viewers.remove(viewer)
            viewer.close_volume()
            viewer.deleteLater()

    def close(self):
        for viewer in self.additional_viewers:
            viewer.close_volume()
        self.primary.close_volume()

    def _copy_from_primary(self, new_viewer: VolumeViewer) -> int:
        volume = self.primary.volume
        if volume is None:
            new_viewer.change_widget_state(False)
            return 0

        return new_viewer.swap_volume(volume)

    def _changed_primary(self):
        return [self._copy_from_primary(x) for x in self.additional_viewers]
