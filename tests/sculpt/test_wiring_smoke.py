"""End-to-end smoke: simulate a sculpt session with no real renderer.

We attach, switch tools, run a stroke driven by an injected MeshHit, undo,
and detach. The point is to catch wiring regressions across the
SculptController -> SculptSession -> SculptTarget seam.
"""

import pytest
from unittest.mock import MagicMock

import numpy as np
import vtk
from vtkmodules.util import numpy_support

from mosaic.sculpt import EventKind, SculptController
from mosaic.sculpt.controller import Brush, MeshHit
from mosaic.undo import STACK


@pytest.fixture(autouse=True)
def _reset_stack():
    STACK.clear()
    yield
    STACK.clear()


class _FakeTriMesh:
    def __init__(self, fs):
        self.triangles = np.asarray(fs, dtype=np.int64)


def _build_polydata(vs, fs):
    polydata = vtk.vtkPolyData()
    vtk_pts = vtk.vtkPoints()
    vtk_pts.SetData(
        numpy_support.numpy_to_vtk(np.asarray(vs, dtype=np.float32), deep=True)
    )
    polydata.SetPoints(vtk_pts)
    cells = vtk.vtkCellArray()
    for tri in np.asarray(fs, dtype=np.int64):
        cells.InsertNextCell(3, tri.tolist())
    polydata.SetPolys(cells)
    return polydata


class _FakeGeometry:
    def __init__(self, vs, fs, uuid="g"):
        self.uuid = uuid
        self._data = _build_polydata(vs, fs)
        self.model = _FakeTriMesh(fs)

    @property
    def points(self):
        return numpy_support.vtk_to_numpy(self._data.GetPoints().GetData())

    def color_points(self, point_ids, color):
        return None

    def set_color(self, color=None):
        return None

    def swap_data(self, points, faces=None, model=None, **_kwargs):
        self._data = _build_polydata(
            points, faces if faces is not None else np.empty((0, 3), dtype=np.int64)
        )
        if model is not None:
            self.model = model


def test_full_smooth_stroke_lifecycle(perturbed_grid_mesh):
    vs, fs, interior = perturbed_grid_mesh
    geom = _FakeGeometry(vs, fs)

    c = SculptController(Brush(radius=0.4))
    c.attach_geometry(geom)
    assert c.session is not None
    c.set_tool("smooth")

    hit = MeshHit(
        world_position=vs[interior].astype(np.float64),
        normal=np.array([0.0, 0.0, 1.0]),
    )
    c._pick = MagicMock(return_value=hit)

    z_before = c.session.target.vs[interior, 2]
    c.handle_event(EventKind.LMB_DOWN, 10, 10)
    for _ in range(5):
        c.handle_event(EventKind.MOUSE_MOVE, 10, 10)
    c.handle_event(EventKind.LMB_UP, 10, 10)
    z_after = c.session.target.vs[interior, 2]
    assert z_after < z_before

    # Polydata received the same final position via PolyDataPointWriter.
    final_polydata = geom.points[interior, 2]
    assert np.isclose(float(final_polydata), float(z_after), atol=1e-4)

    # Undo via the global STACK restores the perturbed peak.
    assert STACK.undo() is not None
    assert np.isclose(c.session.target.vs[interior, 2], z_before)

    c.detach()
    assert c.session is None


def test_tool_switch_does_not_corrupt_state(perturbed_grid_mesh):
    vs, fs, _ = perturbed_grid_mesh
    c = SculptController()
    c.attach_geometry(_FakeGeometry(vs, fs))
    c.set_tool("smooth")
    c.set_tool("grab")
    c.set_tool("patch")
    c.set_tool("grab")
    assert c.session.tool == "grab"


def test_full_patch_stroke_lifecycle(punched_grid_mesh):
    vs, fs = punched_grid_mesh
    geom = _FakeGeometry(vs, fs)

    c = SculptController(Brush(radius=0.5))
    c.attach_geometry(geom)
    c.set_tool("patch")

    # Center of the hole: all boundary vertices are within radius 0.5 of (0.5, 0.5, 0).
    hit = MeshHit(
        world_position=np.array([0.5, 0.5, 0.0]),
        normal=np.array([0.0, 0.0, 1.0]),
    )
    c._pick = MagicMock(return_value=hit)

    face_count_before = len(c.session.target.fs)

    c.handle_event(EventKind.LMB_DOWN, 10, 10)
    for _ in range(3):
        c.handle_event(EventKind.MOUSE_MOVE, 10, 10)
    c.handle_event(EventKind.LMB_UP, 10, 10)

    face_count_filled = len(c.session.target.fs)
    assert (
        face_count_filled > face_count_before
    ), "patch must have added faces to close the hole"

    assert STACK.undo() is not None
    assert (
        len(c.session.target.fs) == face_count_before
    ), "undo must revert to original face count"

    STACK.redo()
    assert (
        len(c.session.target.fs) == face_count_filled
    ), "redo must reapply the filled topology"
