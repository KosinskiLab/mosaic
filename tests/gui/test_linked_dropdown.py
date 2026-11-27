from unittest.mock import Mock

import pytest

from mosaic.tomogram_link import TomogramLink
from mosaic.widgets.volume_viewer_hud import VolumeViewerHUD


@pytest.fixture
def hud(qapp, mock_vtk_widget):
    mock_vtk_widget.update = Mock()
    return VolumeViewerHUD(mock_vtk_widget)


def _link(hud, enabled):
    return TomogramLink(hud.track_path, Mock(), lambda: enabled, hud.track_path)


def _texts(viewer):
    combo = viewer._path_combo
    return [combo.itemText(i) for i in range(combo.count())]


@pytest.mark.parametrize("enabled", [True, False])
def test_restored_link_is_first_recent(hud, tmp_path, enabled):
    tomo = tmp_path / "t.mrc"
    tomo.write_bytes(b"")
    hud.set_recent_paths(["/d/a.mrc", "/d/b.mrc"])
    _link(hud, enabled).restore({"tomogram": str(tomo)})
    assert _texts(hud.primary) == ["t.mrc", "a.mrc", "b.mrc"]
    assert hud.primary._path_combo.itemData(0) == str(tomo)


def test_relink_moves_new_path_to_front(hud):
    hud.set_recent_paths(["/d/a.mrc", "/d/b.mrc"])
    link = _link(hud, False)
    link.set("/d/b.mrc", load=False)
    link.set("/d/c.mrc", load=False)
    assert _texts(hud.primary) == ["c.mrc", "b.mrc", "a.mrc"]


def test_no_duplicates_when_loaded_and_linked(hud, tmp_path):
    tomo = tmp_path / "t.mrc"
    tomo.write_bytes(b"")
    _link(hud, True).restore({"tomogram": str(tomo)})
    assert hud.recent_paths == [str(tomo)]


def test_session_without_link_keeps_recents(hud):
    hud.set_recent_paths(["/d/a.mrc"])
    _link(hud, True).restore({})
    assert hud.recent_paths == ["/d/a.mrc"]


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
