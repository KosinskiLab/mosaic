from unittest.mock import Mock

import pytest

from mosaic.tomogram_link import TomogramLink
from mosaic.widgets.volume_viewer_hud import VolumeViewerHUD


@pytest.fixture
def hud(qapp, mock_vtk_widget):
    mock_vtk_widget.update = Mock()
    return VolumeViewerHUD(mock_vtk_widget)


@pytest.fixture
def vols(tmp_path):
    paths = []
    for name in ("a.mrc", "b.mrc"):
        path = tmp_path / name
        path.write_bytes(b"")
        paths.append(str(path))
    return paths


def _link(hud, enabled):
    return TomogramLink(hud.track_path, Mock(), lambda: enabled, hud.track_path)


def _texts(viewer):
    return [label for _, label in viewer.recents]


@pytest.mark.parametrize("enabled", [True, False])
def test_restored_link_is_first_recent(hud, tmp_path, vols, enabled):
    tomo = tmp_path / "t.mrc"
    tomo.write_bytes(b"")
    hud.set_recent_paths(vols)
    _link(hud, enabled).restore({"tomogram": str(tomo)})
    assert _texts(hud.primary) == ["t.mrc", "a.mrc", "b.mrc"]
    assert hud.primary.recents[0][0] == str(tomo)


def test_relink_moves_new_path_to_front(hud, tmp_path, vols):
    c = tmp_path / "c.mrc"
    c.write_bytes(b"")
    hud.set_recent_paths(vols)
    link = _link(hud, False)
    link.set(vols[1], load=False)
    link.set(str(c), load=False)
    assert _texts(hud.primary) == ["c.mrc", "b.mrc", "a.mrc"]


def test_no_duplicates_when_loaded_and_linked(hud, tmp_path):
    tomo = tmp_path / "t.mrc"
    tomo.write_bytes(b"")
    _link(hud, True).restore({"tomogram": str(tomo)})
    assert hud.recent_paths == [str(tomo)]


def test_session_without_link_keeps_recents(hud, vols):
    hud.set_recent_paths(vols[:1])
    _link(hud, True).restore({})
    assert hud.recent_paths == vols[:1]


def test_missing_local_path_not_listed_but_url_kept(hud, vols, tmp_path):
    missing = str(tmp_path / "gone.mrc")
    url = "s3://bucket/vol.zarr"
    hud.set_recent_paths([missing, url, vols[0]])
    assert _texts(hud.primary) == ["vol.zarr", "a.mrc"]
    assert hud.recent_paths == [missing, url, vols[0]]


def test_link_added_after_recents_restore(qapp, mock_vtk_widget):
    from mosaic.data import MosaicData

    mock_vtk_widget.update = Mock()
    hud = VolumeViewerHUD(mock_vtk_widget)
    data = MosaicData(mock_vtk_widget)
    link = _link(hud, False)
    data.register_session_hook(
        lambda: {}, lambda m: hud.set_recent_paths(m.get("volume_paths", []))
    )
    data.register_session_hook(link.collect, link.restore)
    for _, restore in data._session_hooks:
        restore({"volume_paths": ["/d/a.mrc"], "tomogram": "/d/t.mrc"})
    assert hud.recent_paths == ["/d/t.mrc", "/d/a.mrc"]
