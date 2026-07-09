"""Test fixtures for VolumeViewer / HUD unit tests."""

import pytest
import vtk


class _FakeVTKWidget:
    """Minimal stand-in for QVTKRenderWindowInteractor used by VolumeViewer.

    Owns a real ``vtkRenderWindow`` configured for off-screen rendering so
    ``Render()`` is safe in headless test environments. Exposes the subset
    of the widget API that ``VolumeViewer`` / HUD code touches.
    """

    def __init__(self):
        self._render_window = vtk.vtkRenderWindow()
        self._render_window.SetOffScreenRendering(1)
        self._renderer = vtk.vtkRenderer()
        self._render_window.AddRenderer(self._renderer)
        self._interactor = vtk.vtkRenderWindowInteractor()
        self._interactor.SetRenderWindow(self._render_window)

    def GetRenderWindow(self):
        return self._render_window

    def update(self):
        return None


@pytest.fixture
def fake_vtk_widget():
    """A non-Qt stand-in widget VolumeViewer can be constructed against.

    Use this (instead of mocking) when a test needs VolumeViewer to wire up
    actors and read renderer state — a real ``vtkRenderer`` is attached.
    """
    return _FakeVTKWidget()


@pytest.fixture
def small_volume():
    """A tiny ``vtkImageData`` good enough for state-transition tests."""
    import numpy as np
    from vtkmodules.util import numpy_support

    arr = np.linspace(0.0, 1.0, 8 * 8 * 8, dtype="float32").reshape(8, 8, 8)
    image = vtk.vtkImageData()
    image.SetDimensions(arr.shape[::-1])  # x, y, z
    image.SetSpacing(1.0, 1.0, 1.0)
    image.GetPointData().SetScalars(
        numpy_support.numpy_to_vtk(
            arr.ravel(order="F"), deep=True, array_type=vtk.VTK_FLOAT
        )
    )
    return image
