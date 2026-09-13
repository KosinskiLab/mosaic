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
