import re
import os
from os.path import join
from shutil import rmtree


import numpy as np
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QSizePolicy,
    QFileDialog,
    QLabel,
    QSlider,
    QDoubleSpinBox,
)
from PyQt6.QtCore import Qt, QTimer
import vtkmodules.qt
from vtkmodules.util import numpy_support

from ..io import DataIO, import_points


def load_series(path):
    files = [x for x in os.listdir(path) if x.endswith(".tsi")]
    files = sorted(files, key=lambda x: int(re.findall(r"\d+", x)[0]))
    return [DataIO().open_file(join(path, file)) for file in files]


class DevTab(QWidget):
    def __init__(self, cdata, volume_viewer):
        super().__init__()
        self.cdata = cdata
        self.cloud_series = None
        self.current_frame = 0
        self.playing = False
        self.play_timer = QTimer()
        self.play_timer.timeout.connect(self.next_frame)
        self.play_timer.setInterval(100)
        self.volume_viewer = volume_viewer

        self.setup_ui()

    def setup_ui(self):
        layout_spacing = 5
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(layout_spacing)
        self.setup_basic_controls(main_layout)
        self.setup_operations(main_layout)
        self.setup_player_controls(main_layout)

    def setup_basic_controls(self, main_layout):
        """Setup the original cloud manipulation controls"""
        buttons_layout = QVBoxLayout()

        add_cloud_button = QPushButton("Add Cloud")
        add_cloud_button.clicked.connect(self.add_cloud)
        add_cloud_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        import_button = QPushButton("Import Cloud")
        import_button.clicked.connect(self.import_cloud)
        import_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        scale_layout = QHBoxLayout()
        scale_label = QLabel("Scale Factor:")
        self.scale_input = QDoubleSpinBox()
        self.scale_input.setValue(1.0)
        self.scale_input.setDecimals(18)
        scale_layout.addWidget(scale_label)
        scale_layout.addWidget(self.scale_input)

        offset_layout = QHBoxLayout()
        offset_label = QLabel("Offset:")
        self.offset_input = QDoubleSpinBox()
        self.offset_input.setValue(0)
        offset_layout.addWidget(offset_label)
        offset_layout.addWidget(self.offset_input)

        buttons_layout.addWidget(add_cloud_button)
        buttons_layout.addWidget(import_button)
        buttons_layout.addLayout(scale_layout)
        buttons_layout.addLayout(offset_layout)

        main_layout.addLayout(buttons_layout)

    def setup_operations(self, main_layout):
        """Setup the original cloud manipulation controls"""
        buttons_layout = QVBoxLayout()

        export_series_button = QPushButton("Export Video")
        export_series_button.clicked.connect(self.export_series)
        buttons_layout.addWidget(export_series_button)

        export_series_button = QPushButton("Export Slice Video")
        export_series_button.clicked.connect(self.export_slices)
        buttons_layout.addWidget(export_series_button)

        main_layout.addLayout(buttons_layout)

    def setup_player_controls(self, main_layout):
        """Setup the point cloud series player controls"""
        player_layout = QVBoxLayout()
        open_series_button = QPushButton("Open Series")
        open_series_button.clicked.connect(self.open_series)

        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setEnabled(False)
        self.frame_slider.valueChanged.connect(self.slider_changed)

        playback_layout = QHBoxLayout()
        prev_button = QPushButton("⏮")
        prev_button.clicked.connect(self.prev_frame)

        self.play_button = QPushButton("▶")
        self.play_button.clicked.connect(self.toggle_play)

        next_button = QPushButton("⏭")
        next_button.clicked.connect(self.next_frame)
        self.frame_label = QLabel("Frame: 0/0")

        playback_layout.addWidget(prev_button)
        playback_layout.addWidget(self.play_button)
        playback_layout.addWidget(next_button)
        playback_layout.addWidget(self.frame_label)

        player_layout.addWidget(open_series_button)
        player_layout.addWidget(self.frame_slider)
        player_layout.addLayout(playback_layout)

        main_layout.addLayout(player_layout)

    def open_series(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Directory with Point Cloud Series",
            "",
            QFileDialog.Option.ShowDirsOnly,
        )
        if not directory:
            return

        self.cloud_series = load_series(directory)
        self.cloud = None

        if self.cloud_series:
            self.current_frame = 0
            self.frame_slider.setMinimum(0)
            self.frame_slider.setMaximum(len(self.cloud_series) - 1)
            self.frame_slider.setValue(0)
            self.frame_slider.setEnabled(True)
            self.frame_label.setText(f"Frame: 0/{len(self.cloud_series) - 1}")
            self.display_frame(0)

    def slider_changed(self, value):
        self.current_frame = value
        self.frame_label.setText(f"Frame: {value}/{len(self.cloud_series) - 1}")
        self.display_frame(value)

    def display_frame(self, frame_idx):
        scale = self.scale_input.value()
        offset = self.offset_input.value()

        points = (self.cloud_series[frame_idx] - offset) / scale
        if self.cloud is None:
            index = self.cdata._data.add(points=points)
            self.cloud = self.cdata._data.data[index]
        self.cloud.swap_data(points)
        self.cdata.data.render()

    def next_frame(self):
        if self.cloud_series and self.current_frame < len(self.cloud_series) - 1:
            self.current_frame += 1
            self.frame_slider.setValue(self.current_frame)
        elif self.playing:
            self.toggle_play()

    def prev_frame(self):
        if self.cloud_series and self.current_frame > 0:
            self.current_frame -= 1
            self.frame_slider.setValue(self.current_frame)

    def toggle_play(self):
        if not self.cloud_series:
            return

        self.playing = not self.playing
        if self.playing:
            self.play_button.setText("⏸")
            self.play_timer.start()
        else:
            self.play_button.setText("▶")
            self.play_timer.stop()

    def add_cloud(self, *args):
        num_points = 1000
        points = np.random.rand(num_points, 3) * 100
        self.cdata._data.add(points=points, sampling_rate=1)
        self.cdata.data.data_changed.emit()
        self.cdata.data.render()

    def import_cloud(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Import Point Cloud File",
        )
        if not file_name:
            return -1

        scale = self.scale_input.value()
        offset = self.offset_input.value()
        for points in import_points(file_name, scale, offset):
            self.cdata._data.add(points=points)
        self.cdata.data.render()

    def capture_screenshot(self):
        import cv2

        renderer = self.cdata.data.vtk_widget
        render_window = renderer.GetRenderWindow()

        window_to_image = vtkmodules.vtkRenderingCore.vtkWindowToImageFilter()
        window_to_image.SetInput(render_window)
        window_to_image.Update()

        vtk_image = window_to_image.GetOutput()
        width, height, _ = vtk_image.GetDimensions()
        vtk_array = numpy_support.vtk_to_numpy(vtk_image.GetPointData().GetScalars())

        numpy_array = vtk_array.reshape(height, width, -1)
        numpy_array = numpy_array[:, :, :3]
        numpy_array = numpy_array[::-1]
        numpy_array = cv2.cvtColor(numpy_array, cv2.COLOR_RGB2BGR)

        return numpy_array

    def export_series(self):
        import cv2

        if not self.cloud_series:
            print("No series loaded to export")
            return

        export_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Export Directory",
            "",
            QFileDialog.Option.ShowDirsOnly,
        )

        if not export_dir:
            return

        frames_dir = os.path.join(export_dir, "frames")
        os.makedirs(frames_dir, exist_ok=True)
        original_frame = self.current_frame

        frame_files = []
        for frame_idx in range(0, len(self.cloud_series)):
            self.display_frame(frame_idx)
            self.cdata.data.vtk_widget.GetRenderWindow().Render()

            screenshot = self.capture_screenshot()
            frame_path = os.path.join(frames_dir, f"frame_{frame_idx:04d}.png")
            cv2.imwrite(frame_path, screenshot)
            frame_files.append(frame_path)

        self.create_video(frame_files, export_dir)

        self.display_frame(original_frame)
        self.frame_slider.setValue(original_frame)
        rmtree(frames_dir)

    def export_slices(self):
        import cv2

        export_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Export Directory",
            "",
            QFileDialog.Option.ShowDirsOnly,
        )

        if not export_dir:
            return

        frames_dir = os.path.join(export_dir, "slices")
        os.makedirs(frames_dir, exist_ok=True)

        frame_files = []
        slice_min = self.volume_viewer.slice_slider.minimum()
        slice_max = self.volume_viewer.slice_slider.maximum()
        for slice_idx in range(slice_min, slice_max):
            self.volume_viewer.slice_slider.setValue(slice_idx)

            screenshot = self.capture_screenshot()
            frame_path = os.path.join(frames_dir, f"frame_{slice_idx:04d}.png")
            cv2.imwrite(frame_path, screenshot)
            frame_files.append(frame_path)

        self.create_video(frame_files, export_dir)
        rmtree(frames_dir)

    def create_video(self, frame_files, export_dir, fps=10, frame_stride=1):
        import cv2

        if not frame_files:
            return

        first_frame = cv2.imread(frame_files[0])
        height, width = first_frame.shape[:2]

        output_path = os.path.join(export_dir, "output.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        video_writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        for i in range(0, len(frame_files), frame_stride):
            frame = cv2.imread(frame_files[i])
            video_writer.write(frame)

        video_writer.release()
