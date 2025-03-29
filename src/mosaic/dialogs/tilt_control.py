""" Implements TiltControlDialog for controling camera view angles.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QVBoxLayout,
    QLabel,
    QSlider,
    QPushButton,
    QDialog,
    QGroupBox,
)
import qtawesome as qta
from ..stylesheets import QPushButton_style, QGroupBox_style, QSlider_style


class TiltControlDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.setWindowTitle("Camera Controls")
        self.setup_ui()
        try:
            self.setWindowFlags(
                Qt.WindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
                & ~Qt.WindowContextHelpButtonHint
            )
        except AttributeError:
            self.setWindowFlags(
                Qt.WindowType.Dialog
                | Qt.WindowType.WindowStaysOnTopHint
                & ~Qt.WindowType.WindowContextHelpButtonHint
            )
        self.setStyleSheet(QPushButton_style + QGroupBox_style + QSlider_style)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        def create_angle_frame(title, value_label, slider):
            frame = QGroupBox(title)

            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(4, 4, 4, 4)
            frame_layout.setSpacing(2)

            value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            slider.setOrientation(Qt.Orientation.Horizontal)
            slider.setMinimum(-180)
            slider.setMaximum(180)
            slider.setValue(0)
            slider.setTickPosition(QSlider.TickPosition.TicksBelow)
            slider.setTickInterval(30)

            frame_layout.addWidget(value_label)
            frame_layout.addWidget(slider)

            return frame

        self.elevation_value_label = QLabel("0°")
        self.elevation_slider = QSlider()
        self.elevation_slider.valueChanged.connect(self.on_elevation_slider_changed)
        elevation_frame = create_angle_frame(
            "Elevation", self.elevation_value_label, self.elevation_slider
        )

        self.azimuth_value_label = QLabel("0°")
        self.azimuth_slider = QSlider()
        self.azimuth_slider.valueChanged.connect(self.on_azimuth_slider_changed)
        azimuth_frame = create_angle_frame(
            "Azimuth", self.azimuth_value_label, self.azimuth_slider
        )

        self.pitch_value_label = QLabel("0°")
        self.pitch_slider = QSlider()
        self.pitch_slider.valueChanged.connect(self.on_pitch_slider_changed)
        pitch_frame = create_angle_frame(
            "Pitch", self.pitch_value_label, self.pitch_slider
        )

        reset_button = QPushButton(
            qta.icon("fa5s.undo", opacity=0.7, color="gray"), "Reset"
        )
        reset_button.clicked.connect(self.reset_tilt)

        layout.addWidget(elevation_frame)
        layout.addWidget(azimuth_frame)
        layout.addWidget(pitch_frame)
        layout.addWidget(reset_button)

        self.setFixedSize(280, 280)

    def on_elevation_slider_changed(self, value):
        self.elevation_value_label.setText(f"{value}°")
        if not hasattr(self.main_window, "_camera_view"):
            return -1
        self.main_window.set_camera_view(
            self.main_window._camera_view,
            self.main_window._camera_direction,
            value,
            self.azimuth_slider.value(),
            self.pitch_slider.value(),
        )

    def on_azimuth_slider_changed(self, value):
        self.azimuth_value_label.setText(f"{value}°")
        if not hasattr(self.main_window, "_camera_view"):
            return -1
        self.main_window.set_camera_view(
            self.main_window._camera_view,
            self.main_window._camera_direction,
            self.elevation_slider.value(),
            value,
            self.pitch_slider.value(),
        )

    def on_pitch_slider_changed(self, value):
        self.pitch_value_label.setText(f"{value}°")
        if not hasattr(self.main_window, "_camera_view"):
            return -1
        self.main_window.set_camera_view(
            self.main_window._camera_view,
            self.main_window._camera_direction,
            self.elevation_slider.value(),
            self.azimuth_slider.value(),
            value,
        )

    def show(self):
        self.elevation_slider.setValue(
            getattr(self.main_window, "_camera_elevation", 0)
        )
        self.azimuth_slider.setValue(getattr(self.main_window, "_camera_azimuth", 0))
        self.pitch_slider.setValue(getattr(self.main_window, "_camera_pitch", 0))
        super().show()

    def reset_tilt(self):
        self.elevation_slider.setValue(0)
        self.azimuth_slider.setValue(0)
        self.pitch_slider.setValue(0)

    def update_value(self, elevation_value, azimuth_value=None, pitch_value=None):
        self.elevation_slider.blockSignals(True)
        self.elevation_slider.setValue(elevation_value)
        self.elevation_value_label.setText(f"{elevation_value}°")
        self.elevation_slider.blockSignals(False)

        if azimuth_value is not None:
            self.azimuth_slider.blockSignals(True)
            self.azimuth_slider.setValue(azimuth_value)
            self.azimuth_value_label.setText(f"{azimuth_value}°")
            self.azimuth_slider.blockSignals(False)

        if pitch_value is not None:
            self.pitch_slider.blockSignals(True)
            self.pitch_slider.setValue(pitch_value)
            self.pitch_value_label.setText(f"{pitch_value}°")
            self.pitch_slider.blockSignals(False)
