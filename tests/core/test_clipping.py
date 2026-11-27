from types import SimpleNamespace

import numpy as np
import pytest
from vtkmodules.vtkCommonDataModel import vtkPlane
from vtkmodules.vtkCommonTransforms import vtkTransform

from mosaic import lod
from mosaic.clipping import ClipCut, bounds, clip_targets, eligible
from mosaic.geometry import Geometry, SegmentationGeometry


def _cloud(n=2000, seed=0, low=(10, -5, 100), high=(30, 40, 160)):
    rng = np.random.default_rng(seed)
    points = rng.uniform(low, high, size=(n, 3)).astype(np.float32)
    return Geometry(points=points, sampling_rate=1.0)


def _mesh():
    import open3d as o3d

    from mosaic.parametrization import TriangularMesh

    mesh = o3d.geometry.TriangleMesh.create_icosahedron(radius=20.0)
    mesh = mesh.subdivide_midpoint(number_of_iterations=2)
    tri = TriangularMesh(mesh, repair=False)
    geometry = Geometry(points=tri.vertices.astype(np.float32), model=tri)
    geometry.change_representation("mesh")
    return geometry


def _segmentation():
    points = np.argwhere(np.ones((4, 4, 4))).astype(np.float32)
    return SegmentationGeometry(points=points, sampling_rate=1.0)


def _pane(geometries, selected=()):
    return SimpleNamespace(
        get_selected_geometries=lambda: list(selected),
        container=SimpleNamespace(data=list(geometries)),
    )


def _planes(mapper):
    planes = mapper.GetClippingPlanes()
    if planes is None:
        return []
    return [planes.GetItem(i) for i in range(planes.GetNumberOfItems())]


def _kept(geometry, plane):
    normal, origin = np.array(plane.GetNormal()), np.array(plane.GetOrigin())
    return (geometry.points - origin) @ normal >= 0


def _placed(geometries, direction=(0, 0, -1)):
    cut = ClipCut()
    cut.set_objects(geometries)
    cut.place_facing(direction, geometries[0].actor.GetBounds())
    return cut


def test_eligible_kinds():
    from mosaic.parametrization import Sphere

    sphere = Geometry(
        points=np.zeros((4, 3), np.float32),
        model=Sphere(radius=np.array([5.0]), center=np.zeros(3)),
    )
    segmentation = _segmentation()

    transformed = _cloud(n=10)
    transformed.actor.SetUserTransform(vtkTransform())

    assert eligible(_cloud(n=10))
    assert not eligible(transformed)
    assert eligible(_mesh())
    assert not eligible(sphere)
    assert not eligible(segmentation)
    assert not eligible(Geometry(points=np.empty((0, 3), np.float32)))


def test_targets_selected_eligible_across_panes():
    a, b, c = _cloud(n=10), _cloud(n=10), _mesh()
    segmentation = _segmentation()
    data = _pane([a, b, segmentation], selected=[a, segmentation])
    models = _pane([c], selected=[c])

    assert clip_targets(data, models) == [a, c]


def test_targets_all_visible_when_nothing_selected():
    a, b, c = _cloud(n=10), _cloud(n=10), _mesh()
    b.set_visibility(False)

    assert clip_targets(_pane([a, b]), _pane([c])) == [a, c]


def test_targets_skip_empty_geometries():
    a = _cloud(n=10, low=(1000, 1000, 1000), high=(1100, 1100, 1100))
    empty = Geometry(points=np.empty((0, 3), np.float32))

    assert clip_targets(_pane([a, empty]), _pane([])) == [a]
    assert clip_targets(_pane([a, empty], selected=[empty]), _pane([])) == []


def test_targets_empty_when_selection_ineligible():
    a = _cloud(n=10)
    segmentation = _segmentation()

    data = _pane([a, segmentation], selected=[segmentation])
    assert clip_targets(data, _pane([])) == []


def test_set_objects_attaches_and_moves():
    a, b = _cloud(seed=1), _cloud(seed=2)
    cut = _placed([a])
    pose = cut.plane.GetOrigin(), cut.plane.GetNormal()

    cut.place_facing((0, 0, -1), a.actor.GetBounds())
    assert _planes(a.actor.GetMapper()) == [cut.plane]

    cut.set_objects([b])
    assert _planes(a.actor.GetMapper()) == []
    assert _planes(b.actor.GetMapper()) == [cut.plane]
    assert cut.geometries == [b]
    assert (cut.plane.GetOrigin(), cut.plane.GetNormal()) == pose


def test_set_objects_without_pose_cuts_nothing():
    a = _cloud()
    cut = ClipCut()
    cut.set_objects([a])

    assert not cut.has_pose
    assert _planes(a.actor.GetMapper()) == []


def test_other_planes_untouched():
    a, b = _cloud(seed=1), _cloud(seed=2)
    other = vtkPlane()
    a.actor.GetMapper().AddClippingPlane(other)
    b.actor.GetMapper().AddClippingPlane(other)
    cut = _placed([a])

    cut.set_objects([b])
    assert _planes(a.actor.GetMapper()) == [other]

    cut.clear()
    assert _planes(b.actor.GetMapper()) == [other]
    assert cut.geometries == []
    assert not cut.has_pose


def test_place_facing_cuts_nothing_then_push_cuts():
    a = _cloud()
    cut = _placed([a])
    assert cut.has_pose
    assert _kept(a, cut.plane).all()

    low, high = cut.extent()
    cut.push((high - low) / 2)
    assert 0.4 < _kept(a, cut.plane).mean() < 0.6

    cut.push(1e6)
    assert np.dot(cut.plane.GetNormal(), cut.plane.GetOrigin()) == pytest.approx(high)
    assert _kept(a, cut.plane).sum() <= 1

    cut.push(-1e6)
    assert np.dot(cut.plane.GetNormal(), cut.plane.GetOrigin()) == pytest.approx(low)
    assert _kept(a, cut.plane).all()


def test_place_facing_oblique_cuts_nothing():
    a = _cloud()
    direction = np.array([1.0, -2.0, 0.5])
    cut = _placed([a], direction=direction)

    np.testing.assert_allclose(
        cut.plane.GetNormal(), direction / np.linalg.norm(direction)
    )
    assert _kept(a, cut.plane).all()
    assert np.dot(cut.plane.GetNormal(), cut.plane.GetOrigin()) == pytest.approx(
        cut.extent()[0]
    )


def test_tilt_and_face():
    a = _cloud()
    cut = _placed([a])
    origin = cut.plane.GetOrigin()

    cut.tilt((0, 1, 0), 90)
    normal = np.array(cut.plane.GetNormal())
    np.testing.assert_allclose(np.abs(normal), (1, 0, 0), atol=1e-12)
    assert cut.plane.GetOrigin() == origin

    cut.face((0, 0, -2))
    np.testing.assert_allclose(cut.plane.GetNormal(), (0, 0, -1), atol=1e-12)
    assert cut.plane.GetOrigin() == origin


def test_lod_standin_carries_plane(monkeypatch):
    monkeypatch.setattr(lod, "get_point_budget", lambda: 50)
    a = _cloud(n=500)
    other = vtkPlane()
    a.actor.GetMapper().AddClippingPlane(other)
    a.lod.setup()
    assert a.lod.actor is not None

    cut = _placed([a])
    assert _planes(a.lod.actor.GetMapper()) == [other, cut.plane]

    a.lod.setup()
    assert _planes(a.lod.actor.GetMapper()) == [other, cut.plane]

    a.change_representation("pointcloud")
    assert a.lod.actor is not None
    assert _planes(a.lod.actor.GetMapper()) == [other, cut.plane]

    cut.clear()
    assert _planes(a.lod.actor.GetMapper()) == [other]
    a.lod.begin()
    assert _planes(a.lod.actor.GetMapper()) == [other]


def test_lod_begin_copies_owner_planes(monkeypatch):
    monkeypatch.setattr(lod, "get_point_budget", lambda: 50)
    a = _cloud(n=500)
    a.lod.setup()

    plane = vtkPlane()
    a.actor.GetMapper().AddClippingPlane(plane)
    a.lod.begin()
    assert _planes(a.lod.actor.GetMapper()) == [plane]


def test_representation_change_keeps_plane():
    a = _mesh()
    cut = _placed([a])

    a.change_representation("surface")
    assert _planes(a.actor.GetMapper()) == [cut.plane]

    cut.clear()
    assert _planes(a.actor.GetMapper()) == []


def test_swap_data_keeps_plane():
    a = _cloud()
    cut = _placed([a])

    a.swap_data(_cloud(seed=3).points)
    assert _planes(a.actor.GetMapper()) == [cut.plane]


def test_state_round_trip_skips_missing():
    a, b = _cloud(seed=1), _cloud(seed=2)
    cut = _placed([a, b], direction=(1, 0, 0))
    cut.push(5.0)

    state = cut.to_state({a.uuid})
    assert state == {
        "origin": list(cut.plane.GetOrigin()),
        "normal": list(cut.plane.GetNormal()),
        "uuids": [a.uuid],
    }

    restored = ClipCut()
    restored.from_state({**state, "uuids": [a.uuid, "gone"]}, {a.uuid: a, b.uuid: b})
    assert restored.has_pose
    assert restored.geometries == [a]
    assert restored.plane.GetOrigin() == cut.plane.GetOrigin()
    assert restored.plane.GetNormal() == cut.plane.GetNormal()
    assert restored.plane in _planes(a.actor.GetMapper())

    restored.from_state({**state, "uuids": ["gone"]}, {a.uuid: a})
    assert not restored.has_pose
    assert restored.geometries == []
    assert restored.plane not in _planes(a.actor.GetMapper())

    restored.from_state(state, {a.uuid: a})
    restored.from_state(None, {a.uuid: a})
    assert not restored.has_pose
    assert restored.geometries == []
    assert restored.plane not in _planes(a.actor.GetMapper())
    assert restored.to_state({a.uuid}) is None


def test_bounds_merges_geometries():
    first = _cloud(seed=0, low=(10, -5, 100), high=(30, 40, 160))
    second = _cloud(seed=1, low=(-20, 0, 120), high=(0, 60, 130))

    merged = np.array(bounds([first, second]))

    lower = np.minimum(first.points.min(axis=0), second.points.min(axis=0))
    upper = np.maximum(first.points.max(axis=0), second.points.max(axis=0))
    np.testing.assert_allclose(merged[0::2], lower, rtol=1e-6)
    np.testing.assert_allclose(merged[1::2], upper, rtol=1e-6)
