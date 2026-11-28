import numpy as np
import open3d as o3d
import pytest

from mosaic.meshing.utils import remesh, to_open3d


def test_rejects_inconsistently_oriented_mesh():
    sphere = o3d.geometry.TriangleMesh.create_sphere(radius=10, resolution=10)
    vs, fs = np.asarray(sphere.vertices), np.asarray(sphere.triangles).copy()
    fs[0] = fs[0][::-1]
    with pytest.raises(ValueError):
        remesh(to_open3d(vs, fs))


def test_rejects_mesh_with_non_manifold_vertex():
    tet = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float)
    vs = np.concatenate([tet, -tet[1:]])
    fs = np.array(
        [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]
        + [[0, 4, 5], [0, 6, 4], [0, 5, 6], [4, 6, 5]]
    )
    with pytest.raises(ValueError):
        remesh(to_open3d(vs, fs))
