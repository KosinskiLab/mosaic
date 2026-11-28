import numpy as np
import open3d as o3d

from mosaic.meshing.utils import _orientation_conflicts, to_open3d
from mosaic.parametrization import (
    _drop_small_pieces,
    _fill_by_refinement,
    _orient_closed_outward,
)


def _sphere():
    sphere = o3d.geometry.TriangleMesh.create_sphere(radius=10, resolution=10)
    return np.asarray(sphere.vertices), np.asarray(sphere.triangles)


def _edge_counts(fs):
    edges = np.sort(
        np.concatenate([fs[:, [0, 1]], fs[:, [1, 2]], fs[:, [2, 0]]]), axis=1
    )
    return np.unique(edges, axis=0, return_counts=True)[1]


def _signed_volume(vs, fs):
    tri = vs[fs]
    return np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6


def test_refinement_fill_closes_holes_left_by_non_manifold_faces():
    vs, fs = _sphere()
    a, b = fs[40, :2]
    vs = np.vstack([vs, (vs[a] + vs[b]) * 0.6])
    filled = np.vstack([fs, [a, b, len(vs) - 1]])
    _, new_fs, _ = _fill_by_refinement(vs, fs, filled, None)
    counts = _edge_counts(new_fs)
    assert counts.min() == 2 and counts.max() == 2


def test_drops_pieces_far_smaller_than_the_surface():
    vs, fs = _sphere()
    tet = np.array([[50, 0, 0], [51, 0, 0], [50, 1, 0], [50, 0, 1]], dtype=float)
    tet_fs = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]) + len(vs)
    mesh = _drop_small_pieces(to_open3d(np.vstack([vs, tet]), np.vstack([fs, tet_fs])))
    assert len(mesh.triangles) == len(fs)


def test_turns_inside_out_closed_surface_outward():
    vs, fs = _sphere()
    oriented = _orient_closed_outward(vs, fs[:, ::-1].copy())
    assert _signed_volume(vs, oriented) > 0


def test_leaves_open_surface_orientation_alone():
    vs, fs = _sphere()
    cap = fs[(vs[fs][:, :, 2] > 0).all(axis=1)][:, ::-1].copy()
    np.testing.assert_array_equal(_orient_closed_outward(vs, cap), cap)


def test_turns_single_reversed_faces_to_match_their_surface():
    vs, fs = _sphere()
    fs = fs.copy()
    a, b = fs[40, :2]
    neighbours = np.flatnonzero(np.isin(fs, [a, b]).sum(axis=1) == 2)
    fs[neighbours] = fs[neighbours, ::-1]
    oriented = _orient_closed_outward(vs, fs)
    assert _orientation_conflicts(oriented) == 0
    assert _signed_volume(vs, oriented) > 0


def test_orient_outward_turns_closed_surfaces_and_normals():
    from mosaic.parametrization import TriangularMesh

    vs, fs = _sphere()
    inside_out = to_open3d(vs, fs[:, ::-1].copy())
    inside_out.compute_vertex_normals()
    model = TriangularMesh(inside_out)
    model.orient_outward()
    v, f = np.asarray(model.vertices), np.asarray(model.triangles)
    assert _signed_volume(v, f) > 0
    normals = np.asarray(model.mesh.vertex_normals)
    assert (np.einsum("ij,ij->i", normals, v) > 0).all()


def test_construction_keeps_a_flipped_closed_surface():
    from mosaic.parametrization import TriangularMesh

    vs, fs = _sphere()
    for repair in (True, False):
        model = TriangularMesh(to_open3d(vs, fs[:, ::-1].copy()), repair=repair)
        assert _signed_volume(model.vertices, model.triangles) < 0


def test_unpickled_flipped_mesh_stays_flipped():
    from mosaic.parametrization import TriangularMesh

    vs, fs = _sphere()
    model = TriangularMesh.__new__(TriangularMesh)
    model.__setstate__({"vertices": vs, "triangles": fs[:, ::-1].copy()})
    assert _signed_volume(model.vertices, model.triangles) < 0


def test_fit_faces_closed_surfaces_outward(monkeypatch):
    from mosaic.geometry import GeometryData
    from mosaic.operations import fit
    from mosaic.parametrization import BallPivoting

    vs, fs = _sphere()
    inside_out = BallPivoting(to_open3d(vs, fs[:, ::-1].copy()))
    monkeypatch.setattr(
        BallPivoting, "fit", classmethod(lambda cls, *a, **k: inside_out)
    )
    result = fit(GeometryData(points=vs), method="ball_pivoting", radii="1")
    assert _signed_volume(result.model.vertices, result.model.triangles) > 0


def test_flip_normals_turns_a_closed_mesh_inward():
    from mosaic.geometry import GeometryData
    from mosaic.parametrization import TriangularMesh
    from mosaic.tabs.model import _repair_mesh

    vs, fs = _sphere()
    geometry = GeometryData(points=vs, model=TriangularMesh(to_open3d(vs, fs)))
    flipped = _repair_mesh(geometry, max_hole_size=0, flip_normals=True)
    assert _signed_volume(flipped.model.vertices, flipped.model.triangles) < 0


def test_orientation_keeps_vertex_indices():
    from mosaic.parametrization import TriangularMesh

    vs, fs = _sphere()
    model = TriangularMesh(to_open3d(vs, fs[:, ::-1].copy()), repair=False)
    np.testing.assert_array_equal(model.vertices, vs)
    np.testing.assert_array_equal(np.sort(model.triangles, axis=1), np.sort(fs, axis=1))
