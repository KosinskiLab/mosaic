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
