from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
import vtk

from mosaic.clip_mode import ClipInteractorStyle
from mosaic.data import MosaicData
from mosaic.formats import read_session_meta
from mosaic.gui import App
from mosaic.undo import STACK
from mosaic.widgets.status_indicator import ViewerModes


@pytest.fixture
def md(qapp, mock_vtk_widget):
    window = mock_vtk_widget.GetRenderWindow()
    window.GetRenderers.return_value.GetFirstRenderer.return_value = vtk.vtkRenderer()
    return MosaicData(mock_vtk_widget)


def _add_cloud(pane, seed=0):
    rng = np.random.default_rng(seed)
    points = rng.uniform((10, -5, 100), (30, 40, 160), size=(500, 3))
    geometry = pane.container.get(
        pane.add(points=points.astype(np.float32), sampling_rate=1.0)
    )
    pane.update()
    return geometry


def _cut(md, geometries):
    cut = md.viewport.clip_cut
    cut.set_objects(geometries)
    cut.place_facing((0.3, -0.2, -1.0), geometries[0].actor.GetBounds())
    cut.push(12.5)
    return cut


def _register(md):
    fake = SimpleNamespace(cdata=md)
    md.register_session_hook(
        lambda: App._collect_clip(fake), lambda meta: App._restore_clip(fake, meta)
    )
    return None


def _planes(geometry):
    planes = geometry.actor.GetMapper().GetClippingPlanes()
    if planes is None:
        return []
    return [planes.GetItem(i) for i in range(planes.GetNumberOfItems())]


def test_session_round_trip_restores_cut(md, mock_vtk_widget, tmp_path):
    cloud = _add_cloud(md.data)
    _register(md)
    cut = _cut(md, [cloud])
    path = md.to_file(str(tmp_path / "s.mosaic"))

    loaded = MosaicData(mock_vtk_widget)
    _register(loaded)
    loaded.load_session(path)

    restored = loaded.data.container.get(cloud.uuid)
    plane = loaded.viewport.clip_cut.plane
    assert _planes(restored) == [plane]
    np.testing.assert_allclose(plane.GetOrigin(), cut.plane.GetOrigin())
    np.testing.assert_allclose(plane.GetNormal(), cut.plane.GetNormal())


def test_removed_object_not_saved(md, tmp_path):
    first, second = _add_cloud(md.data, seed=0), _add_cloud(md.data, seed=1)
    _register(md)
    _cut(md, [first, second])

    md.data.remove([second])
    path = md.to_file(str(tmp_path / "s.mosaic"))

    assert read_session_meta(path)["clip"]["uuids"] == [first.uuid]


def test_right_click_does_not_deselect_in_clip_mode(md):
    cloud = _add_cloud(md.data)
    md.data.set_selection_by_uuid([cloud.uuid])
    fake = SimpleNamespace(cdata=md)

    md.viewport._interaction_mode = "clip"
    App.on_right_click(fake, None, None)
    assert md.data.get_selected_geometries() == [cloud]

    md.viewport._interaction_mode = None
    App.on_right_click(fake, None, None)
    assert md.data.get_selected_geometries() == []


def test_close_session_clears_cut(md):
    cloud = _add_cloud(md.data)
    cut = _cut(md, [cloud])
    names = (
        "renderer",
        "volume_viewer",
        "bbox_manager",
        "trajectory_player",
        "dataset_bbox",
        "computed_bbox",
        "scale_bar",
        "status_indicator",
        "_tomogram_link",
        "prime_viewport_placeholder",
    )
    fake = SimpleNamespace(cdata=md, **{name: MagicMock() for name in names})

    App.close_session(fake, render=False)

    assert not cut.has_pose
    assert cut.geometries == []
    assert _planes(cloud) == []


def test_close_session_leaves_clip_mode(md):
    cloud = _add_cloud(md.data)
    md.data.set_selection_by_uuid([cloud.uuid])
    md.viewport.set_mode(ViewerModes.CLIP)
    names = (
        "renderer",
        "volume_viewer",
        "bbox_manager",
        "trajectory_player",
        "dataset_bbox",
        "computed_bbox",
        "scale_bar",
        "status_indicator",
        "_tomogram_link",
        "prime_viewport_placeholder",
        "vtk_widget",
    )
    fake = SimpleNamespace(
        cdata=md,
        cursor_handler=MagicMock(current_mode=ViewerModes.CLIP),
        **{name: MagicMock() for name in names},
    )
    fake._transition_modes = lambda mode: App._transition_modes(fake, mode)

    App.close_session(fake, render=False)

    interactor = md.viewport.vtk_widget.GetRenderWindow().GetInteractor()
    style = interactor.SetInteractorStyle.call_args.args[0]
    assert md.viewport._interaction_mode is None
    assert md.viewport._active_mode is None
    assert not isinstance(style, ClipInteractorStyle)
    fake.cursor_handler.update_mode.assert_called_with(ViewerModes.VIEWING)


def _collected_uuids(md):
    return App._collect_clip(SimpleNamespace(cdata=md))["clip"]["uuids"]


def test_representation_copy_keeps_cut(md):
    cloud = _add_cloud(md.data)
    cut = _cut(md, [cloud])
    md.data.set_selection_by_uuid([cloud.uuid])

    md.data.change_representation("normals")

    replaced = md.data.container.get(cloud.uuid)
    assert replaced is not cloud
    assert cut.geometries == [replaced]
    assert _planes(replaced) == [cut.plane]
    assert _planes(cloud) == []
    assert _collected_uuids(md) == [cloud.uuid]


def _assert_cut_on(md, uuid):
    cut = md.viewport.clip_cut
    geometry = md.data.container.get(uuid)
    assert cut.geometries == [geometry]
    assert _planes(geometry) == [cut.plane]
    assert _collected_uuids(md) == [uuid]


def test_point_removal_keeps_cut(md):
    cloud = _add_cloud(md.data)
    _cut(md, [cloud])
    md.data.point_selection[cloud.uuid] = np.arange(100)

    md.data.remove_selection()
    assert md.data.container.get(cloud.uuid).get_number_of_points() == 400
    _assert_cut_on(md, cloud.uuid)

    STACK.undo()
    restored = md.data.container.get(cloud.uuid)
    assert restored is not cloud and restored.get_number_of_points() == 500
    _assert_cut_on(md, cloud.uuid)

    STACK.redo()
    assert md.data.container.get(cloud.uuid) is not restored
    _assert_cut_on(md, cloud.uuid)


def test_segmentation_switch_leaves_cut(md):
    first, second = _add_cloud(md.data, seed=0), _add_cloud(md.data, seed=1)
    cut = _cut(md, [first, second])
    md.data.set_selection_by_uuid([second.uuid])

    md.data.change_representation("segmentation")

    assert cut.geometries == [first]
    assert _planes(md.data.container.get(second.uuid)) == []
