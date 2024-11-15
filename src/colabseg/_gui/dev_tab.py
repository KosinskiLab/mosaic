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
from hmff.utils import read_topology_file


from ..io import DataIO, _compute_bounding_box
from ..parametrization import Ellipsoid
from ..utils import points_to_volume

import re
from os import listdir
from os.path import join


def load_series(path):
    ret = []
    files = [x for x in listdir(path) if x.endswith(".tsi")]
    files = sorted(files, key=lambda x: int(re.findall(r"\d+", x)[0]))

    for file in files:
        data = read_topology_file(join(path, file))
        ret.append(data["vertices"][:, 1:4])

    return ret


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

        scale_factor = 0.00906220370306874
        offset = 20.011848400346935
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

        data, shape, sampling = DataIO().open_file(filename=file_name)
        for points in data:
            self.cdata._data.add(
                points=points * 1 / scale_factor, sampling_rate=sampling
            )
        self.cdata.data.render()
