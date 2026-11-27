"""Tests for the volume viewer's single load combobox."""

import pytest

from mosaic.widgets import volume_viewer as vv
from mosaic.widgets.volume_viewer import VolumeViewer


@pytest.fixture
def viewer(qapp, fake_vtk_widget, small_volume, monkeypatch):
    monkeypatch.setattr(vv, "_load_vtk_image", lambda path: small_volume)
    return VolumeViewer(fake_vtk_widget)


@pytest.fixture
def vols(tmp_path):
    paths = []
    for name in ("a.mrc", "b.mrc"):
        path = tmp_path / name
        path.write_bytes(b"")
        paths.append(str(path))
    return paths


def _entries(combo):
    return [
        "<separator>" if combo.itemData(i) is None else combo.itemText(i)
        for i in range(combo.count())
    ]


def _choose(combo, index):
    combo.activated.emit(index)
    return None


def _shown(combo):
    return combo.currentText() or combo.placeholderText()


def test_placeholder_when_nothing_loaded(viewer):
    combo = viewer.load_combo
    assert combo.currentIndex() == -1
    assert _shown(combo) == "Load volume…"
    assert _entries(combo) == ["Browse…"]


def test_recents_then_separator_then_browse(viewer, vols):
    viewer._rebuild_load_menu(vols)
    assert _entries(viewer.load_combo) == ["a.mrc", "b.mrc", "<separator>", "Browse…"]
    assert viewer.load_combo.itemData(0, 3) == vols[0]


def test_missing_recents_hidden(viewer, vols, tmp_path):
    viewer._rebuild_load_menu([str(tmp_path / "gone.mrc"), vols[0]])
    assert _entries(viewer.load_combo) == ["a.mrc", "<separator>", "Browse…"]


def test_selecting_recent_loads_it(viewer, vols):
    viewer._rebuild_load_menu(vols)
    _choose(viewer.load_combo, 1)
    assert viewer.source_path == vols[1]
    assert _shown(viewer.load_combo) == "b.mrc"


def test_reselecting_loaded_volume_does_nothing(viewer, vols, monkeypatch):
    viewer._rebuild_load_menu(vols)
    _choose(viewer.load_combo, 0)
    calls = []
    monkeypatch.setattr(viewer, "load_volume", calls.append)
    _choose(viewer.load_combo, 0)
    assert calls == []
    assert _shown(viewer.load_combo) == "a.mrc"


def test_browse_loads_chosen_file(viewer, vols, monkeypatch):
    monkeypatch.setattr(
        vv.QFileDialog, "getOpenFileName", lambda *a, **k: (vols[1], "")
    )
    viewer._rebuild_load_menu(vols[:1])
    _choose(viewer.load_combo, viewer.load_combo.count() - 1)
    assert viewer.source_path == vols[1]
    assert _shown(viewer.load_combo) == "b.mrc"


def test_cancelled_browse_keeps_previous_display(viewer, vols, monkeypatch):
    monkeypatch.setattr(vv.QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    viewer._rebuild_load_menu(vols)
    _choose(viewer.load_combo, 0)
    _choose(viewer.load_combo, viewer.load_combo.count() - 1)
    assert viewer.source_path == vols[0]
    assert _shown(viewer.load_combo) == "a.mrc"


def test_loaded_volume_outside_recents_shows_name_and_path(viewer, vols):
    viewer.load_volume(vols[0])
    assert _shown(viewer.load_combo) == "a.mrc"
    assert viewer.load_combo.toolTip() == vols[0]


def test_close_restores_placeholder(viewer, vols):
    viewer._rebuild_load_menu(vols)
    _choose(viewer.load_combo, 0)
    viewer.close_volume()
    assert _shown(viewer.load_combo) == "Load volume…"
    assert viewer.load_combo.toolTip() == ""
