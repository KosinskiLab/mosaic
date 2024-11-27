import re
import os
from os.path import join


import numpy as np
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QSizePolicy,
    QFileDialog,
    QLineEdit,
    QLabel,
    QSlider,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QDoubleValidator
import vtkmodules.qt
from vtkmodules.util import numpy_support

from ..io import DataIO
from ..parametrization import Ellipsoid


def load_series(path):
    files = [x for x in os.listdir(path) if x.endswith(".tsi")]
    files = sorted(files, key=lambda x: int(re.findall(r"\d+", x)[0]))
    return [DataIO().open_file(join(path, file)) for file in files]


class DevTab(QWidget):
    def __init__(self, cdata):
        super().__init__()
        self.cdata = cdata
        self.cloud_series = None
        self.current_frame = 0
        self.playing = False
        self.play_timer = QTimer()
        self.play_timer.timeout.connect(self.next_frame)
        self.play_timer.setInterval(100)  # 10 FPS default

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

        # Add Cloud button
        add_cloud_button = QPushButton("Add Cloud")
        add_cloud_button.clicked.connect(self.add_cloud)
        add_cloud_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        # Import Cloud button
        import_button = QPushButton("Import Cloud")
        import_button.clicked.connect(self.import_cloud)
        import_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        # Scale factor controls
        scale_layout = QHBoxLayout()
        scale_label = QLabel("Scale Factor:")
        self.scale_input = QLineEdit()
        self.scale_input.setValidator(QDoubleValidator())
        self.scale_input.setText("0.03777476638012516")
        scale_layout.addWidget(scale_label)
        scale_layout.addWidget(self.scale_input)

        # Add all elements to the layout
        buttons_layout.addWidget(add_cloud_button)
        buttons_layout.addWidget(import_button)
        buttons_layout.addLayout(scale_layout)

        main_layout.addLayout(buttons_layout)

    def setup_operations(self, main_layout):
        """Setup the original cloud manipulation controls"""
        buttons_layout = QVBoxLayout()

        distance_button = QPushButton("Make Distance Map")
        distance_button.clicked.connect(self.make_distance_map)
        buttons_layout.addWidget(distance_button)

        export_series_button = QPushButton("Export Video")
        export_series_button.clicked.connect(self.export_series)
        buttons_layout.addWidget(export_series_button)

        main_layout.addLayout(buttons_layout)

    def make_distance_map(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getSaveFileName(self, "Save File")
        if not file_path:
            return -1

        file_path = file_path.replace(".mrc.m", ".mrc")
        sampling_rate = 1
        all_points, all_weights = [], []
        for cloud in self.cdata._data.data:
            if cloud._sampling_rate is None:
                continue
            sampling_rate = cloud._sampling_rate

        shape = self.cdata.shape
        if shape is None:
            shape = (50, 50, 50)
        shape = tuple(int(x) for x in np.divide(shape, sampling_rate).astype(int))
        ret = np.zeros(shape)

        margin = 5
        for cloud in self.cdata._data.data:
            if cloud._sampling_rate is None:
                continue
            sampling_rate = cloud._sampling_rate
            points = cloud.points

            fit = Ellipsoid.fit(points)
            distances = (fit._compute_residual(points) - 1) * -1
            distances = np.exp(
                (distances - distances.min()) / (distances.max() - distances.min())
            )

            points = np.divide(points, cloud._sampling_rate).astype(int)
            ret[tuple(points.T)] += np.maximum(distances, ret[tuple(points.T)])

        from tme import Density, Preprocessor

        ret = np.swapaxes(ret, 0, 2)
        ret = Preprocessor().gaussian_filter(ret, sigma=1)

        dens = Density(ret, sampling_rate=sampling_rate)
        dens.to_file(file_path)

    def setup_player_controls(self, main_layout):
        """Setup the point cloud series player controls"""
        player_layout = QVBoxLayout()

        # Open series button
        open_series_button = QPushButton("Open Series")
        open_series_button.clicked.connect(self.open_series)

        # Frame slider
        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setEnabled(False)
        self.frame_slider.valueChanged.connect(self.slider_changed)

        # Playback controls
        playback_layout = QHBoxLayout()

        # Previous frame button
        prev_button = QPushButton("⏮")
        prev_button.clicked.connect(self.prev_frame)

        # Play/Pause button
        self.play_button = QPushButton("▶")
        self.play_button.clicked.connect(self.toggle_play)

        # Next frame button
        next_button = QPushButton("⏭")
        next_button.clicked.connect(self.next_frame)

        # Frame counter
        self.frame_label = QLabel("Frame: 0/0")

        # Add controls to playback layout
        playback_layout.addWidget(prev_button)
        playback_layout.addWidget(self.play_button)
        playback_layout.addWidget(next_button)
        playback_layout.addWidget(self.frame_label)

        # Add all elements to the player layout
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

        # Assuming load_series exists and returns a list of point clouds
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
        offset = 0
        try:
            scale_factor = float(self.scale_input.text())
        except ValueError:
            scale_factor = 0.03777476638012516

        # scale_factor = 0.005365266062387542
        scale_factor = 0.0055079992690044936
        offset = 22.0

        # scale_factor =0.012626655910736868
        # offset = 19.95996379852295
        points = (self.cloud_series[frame_idx] - offset) / scale_factor
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
        self.cdata.data.render()

    def import_cloud(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Import Point Cloud File",
        )
        if not file_name:
            return -1

        try:
            scale_factor = float(self.scale_input.text())
        except ValueError:
            scale_factor = 0.03777476638012516

        ret = DataIO().open_file(filename=file_name)

        if isinstance(ret, np.ndarray):
            data = [ret]

        if len(ret) == 3:
            data, shape, sampling_rate = ret

        for points in data:
            self.cdata._data.add(points=points / scale_factor)
        self.cdata.data.render()

    def capture_screenshot(self):
        import cv2

        """Capture the current VTK render window as a numpy array"""
        renderer = self.cdata.data.vtk_widget
        render_window = renderer.GetRenderWindow()

        # Create a window to image filter
        window_to_image = vtkmodules.vtkRenderingCore.vtkWindowToImageFilter()
        window_to_image.SetInput(render_window)
        window_to_image.Update()

        # Convert VTK image data to numpy array
        vtk_image = window_to_image.GetOutput()
        width, height, _ = vtk_image.GetDimensions()
        vtk_array = numpy_support.vtk_to_numpy(vtk_image.GetPointData().GetScalars())

        # Reshape and reorder to BGR for OpenCV
        numpy_array = vtk_array.reshape(height, width, -1)
        numpy_array = numpy_array[:, :, :3]  # Keep only RGB channels
        numpy_array = numpy_array[::-1]  # Flip vertically
        numpy_array = cv2.cvtColor(numpy_array, cv2.COLOR_RGB2BGR)

        return numpy_array

    def export_series(self):
        import cv2

        """Export the point cloud series as a video"""
        if not self.cloud_series:
            print("No series loaded to export")
            return

        # Ask for export directory
        export_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Export Directory",
            "",
            QFileDialog.Option.ShowDirsOnly,
        )

        if not export_dir:
            return

        # Create frames directory
        frames_dir = os.path.join(export_dir, "frames")
        os.makedirs(frames_dir, exist_ok=True)

        # Save current frame to restore later
        original_frame = self.current_frame

        # Capture screenshots for each frame
        frame_files = []
        # for frame_idx in range(len(self.cloud_series)):
        for frame_idx in range(100):
            self.display_frame(frame_idx)
            self.cdata.data.vtk_widget.GetRenderWindow().Render()

            # Capture and save screenshot
            screenshot = self.capture_screenshot()
            frame_path = os.path.join(frames_dir, f"frame_{frame_idx:04d}.png")
            cv2.imwrite(frame_path, screenshot)
            frame_files.append(frame_path)

        # Create video from frames
        self.create_video(frame_files, export_dir)

        # Restore original frame
        self.display_frame(original_frame)
        self.frame_slider.setValue(original_frame)

    def create_video(self, frame_files, export_dir, fps=10, frame_stride=1):
        """Create a video from a list of frame files"""
        import cv2

        if not frame_files:
            return

        # Read first frame to get dimensions
        first_frame = cv2.imread(frame_files[0])
        height, width = first_frame.shape[:2]

        # Create video writer
        output_path = os.path.join(export_dir, "output.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        video_writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        # Write frames to video
        for i in range(0, len(frame_files), frame_stride):
            frame = cv2.imread(frame_files[i])
            video_writer.write(frame)

        video_writer.release()
