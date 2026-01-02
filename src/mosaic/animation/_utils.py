"""
Utility functions for animation export and screenshots.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from os.path import splitext

import numpy as np
from PIL import Image
from qtpy.QtGui import QImage, QPixmap, QGuiApplication
from qtpy.QtWidgets import QFileDialog
from vtkmodules.util import numpy_support
from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter


def capture_frame(
    render_window,
    transparent_bg: bool = False,
    magnification: int = 1,
    multisamples: int = None,
    width: int = None,
    height: int = None,
) -> np.ndarray:
    """Capture the current frame from a VTK render window.

    Parameters
    ----------
    render_window : vtkRenderWindow
        The VTK render window to capture from.
    transparent_bg : bool, optional
        If True, preserve alpha channel for transparency.
    magnification : int, optional
        Render at higher resolution then downsample for quality.
    multisamples : int, optional
        Number of multisamples for hardware antialiasing. If None, uses current.
    width : int, optional
        Custom target width, uses current window width by default.
    height : int, optional
        Custom target height, uses current window height by default.

    Returns
    -------
    np.ndarray
        The captured frame as a numpy array (RGB or RGBA).
    """
    render_window.SetAlphaBitPlanes(1)

    original_size = render_window.GetSize()
    original_multisamples = render_window.GetMultiSamples()

    # Apply multisamples if specified
    if multisamples is not None:
        render_window.SetMultiSamples(multisamples)

    # Determine target dimensions
    target_width = width if width is not None else original_size[0]
    target_height = height if height is not None else original_size[1]

    # Apply magnification for supersampling
    render_width = target_width * magnification
    render_height = target_height * magnification

    size_changed = False
    if render_width != original_size[0] or render_height != original_size[1]:
        render_window.SetSize(render_width, render_height)
        render_window.Render()
        size_changed = True

    window_to_image = vtkWindowToImageFilter()
    window_to_image.SetInput(render_window)
    window_to_image.SetInputBufferTypeToRGBA()
    window_to_image.SetScale(1)
    window_to_image.ReadFrontBufferOff()
    window_to_image.Update()

    vtk_image = window_to_image.GetOutput()
    img_width, img_height, _ = vtk_image.GetDimensions()

    arr = numpy_support.vtk_to_numpy(vtk_image.GetPointData().GetScalars())
    # Reshape, flip vertically, and copy to ensure contiguous memory
    # (vtk_to_numpy returns a view, [::-1] creates non-contiguous view)
    arr = np.ascontiguousarray(arr.reshape(img_height, img_width, -1)[::-1])

    # Restore original settings
    if multisamples is not None:
        render_window.SetMultiSamples(original_multisamples)

    if size_changed:
        render_window.SetSize(*original_size)
        render_window.Render()

    # Downscale if magnification was applied
    if magnification > 1:
        img = Image.fromarray(arr, "RGBA")
        img = img.resize((target_width, target_height), Image.LANCZOS)
        arr = np.array(img)

    if not transparent_bg:
        # Slice and ensure contiguous for downstream consumers
        arr = np.ascontiguousarray(arr[:, :, :3])

    return arr


class ScreenshotManager:
    """Manages screenshot capture and export for VTK widgets."""

    def __init__(self, vtk_widget):
        self.vtk_widget = vtk_widget

    def copy_to_clipboard(self, window: bool = False):
        """Copy screenshot to system clipboard.

        Parameters
        ----------
        window : bool, optional
            If True, capture entire window instead of just VTK widget.
        """
        if window:
            screenshot = np.ascontiguousarray(self.capture_window())

            # Add alpha channel for clipboard compatibility
            alpha = np.full((*screenshot.shape[:2], 1), 255, dtype=np.uint8)
            screenshot = np.concatenate([screenshot, alpha], axis=2)
        else:
            screenshot = self.capture(transparent_bg=True)

        screenshot = np.ascontiguousarray(screenshot)
        height, width = screenshot.shape[:2]

        q_image = QImage(
            screenshot,
            width,
            height,
            width * 4,
            QImage.Format.Format_RGBA8888,
        )

        clipboard = QGuiApplication.clipboard()
        clipboard.setImage(q_image)

    def capture(
        self,
        transparent_bg: bool = False,
        width: int = None,
        height: int = None,
        magnification: int = 2,
        multisamples: int = 8,
    ):
        """Capture high-quality screenshot of current VTK window.

        Parameters
        ----------
        transparent_bg : bool, optional
            Whether to keep transparent background.
        width : int, optional
            Custom width, uses current window width by default.
        height : int, optional
            Custom height, uses current window height by default.
        magnification : int, optional
            Resolution multiplier for supersampling (1-8).
        multisamples : int, optional
            Number of multisamples for hardware antialiasing.

        Returns
        -------
        PIL.Image
            Screenshot image.
        """
        render_window = self.vtk_widget.GetRenderWindow()
        arr = capture_frame(
            render_window,
            transparent_bg=transparent_bg,
            magnification=magnification,
            multisamples=multisamples,
            width=width,
            height=height,
        )
        mode = "RGBA" if transparent_bg else "RGB"
        return Image.fromarray(arr, mode)

    def capture_window(self):
        """Capture a screenshot of the entire PyQt window application."""
        top_window = self.vtk_widget
        while top_window.parent():
            top_window = top_window.parent()

        pixmap = top_window.grab()
        image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB888)

        width = image.width()
        height = image.height()
        ptr = image.constBits()
        ptr.setsize(height * width * 3)

        window_arr = np.frombuffer(ptr, np.uint8).reshape(height, width, 3).copy()
        window_img = Image.fromarray(window_arr, "RGB")

        vtk_img = self.capture(transparent_bg=False, magnification=1, multisamples=0)
        vtk_pos = self.vtk_widget.mapTo(top_window, self.vtk_widget.rect().topLeft())

        dpr = top_window.devicePixelRatio()
        x = int(vtk_pos.x() * dpr)
        y = int(vtk_pos.y() * dpr)

        window_img.paste(vtk_img, (x, y))
        return window_img

    def save(self):
        """Open save dialog and save screenshot to file."""
        file_path, _ = QFileDialog.getSaveFileName(
            None, "Save Screenshot", "", "Images (*.png *.jpg)"
        )
        if not file_path:
            return -1

        transparent_bg = file_path.lower().endswith(".png")
        screenshot = self.capture(transparent_bg=transparent_bg)
        screenshot.save(file_path)


class FrameWriter:
    """Writes individual frames as image files."""

    def __init__(self, filename: str):
        self.index = 0
        self.filename, self.ext = splitext(filename)

    def append_data(self, img: np.ndarray):
        image = Image.fromarray(np.asarray(img))
        image.save(f"{self.filename}_{self.index:04d}{self.ext}")
        self.index += 1

    def close(self):
        self.index = 0
