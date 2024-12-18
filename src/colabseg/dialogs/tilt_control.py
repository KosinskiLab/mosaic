from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QLabel,
    QSlider,
    QPushButton,
    QDialog,
)
import qtawesome as qta


class TiltControlDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.setWindowTitle("Camera Tilt")
        self.setup_ui()

        self.setWindowFlags(
            Qt.Dialog | Qt.WindowStaysOnTopHint & ~Qt.WindowContextHelpButtonHint
        )

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.value_label = QLabel("0°")
        self.value_label.setAlignment(Qt.AlignCenter)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(-180)
        self.slider.setMaximum(180)
        self.slider.setValue(0)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.slider.setTickInterval(15)
        self.slider.valueChanged.connect(self.on_slider_changed)

        reset_button = QPushButton(
            qta.icon("fa5s.undo", opacity=0.7, color="gray"), "Reset"
        )
        reset_button.clicked.connect(self.reset_tilt)

        layout.addWidget(self.value_label)
        layout.addWidget(self.slider)
        layout.addWidget(reset_button)

        self.setFixedSize(300, 120)

    def on_slider_changed(self, value):
        self.value_label.setText(f"{value}°")
        if not hasattr(self.main_window, "_camera_view"):
            return -1

        self.main_window.set_camera_view(
            self.main_window._camera_view, self.main_window._camera_direction, value
        )

    def show(self):
        self.slider.setValue(getattr(self.main_window, "_camera_tilt", 0))
        super().show()

    def reset_tilt(self):
        self.slider.setValue(0)

    def update_value(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(value)
        self.value_label.setText(f"{value}°")
        self.slider.blockSignals(False)
