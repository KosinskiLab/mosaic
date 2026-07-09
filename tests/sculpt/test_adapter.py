"""Tests for the geometry <-> array adapter and the zero-copy point writer."""

import numpy as np
import vtk
from vtkmodules.util import numpy_support

from mosaic.sculpt.adapter import (
    PolyDataPointWriter,
    read_geometry_arrays,
    sync_model_vertices,
)


class _FakeTriMesh:
    """Stand-in for a TriangularMesh parametrization (only needs ``triangles``)."""

    def __init__(self, fs: np.ndarray) -> None:
        self.triangles = np.asarray(fs, dtype=np.int64)


class _FakeGeometry:
    """Minimal stand-in for a Mosaic ``Geometry`` for adapter tests."""

    def __init__(self, vs: np.ndarray, fs: np.ndarray, uuid: str = "u") -> None:
        self.uuid = uuid
        polydata = vtk.vtkPolyData()
        vtk_pts = vtk.vtkPoints()
        vtk_pts.SetData(numpy_support.numpy_to_vtk(vs.astype(np.float32), deep=True))
        polydata.SetPoints(vtk_pts)
        cells = vtk.vtkCellArray()
        for tri in fs:
            cells.InsertNextCell(3, tri.tolist())
        polydata.SetPolys(cells)
        self._data = polydata
        self._points = vs.astype(np.float32)
        self.model = _FakeTriMesh(fs)

    @property
    def points(self):
        return numpy_support.vtk_to_numpy(self._data.GetPoints().GetData())


def test_read_geometry_arrays_returns_vs_fs(flat_grid_mesh):
    vs, fs = flat_grid_mesh
    geom = _FakeGeometry(vs, fs)
    out_vs, out_fs = read_geometry_arrays(geom)
    assert out_vs.dtype == np.float64
    assert out_vs.shape == vs.shape
    assert np.allclose(out_vs, vs, atol=1e-5)
    assert out_fs.shape == fs.shape
    assert np.array_equal(out_fs, fs)


def test_polydata_point_writer_writes_in_place(flat_grid_mesh):
    vs, fs = flat_grid_mesh
    geom = _FakeGeometry(vs, fs)
    writer = PolyDataPointWriter(geom._data)
    new_vs = vs.copy()
    new_vs[:, 2] = 0.7
    writer.write(new_vs)
    assert np.allclose(geom.points[:, 2], 0.7, atol=1e-5)


def test_polydata_point_writer_rejects_shape_mismatch(flat_grid_mesh):
    vs, fs = flat_grid_mesh
    geom = _FakeGeometry(vs, fs)
    writer = PolyDataPointWriter(geom._data)
    bad = np.zeros((len(vs) + 1, 3), dtype=np.float32)
    raised = False
    try:
        writer.write(bad)
    except ValueError:
        raised = True
    assert raised


def test_polydata_point_writer_is_zero_copy(flat_grid_mesh):
    vs, fs = flat_grid_mesh
    geom = _FakeGeometry(vs, fs)
    writer = PolyDataPointWriter(geom._data)
    view_before = numpy_support.vtk_to_numpy(geom._data.GetPoints().GetData())
    writer.write(vs)
    view_after = numpy_support.vtk_to_numpy(geom._data.GetPoints().GetData())
    assert (
        view_before.ctypes.data == view_after.ctypes.data
    ), "writer must not reallocate the polydata's point buffer"


def test_sync_model_vertices_updates_open3d_mesh(flat_grid_mesh):
    """Stroke commits must push target.vs into the parametrization model's
    Open3D mesh so a later change_representation rebuild starts from the
    sculpted state, not the original vertices."""
    import open3d as o3d

    class _Model:
        def __init__(self, n: int):
            self.mesh = o3d.geometry.TriangleMesh()
            self.mesh.vertices = o3d.utility.Vector3dVector(np.zeros((n, 3)))

    vs, fs = flat_grid_mesh
    geom = _FakeGeometry(vs, fs)
    geom.model = _Model(len(vs))

    sculpted = vs.copy()
    sculpted[:, 2] = 0.9
    sync_model_vertices(geom, sculpted)
    out = np.asarray(geom.model.mesh.vertices)
    assert np.allclose(out, sculpted, atol=1e-6)


def test_sync_model_vertices_noops_without_model(flat_grid_mesh):
    """A geometry without a model attribute (or without a model.mesh)
    must not raise; sculpt still operates on the polydata buffer."""
    vs, fs = flat_grid_mesh
    geom = _FakeGeometry(vs, fs)
    sync_model_vertices(geom, vs)  # no model → silently no-op

    class _ParametrizationWithoutMesh:
        pass

    geom.model = _ParametrizationWithoutMesh()
    sync_model_vertices(geom, vs)  # no .mesh → silently no-op


def test_polydata_point_writer_rebinds_after_points_swap(flat_grid_mesh):
    """change_representation reassigns the polydata's vtkPoints under the
    same Geometry. The writer must self-heal so subsequent writes land on
    the live buffer, not the orphaned one."""
    vs, fs = flat_grid_mesh
    geom = _FakeGeometry(vs, fs)
    writer = PolyDataPointWriter(geom._data)

    # Simulate change_representation: replace the polydata's points with a
    # freshly built vtkPoints (same coordinates, different buffer object).
    fresh = vtk.vtkPoints()
    fresh.SetData(numpy_support.numpy_to_vtk(vs.astype(np.float32), deep=True))
    geom._data.SetPoints(fresh)

    new_vs = vs.copy()
    new_vs[:, 2] = 1.3
    writer.write(new_vs)

    live = numpy_support.vtk_to_numpy(geom._data.GetPoints().GetData())
    assert np.allclose(
        live[:, 2], 1.3, atol=1e-5
    ), "writer must follow the polydata's current points buffer after a swap"
