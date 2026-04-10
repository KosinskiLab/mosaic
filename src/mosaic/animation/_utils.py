"""
Utility functions for animation export and screenshots.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from os.path import splitext

import numpy as np
from PIL import Image
from qtpy.QtGui import QImage, QGuiApplication
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
    original_alpha_bit_planes = render_window.GetAlphaBitPlanes()
    render_window.SetAlphaBitPlanes(1 if transparent_bg else 0)

    original_size = render_window.GetSize()
    original_multisamples = render_window.GetMultiSamples()

    if multisamples is not None:
        render_window.SetMultiSamples(multisamples)

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

    render_window.SetAlphaBitPlanes(original_alpha_bit_planes)

    if multisamples is not None:
        render_window.SetMultiSamples(original_multisamples)

    if size_changed:
        render_window.SetSize(*original_size)
        render_window.Render()

    # Downscale if magnification was applied
    if magnification > 1:
        if transparent_bg:
            # Premultiply alpha before resize to avoid light fringe at edges
            alpha_f = arr[:, :, 3:4].astype(np.float32) / 255.0
            premult = arr.copy()
            premult[:, :, :3] = np.clip(
                arr[:, :, :3].astype(np.float32) * alpha_f, 0, 255
            ).astype(np.uint8)
            img = Image.fromarray(premult, "RGBA")
            img = img.resize((target_width, target_height), Image.LANCZOS)
            arr = np.array(img)
            # Unpremultiply alpha
            out_alpha = arr[:, :, 3:4].astype(np.float32) / 255.0
            safe_alpha = np.where(out_alpha > 0, out_alpha, 1.0)
            arr[:, :, :3] = np.clip(
                arr[:, :, :3].astype(np.float32) / safe_alpha, 0, 255
            ).astype(np.uint8)
        else:
            # Strip alpha before downsampling to prevent fringe artifacts
            img = Image.fromarray(np.ascontiguousarray(arr[:, :, :3]), "RGB")
            img = img.resize((target_width, target_height), Image.LANCZOS)
            arr = np.array(img)

    if not transparent_bg:
        # Slice and ensure contiguous for downstream consumers
        arr = np.ascontiguousarray(arr[:, :, :3])

    return arr


def compute_crop_context(render_window, width, height, padding=0.1):
    """Precompute render window size and crop region for actor-tight capture.

    Parameters
    ----------
    render_window : vtkRenderWindow
        The render window to analyse.
    width, height : int
        Desired output dimensions in pixels.
    padding : float
        Fractional padding around the actor bounding box.

    Returns
    -------
    dict or None
        Context dict with ``render_size``, ``crop_x``, ``crop_y``,
        ``width``, ``height``, ``original_size``.
        Returns None if no visible actors.
    """
    import vtk

    renderer = render_window.GetRenderers().GetFirstRenderer()
    bounds = [0.0] * 6
    renderer.ComputeVisiblePropBounds(bounds)
    if bounds[0] > bounds[1]:
        return None

    ow, oh = render_window.GetSize()
    coord = vtk.vtkCoordinate()
    coord.SetCoordinateSystemToWorld()

    xs, ys = [], []
    for i in (0, 1):
        for j in (2, 3):
            for k in (4, 5):
                coord.SetValue(bounds[i], bounds[j], bounds[k])
                d = coord.GetComputedDisplayValue(renderer)
                xs.append(d[0])
                ys.append(d[1])

    data_w = max(max(xs) - min(xs), 1)
    data_h = max(max(ys) - min(ys), 1)

    scale = max(
        width / (data_w * (1 + 2 * padding)),
        height / (data_h * (1 + 2 * padding)),
    )
    new_w = int(ow * scale)
    new_h = int(oh * scale)

    render_window.SetSize(new_w, new_h)
    render_window.Render()

    xs2, ys2 = [], []
    for i in (0, 1):
        for j in (2, 3):
            for k in (4, 5):
                coord.SetValue(bounds[i], bounds[j], bounds[k])
                d = coord.GetComputedDisplayValue(renderer)
                xs2.append(d[0])
                ys2.append(d[1])

    cx = (min(xs2) + max(xs2)) / 2
    cy = (min(ys2) + max(ys2)) / 2

    crop_x = max(0, min(int(cx - width / 2), new_w - width))
    crop_y = max(0, min(int(cy - height / 2), new_h - height))

    return {
        "render_size": (new_w, new_h),
        "original_size": (ow, oh),
        "crop_x": crop_x,
        "crop_y": crop_y,
        "width": width,
        "height": height,
    }


def capture_cropped(render_window, ctx):
    """Capture a frame and crop using a precomputed context.

    Parameters
    ----------
    render_window : vtkRenderWindow
        The render window (should already be at ``ctx["render_size"]``).
    ctx : dict
        Context from :func:`compute_crop_context`.

    Returns
    -------
    np.ndarray
        Cropped RGB image of exactly ``ctx["width"]`` x ``ctx["height"]``.
    """
    rw, rh = ctx["render_size"]
    frame = capture_frame(render_window, width=rw, height=rh)

    fh = frame.shape[0]
    x, y, w, h = ctx["crop_x"], ctx["crop_y"], ctx["width"], ctx["height"]
    return np.ascontiguousarray(frame[fh - y - h : fh - y, x : x + w])


def restore_window_size(render_window, ctx):
    """Restore the render window to its original size after cropped capture."""
    render_window.SetSize(*ctx["original_size"])
    render_window.Render()


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
