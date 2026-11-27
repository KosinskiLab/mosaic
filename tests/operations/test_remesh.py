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
