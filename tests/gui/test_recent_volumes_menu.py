from unittest.mock import Mock

import pytest
from qtpy.QtCore import QPoint, QRect, QSize
from qtpy.QtWidgets import QMenu

from mosaic.widgets.dock import menu_pos_above
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


@pytest.fixture
def strip(hud):
    return hud._primary_strip


def _caret_menu(strip, monkeypatch):
    shown = {}

    def fake_exec(menu, pos=None):
        shown["menu"] = menu
        shown["pos"] = pos
        shown["parent"] = menu.parent()
        shown["actions"] = [(a.text(), a.toolTip()) for a in menu.actions()]
        shown["tips"] = menu.toolTipsVisible()
        shown["triggers"] = menu.actions()
        return None

    monkeypatch.setattr(QMenu, "exec", fake_exec)
    strip._show_recent_menu()
    return shown


def test_menu_position_above_button():
    button = QRect(QPoint(200, 500), QSize(24, 24))
    pos = menu_pos_above(button, QSize(150, 80))
    assert pos == QPoint(200, 500 - 80)
    assert pos.y() + 80 == button.top()


def test_caret_disabled_without_recents_enabled_with(hud, strip, vols):
    hud.set_recent_paths([])
    assert not strip._recent_btn.isEnabled()
    hud.set_recent_paths(vols)
    assert strip._recent_btn.isEnabled()
    hud.set_recent_paths([])
    assert not strip._recent_btn.isEnabled()


def test_menu_lists_recents_with_full_path_tooltips(
    hud, strip, vols, monkeypatch
):
    hud.set_recent_paths(vols)
    combo = hud.primary._path_combo
    shown = _caret_menu(strip, monkeypatch)
    assert shown["actions"] == [
        (combo.itemText(i), combo.itemData(i)) for i in range(combo.count())
    ]
    assert [t for _, t in shown["actions"]] == vols
    assert shown["tips"]


def test_menu_opens_above_caret_left_edge_without_parent(
    hud, strip, vols, monkeypatch
):
    hud.set_recent_paths(vols)
    btn = strip._recent_btn
    shown = _caret_menu(strip, monkeypatch)
    top_left = btn.mapToGlobal(QPoint(0, 0))
    assert shown["parent"] is None
    assert shown["pos"].x() == top_left.x()
    assert shown["pos"].y() + shown["menu"].sizeHint().height() == top_left.y()


def test_selecting_entry_loads_that_path(hud, strip, vols, monkeypatch):
    hud.set_recent_paths(vols)
    hud.primary._load_from_path = Mock()
    shown = _caret_menu(strip, monkeypatch)
    shown["triggers"][1].trigger()
    hud.primary._load_from_path.assert_called_once_with(vols[1])
