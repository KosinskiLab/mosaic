from unittest.mock import Mock

from mosaic.data import MosaicData
from mosaic.formats.session import read_session_meta
from mosaic.tomogram_link import TomogramLink


def _link(enabled=True):
    loader, notify = Mock(), Mock()
    return TomogramLink(loader, notify, lambda: enabled, Mock()), loader, notify


def test_restore_loads_existing(tmp_path):
    tomo = tmp_path / "t.mrc"
    tomo.write_bytes(b"")
    link, loader, notify = _link()
    link.restore({"tomogram": str(tomo)})
    loader.assert_called_once_with(str(tomo))
    notify.assert_called_once_with("Loaded ", str(tomo), False, False)


def test_missing_file_is_persistent_warning(tmp_path):
    link, loader, notify = _link()
    link.restore({"tomogram": str(tmp_path / "moved.mrc")})
    loader.assert_not_called()
    notify.assert_called_once_with(
        "Tomogram missing: ", str(tmp_path / "moved.mrc"), True, True
    )


def test_loader_error_is_persistent_warning(tmp_path):
    tomo = tmp_path / "t.mrc"
    tomo.write_bytes(b"")
    link, loader, notify = _link()
    loader.side_effect = OSError("bad header")
    link.restore({"tomogram": str(tomo)})
    notify.assert_called_once_with("Could not load ", str(tomo), True, True)


def test_disabled_does_not_load(tmp_path):
    tomo = tmp_path / "t.mrc"
    tomo.write_bytes(b"")
    link, loader, notify = _link(enabled=False)
    link.restore({"tomogram": str(tomo)})
    loader.assert_not_called()
    notify.assert_not_called()
    assert link.path == str(tomo)


def test_roundtrip_through_mosaic_data(qapp, mock_vtk_widget, tmp_path):
    md = MosaicData(mock_vtk_widget)
    link, _, _ = _link(enabled=False)
    md.register_session_hook(link.collect, link.restore)
    link.set("/data/TS_012.mrc", load=False)
    path = md.to_file(str(tmp_path / "s.mosaic"))
    link.set(None, load=False)
    md.load_session(path)
    assert link.path == "/data/TS_012.mrc"
    link.set(None, load=False)
    md.to_file(path)
    assert "tomogram" not in read_session_meta(path)


def test_on_change_gets_linked_paths_only():
    on_change = Mock()
    link = TomogramLink(Mock(), Mock(), lambda: False, on_change)
    link.restore({"tomogram": "/d/t.mrc"})
    link.set("/d/u.mrc", load=False)
    link.set(None, load=False)
    link.restore({})
    assert [c.args[0] for c in on_change.call_args_list] == ["/d/t.mrc", "/d/u.mrc"]
