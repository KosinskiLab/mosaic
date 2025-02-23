""" Screenshot and video export functionalities for vtk viewer.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import Callable, Tuple
from os.path import splitext


import imageio
import numpy as np
from PIL import Image
from qtpy.QtGui import QImage, QGuiApplication
from qtpy.QtWidgets import (
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
    QApplication,
)
from vtkmodules.util import numpy_support
from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter

from .dialogs import ProgressDialog
from .geometry import GeometryTrajectory


def _get_trajectories(geometries):
    return [x for x in geometries if isinstance(x, GeometryTrajectory)]


class FrameWriter:
    def __init__(self, filename):
        self.index = 0
        self.filename, self.ext = splitext(filename)

    def append_data(self, img: np.ndarray):
        image = Image.fromarray(np.asarray(img))
        image.save(f"{self.filename}_{self.index}{self.ext}")
        self.index += 1

    def release(self):
        self.index = 0


class ExportManager:
    def __init__(self, vtk_widget, volume_viewer, cdata):
        self.vtk_widget = vtk_widget
        self.viewer = volume_viewer
        self.cdata = cdata

        self.format_settings = {
            "MP4": {"ext": ".mp4"},
            "AVI": {"ext": ".avi"},
            "RGBA": {"frame_series": True, "ext": ".png"},
        }

    def copy_screenshot_to_clipboard(self, window: bool = False):
        screenshot = self.capture_screenshot(transparent_bg=True)
        if window:
            screenshot = self.capture_window_screenshot(transparent_bg=True)

        screenshot = np.array(screenshot)
        height, width = screenshot.shape[:2]

        q_image = QImage(
            screenshot.data,
            width,
            height,
            width * 4,
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

        arr = numpy_support.vtk_to_numpy(vtk_image.GetPointData().GetScalars())
        arr = arr.reshape(height, width, -1)[::-1]

        ret = Image.fromarray(arr, "RGBA")
        if transparent_bg:
            return ret
        return ret.convert("RGB")

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

        arr = np.frombuffer(ptr, np.uint8).reshape(height, width, -1).copy()
        arr[:, :, [0, 2]] = arr[:, :, [2, 0]]
        ret = Image.fromarray(arr, "RGBA")
        if transparent_bg:
            return ret
        return ret.convert("RGB")

    def save_screenshot(self):
        file_path, _ = QFileDialog.getSaveFileName(
            None, "Save Screenshot", "", "Images (*.png *.jpg)"
        )
        if not file_path:
            return -1

        transparent_bg = file_path.lower().endswith(".png")
        screenshot = self.capture_screenshot(transparent_bg=transparent_bg)
        screenshot.save(file_path)

    def export_animation(self):
        has_volume = getattr(self.viewer.primary, "volume", None) is not None
        has_trajectory = len(_get_trajectories(self.cdata._models.data))

        dialog = AnimationSettingsDialog(
            self.viewer, self.cdata, self.format_settings.keys()
        )

        if not dialog.exec():
            return -1

        use_reveal = dialog.reveal_radio.isChecked()
        use_trajectory = dialog.trajectory_radio.isChecked()

        if dialog.start_frame.value() > dialog.end_frame.value():
            QMessageBox.warning(
                None,
                "Export Error",
                "Start frame larger than stop frame.",
            )
            return -1

        if not (has_trajectory or has_volume):
            QMessageBox.warning(
                None,
                "Export Error",
                "Please load a trajectory or volume to animate.",
            )
            return -1

        actors = (
            self.vtk_widget.GetRenderWindow()
            .GetRenderers()
            .GetFirstRenderer()
            .GetActors()
        )
        actors_visible = []
        actors.InitTraversal()
        for _ in range(actors.GetNumberOfItems()):
            actor = actors.GetNextActor()
            if actor:
                actors_visible.append(actor.GetVisibility())

        original_frame = 0
        if not use_trajectory:
            original_frame = self.viewer.primary.slice_slider.value()

        stride = dialog.frame_stride.value()
        start, end = dialog.start_frame.value(), dialog.end_frame.value()
        frames = tuple(range(start, end, stride))
        if use_reveal:
            frames = (*frames, None, *list(range(end, start, -stride)))
            actors.InitTraversal()
            for _ in range(actors.GetNumberOfItems()):
                actors.GetNextActor().SetVisibility(0)

        def _update(frame_idx):
            if use_trajectory:
                for geometry in _get_trajectories(self.cdata._models.data):
                    geometry.display_frame(frame_idx)

                selected_indices = self.cdata.models._get_selected_indices()
                if selected_indices:
                    return self.cdata.models.set_selection(selected_indices)
                return self.cdata.models.render_vtk()

            if use_reveal and frame_idx is None:
                actors.InitTraversal()
                for visible in actors_visible:
                    actors.GetNextActor().SetVisibility(visible)
                return None

            if frame_idx is not None:
                return self.viewer.primary.slice_slider.setValue(frame_idx)

        self._create_animation(
            update_func=_update,
            original_frame=original_frame,
            fps=dialog.frame_rate.value(),
            frames=frames,
            format_settings=self.format_settings[dialog.format_combo.currentText()],
        )

    def _create_animation(
        self,
        update_func: Callable,
        fps: int,
        frames: Tuple[int],
        format_settings: dict,
        original_frame: int = None,
        quality: int = 80,
    ):
        """Create animation video from frames"""
        filename, _ = QFileDialog.getSaveFileName(
            None, "Save Animation", "", f"Video (*{format_settings['ext']})"
        )
        if filename is None or len(filename) == 0 or len(frames) == 0:
            return -1

        renderer = self.vtk_widget.GetRenderWindow()
        renderer.SetOffScreenRendering(1)

        is_video = not format_settings.get("frame_series", False)

        update_func(frames[0])
        renderer.Render()
        screenshot = self.capture_screenshot(not is_video)
        height, width = np.array(screenshot).shape[:2]

        writer = FrameWriter(filename=filename)
        quality = max(min(quality / 10.0, 10), 1) if quality else None
        if is_video:
            writer = imageio.get_writer(
                filename, mode="I", fps=fps, quality=quality, macro_block_size=None
            )

        progress = ProgressDialog(frames, title="Processing Frames")
        for frame_idx in progress:
            update_func(frame_idx)
            if frame_idx is None:
                continue
            renderer.Render()
            frame = np.asarray(self.capture_screenshot(not is_video))
            writer.append_data(frame)
            QApplication.processEvents()

        writer.close()

        renderer.SetOffScreenRendering(0)
        if original_frame is not None:
            update_func(original_frame)


class AnimationSettingsDialog(QDialog):
    def __init__(self, volume_viewer, cdata, formats, parent=None):
        super().__init__(parent)
        self.viewer = volume_viewer
        self.cdata = cdata
        self.formats = formats
        self.setWindowTitle("Animation Settings")
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        type_group = QGroupBox("Animation Type")
        type_layout = QVBoxLayout()
        self.trajectory_radio = QRadioButton("Trajectory")
        self.slice_radio = QRadioButton("Slices")
        self.reveal_radio = QRadioButton("Reveal Flythrough")

        has_volume = getattr(self.viewer.primary, "volume", None) is not None
        has_trajectory = len(_get_trajectories(self.cdata._models.data))

        self.slice_radio.setEnabled(has_volume)
        self.reveal_radio.setEnabled(has_volume)
        self.trajectory_radio.setEnabled(has_trajectory)
        if has_trajectory:
            self.trajectory_radio.setChecked(True)
        elif has_volume:
            self.slice_radio.setChecked(True)

        self.trajectory_radio.toggled.connect(self.update_frame_ranges)
        self.slice_radio.toggled.connect(self.update_frame_ranges)
        self.reveal_radio.toggled.connect(self.update_frame_ranges)
        type_layout.addWidget(self.trajectory_radio)
        type_layout.addWidget(self.slice_radio)
        type_layout.addWidget(self.reveal_radio)
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
        self.frame_rate.setRange(1, 1 << 30)
        self.frame_rate.setValue(30)
        frame_grid.addWidget(self.frame_rate, 0, 1)

        frame_grid.addWidget(QLabel("Stride:"), 1, 0)
        self.frame_stride = QSpinBox()
        self.frame_stride.setRange(1, 1 << 30)
        self.frame_stride.setValue(1)
        frame_grid.addWidget(self.frame_stride, 1, 1)

        frame_grid.addWidget(QLabel("Window:"), 2, 0)
        range_layout = QHBoxLayout()
        self.start_frame = QSpinBox()
        self.start_frame.setFixedWidth(70)
        self.end_frame = QSpinBox()
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
        if self.trajectory_radio.isChecked():
            max_frame = max(
                *[x.frames - 1 for x in _get_trajectories(self.cdata._models.data)], 0
            )
        elif self.slice_radio.isChecked() or self.reveal_radio.isChecked():
            if self.viewer.primary.volume is not None:
                max_frame = self.viewer.primary.slice_slider.maximum()
                min_frame = self.viewer.primary.slice_slider.minimum()

        self.start_frame.setRange(min_frame, max_frame)
        self.end_frame.setRange(min_frame, max_frame)
        self.start_frame.setValue(min_frame)
        self.end_frame.setValue(max_frame)
