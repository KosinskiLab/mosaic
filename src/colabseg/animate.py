""" Screenshot and video export functionalities for vtk viewer.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import Callable
from os.path import splitext

try:
    import cv2
except Exception:
    print("Run: 'pip install opencv-python' for export functionality.")
    cv2 = None

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QComboBox,
    QPushButton,
    QGroupBox,
    QRadioButton,
    QFileDialog,
    QMessageBox,
    QGridLayout,
    QProgressDialog,
    QApplication,
)
from PyQt6.QtGui import QImage, QGuiApplication

from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
from vtkmodules.util import numpy_support


class FrameWriter:
    def __init__(self, filename):
        self.index = 0
        self.filename, self.ext = splitext(filename)

    def write(self, img):
        cv2.imwrite(f"{self.filename}_{self.index}{self.ext}", img)
        self.index += 1

    def release(self):
        self.index = 0


class AnimationSettingsDialog(QDialog):
    def __init__(self, volume_viewer, param_tab, formats, parent=None):
        super().__init__(parent)
        self.volume_viewer = volume_viewer
        self.param_tab = param_tab
        self.formats = formats
        self.setWindowTitle("Animation Settings")
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        type_group = QGroupBox("Animation Type")
        type_layout = QVBoxLayout()
        self.trajectory_radio = QRadioButton("Trajectory")
        self.slice_radio = QRadioButton("Slices")

        has_volume = getattr(self.volume_viewer, "volume", None) is not None
        has_trajectory = getattr(self.param_tab, "mesh_trajectory", None) is not None

        self.slice_radio.setEnabled(has_volume)
        self.trajectory_radio.setEnabled(has_trajectory)
        if has_trajectory:
            self.trajectory_radio.setChecked(True)
        elif has_volume:
            self.slice_radio.setChecked(True)

        self.trajectory_radio.toggled.connect(self.update_frame_ranges)
        self.slice_radio.toggled.connect(self.update_frame_ranges)
        type_layout.addWidget(self.trajectory_radio)
        type_layout.addWidget(self.slice_radio)
        type_group.setLayout(type_layout)
        layout.addWidget(type_group)

        export_format_group = QGroupBox("Export Settings")
        export_format_grid = QGridLayout()
        export_format_grid.addWidget(QLabel("Format:"), 0, 0)
        self.format_combo = QComboBox()
        self.format_combo.addItems(self.formats)
        export_format_grid.addWidget(self.format_combo, 0, 1)
        export_format_grid.addWidget(QLabel("Quality:"), 1, 0)
        self.quality = QSpinBox()
        self.quality.setRange(0, 100)
        self.quality.setValue(80)
        self.quality.setSuffix("%")
        export_format_grid.addWidget(self.quality, 1, 1)
        export_format_group.setLayout(export_format_grid)
        layout.addWidget(export_format_group)

        # Frame settings
        frame_group = QGroupBox("Frame Settings")
        frame_grid = QGridLayout()

        frame_grid.addWidget(QLabel("Rate (fps):"), 0, 0)
        self.frame_rate = QSpinBox()
        self.frame_rate.setRange(1, 60)
        self.frame_rate.setValue(30)
        frame_grid.addWidget(self.frame_rate, 0, 1)

        frame_grid.addWidget(QLabel("Stride:"), 1, 0)
        self.frame_stride = QSpinBox()
        self.frame_stride.setRange(1, 100)
        self.frame_stride.setValue(1)
        frame_grid.addWidget(self.frame_stride, 1, 1)

        frame_grid.addWidget(QLabel("Window:"), 2, 0)
        range_layout = QHBoxLayout()
        self.start_frame = QSpinBox()
        self.end_frame = QSpinBox()
        self.start_frame.setFixedWidth(70)
        self.end_frame.setFixedWidth(70)
        range_layout.addWidget(self.start_frame)
        range_layout.addWidget(self.end_frame)
        frame_grid.addLayout(range_layout, 2, 1)

        frame_group.setLayout(frame_grid)
        layout.addWidget(frame_group)

        button_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        cancel_button = QPushButton("Cancel")
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)

        self.update_frame_ranges()

    def update_frame_ranges(self):
        min_frame, max_frame = 0, 0
        if self.trajectory_radio.isChecked() and self.param_tab.mesh_trajectory:
            max_frame = len(self.param_tab.mesh_trajectory) - 1
        elif self.slice_radio.isChecked() and self.volume_viewer.volume is not None:
            max_frame = self.volume_viewer.slice_slider.maximum()
            min_frame = self.volume_viewer.slice_slider.minimum()

        self.start_frame.setRange(min_frame, max_frame)
        self.end_frame.setRange(min_frame, max_frame)
        self.start_frame.setValue(min_frame)
        self.end_frame.setValue(max_frame)


class ExportManager:
    def __init__(self, vtk_widget, volume_viewer, param_tab):
        self.vtk_widget = vtk_widget
        self.volume_viewer = volume_viewer
        self.param_tab = param_tab

        self.format_settings = {
            "MP4": {"fourcc": "mp4v", "ext": ".mp4"},
            "AVI": {"fourcc": "MJPG", "ext": ".avi"},
            "RGBA": {"frame_series": True, "ext": ".png"},
        }

    def copy_screenshot_to_clipboard(self, window: bool = False):
        screenshot = self.capture_screenshot(transparent_bg=True)
        if window:
            screenshot = self.capture_window_screenshot(transparent_bg=True)
        screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2RGBA)

        height, width, channel = screenshot.shape
        q_image = QImage(
            screenshot.data,
            width,
            height,
            channel * width,
            QImage.Format.Format_RGBA8888,
        )

        clipboard = QGuiApplication.clipboard()
        return clipboard.setImage(q_image)

    def capture_screenshot(self, transparent_bg: bool = False):
        """Capture screenshot of current VTK window"""
        render_window = self.vtk_widget.GetRenderWindow()
        render_window.SetAlphaBitPlanes(1)
        render_window.SetMultiSamples(0)

        window_to_image = vtkWindowToImageFilter()
        window_to_image.SetInput(render_window)
        window_to_image.SetInputBufferTypeToRGBA()
        window_to_image.Update()

        vtk_image = window_to_image.GetOutput()
        width, height, _ = vtk_image.GetDimensions()

        ret = numpy_support.vtk_to_numpy(vtk_image.GetPointData().GetScalars())

        ret_format = cv2.COLOR_RGBA2BGRA
        ret = ret.reshape(height, width, -1)
        if not transparent_bg:
            ret_format = cv2.COLOR_RGB2BGR

        return cv2.cvtColor(ret[::-1], ret_format)

    def capture_window_screenshot(self, transparent_bg: bool = False):
        """Capture a screenshot of the entire PyQt window application."""
        top_window = self.vtk_widget
        while top_window.parent():
            top_window = top_window.parent()

        geometry = top_window.geometry()
        screen = QGuiApplication.screenAt(top_window.mapToGlobal(geometry.topLeft()))
        if screen is None:
            raise RuntimeError("Could not find screen containing the window")

        image = screen.grabWindow(
            top_window.winId(), 0, 0, geometry.width(), geometry.height()
        ).toImage()

        width = image.width()
        height = image.height()
        ptr = image.constBits()
        ptr.setsize(height * width * 4)

        ret_format = cv2.COLOR_RGBA2BGRA
        if not transparent_bg:
            ret_format = cv2.COLOR_RGB2BGR
        arr = np.frombuffer(ptr, np.uint8).reshape(height, width, -1)
        return cv2.cvtColor(arr, ret_format)

    def save_screenshot(self):
        file_path, _ = QFileDialog.getSaveFileName(
            None, "Save Screenshot", "", "Images (*.png *.jpg)"
        )
        if file_path:
            screenshot = self.capture_screenshot()
            cv2.imwrite(file_path, screenshot)

    def export_animation(self):
        has_volume = getattr(self.volume_viewer, "volume", None) is not None
        has_trajectory = getattr(self.param_tab, "mesh_trajectory", None) is not None

        if not (has_trajectory or has_volume):
            QMessageBox.warning(
                None,
                "Export Error",
                "No data available for animation. Please load a trajectory or volume.",
            )
            return -1

        dialog = AnimationSettingsDialog(
            self.volume_viewer, self.param_tab, self.format_settings.keys()
        )

        if dialog.exec():
            use_trajectory = dialog.trajectory_radio.isChecked()

            if dialog.start_frame.value() > dialog.end_frame.value():
                QMessageBox.warning(
                    None,
                    "Export Error",
                    "Start frame larger than stop frame.",
                )
                return -1

            def _update(frame_idx):
                if use_trajectory:
                    self.param_tab.display_frame(frame_idx)
                else:
                    self.volume_viewer.slice_slider.setValue(frame_idx)

            original_frame = 0
            if use_trajectory:
                original_frame = self.param_tab.current_frame
            else:
                original_frame = self.volume_viewer.slice_slider.value()

            self._create_animation(
                update_func=_update,
                original_frame=original_frame,
                fps=dialog.frame_rate.value(),
                stride=dialog.frame_stride.value(),
                start_frame=dialog.start_frame.value(),
                end_frame=dialog.end_frame.value(),
                format_settings=self.format_settings[dialog.format_combo.currentText()],
            )

    def _create_animation(
        self,
        update_func: Callable,
        fps: int,
        stride: int,
        start_frame: int,
        end_frame: int,
        format_settings: dict,
        original_frame: int = None,
        quality: int = 80,
    ):
        """Create animation video from frames"""
        filename, _ = QFileDialog.getSaveFileName(
            None, "Save Animation", "", f"Video (*{format_settings['ext']})"
        )
        if filename is None or len(filename) == 0:
            return -1

        renderer = self.vtk_widget.GetRenderWindow()
        renderer.SetOffScreenRendering(1)

        is_video = not format_settings.get("frame_series", False)

        update_func(start_frame)
        renderer.Render()
        height, width = self.capture_screenshot(not is_video).shape[:2]

        writer = FrameWriter(filename=filename)
        if is_video:
            writer = cv2.VideoWriter(
                filename,
                cv2.VideoWriter_fourcc(*format_settings["fourcc"]),
                fps,
                (width, height),
                isColor=True,
            )
            if format_settings["fourcc"] in ["mp4v", "MJPG"]:
                writer.set(cv2.VIDEOWRITER_PROP_QUALITY, quality)

        progress = QProgressDialog()
        progress.setWindowTitle("Animation")
        progress.setLabelText("Processing frames...")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setMaximum(end_frame)
        progress.setCancelButton(None)

        for frame_idx in range(start_frame, end_frame + 1, stride):
            update_func(frame_idx)
            renderer.Render()
            writer.write(self.capture_screenshot(not is_video))

            progress.setValue(frame_idx)
            QApplication.processEvents()

        writer.release()
        progress.close()

        renderer.SetOffScreenRendering(0)
        if original_frame is not None:
            update_func(original_frame)
