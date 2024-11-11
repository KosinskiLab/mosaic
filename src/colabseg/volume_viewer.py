import vtk
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QSlider,
    QComboBox,
    QPushButton,
    QFileDialog,
    QLabel,
)
from PyQt6.QtCore import Qt, pyqtSignal
from vtkmodules.util import numpy_support
from matplotlib.pyplot import get_cmap

from .io import load_density


_colormaps = ["gray", "gray_r", "viridis", "magma", "twilight_shifted"]


class VolumeViewer(QWidget):
    data_changed = pyqtSignal()

    def __init__(self, vtk_widget, parent=None):
        super().__init__(parent)
        self.vtk_widget = vtk_widget

        self.renderer = (
            self.vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer()
        )

        self.slice_mapper = vtk.vtkImageSliceMapper()
        self.slice = vtk.vtkImageSlice()
        self.volume = None

        # Create widgets
        self.tomogram_label = QLabel("Tomogram:")
        self.open_button = QPushButton("Open")
        self.open_button.clicked.connect(self.open_tomogram)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close_tomogram)

        self.slice_slider = QSlider(Qt.Orientation.Horizontal)
        self.slice_slider.setEnabled(False)
        self.slice_slider.valueChanged.connect(self.update_slice)

        self.orientation_selector = QComboBox()
        self.orientation_selector.addItems(["X", "Y", "Z"])
        self.orientation_selector.currentTextChanged.connect(self.change_orientation)
        self.orientation_selector.setEnabled(False)

        self.color_selector = QComboBox()
        self.color_selector.addItems(_colormaps)
        self.color_selector.currentTextChanged.connect(self.change_color_palette)
        self.color_selector.setEnabled(False)

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

        self.gamma_slider = QSlider(Qt.Orientation.Horizontal)
        self.gamma_slider.setRange(1, 300)
        self.gamma_slider.setValue(100)
        self.gamma_slider.valueChanged.connect(self.update_contrast_and_gamma)
        self.gamma_slider.setEnabled(False)

        # Create labels for current values
        self.slice_value_label = QLabel("0")
        self.contrast_value_label = QLabel("0 - 100")
        self.gamma_value_label = QLabel("1.00")

        self.slice_value_label.setFixedWidth(30)
        self.contrast_value_label.setFixedWidth(80)
        self.gamma_value_label.setFixedWidth(30)

        # Create layout
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.tomogram_label)
        controls_layout.addWidget(self.open_button)
        controls_layout.addWidget(self.close_button)
        controls_layout.addWidget(self.orientation_selector)
        controls_layout.addWidget(self.color_selector)
        controls_layout.addWidget(QLabel("Slice:"))
        controls_layout.addWidget(self.slice_slider)
        controls_layout.addWidget(self.slice_value_label)
        controls_layout.addWidget(QLabel("Contrast:"))
        controls_layout.addWidget(self.min_contrast_slider)
        controls_layout.addWidget(self.max_contrast_slider)
        controls_layout.addWidget(self.contrast_value_label)
        controls_layout.addWidget(QLabel("Gamma:"))
        controls_layout.addWidget(self.gamma_slider)
        controls_layout.addWidget(self.gamma_value_label)

        self.editable_widgets = [
            self.slice_slider,
            self.orientation_selector,
            self.color_selector,
            self.min_contrast_slider,
            self.max_contrast_slider,
            self.gamma_slider,
            self.close_button,
        ]

        layout = QVBoxLayout(self)
        layout.addLayout(controls_layout)
        self.setLayout(layout)

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, volume):
        self._volume = volume
        self.data_changed.emit()

    def open_tomogram(self):
        if self.volume is not None:
            self.close_tomogram()

        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Open Tomogram")
        if file_path is None:
            return -1

        try:
            self.load_volume(file_path)
        except Exception as e:
            print(f"Error opening tomogram: {e}")

    def close_tomogram(self):
        if self.volume is None:
            return -1

        self.orientation_selector.setCurrentIndex(0)

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
        volume = load_density(file_path)

        self.volume = vtk.vtkImageData()
        self.volume.SetDimensions(volume.shape)
        self.volume.SetSpacing(volume.sampling_rate)
        self.volume.AllocateScalars(vtk.VTK_FLOAT, 1)

        volume = numpy_support.numpy_to_vtk(
            volume.data.ravel(order="F"), deep=True, array_type=vtk.VTK_FLOAT
        )
        self.volume.GetPointData().SetScalars(volume)

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
        self.vtk_widget.GetRenderWindow().Render()

    def change_orientation(self, orientation):
        dimensions = self.get_dimensions()
        if orientation == "X":
            self.slice_mapper.SetOrientationToX()
            slider_range = (0, dimensions[0] - 1)
        elif orientation == "Y":
            self.slice_mapper.SetOrientationToY()
            slider_range = (0, dimensions[1] - 1)
        elif orientation == "Z":
            self.slice_mapper.SetOrientationToZ()
            slider_range = (0, dimensions[2] - 1)

        self.slice_slider.setRange(*slider_range)

        self.slice_slider.setValue(0)
        self.slice_mapper.SetSliceNumber(0)

        self.renderer.ResetCamera()
        self.vtk_widget.GetRenderWindow().Render()

    def get_dimensions(self):
        return self.volume.GetDimensions()

    def change_color_palette(self, palette_name):
        self.current_palette = palette_name
        self.update_contrast_and_gamma()

    def update_contrast_and_gamma(self):
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

        color_transfer_function = vtk.vtkColorTransferFunction()

        adjusted_min = min_value + min_contrast * value_range
        adjusted_max = min_value + max_contrast * value_range

        cmap = get_cmap(self.current_palette)
        for i in range(256):
            data_value = min_value + (i / 255.0) * value_range

            x = (data_value - adjusted_min) / (adjusted_max - adjusted_min)
            x = max(0, min(1, x))
            x = x ** (1 / gamma)

            color_transfer_function.AddRGBPoint(data_value, *cmap(x)[0:3])

        self.slice.GetProperty().SetLookupTable(color_transfer_function)
        self.slice.GetProperty().SetUseLookupTableScalarRange(True)

        self.slice.GetProperty().SetColorWindow(value_range)
        self.slice.GetProperty().SetColorLevel(min_value + value_range / 2)

        self.vtk_widget.GetRenderWindow().Render()
