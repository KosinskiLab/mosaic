""" Implements TiltControlDialog for controling camera view angles.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QLabel,
    QSlider,
    QPushButton,
    QDialog,
    QFrame,
)
import qtawesome as qta


class TiltControlDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.setWindowTitle("Camera Controls")
        self.setup_ui()
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        elevation_frame = QFrame()
        elevation_frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Sunken)
        elevation_layout = QVBoxLayout(elevation_frame)
        elevation_layout.setContentsMargins(8, 8, 8, 8)
        elevation_layout.setSpacing(4)
        elevation_title = QLabel("Elevation")
        elevation_title.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.elevation_value_label = QLabel("0°")
        self.elevation_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.elevation_slider = QSlider(Qt.Orientation.Horizontal)
        self.elevation_slider.setMinimum(-180)
        self.elevation_slider.setMaximum(180)
        self.elevation_slider.setValue(0)
        self.elevation_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.elevation_slider.setTickInterval(15)
        self.elevation_slider.valueChanged.connect(self.on_elevation_slider_changed)

        elevation_layout.addWidget(elevation_title)
        elevation_layout.addWidget(self.elevation_value_label)
        elevation_layout.addWidget(self.elevation_slider)

        azimuth_frame = QFrame()
        azimuth_frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Sunken)
        azimuth_layout = QVBoxLayout(azimuth_frame)
        azimuth_layout.setContentsMargins(8, 8, 8, 8)
        azimuth_layout.setSpacing(4)
        azimuth_title = QLabel("Azimuth")
        azimuth_title.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.azimuth_value_label = QLabel("0°")
        self.azimuth_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.azimuth_slider = QSlider(Qt.Orientation.Horizontal)
        self.azimuth_slider.setMinimum(-180)
        self.azimuth_slider.setMaximum(180)
        self.azimuth_slider.setValue(0)
        self.azimuth_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.azimuth_slider.setTickInterval(15)
        self.azimuth_slider.valueChanged.connect(self.on_azimuth_slider_changed)

        azimuth_layout.addWidget(azimuth_title)
        azimuth_layout.addWidget(self.azimuth_value_label)
        azimuth_layout.addWidget(self.azimuth_slider)

        reset_button = QPushButton(
            qta.icon("fa5s.undo", opacity=0.7, color="gray"), "Reset"
        )
        reset_button.clicked.connect(self.reset_tilt)

        layout.addWidget(elevation_frame)
        layout.addWidget(azimuth_frame)
        layout.addWidget(reset_button)

        self.setFixedSize(300, 240)

    def on_elevation_slider_changed(self, value):
        self.elevation_value_label.setText(f"{value}°")
        if not hasattr(self.main_window, "_camera_view"):
            return -1
        self.main_window.set_camera_view(
            self.main_window._camera_view,
            self.main_window._camera_direction,
            value,
            self.azimuth_slider.value(),
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
        )

    def show(self):
        self.elevation_slider.setValue(getattr(self.main_window, "_camera_tilt", 0))
        self.azimuth_slider.setValue(
            getattr(self.main_window, "_camera_second_tilt", 0)
        )
        super().show()

    def reset_tilt(self):
        self.elevation_slider.setValue(0)
        self.azimuth_slider.setValue(0)

    def update_value(self, elevation_value, azimuth_value=None):
        self.elevation_slider.blockSignals(True)
        self.elevation_slider.setValue(elevation_value)
        self.elevation_value_label.setText(f"{elevation_value}°")
        self.elevation_slider.blockSignals(False)

        if azimuth_value is not None:
            self.azimuth_slider.blockSignals(True)
            self.azimuth_slider.setValue(azimuth_value)
            self.azimuth_value_label.setText(f"{azimuth_value}°")
            self.azimuth_slider.blockSignals(False)
