from unittest.mock import Mock, call

import numpy as np
import pytest
import vtk

from mosaic.clip_mode import ClipInteractorStyle, ClipMode
from mosaic.data import MosaicData
from mosaic.geometry import SegmentationGeometry
from mosaic.widgets.status_indicator import ViewerModes

HINT = (
    "Right-drag to cut · Shift+right-drag to tilt · F to face · Right-click to remove"
)


@pytest.fixture
def md(qapp, mock_vtk_widget):
    window = mock_vtk_widget.GetRenderWindow()
    window.GetRenderers.return_value.GetFirstRenderer.return_value = vtk.vtkRenderer()
    window.GetSize.return_value = (300, 400)
    return MosaicData(mock_vtk_widget)


def _add_cloud(pane, seed=0, low=(10, -5, 100), high=(30, 40, 160)):
    rng = np.random.default_rng(seed)
    points = rng.uniform(low, high, size=(500, 3)).astype(np.float32)
    geometry = pane.container.get(pane.add(points=points, sampling_rate=1.0))
    pane.update()
    return geometry


def _select(pane, geometry):
    pane.set_selection_by_uuid([geometry.uuid])
    assert pane.get_selected_geometries() == [geometry]


def _planes(geometry):
    planes = geometry.actor.GetMapper().GetClippingPlanes()
    if planes is None:
        return []
    return [planes.GetItem(i) for i in range(planes.GetNumberOfItems())]


def _drag(mode, start, end, shift=False):
    mode.right_press(*start)
    mode.right_move(*end, shift)
    mode.right_release(*end)


def _active(md, geometry):
    mode = ClipMode(md.viewport, md.viewport.clip_cut, lambda text: None)
    _select(md.data, geometry)
    mode.activate()
    return mode


def _pose(cut):
    return np.array(cut.plane.GetOrigin()), np.array(cut.plane.GetNormal())


def test_activate_targets_and_hint(md):
    cloud = _add_cloud(md.data)
    _select(md.data, cloud)
    messages = []
    ClipMode(md.viewport, md.viewport.clip_cut, messages.append).activate()

    assert md.viewport.clip_cut.geometries == [cloud]
    assert messages == [HINT]

    segmentation = SegmentationGeometry(
        points=np.argwhere(np.ones((4, 4, 4))).astype(np.float32), sampling_rate=1.0
    )
    md.data.add(segmentation)
    md.data.update()
    _select(md.data, segmentation)
    messages.clear()
    ClipMode(md.viewport, md.viewport.clip_cut, messages.append).activate()

    assert md.viewport.clip_cut.geometries == []
    assert messages == ["Nothing to cut in the selection"]


def test_first_drag_places_then_pushes(md):
    cloud = _add_cloud(md.data)
    mode = _active(md, cloud)
    cut = md.viewport.clip_cut

    mode.right_press(100, 100)
    mode.right_move(100, 98, False)
    assert not cut.has_pose

    mode.right_move(100, 60, False)
    mode.right_release(100, 60)

    zmin, zmax = cloud.actor.GetBounds()[4:6]
    origin, normal = _pose(cut)
    assert cut.has_pose
    np.testing.assert_allclose(normal, (0, 0, -1))
    assert origin @ normal == pytest.approx(-zmax + 40 / 400 * (zmax - zmin))
    assert _planes(cloud) == [cut.plane]


def test_drag_up_pulls_back(md):
    cloud = _add_cloud(md.data)
    mode = _active(md, cloud)
    cut = md.viewport.clip_cut
    _drag(mode, (100, 100), (100, 20))
    deep = _pose(cut)[0] @ _pose(cut)[1]

    _drag(mode, (100, 100), (100, 140))

    origin, normal = _pose(cut)
    assert origin @ normal == pytest.approx(deep - 40 / 400 * np.ptp(cut.extent()))


def test_shift_drag_tilts(md):
    cloud = _add_cloud(md.data)
    mode = _active(md, cloud)
    cut = md.viewport.clip_cut
    _drag(mode, (100, 100), (100, 60))
    origin, normal = _pose(cut)

    _drag(mode, (100, 100), (120, 100), shift=True)

    tilted_origin, tilted_normal = _pose(cut)
    np.testing.assert_allclose(tilted_origin, origin)
    assert tilted_normal @ normal == pytest.approx(np.cos(np.radians(10)))
    assert tilted_normal[1] == pytest.approx(0, abs=1e-12)


def test_shift_drag_vertical_tilts_about_right_axis(md):
    cloud = _add_cloud(md.data)
    mode = _active(md, cloud)
    cut = md.viewport.clip_cut
    _drag(mode, (100, 100), (100, 60))

    _drag(mode, (100, 100), (100, 110), shift=True)

    tilted_normal = _pose(cut)[1]
    assert tilted_normal @ (0, 0, -1) == pytest.approx(np.cos(np.radians(5)))
    assert tilted_normal[0] == pytest.approx(0, abs=1e-12)


def test_click_removes_cut(md):
    cloud = _add_cloud(md.data)
    mode = _active(md, cloud)
    cut = md.viewport.clip_cut
    _drag(mode, (100, 100), (100, 60))

    _drag(mode, (100, 100), (103, 102))

    assert cut.geometries == []
    assert _planes(cloud) == []


def test_drag_after_click_cuts_again(md):
    cloud = _add_cloud(md.data)
    mode = _active(md, cloud)
    cut = md.viewport.clip_cut
    _drag(mode, (100, 100), (100, 60))
    _drag(mode, (100, 100), (100, 100))

    _drag(mode, (100, 100), (100, 60))

    assert cut.geometries == [cloud]
    assert _planes(cloud) == [cut.plane]


def test_f_faces_camera(md):
    cloud = _add_cloud(md.data)
    mode = _active(md, cloud)
    cut = md.viewport.clip_cut
    _drag(mode, (100, 100), (100, 60))
    _drag(mode, (100, 100), (130, 100), shift=True)
    origin = _pose(cut)[0]

    mode.key("f")

    np.testing.assert_allclose(_pose(cut)[1], (0, 0, -1), atol=1e-12)
    np.testing.assert_allclose(_pose(cut)[0], origin)


def test_drag_uses_lod_and_restores(md, monkeypatch):
    cloud = _add_cloud(md.data)
    mode = _active(md, cloud)
    calls = []
    monkeypatch.setattr(cloud.lod, "begin", lambda: calls.append("begin"))
    monkeypatch.setattr(cloud.lod, "end", lambda: calls.append("end"))

    mode.right_press(100, 100)
    mode.right_move(100, 60, False)
    mode.right_move(100, 50, False)
    assert calls == ["begin"]

    mode.right_release(100, 50)
    assert calls == ["begin", "end"]


def test_outline_shown_while_moving(md, qtbot):
    cloud = _add_cloud(md.data)
    mode = _active(md, cloud)
    renderer = md.viewport.vtk_widget.GetRenderWindow().GetRenderers()
    renderer = renderer.GetFirstRenderer()
    actors = renderer.GetActors()
    assert actors.GetNumberOfItems() == 1
    outline = actors.GetItemAsObject(0)
    assert not outline.GetVisibility()

    mode.right_press(100, 100)
    mode.right_move(100, 60, False)
    assert outline.GetVisibility()
    outline.GetMapper().Update()
    assert outline.GetMapper().GetInput().GetNumberOfPoints() > 0

    mode.right_release(100, 60)
    qtbot.waitUntil(lambda: not outline.GetVisibility(), timeout=2000)

    mode.deactivate()
    assert renderer.GetActors().GetNumberOfItems() == 0


def test_reenter_moves_cut(md):
    first, second = _add_cloud(md.data, seed=0), _add_cloud(md.data, seed=1)
    mode = _active(md, first)
    cut = md.viewport.clip_cut
    _drag(mode, (100, 100), (100, 60))
    origin, normal = _pose(cut)
    mode.deactivate()

    _active(md, second)

    assert _planes(first) == []
    assert _planes(second) == [cut.plane]
    np.testing.assert_allclose(_pose(cut)[0], origin)
    np.testing.assert_allclose(_pose(cut)[1], normal)


def test_set_mode_clip_and_back(md):
    cloud = _add_cloud(md.data)
    _select(md.data, cloud)
    viewport = md.viewport
    messages = []
    viewport.status_message.connect(messages.append)

    viewport.set_mode(ViewerModes.CLIP)
    assert viewport._interaction_mode == "clip"
    assert messages == [HINT]
    _drag(viewport._active_mode, (100, 100), (100, 60))

    viewport.set_mode(ViewerModes.VIEWING)

    assert viewport._interaction_mode is None
    assert viewport._active_mode is None
    assert viewport.clip_cut.has_pose
    assert _planes(cloud) == [viewport.clip_cut.plane]


def test_style_forwards_right_drag_and_f():
    mode = Mock()
    interactor = vtk.vtkGenericRenderWindowInteractor()
    interactor.SetInteractorStyle(ClipInteractorStyle(mode))

    interactor.SetEventInformation(10, 20, 0, 0)
    interactor.InvokeEvent("RightButtonPressEvent")
    interactor.SetEventInformation(10, 50, 0, 1)
    interactor.InvokeEvent("MouseMoveEvent")
    interactor.InvokeEvent("RightButtonReleaseEvent")
    interactor.SetEventInformation(30, 50, 0, 0)
    interactor.InvokeEvent("MouseMoveEvent")
    for key in ("F", "x"):
        interactor.SetKeySym(key)
        interactor.SetKeyCode(key)
        interactor.InvokeEvent("CharEvent")

    assert mode.mock_calls == [
        call.right_press(10, 20),
        call.right_move(10, 50, True),
        call.right_release(10, 50),
        call.key("f"),
    ]
