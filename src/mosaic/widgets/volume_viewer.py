"""
Implements VolumeViewer, which provides overlays volumeetric data with
the corresponding point cloud segmentations.

Copyright (c) 2024-2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import vtk
from qtpy.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QComboBox,
    QPushButton,
    QFileDialog,
    QLabel,
    QGroupBox,
)
import qtawesome as qta

from qtpy.QtCore import Signal
from vtkmodules.util import numpy_support

from .sliders import SliderRow, DualHandleSlider
from ..stylesheets import QPushButton_style, Colors

_colormaps = [
    "gray",
    "gray_r",
    "viridis",
    "magma",
    "twilight_shifted",
    "coolwarm",
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

        self.open_button = QPushButton("Load")
        self.open_button.clicked.connect(self.open_volume)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close_volume)

        self.is_visible = True
        self.visibility_button = QPushButton()
        self.visibility_button.setIcon(qta.icon("ph.eye", color=Colors.ICON))
        self.visibility_button.setFixedWidth(30)
        self.visibility_button.setToolTip("Toggle volume visibility")
        self.visibility_button.clicked.connect(self.toggle_visibility)
        self.visibility_button.setEnabled(False)

        self.slice_row = SliderRow(
            label="Slice",
            min_val=0,
            max_val=100,
            default=0,
            decimals=0,
            label_position="right",
        )
        self.slice_row.setEnabled(False)
        self.slice_row.valueChanged.connect(self._on_slice_changed)

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
        self.contrast_label.setStyleSheet(
            f"font-size: 13px; color: {Colors.TEXT_PRIMARY};"
        )
        self.contrast_slider = DualHandleSlider()
        self.contrast_slider.setRange(0, 100)
        self.contrast_slider.setValues(0, 100)
        self.contrast_slider.rangeChanged.connect(self.update_contrast_and_gamma)
        self.contrast_slider.setEnabled(False)
        self.contrast_value_label = QLabel("0.00 - 1.00")
        self.contrast_value_label.setStyleSheet(
            f"font-size: 13px; font-weight: 500; color: {Colors.TEXT_PRIMARY}; min-width: 80px;"
        )
        self.contrast_value_label.setEnabled(False)

        self.gamma_row = SliderRow(
            label="Gamma",
            min_val=0.01,
            max_val=3.0,
            default=1.0,
            decimals=2,
            label_position="right",
        )
        self.gamma_row.setEnabled(False)
        self.gamma_row.valueChanged.connect(self.update_contrast_and_gamma)

        # Project 3D geometries on 2D slice
        self.project_selector = QComboBox()
        self.project_selector.addItems(["Off", "Project +", "Project -"])
        self.project_selector.setEnabled(False)
        self.project_selector.currentTextChanged.connect(self.handle_projection_change)
        self.clipping_plane = vtk.vtkPlane()
        self.clipping_direction = 1

        # Create layout
        self.controls_layout = QHBoxLayout()
        self.controls_layout.addWidget(self.open_button)
        self.controls_layout.addWidget(self.close_button)
        self.controls_layout.addWidget(self.orientation_selector)
        self.controls_layout.addWidget(self.color_selector)
        self.controls_layout.addWidget(self.visibility_button)
        self.controls_layout.addWidget(self.slice_row, 1)
        self.controls_layout.addWidget(self.contrast_slider, 1)
        self.controls_layout.addWidget(self.contrast_label)
        self.controls_layout.addWidget(self.contrast_value_label)
        self.controls_layout.addWidget(self.gamma_row, 1)
        self.controls_layout.addWidget(self.project_selector)

        self.editable_widgets = [
            self.slice_row,
            self.orientation_selector,
            self.color_selector,
            self.contrast_label,
            self.contrast_slider,
            self.contrast_value_label,
            self.gamma_row,
            self.close_button,
            self.visibility_button,
            self.project_selector,
        ]
        self.change_widget_state(False)

        layout = QVBoxLayout(self)
        layout.addLayout(self.controls_layout)
        self.setLayout(layout)
        self.setStyleSheet(QPushButton_style)

    def toggle_visibility(self):
        """Toggle the visibility of the volume slice"""
        if self.volume is None:
            return

        self.is_visible = not self.is_visible
        self.slice.SetVisibility(self.is_visible)

        self.visibility_button.setIcon(qta.icon("ph.eye-slash", color=Colors.ICON))
        self.visibility_button.setToolTip("Show volume")
        if self.is_visible:
            self.visibility_button.setIcon(qta.icon("ph.eye", color=Colors.ICON))
            self.visibility_button.setToolTip("Hide volume")

        self.vtk_widget.GetRenderWindow().Render()

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

        self.contrast_slider.setValues(0, 100)
        self.contrast_value_label.setText("0.00 - 1.00")
        self.gamma_row.setValue(1.0)
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
        self.slice_row.setRange(0, dimensions[0] - 1)
        self.slice_row.setValue(0)

        self.change_widget_state(is_enabled=True)

        self.renderer.ResetCamera()
        self.vtk_widget.GetRenderWindow().Render()

    def _on_slice_changed(self, value: float):
        """Handle slice row value change (converts float to int)."""
        self.update_slice(int(value))

    def update_slice(self, slice_number):
        self.slice_mapper.SetSliceNumber(slice_number)
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

        self._orientation = orientation
        dim = self._orientation_mapping.get(orientation, 0)
        self.slice_row.setRange(0, dimensions[dim] - 1)

        self.slice_row.setValue(0)
        self.slice_mapper.SetSliceNumber(0)
        self.update_clipping_plane()

        self.renderer.ResetCamera()
        self.vtk_widget.GetRenderWindow().Render()

    def get_slice(self):
        return int(self.slice_row.value())

    def get_orientation(self):
        return getattr(self, "_orientation", None)

    def get_projection(self):
        return getattr(self, "_projection", "Off")

    def get_dimensions(self):
        return self.volume.GetDimensions()

    def change_color_palette(self, palette_name):
        self.current_palette = palette_name
        self.update_contrast_and_gamma()
        self.vtk_widget.GetRenderWindow().Render()

    def update_contrast_and_gamma(self, *args):
        from ..utils import cmap_to_vtkctf

        scalar_range = self.volume.GetScalarRange()
        min_value, max_value = scalar_range
        value_range = max_value - min_value

        min_contrast = self.contrast_slider.lower_pos / 100.0
        max_contrast = self.contrast_slider.upper_pos / 100.0
        gamma = self.gamma_row.value()

        if min_contrast >= max_contrast:
            min_contrast = max_contrast - 0.01

        self.contrast_value_label.setText(f"{min_contrast:.2f} - {max_contrast:.2f}")
        adjusted_min = min_value + min_contrast * value_range
        adjusted_max = min_value + max_contrast * value_range

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

        pos = int(self.slice_row.value())
        origin, spacing = self.volume.GetOrigin()[dim], self.volume.GetSpacing()[dim]
        normal = [0 if i != dim else self.clipping_direction for i in range(3)]
        self.clipping_plane.SetNormal(*normal)
        self.clipping_plane.SetOrigin(
            *[0 if i != dim else origin + pos * spacing for i in range(3)]
        )

    def remove_existing_clipping_plane(self, mapper):
        if (planes := mapper.GetClippingPlanes()) is None:
            return None

        planes.InitTraversal()
        for j in range(planes.GetNumberOfItems()):
            plane = planes.GetNextItem()
            if plane == self.clipping_plane:
                mapper.RemoveClippingPlane(self.clipping_plane)

    def handle_projection_change(self, state=None):
        if self.volume is None:
            return

        if state is None:
            state = self.project_selector.currentText()

        self._projection = state
        actors = self.renderer.GetActors()
        actors.InitTraversal()

        for i in range(actors.GetNumberOfItems()):
            actor = actors.GetNextActor()
            mapper = actor.GetMapper()

            self.remove_existing_clipping_plane(mapper)
            if state == "Off":
                continue

            self.clipping_direction = 1 if state == "Project +" else -1
            self.update_clipping_plane()
            mapper.AddClippingPlane(self.clipping_plane)

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
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(4, 4, 4, 4)

        self.viewer_group = QGroupBox("Volume Viewer")
        self.viewer_layout = QVBoxLayout(self.viewer_group)
        self.layout.addWidget(self.viewer_group)
        self.viewer_layout.setSpacing(4)
        self.viewer_layout.setContentsMargins(0, 4, 0, 4)

        self.primary = VolumeViewer(self.vtk_widget, self.legend)
        current_margins = self.primary.layout().contentsMargins()
        self.primary.layout().setContentsMargins(
            current_margins.left(), 0, current_margins.right(), 0
        )
        self.primary_margins = self.primary.layout().contentsMargins()
        self.viewer_layout.addWidget(self.primary)
        # self.layout.addWidget(self.primary)

        add_button = QPushButton()
        add_button.setIcon(qta.icon("ph.plus", color=Colors.ICON))
        add_button.setFixedWidth(30)
        add_button.clicked.connect(self.add_viewer)
        self.primary.controls_layout.addWidget(add_button)
        self.primary.close_button.clicked.connect(self._promote_new_primary)

        self.additional_viewers = []

    def add_viewer(self):
        """Add a new VolumeViewer instance"""
        new_viewer = VolumeViewer(self.vtk_widget, self.legend)
        new_viewer.layout().setContentsMargins(self.primary_margins)

        remove_button = QPushButton()
        remove_button.setIcon(qta.icon("ph.trash", color=Colors.ICON))
        remove_button.setFixedWidth(30)
        remove_button.clicked.connect(lambda: self.remove_viewer(new_viewer))
        new_viewer.controls_layout.addWidget(remove_button)

        if self.primary.volume is not None:
            new_viewer.volume = self.primary.volume
            new_viewer.change_widget_state(True)
            new_viewer.change_color_palette("gray")
            new_viewer.update_contrast_and_gamma()

        self._copy_from_primary(new_viewer)
        self.additional_viewers.append(new_viewer)
        self.viewer_layout.addWidget(new_viewer)

    def remove_viewer(self, viewer):
        """Remove a specific viewer"""
        if viewer in self.additional_viewers:
            self.additional_viewers.remove(viewer)
            viewer.close_volume()
            viewer.deleteLater()

    def close(self):
        for viewer in self.additional_viewers:
            viewer.close_volume()
        try:
            self.primary.close_button.clicked.disconnect(self._promote_new_primary)
        except TypeError:
            pass
        self.primary.close_volume()

    def _copy_from_primary(self, new_viewer: VolumeViewer) -> int:
        volume = self.primary.volume
        if volume is None:
            new_viewer.change_widget_state(False)
            return 0

        return new_viewer.swap_volume(volume)

    def _promote_new_primary(self) -> int:
        viewers = [
            x for x in self.additional_viewers if getattr(x, "volume") is not None
        ]

        if not len(viewers):
            return None

        new_primary = viewers[0]

        # Copy all state from the viewer being promoted
        self.primary.swap_volume(new_primary.volume)
        self.primary.change_orientation(new_primary.get_orientation())
        self.primary.update_slice(new_primary.get_slice())
        self.primary.handle_projection_change(new_primary.get_projection())

        # Copy visual settings
        self.primary.color_selector.setCurrentText(
            new_primary.color_selector.currentText()
        )
        self.primary.contrast_slider.setValues(
            new_primary.contrast_slider.lower_pos,
            new_primary.contrast_slider.upper_pos,
        )
        self.primary.contrast_value_label.setText(
            new_primary.contrast_value_label.text()
        )
        self.primary.gamma_row.setValue(new_primary.gamma_row.value())

        if new_primary.is_visible != self.primary.is_visible:
            self.primary.toggle_visibility()

        self.remove_viewer(new_primary)
