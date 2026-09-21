"""
Tests for screenshot capture sizing on high-DPI displays.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np
import pytest

from mosaic.animation import _utils
from mosaic.animation._utils import ScreenshotManager


class FakeRenderWindow:
    def __init__(self, size):
        self._size = size

    def GetSize(self):
        return self._size


class FakeVTKWidget:
    """Mimics QVTKRenderWindowInteractor, whose render window is sized in
    physical pixels (logical size times the device pixel ratio)."""

    def __init__(self, logical_size=(800, 600), device_pixel_ratio=1.0):
        self._logical_size = logical_size
        self._dpr = device_pixel_ratio
        self._render_window = FakeRenderWindow(
            (
                round(logical_size[0] * device_pixel_ratio),
                round(logical_size[1] * device_pixel_ratio),
            )
        )

    def GetRenderWindow(self):
        return self._render_window

    def width(self):
        return self._logical_size[0]

    def height(self):
        return self._logical_size[1]


@pytest.fixture
def recorded_capture(monkeypatch):
    """Replace capture_frame with a recorder returning a matching array."""
    calls = {}

    def fake_capture_frame(render_window, transparent_bg=False, magnification=1, **kw):
        width = kw["width"] if kw.get("width") is not None else render_window.GetSize()[0]
        height = (
            kw["height"] if kw.get("height") is not None else render_window.GetSize()[1]
        )
        calls.update(width=width, height=height, magnification=magnification)
        channels = 4 if transparent_bg else 3
        return np.zeros(
            (height * magnification, width * magnification, channels), dtype=np.uint8
        )

    monkeypatch.setattr(_utils, "capture_frame", fake_capture_frame)
    return calls


class TestScreenshotResolution:
    @pytest.mark.parametrize("device_pixel_ratio", [1.0, 2.0])
    def test_capture_size_is_independent_of_device_pixel_ratio(
        self, recorded_capture, device_pixel_ratio
    ):
        widget = FakeVTKWidget((800, 600), device_pixel_ratio)
        image = ScreenshotManager(widget).capture(magnification=2)
        assert image.size == (1600, 1200)

    def test_capture_honors_explicit_dimensions(self, recorded_capture):
        widget = FakeVTKWidget((800, 600), 2.0)
        image = ScreenshotManager(widget).capture(width=320, height=240, magnification=1)
        assert image.size == (320, 240)


def _offscreen_window(size=(400, 300)):
    """Render window holding two points spanning the scene."""
    import vtk

    points = vtk.vtkPoints()
    points.InsertNextPoint(-5, -4, 0)
    points.InsertNextPoint(5, 4, 0)

    vertices = vtk.vtkCellArray()
    for index in range(2):
        vertices.InsertNextCell(1)
        vertices.InsertCellPoint(index)

    poly_data = vtk.vtkPolyData()
    poly_data.SetPoints(points)
    poly_data.SetVerts(vertices)

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(poly_data)

    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetColor(1, 1, 1)
    prop.SetPointSize(8)
    prop.SetRenderPointsAsSpheres(True)

    renderer = vtk.vtkRenderer()
    renderer.AddActor(actor)
    renderer.SetBackground(0, 0, 0)

    render_window = vtk.vtkRenderWindow()
    render_window.SetOffScreenRendering(1)
    render_window.AddRenderer(renderer)
    render_window.SetSize(*size)
    render_window.Render()
    renderer.ResetCamera()
    render_window.Render()
    return render_window


def _measure(frame):
    """Return (point diameter, point separation) in pixels for a capture."""
    lit = frame[:, :, :3].sum(axis=2) > 30
    _, columns = np.nonzero(lit)
    assert columns.size, "nothing rendered"

    midpoint = (columns.min() + columns.max()) / 2
    left_blob = columns[columns < midpoint]
    diameter = left_blob.max() - left_blob.min() + 1
    separation = columns.max() - columns.min()
    return diameter, separation


@pytest.mark.gui
class TestRelativeScaling:
    """Screenshots must show the scene at the proportions the viewer shows."""

    def test_point_size_keeps_its_share_of_the_frame(
        self, require_vtk_render_window
    ):
        render_window = _offscreen_window()

        base_diameter, base_separation = _measure(
            _utils.capture_frame(render_window, width=400, height=300, magnification=1)
        )
        scaled_diameter, scaled_separation = _measure(
            _utils.capture_frame(render_window, width=400, height=300, magnification=2)
        )

        assert scaled_separation == pytest.approx(2 * base_separation, rel=0.05)
        assert scaled_diameter == pytest.approx(2 * base_diameter, rel=0.2)

    def test_cropped_capture_keeps_point_proportions(
        self, require_vtk_render_window
    ):
        render_window = _offscreen_window()

        diameter, separation = _measure(
            _utils.capture_frame(render_window, width=400, height=300, magnification=1)
        )
        context = _utils.compute_crop_context(render_window, 400, 300)
        try:
            cropped = _utils.capture_cropped(render_window, context)
        finally:
            _utils.restore_window_size(render_window, context)

        crop_diameter, crop_separation = _measure(cropped)
        assert crop_diameter / crop_separation == pytest.approx(
            diameter / separation, rel=0.25
        )


def _line_window(size=(400, 300)):
    """Render window holding a single line spanning the scene."""
    import vtk

    line = vtk.vtkLineSource()
    line.SetPoint1(-5, 0, 0)
    line.SetPoint2(5, 0, 0)

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(line.GetOutputPort())

    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(1, 1, 1)
    actor.GetProperty().SetLineWidth(2)

    renderer = vtk.vtkRenderer()
    renderer.AddActor(actor)
    renderer.SetBackground(0, 0, 0)

    render_window = vtk.vtkRenderWindow()
    render_window.SetOffScreenRendering(1)
    render_window.AddRenderer(renderer)
    render_window.SetSize(*size)
    render_window.Render()
    renderer.ResetCamera()
    render_window.Render()
    return render_window


def _lit_extent(frame, axis):
    """Return the number of lit pixels along one axis of a capture."""
    lit = frame[:, :, :3].sum(axis=2) > 30
    indices = np.nonzero(lit)[axis]
    assert indices.size, "nothing rendered"
    return indices.max() - indices.min() + 1


@pytest.mark.gui
class TestLineAndTextScaling:
    """Line width and font size are device-pixel attributes as well."""

    def test_line_width_keeps_its_share_of_the_frame(self, require_vtk_render_window):
        render_window = _line_window()

        base = _lit_extent(
            _utils.capture_frame(render_window, width=400, height=300, magnification=1),
            0,
        )
        scaled = _lit_extent(
            _utils.capture_frame(render_window, width=400, height=300, magnification=2),
            0,
        )

        assert scaled == pytest.approx(2 * base, rel=0.3)

    def test_text_keeps_its_share_of_the_frame(self, require_vtk_render_window):
        import vtk

        text = vtk.vtkTextActor()
        text.SetInput("Mosaic")
        text.SetPosition(20, 20)
        text.GetTextProperty().SetFontSize(14)
        text.GetTextProperty().SetColor(1, 1, 1)

        renderer = vtk.vtkRenderer()
        renderer.AddActor(text)
        renderer.SetBackground(0, 0, 0)

        render_window = vtk.vtkRenderWindow()
        render_window.SetOffScreenRendering(1)
        render_window.AddRenderer(renderer)
        render_window.SetSize(400, 300)
        render_window.Render()

        base = _lit_extent(
            _utils.capture_frame(render_window, width=400, height=300, magnification=1),
            0,
        )
        scaled = _lit_extent(
            _utils.capture_frame(render_window, width=400, height=300, magnification=2),
            0,
        )

        assert scaled == pytest.approx(2 * base, rel=0.3)
