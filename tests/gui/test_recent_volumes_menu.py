from unittest.mock import Mock

import pytest
import vtk
from qtpy.QtCore import QPoint, QRect, QSize, QTimer

from mosaic.widgets.dock import menu_pos_above
from mosaic.widgets.volume_viewer_hud import VolumeViewerHUD


@pytest.fixture
def hud(qapp, mock_vtk_widget):
    mock_vtk_widget.update = Mock()
    hud = VolumeViewerHUD(mock_vtk_widget)
    yield hud
    hud.hide()


@pytest.fixture
def vols(tmp_path):
    paths = []
    for name in ("a.mrc", "b.mrc"):
        path = tmp_path / name
        path.write_bytes(b"")
        paths.append(str(path))
    return paths


@pytest.fixture(params=["primary", "added"])
def strip(request, hud):
    if request.param == "added":
        hud.add_viewer()
        return hud._strips[-1]
    return hud._primary_strip


def _volume():
    image = vtk.vtkImageData()
    image.SetDimensions(4, 5, 6)
    image.AllocateScalars(vtk.VTK_FLOAT, 1)
    return image


def test_menu_position_above_button():
    button = QRect(QPoint(200, 500), QSize(24, 24))
    pos = menu_pos_above(button, QSize(150, 80))
    assert pos == QPoint(200, 500 - 80)
    assert pos.y() + 80 == button.top()


def test_click_opens_browser_when_empty(strip):
    strip.viewer.open_volume = Mock()
    strip._load_btn.click()
    strip.viewer.open_volume.assert_called_once_with()


def test_click_closes_loaded_volume(strip):
    strip.viewer.swap_volume(_volume())
    strip.viewer.open_volume = Mock()
    strip._load_btn.click()
    assert strip.viewer.volume is None
    strip.viewer.open_volume.assert_not_called()


def test_menu_lists_existing_recents_with_path_tooltips(hud, strip, vols, tmp_path):
    hud.set_recent_paths([str(tmp_path / "gone.mrc"), *vols])
    menu = strip._load_btn.menu()
    shown = [(a.toolTip(), a.text()) for a in menu.actions()]
    assert shown == strip.viewer.recents
    assert [path for path, _ in shown] == vols
    assert menu.toolTipsVisible()


def test_selecting_entry_loads_that_path(hud, strip, vols):
    hud.set_recent_paths(vols)
    strip.viewer._load_from_path = Mock()
    strip._load_btn.menu().actions()[1].trigger()
    strip.viewer._load_from_path.assert_called_once_with(vols[1])


def test_menu_inert_without_recents(hud, strip, vols):
    button = strip._load_btn
    hud.set_recent_paths([])
    assert button.menu() is None
    hud.set_recent_paths(vols)
    assert len(button.menu().actions()) == 2
    hud.set_recent_paths([])
    assert button.menu() is None
    assert button.isEnabled()


def test_menu_opens_above_button_left_edge(hud, strip, vols):
    hud.set_recent_paths(vols)
    hud.move(100, 400)
    hud.show()
    button = strip._load_btn
    menu = button.menu()
    shown = {}

    def grab():
        shown["geometry"] = menu.geometry()
        menu.hide()
        return None

    QTimer.singleShot(0, grab)
    button.showMenu()
    top_left = button.mapToGlobal(QPoint(0, 0))
    assert menu.parent() is None
    assert shown["geometry"].left() == top_left.x()
    assert shown["geometry"].bottom() + 1 == top_left.y()
