"""Orientation-free point clouds must not acquire fabricated normals/quaternions.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np

from mosaic.geometry import Geometry, merge_geometries
from mosaic.utils import normals_to_rot, NORMAL_REFERENCE
import mosaic.operations as ops


def _pts(n=2000, seed=0):
    return np.random.default_rng(seed).uniform(0, 50, size=(n, 3)).astype(np.float32)


def test_fresh_pointcloud_has_no_normals():
    g = Geometry(points=_pts())
    assert g._geometry_data.normals is None
    assert g.has_normals is False


def test_downsample_number_does_not_fabricate_normals():
    g = Geometry(points=_pts())
    res = ops.downsample(g._geometry_data, method="number", size=500)
    assert res.has_normals is False


def test_downsample_radius_does_not_fabricate_normals():
    g = Geometry(points=_pts())
    res = ops.downsample(g._geometry_data, method="radius", voxel_size=2.0)
    assert res.has_normals is False


def test_cluster_children_have_no_normals():
    g = Geometry(points=_pts())
    children = ops.cluster(g._geometry_data, method="kmeans")
    assert all(c.has_normals is False for c in children)


def test_subset_of_normalless_cloud_has_no_normals():
    g = Geometry(points=_pts())
    assert g[np.arange(100)].has_normals is False


def test_compute_normals_flip_without_normals_raises():
    import pytest

    g = Geometry(points=_pts(n=100))
    with pytest.raises(ValueError):
        ops.compute_normals(g._geometry_data, method="flip")


def test_quaternions_none_without_orientation():
    # No stored quaternions and no real normals -> None, and reading it must
    # not persist anything.
    g = Geometry(points=_pts(n=10))
    assert g.quaternions is None
    assert g.has_normals is False
    assert g._geometry_data.quaternions is None


def test_quaternions_derived_from_real_normals_not_persisted():
    g = Geometry(points=_pts(n=8))
    normals = np.tile(np.array([0, 1, 0], np.float32), (8, 1))
    g.normals = normals  # real normals, no stored quaternions

    q = g.quaternions
    assert q is not None
    assert q.shape == (8, 4)
    assert np.allclose(q, normals_to_rot(normals, scalar_first=True))
    # Derived on demand, not written back.
    assert g._geometry_data.quaternions is None


def test_quaternions_real_after_compute_normals():
    g = Geometry(points=_pts(n=200))
    computed = ops.compute_normals(g._geometry_data, method="compute")
    gc = Geometry(polydata=computed.polydata)
    assert gc.has_normals is True
    q = gc.quaternions
    assert q is not None
    assert q.shape == (gc.get_number_of_points(), 4)
    assert np.allclose(q, normals_to_rot(gc.normals, scalar_first=True))


def test_swap_data_points_only_leaves_no_normals():
    g = Geometry(points=_pts(n=100))
    g.swap_data(points=_pts(n=120, seed=5))
    assert g.has_normals is False


def test_swap_data_with_quaternions_still_sets_normals():
    g = Geometry(points=_pts(n=8))
    normals = np.tile(np.array([0, 1, 0], np.float32), (8, 1))
    quats = normals_to_rot(normals, scalar_first=True)
    g.swap_data(points=_pts(n=8, seed=3), quaternions=quats)
    assert g.has_normals is True


def _cloud(n, seed, with_normals=False, with_quats=False):
    g = Geometry(points=_pts(n=n, seed=seed))
    if with_normals:
        g.normals = np.tile(np.array([0, 1, 0], np.float32), (n, 1))
    if with_quats:
        g.quaternions = normals_to_rot(
            np.tile(np.array([1, 0, 0], np.float32), (n, 1)), scalar_first=True
        )
    return g


def test_merge_normalless_clouds_stays_normalless():
    merged = merge_geometries([_cloud(50, 1), _cloud(30, 2)])
    assert merged.has_normals is False


def test_merge_mixed_normals_fills_missing_only():
    a = _cloud(50, 1, with_normals=True)  # real (0,1,0)
    b = _cloud(30, 2)  # none
    merged = merge_geometries([a, b])
    assert merged.has_normals is True
    n = merged.normals
    assert n.shape == (80, 3)
    assert np.allclose(n[:50], (0, 1, 0))  # a preserved
    assert np.allclose(n[50:], NORMAL_REFERENCE)  # b filled


def test_merge_all_real_normals_preserved():
    a = _cloud(50, 1, with_normals=True)
    b = _cloud(30, 2, with_normals=True)
    merged = merge_geometries([a, b])
    assert np.allclose(merged.normals, (0, 1, 0))


def test_merge_mixed_quaternions_fills_identity():
    a = _cloud(40, 1, with_quats=True)
    b = _cloud(20, 2)
    merged = merge_geometries([a, b])
    q = merged._geometry_data.quaternions
    assert q is not None
    assert q.shape == (60, 4)
    identity = normals_to_rot(
        np.tile(np.array(NORMAL_REFERENCE, np.float32), (20, 1)), scalar_first=True
    )
    assert np.allclose(q[40:], identity)


def test_merge_quaternionless_clouds_stay_quaternionless():
    merged = merge_geometries([_cloud(50, 1), _cloud(30, 2)])
    assert merged._geometry_data.quaternions is None


def test_swap_data_points_only_clears_stale_normals():
    g = Geometry(points=_pts(n=50))
    g.normals = np.tile(np.array([0, 1, 0], np.float32), (50, 1))
    assert g.has_normals is True
    g.swap_data(points=_pts(n=51, seed=9))  # count changed, no normals given
    assert g.has_normals is False  # stale normals dropped, not ragged


def test_swap_data_same_count_with_normals_keeps_them():
    g = Geometry(points=_pts(n=20))
    normals = np.tile(np.array([0, 1, 0], np.float32), (20, 1))
    g.swap_data(points=_pts(n=20, seed=4), normals=normals)
    assert g.has_normals is True
    assert g.normals.shape == (20, 3)


def test_swap_data_points_only_clears_stale_quaternions():
    g = Geometry(points=_pts(n=20))
    normals = np.tile(np.array([0, 1, 0], np.float32), (20, 1))
    g.quaternions = normals_to_rot(normals, scalar_first=True)
    assert g._geometry_data.quaternions is not None
    g.swap_data(points=_pts(n=25, seed=6))  # count changed, no quaternions given
    assert g._geometry_data.quaternions is None


def _icosphere_mesh(radius=20.0, iterations=2):
    import open3d as o3d
    from mosaic.parametrization import TriangularMesh

    mesh = o3d.geometry.TriangleMesh.create_icosahedron(radius=radius)
    mesh = mesh.subdivide_midpoint(number_of_iterations=iterations)
    return TriangularMesh(mesh, repair=False)


def test_mesh_to_cg_with_normalless_inclusion_does_not_raise(tmp_path):
    from mosaic.meshing.coarse_graining import mesh_to_cg

    tri = _icosphere_mesh()
    mesh_geom = Geometry(points=tri.vertices.astype(np.float32), model=tri)
    mesh_geom.change_representation("mesh")

    inclusion = Geometry(points=tri.vertices[:5].astype(np.float32))
    assert inclusion.has_normals is False
    assert inclusion.quaternions is None

    ret = mesh_to_cg(
        mesh_geom._geometry_data,
        output_directory=str(tmp_path),
        inclusions=[{"name": "test", "data": inclusion}],
        edge_length=10.0,
        include_normals=False,
    )
    assert ret is True


def test_projected_angle_normalless_geometry_returns_none():
    tri = _icosphere_mesh()
    query = Geometry(points=tri.vertices.astype(np.float32), model=tri)
    query.change_representation("mesh")

    g = Geometry(points=tri.vertices[:10].astype(np.float32))
    assert g.has_normals is False

    from mosaic.properties import projected_angle

    assert projected_angle(g, [query]) is None
