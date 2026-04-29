"""
Implements volume viewer widget.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from contextlib import contextmanager

import vtk
from qtpy.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QComboBox,
    QPushButton,
    QFileDialog,
    QLabel,
)
from ..icons import icon as _icon_factory
from .message_box import MosaicMessageBox

from qtpy.QtCore import Signal
from vtkmodules.util import numpy_support

from ..utils import Throttle
from ..stylesheets import Colors
from .colors import ColorMapSelector
from .sliders import SliderRow, DualHandleSlider

_VTK_READERS = {
    ".mrc": "vtkMRCReader",
    ".nii": "vtkNIFTIImageReader",
    ".nii.gz": "vtkNIFTIImageReader",
    ".nrrd": "vtkNrrdReader",
}

_VTK_MRC_MODES = {0, 1, 2, 6}


def _load_vtk_image(filepath):
    """Load *filepath* via a native VTK reader, or return *None*."""
    import struct

    lower = filepath.lower()
    cls_name = next(
        (name for ext, name in _VTK_READERS.items() if lower.endswith(ext)),
        None,
    )
    if cls_name is None:
        return None

    if cls_name == "vtkMRCReader":
        try:
            with open(filepath, "rb") as fh:
                fh.seek(12)
                if struct.unpack("<i", fh.read(4))[0] not in _VTK_MRC_MODES:
                    return None
        except Exception:
            return None

    cls = getattr(vtk, cls_name, None)
    if cls is None:
        return None

    reader = cls()
    reader.SetFileName(filepath)
    reader.Update()
    return reader.GetOutput()


def _load_density_image(filepath):
    """Load *filepath* via load_density and wrap in a vtkImageData."""
    from ..formats.parser import load_density

    density = load_density(filepath, use_memmap=True)
    image = vtk.vtkImageData()
    image.SetDimensions(density.shape)
    image.SetSpacing(density.sampling_rate)
    image.GetPointData().SetScalars(
        numpy_support.numpy_to_vtk(
            density.data.ravel(order="F"), deep=False, array_type=vtk.VTK_FLOAT
        )
    )
    return image


class VolumeViewer(QWidget):
    data_changed = Signal()

    def __init__(self, vtk_widget, legend=None, parent=None):
        super().__init__(parent)
        self._rendering_suspended = False
        self.vtk_widget = vtk_widget
        self.legend = legend
        self.renderer = (
            self.vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer()
        )

        self.slice_mapper = vtk.vtkImageSliceMapper()
        self.slice = vtk.vtkImageSlice()
        self._source_path = None
        self._volume = None
        self._streaming = False
        self._zarr_source = None
        self._scalar_range = (0.0, 1.0)
        self._orientation_mapping = {"X": 0, "Y": 1, "Z": 2}
        self.is_visible = True
        self.current_palette = "gray"
        self.clipping_plane = vtk.vtkPlane()
        self.clipping_direction = 1

        self._build_ui()

    def _build_ui(self):

        self.open_button = QPushButton("Load")
        self.open_button.clicked.connect(self.open_volume)
        self.open_button.setStyleSheet(
            "QPushButton { border-top-right-radius: 0;"
            " border-bottom-right-radius: 0; margin-right: 0; }"
        )

        self._path_combo = QComboBox()
        self._path_combo.setFixedWidth(20)
        self._path_combo.setStyleSheet(
            "QComboBox { border-top-left-radius: 0;"
            " border-bottom-left-radius: 0; border-left: none; }"
        )
        self._path_combo.activated.connect(self._on_path_selected)

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close_volume)

        self.visibility_button = self._icon_button(
            "ph.eye", "Toggle volume visibility", self.toggle_visibility
        )
        self.auto_contrast_button = self._icon_button(
            "ph.magic-wand",
            "Auto contrast (percentile-based)",
            lambda: self.auto_contrast(),
        )

        self.slice_row = SliderRow(
            label="Slice",
            min_val=0,
            max_val=100,
            default=0,
            decimals=0,
            label_position="right",
        )
        self._slice_throttle = Throttle(
            lambda v: self.update_slice(int(v)), interval_ms=30
        )
        self.slice_row.valueChanged.connect(self._slice_throttle)

        self.orientation_selector = QComboBox()
        self.orientation_selector.addItems(["X", "Y", "Z"])
        self.orientation_selector.setCurrentText("Z")
        self.orientation_selector.currentTextChanged.connect(self.change_orientation)

        self.color_selector = ColorMapSelector(default=self.current_palette)
        self.color_selector.setMinimumWidth(120)
        self.color_selector.setFixedHeight(Colors.WIDGET_HEIGHT)
        self.color_selector.colormapChanged.connect(self.change_color_palette)

        self.contrast_label = QLabel("Contrast:")
        self.contrast_slider = DualHandleSlider()
        self.contrast_slider.setRange(0, 100)
        self.contrast_slider.setValues(0, 100)
        self._contrast_throttle = Throttle(
            self.update_contrast_and_gamma, interval_ms=50
        )
        self.contrast_slider.rangeChanged.connect(self._contrast_throttle)
        self.contrast_value_label = QLabel("0.00 - 1.00")
        self.contrast_value_label.setFixedWidth(70)

        self.gamma_row = SliderRow(
            label="Gamma",
            min_val=0.01,
            max_val=3.0,
            default=1.0,
            decimals=2,
            label_position="right",
        )
        self.gamma_row.valueChanged.connect(self._contrast_throttle)

        self.project_selector = QComboBox()
        self.project_selector.addItems(["Off", "Project +", "Project -"])
        self.project_selector.currentTextChanged.connect(self.handle_projection_change)

        self.controls_layout = QHBoxLayout()

        load_group = QHBoxLayout()
        load_group.setSpacing(0)
        load_group.setContentsMargins(0, 0, 0, 0)
        load_group.addWidget(self.open_button)
        load_group.addWidget(self._path_combo)
        self.controls_layout.addLayout(load_group)

        self.controls_layout.addWidget(self.close_button)
        self.controls_layout.addWidget(self.orientation_selector)
        self.controls_layout.addWidget(self.color_selector)
        self.controls_layout.addWidget(self.visibility_button)
        self.controls_layout.addWidget(self.auto_contrast_button)
        self.controls_layout.addWidget(self.slice_row, 2)
        self.controls_layout.addWidget(self.contrast_label)
        self.controls_layout.addWidget(self.contrast_slider, 1)
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
            self.auto_contrast_button,
            self.project_selector,
        ]
        self.change_widget_state(False)

        layout = QVBoxLayout(self)
        layout.addLayout(self.controls_layout)
        self.setLayout(layout)

    def _icon_button(self, icon_name, tooltip, callback):
        btn = QPushButton()
        btn.setIcon(_icon_factory(icon_name, role="muted"))
        btn.setFixedWidth(30)
        btn.setToolTip(tooltip)
        btn.clicked.connect(callback)
        btn.setEnabled(False)
        return btn

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, volume):
        self._volume = volume
        self.data_changed.emit()

    @property
    def source_path(self):
        return self._source_path

    def load_volume(self, source):
        """Load a volume from a local file path or remote Zarr URL."""
        if self.volume is not None:
            self._close_volume()

        self._source_path = source
        if isinstance(source, str) and (
            source.startswith("s3://") or source.endswith(".zarr")
        ):
            return self._load_zarr(source)

        self.volume = _load_vtk_image(source)
        if self.volume is None:
            self.volume = _load_density_image(source)

        self.slice_mapper.SetInputData(self.volume)
        self.slice_mapper.StreamingOff()
        self._setup_after_load()

    def _load_zarr(self, source):
        from ..formats.stream import open_omezarr

        self._streaming = True
        self._zarr_source, info = open_omezarr(source)
        self._zarr_source.set_on_chunk_ready(self._on_zarr_slice_ready)

        z, y, x = self._zarr_source.shape
        self.volume = vtk.vtkImageData()
        self.volume.SetDimensions(x, y, z)
        self.volume.SetSpacing(*self._zarr_source.spacing)
        self.slice_mapper.SetInputConnection(self._zarr_source.GetOutputPort())
        self.slice_mapper.StreamingOn()
        self._setup_after_load()
        self._install_lod_observer()

    def swap_volume(self, new_volume):
        """Replace the current volume with a pre-built vtkImageData."""
        self._remove_lod_observer()
        self._streaming = False
        self._zarr_source = None
        self.volume = new_volume
        self.slice_mapper.SetInputData(self.volume)
        self.slice_mapper.StreamingOff()
        self._setup_after_load()

    def _rebuild_load_menu(self, paths=None):
        import os

        self._path_combo.blockSignals(True)
        self._path_combo.clear()
        for path in paths or []:
            self._path_combo.addItem(os.path.basename(path), path)
        self._path_combo.setCurrentIndex(-1)
        self._path_combo.blockSignals(False)

    def _on_path_selected(self, index):
        path = self._path_combo.itemData(index)
        if path:
            self._load_from_path(path)
        self._path_combo.setCurrentIndex(-1)

    def _load_from_path(self, path):
        try:
            self.load_volume(path)
        except Exception as e:
            MosaicMessageBox.warning(self, "Error", f"Failed to open volume:\n{e}")

    def open_volume(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Volume")
        if not file_path:
            return -1

        try:
            self.load_volume(file_path)
        except Exception as e:
            MosaicMessageBox.warning(self, "Error", f"Failed to open volume:\n{e}")

    def _close_volume(self):
        self._remove_lod_observer()
        self._source_path = None
        self.volume = None
        self._streaming = False
        self._zarr_source = None
        self._scalar_range = (0.0, 1.0)

        self.renderer.RemoveViewProp(self.slice)
        self.slice.SetMapper(None)
        self.slice_mapper = vtk.vtkImageSliceMapper()
        self.slice = vtk.vtkImageSlice()

    def close_volume(self):
        if self.volume is None:
            return -1

        self.contrast_slider.setValues(0, 100)
        self.contrast_value_label.setText("0.00 - 1.00")
        self.gamma_row.setValue(1.0)
        self.orientation_selector.setCurrentText("Z")
        self.project_selector.setCurrentText("Off")
        self.set_visibility(False)

        self._close_volume()
        self.change_widget_state(is_enabled=False)
        self._render()

    def _render(self):
        if not self._rendering_suspended:
            self.vtk_widget.GetRenderWindow().Render()

    def _on_zarr_slice_ready(self, *_):
        if self._zarr_source is not None:
            self._zarr_source.Modified()
        self._render()
        self.auto_contrast()

    @contextmanager
    def _suspend_rendering(self):
        self._rendering_suspended = True
        try:
            yield
        finally:
            self._rendering_suspended = False
            self._render()

    def _setup_after_load(self):
        with self._suspend_rendering():
            self.change_orientation(self.orientation_selector.currentText())
            self.slice.SetMapper(self.slice_mapper)
            self.renderer.AddViewProp(self.slice)
            self.change_widget_state(is_enabled=True)
            self.auto_contrast()
            self.set_visibility(True)
            self.renderer.ResetCamera()

    def change_widget_state(self, is_enabled: bool = False):
        for widget in self.editable_widgets:
            widget.setEnabled(is_enabled)

    def toggle_visibility(self):
        return self.set_visibility(not self.slice.GetVisibility())

    def set_visibility(self, visible: bool):
        self.is_visible = visible
        self.slice.SetVisibility(visible)
        icon = "ph.eye" if visible else "ph.eye-slash"
        tip = "Hide volume" if visible else "Show volume"
        self.visibility_button.setIcon(_icon_factory(icon, role="muted"))
        self.visibility_button.setToolTip(tip)
        self._render()

    def set_slice(self, slice_number: int):
        self.slice_row.slider.blockSignals(True)
        self.slice_row.setValue(slice_number)
        self.slice_row.slider.blockSignals(False)
        self.update_slice(slice_number)

    def update_slice(self, slice_number):
        self.slice_mapper.SetSliceNumber(slice_number)
        self.update_clipping_plane()
        self._render()

    def change_orientation(self, orientation):
        dimensions = self.get_dimensions()
        {
            "X": self.slice_mapper.SetOrientationToX,
            "Y": self.slice_mapper.SetOrientationToY,
            "Z": self.slice_mapper.SetOrientationToZ,
        }.get(orientation, lambda: None)()

        self._orientation = orientation
        dim = self._orientation_mapping.get(orientation, 0)
        self.slice_row.setRange(0, dimensions[dim] - 1)

        mid = dimensions[dim] // 2
        self.slice_row.setValue(mid)
        self.slice_mapper.SetSliceNumber(mid)
        self.update_clipping_plane()
        self._render()

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
        self._render()

    def _current_slice_extractor(self):
        """Return a vtkExtractVOI configured for the current slice."""
        if self.volume is None:
            return None

        dims = self.volume.GetDimensions()
        dim = self._orientation_mapping[self.orientation_selector.currentText()]
        idx = self.slice_mapper.GetSliceNumber()

        voi = [0, dims[0] - 1, 0, dims[1] - 1, 0, dims[2] - 1]
        voi[2 * dim] = idx
        voi[2 * dim + 1] = idx

        extractor = vtk.vtkExtractVOI()
        if self._streaming and self._zarr_source is not None:
            extractor.SetInputConnection(self._zarr_source.GetOutputPort())
        else:
            extractor.SetInputData(self.volume)
        extractor.SetVOI(*voi)
        return extractor

    def auto_contrast(self, low_pct: float = 0.01, high_pct: float = 99.9):
        """Set contrast from percentile thresholds of the current slice."""
        extractor = self._current_slice_extractor()
        if extractor is None:
            return

        stats = vtk.vtkImageHistogramStatistics()
        stats.SetInputConnection(extractor.GetOutputPort())
        stats.SetAutoRangePercentiles(low_pct, high_pct)
        stats.Update()

        min_value, max_value = stats.GetMinimum(), stats.GetMaximum()
        self._scalar_range = (min_value, max_value)

        low_val, high_val = stats.GetAutoRange()
        if low_val == high_val:
            high_val = max_value

        value_range = max_value - min_value
        if value_range <= 0:
            return None

        import numpy as np

        low_pos = np.clip(100.0 * (low_val - min_value) / value_range, 0, 100)
        high_pos = np.clip(100.0 * (high_val - min_value) / value_range, 0, 100)
        self.contrast_slider.setValues(low_pos, high_pos)
        self.update_contrast_and_gamma()

    def update_contrast_and_gamma(self, *args):
        from ..utils import cmap_to_vtkctf

        min_value, max_value = getattr(self, "_scalar_range", (0.0, 1.0))
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

        prop = self.slice.GetProperty()
        prop.SetLookupTable(ctf)
        prop.SetUseLookupTableScalarRange(True)
        prop.SetColorWindow(value_range)
        prop.SetColorLevel(min_value + value_range / 2)
        self._render()

    def update_clipping_plane(self):
        if self.volume is None or self.project_selector.currentText() == "Off":
            return

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
            return

        planes.InitTraversal()
        for j in range(planes.GetNumberOfItems()):
            plane = planes.GetNextItem()
            if plane == self.clipping_plane:
                mapper.RemoveClippingPlane(self.clipping_plane)

    def handle_projection_change(self, state=None):
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

        self._render()

    def _world_per_pixel(self):
        camera = self.renderer.GetActiveCamera()
        render_window = self.vtk_widget.GetRenderWindow()
        _, _, w, h = self.renderer.GetViewport()
        win_w, win_h = render_window.GetSize()
        viewport_h = int(h * win_h)
        if viewport_h == 0:
            return 1.0
        return 2.0 * camera.GetParallelScale() / viewport_h

    def _on_camera_interaction(self, obj=None, event=None):
        if not self._streaming or self._zarr_source is None:
            return
        from ..formats.stream import pick_level

        wpp = self._world_per_pixel()
        spacings = self._zarr_source.level_spacings
        new_level = pick_level(spacings, wpp)
        if new_level == self._zarr_source.level:
            return
        self._switch_zarr_level(new_level)

    def _switch_zarr_level(self, new_level):
        old_shape = self._zarr_source.shape
        old_slice = self.slice_mapper.GetSliceNumber()
        old_dim = self._orientation_mapping.get(
            self.orientation_selector.currentText(), 0
        )

        self._zarr_source.set_level(new_level)
        self._zarr_source.Modified()

        new_shape = self._zarr_source.shape
        z, y, x = new_shape
        self.volume.SetDimensions(x, y, z)
        self.volume.SetSpacing(*self._zarr_source.spacing)

        ratio = new_shape[old_dim] / old_shape[old_dim] if old_shape[old_dim] else 1
        new_slice = int(old_slice * ratio)

        dims = (x, y, z)
        dim = self._orientation_mapping.get(self.orientation_selector.currentText(), 0)
        self.slice_row.blockSignals(True)
        self.slice_row.setRange(0, dims[dim] - 1)
        self.slice_row.setValue(new_slice)
        self.slice_row.blockSignals(False)

        self.slice_mapper.SetSliceNumber(new_slice)
        self._render()

    def _install_lod_observer(self):
        interactor = self.vtk_widget.GetRenderWindow().GetInteractor()
        cb = lambda obj, evt: self._on_camera_interaction()
        self._lod_observer_ids = [
            interactor.AddObserver("MouseWheelForwardEvent", cb),
            interactor.AddObserver("MouseWheelBackwardEvent", cb),
        ]

    def _remove_lod_observer(self):
        if hasattr(self, "_lod_observer_ids"):
            interactor = self.vtk_widget.GetRenderWindow().GetInteractor()
            for oid in self._lod_observer_ids:
                interactor.RemoveObserver(oid)
            del self._lod_observer_ids
