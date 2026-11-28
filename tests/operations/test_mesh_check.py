import numpy as np
import open3d as o3d

from mosaic.meshing.check import check_mesh
from mosaic.meshing.utils import to_open3d
from mosaic.parametrization import TriangularMesh

from .test_close_holes import _mobius


def _sphere(resolution=10):
    sphere = o3d.geometry.TriangleMesh.create_sphere(radius=10, resolution=resolution)
    return np.asarray(sphere.vertices), np.asarray(sphere.triangles)


def _touching_tetrahedra():
    tet = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float)
    vs = np.concatenate([tet, -tet[1:]])
    fs = np.array(
        [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]
        + [[0, 4, 5], [0, 6, 4], [0, 5, 6], [4, 6, 5]]
    )
    return vs, fs


def test_closed_sphere_has_no_defects():
    assert check_mesh(*_sphere()) == []


def test_small_hole_is_a_defect():
    vs, fs = _sphere()
    defects = check_mesh(vs, fs[1:])
    assert [d.kind for d in defects] == ["hole"]
    assert defects[0].perimeter > 0


def test_large_opening_is_not_a_defect():
    vs, fs = _sphere()
    assert check_mesh(vs, fs[(vs[fs][:, :, 2].max(axis=1) < 4)]) == []


def test_non_orientable_surface_has_a_twisted_spot():
    assert "twisted" in {d.kind for d in check_mesh(*_mobius(60, 4))}


def test_self_touching_vertex_is_a_twisted_spot():
    assert [d.kind for d in check_mesh(*_touching_tetrahedra())] == ["twisted"]


def test_fin_triangle_gives_a_non_manifold_edge():
    vs, fs = _sphere()
    a, b = fs[40, :2]
    vs = np.vstack([vs, (vs[a] + vs[b]) * 0.6])
    fs = np.vstack([fs, [a, b, len(vs) - 1]])
    assert "nonmanifold" in {d.kind for d in check_mesh(vs, fs)}


def test_mesh_without_faces_has_no_defects():
    assert check_mesh(np.zeros((3, 3)), np.zeros((0, 3), dtype=int)) == []


def test_replaced_model_is_checked_again():
    vs, fs = _sphere()
    assert TriangularMesh(to_open3d(vs, fs)).defects == []
    assert TriangularMesh(to_open3d(vs, fs[1:]), repair=False).defects != []


def test_checking_one_mesh_does_not_block_another(monkeypatch):
    import threading
    import time

    from mosaic import meshing

    def slow_for_big(vertices, faces):
        if len(faces) > 1000:
            time.sleep(1.0)
        return []

    monkeypatch.setattr(meshing, "check_mesh", slow_for_big)
    big = TriangularMesh(to_open3d(*_sphere(resolution=40)), repair=False)
    small = TriangularMesh(to_open3d(*_sphere()), repair=False)
    worker = threading.Thread(target=lambda: big.defects)
    worker.start()
    time.sleep(0.1)
    start = time.perf_counter()
    _ = small.defects
    elapsed = time.perf_counter() - start
    worker.join()
    assert elapsed < 0.5
