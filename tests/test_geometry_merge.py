import numpy as np

from mosaic.geometry import (
    Geometry,
    SegmentationGeometry,
    VolumeGeometry,
    merge_geometries,
)


def _pts(n: int = 60, seed: int = 0) -> np.ndarray:
    return (
        np.random.default_rng(seed).uniform(0.0, 10.0, size=(n, 3)).astype(np.float32)
    )


def _seg(seed: int) -> SegmentationGeometry:
    return SegmentationGeometry(points=_pts(seed=seed), sampling_rate=1.0)


def test_homogeneous_segmentation_keeps_representation():
    merged = merge_geometries([_seg(1), _seg(2)])
    assert isinstance(merged, SegmentationGeometry)
    assert merged._representation == "segmentation"


def test_homogeneous_pointcloud_stays_base_geometry():
    merged = merge_geometries(
        [Geometry(points=_pts(seed=1)), Geometry(points=_pts(seed=2))]
    )
    assert type(merged) is Geometry
    assert merged._representation == "pointcloud"


def test_mixed_types_fall_back_to_pointcloud():
    merged = merge_geometries([_seg(1), Geometry(points=_pts(seed=3))])
    assert type(merged) is Geometry
    assert merged._representation == "pointcloud"


def _vol(seed: int) -> VolumeGeometry:
    rng = np.random.default_rng(seed)
    n = 24
    zz, yy, xx = np.mgrid[0:n, 0:n, 0:n]
    r = np.sqrt((xx - 12) ** 2 + (yy - 12) ** 2 + (zz - 12) ** 2)
    vol = (r < 7).astype(np.float32)
    normals = rng.normal(size=(40, 3)).astype(np.float32)
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)
    return VolumeGeometry(
        points=rng.uniform(0, n, size=(40, 3)).astype(np.float32),
        normals=normals,
        volume=vol,
        volume_sampling_rate=np.ones(3),
        target_resolution=1.0,
    )


def test_homogeneous_volume_keeps_representation_and_grid():
    merged = merge_geometries([_vol(1), _vol(2)])
    assert isinstance(merged, VolumeGeometry)


def test_merge_synthesizes_lod_from_inputs(monkeypatch):
    from mosaic import lod
    from mosaic.geometry import Geometry, merge_geometries

    monkeypatch.setattr(lod, "get_point_budget", lambda: 50)

    a = Geometry(points=_pts(n=60, seed=1))
    b = Geometry(points=_pts(n=60, seed=2))
    a.lod.indices = np.array([0, 10, 20])
    b.lod.indices = np.array([5, 15, 25])

    merged = merge_geometries([a, b])

    # b's indices shift by a's point count (60).
    assert merged.lod.indices.tolist() == [0, 10, 20, 65, 75, 85]
    assert merged.lod.actor is not None


def test_merge_skips_lod_when_an_input_lacks_one(monkeypatch):
    from mosaic import lod
    from mosaic.geometry import Geometry, merge_geometries

    monkeypatch.setattr(lod, "get_point_budget", lambda: 50)

    a = Geometry(points=_pts(n=60, seed=1))
    b = Geometry(points=_pts(n=60, seed=2))
    a.lod.indices = np.array([0, 10, 20])
    # b has no LOD -> not a resynthesizable merge.

    merged = merge_geometries([a, b])

    assert merged.lod.indices is None


def test_merge_skips_lod_when_result_fits_budget(monkeypatch):
    from mosaic import lod
    from mosaic.geometry import Geometry, merge_geometries

    monkeypatch.setattr(lod, "get_point_budget", lambda: 1000)

    a = Geometry(points=_pts(n=60, seed=1))
    b = Geometry(points=_pts(n=60, seed=2))
    a.lod.indices = np.array([0, 10, 20])
    b.lod.indices = np.array([5, 15, 25])

    merged = merge_geometries([a, b])

    # 120 points <= budget -> no LOD needed.
    assert merged.lod.indices is None
