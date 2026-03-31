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
    QGroupBox,
    QMessageBox,
)
import qtawesome as qta

from qtpy.QtCore import Signal
from vtkmodules.util import numpy_support

from ..utils import Throttle
from .colors import ColorMapSelector
from .sliders import SliderRow, DualHandleSlider
from ..stylesheets import QPushButton_style, Colors


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
    _zarr_ready = Signal(object, object)

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
        self._zarr_ready.connect(self._finish_zarr_load)

        self._orientation_mapping = {"X": 0, "Y": 1, "Z": 2}
        self.is_visible = True
        self.current_palette = "gray"
        self.clipping_plane = vtk.vtkPlane()
        self.clipping_direction = 1

        self._build_ui()

    def _build_ui(self):
        self.open_button = QPushButton("Load")
        self.open_button.clicked.connect(self.open_volume)

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

        # self.color_selector = QLabel("Contrast:")
        self.color_selector = ColorMapSelector(default=self.current_palette)
        self.color_selector.setMinimumWidth(120)
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
        self.contrast_value_label.setFixedWidth(80)

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
        self.controls_layout.addWidget(self.open_button)
        self.controls_layout.addWidget(self.close_button)
        self.controls_layout.addWidget(self.orientation_selector)
        self.controls_layout.addWidget(self.color_selector)
        self.controls_layout.addWidget(self.visibility_button)
        self.controls_layout.addWidget(self.auto_contrast_button)
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
            self.auto_contrast_button,
            self.project_selector,
        ]
        self.change_widget_state(False)

        layout = QVBoxLayout(self)
        layout.addLayout(self.controls_layout)
        self.setLayout(layout)
        self.setStyleSheet(QPushButton_style)

    def _icon_button(self, icon_name, tooltip, callback):
        btn = QPushButton()
        btn.setIcon(qta.icon(icon_name, color=Colors.ICON))
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
        import threading

        self._streaming = True
        self._zarr_source = None

        def _open():
            try:
                from ..formats.czi.zarr_source import open_omezarr

                zarr_src, info = open_omezarr(
                    source,
                    on_slice_ready=self._on_zarr_slice_ready,
                )
                self._zarr_ready.emit(zarr_src, info)
            except Exception as e:
                print(f"Zarr open error: {e}")

        threading.Thread(target=_open, daemon=True).start()

    def _finish_zarr_load(self, zarr_src, info):
        self._zarr_source = zarr_src
        z, y, x = info["shape"]
        self.volume = vtk.vtkImageData()
        self.volume.SetDimensions(x, y, z)
        self.volume.SetSpacing(*info["spacing"])
        self.slice_mapper.SetInputConnection(zarr_src.GetOutputPort())
        self.slice_mapper.StreamingOn()
        self._setup_after_load()

    def _on_zarr_slice_ready(self):
        from qtpy.QtCore import QTimer

        QTimer.singleShot(0, self._zarr_rerender)

    def _zarr_rerender(self):
        if self._zarr_source is not None:
            self._zarr_source.Modified()
        self._render()

    def swap_volume(self, new_volume):
        """Replace the current volume with a pre-built vtkImageData."""
        self._streaming = False
        self._zarr_source = None
        self.volume = new_volume
        self.slice_mapper.SetInputData(self.volume)
        self.slice_mapper.StreamingOff()
        self._setup_after_load()

    def open_volume(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Volume")
        if not file_path:
            return -1

        try:
            self.load_volume(file_path)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open volume:\n{e}")

    def _close_volume(self):
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
        self.color_selector.setCurrentText("gray")
        self.project_selector.setCurrentText("Off")

        self._close_volume()
        self.change_widget_state(is_enabled=False)
        self._render()

    def _render(self):
        if not self._rendering_suspended:
            self.vtk_widget.GetRenderWindow().Render()

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
        self.visibility_button.setIcon(qta.icon(icon, color=Colors.ICON))
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


class MultiVolumeViewer(QWidget):
    """Container widget for managing multiple VolumeViewer instances."""

    def __init__(self, vtk_widget, legend=None, parent=None):
        super().__init__(parent)
        self.vtk_widget = vtk_widget
        self.legend = legend

        self.setStyleSheet("QPushButton:hover { background-color: #f3f4f6; }")

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

        add_button = QPushButton()
        add_button.setIcon(qta.icon("ph.plus", color=Colors.ICON))
        add_button.setFixedWidth(30)
        add_button.clicked.connect(self.add_viewer)
        self.primary.controls_layout.addWidget(add_button)
        self.primary.close_button.clicked.connect(self._promote_new_primary)

        self.additional_viewers = []

    def add_viewer(self):
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
        if self.primary.volume is None:
            new_viewer.change_widget_state(False)
            return 0
        return new_viewer.swap_volume(self.primary.volume)

    def _promote_new_primary(self) -> int:
        viewers = [
            x for x in self.additional_viewers if getattr(x, "volume") is not None
        ]
        if not len(viewers):
            return None

        new_primary = viewers[0]
        self.primary._source_path = new_primary._source_path
        self.primary.swap_volume(new_primary.volume)
        self.primary.change_orientation(new_primary.get_orientation())
        self.primary.update_slice(new_primary.get_slice())
        self.primary.handle_projection_change(new_primary.get_projection())

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
