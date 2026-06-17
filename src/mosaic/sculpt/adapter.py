"""I/O between Mosaic ``Geometry`` and the numpy arrays used inside sculpt.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import Tuple

import numpy as np
import vtk
from vtkmodules.util import numpy_support


__all__ = [
    "PolyDataPointWriter",
    "read_geometry_arrays",
    "swap_geometry_topology",
    "sync_model_vertices",
]


def read_geometry_arrays(geometry) -> Tuple[np.ndarray, np.ndarray]:
    """Return ``(vs, fs)`` as numpy arrays for a Mosaic ``Geometry``.

    Faces come from ``geometry.model.triangles``; sculpt only ever binds to
    geometries whose model is a ``TriangularMesh``.
    """
    vs = np.ascontiguousarray(geometry.points, dtype=np.float64)
    fs = np.ascontiguousarray(geometry.model.triangles, dtype=np.int64)
    return vs, fs


class PolyDataPointWriter:
    """Zero-copy writer into a vtkPolyData's current point array.

    Wraps the polydata's ``vtkPoints`` buffer as a float32 numpy view; calling
    :py:meth:`write` copies into that view in place and marks the array
    ``Modified``.

    Self-heals across point-buffer swaps. Some Mosaic code paths (notably
    ``Geometry.change_representation`` going to surface/wireframe) reassign
    ``geometry._data.GetPoints()`` to a freshly built ``vtkPoints``; the
    cached numpy view from the *old* buffer would then write into a
    detached array that nothing renders. ``write`` checks the current
    ``GetData()`` reference against the cached one and rebinds when they
    diverge, so sculpting keeps working after a representation change.
    """

    __slots__ = ("_polydata", "_data_array", "_view")

    def __init__(self, polydata: vtk.vtkPolyData) -> None:
        if polydata.GetPoints() is None:
            raise ValueError("polydata has no point set; cannot bind writer")
        self._polydata = polydata
        self._bind()

    def _bind(self) -> None:
        self._data_array = self._polydata.GetPoints().GetData()
        self._view = numpy_support.vtk_to_numpy(self._data_array)

    def write(self, vs: np.ndarray) -> None:
        live = self._polydata.GetPoints().GetData()
        if live is not self._data_array:
            self._bind()
        arr = np.ascontiguousarray(vs, dtype=np.float32)
        if arr.shape != self._view.shape:
            raise ValueError(
                f"point count changed: writer expects {self._view.shape}, got {arr.shape}"
            )
        np.copyto(self._view, arr)
        self._data_array.Modified()
        self._polydata.Modified()


def sync_model_vertices(geometry, vs: np.ndarray) -> None:
    """Push sculpted vertex positions to the geometry's parametrization model."""
    model = getattr(geometry, "model", None)
    if model is None:
        return None
    mesh = getattr(model, "mesh", None)
    if mesh is None:
        return None
    import open3d as o3d

    mesh.vertices = o3d.utility.Vector3dVector(
        np.ascontiguousarray(vs, dtype=np.float64)
    )
    return None


def swap_geometry_topology(geometry, vs: np.ndarray, fs: np.ndarray) -> None:
    """Replace vertex coordinates AND face connectivity on a geometry."""
    from mosaic.meshing.utils import to_open3d
    from mosaic.parametrization import TriangularMesh

    vs_arr = np.ascontiguousarray(vs, dtype=np.float64)
    fs_arr = np.ascontiguousarray(fs, dtype=np.int64)
    new_mesh = TriangularMesh(to_open3d(vs_arr, fs_arr), repair=False)
    geometry.swap_data(points=vs_arr, faces=fs_arr, model=new_mesh)
