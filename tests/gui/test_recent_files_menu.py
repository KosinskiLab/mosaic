from types import SimpleNamespace

import pytest
from qtpy.QtGui import QAction

from mosaic.gui import App
from mosaic.settings import Settings


@pytest.fixture
def menu(qapp):
    return SimpleNamespace(
        recent_file_actions=[QAction() for _ in range(Settings.ui.max_recent_files)],
        recent_menu=QAction(),
    )


def test_colliding_names_show_parent_and_tooltip_has_full_path(menu, tmp_path):
    files = []
    for folder in ("run1", "run2"):
        (tmp_path / folder).mkdir()
        path = tmp_path / folder / "s.mosaic"
        path.write_bytes(b"")
        files.append(str(path))
    other = tmp_path / "other.mosaic"
    other.write_bytes(b"")
    files.append(str(other))
    Settings.ui.recent_files = files

    App.update_recent_files_menu(menu)

    actions = menu.recent_file_actions
    assert "run1" in actions[0].text() and "run2" in actions[1].text()
    assert actions[2].text() == "&3 other.mosaic"
    assert [a.toolTip() for a in actions[:3]] == files
