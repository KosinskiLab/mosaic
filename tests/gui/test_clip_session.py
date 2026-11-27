from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
import vtk

from mosaic.data import MosaicData
from mosaic.formats import read_session_meta
from mosaic.gui import App


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
