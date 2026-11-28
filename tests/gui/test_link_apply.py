from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from mosaic.formats.session import session_save_path
from mosaic.formats.tomogram_matching import LinkWriteResult
from mosaic.gui import App


def _apply(errors):
    fake = SimpleNamespace(
        _current_session_path="a.mosaic",
        _tomogram_link=MagicMock(),
        status_indicator=MagicMock(),
    )
    widget = MagicMock()
    result = LinkWriteResult(paths={"a.mosaic": "a.mosaic"}, errors=errors)
    App._apply_link_result(fake, widget, {"a.mosaic": "t.mrc"}, result)
    return fake._tomogram_link, widget


def test_open_session_link_updated_on_success():
    link, _ = _apply({})
    link.set.assert_called_once_with("t.mrc", load=True)


def test_open_session_link_kept_when_write_failed():
    link, widget = _apply({"a.mosaic": "disk full"})
    link.set.assert_not_called()
    widget.replace_paths.assert_called_once_with({"a.mosaic": "a.mosaic"})


def _save(path, widget):
    fake = SimpleNamespace(
        _current_session_path=path,
        cdata=SimpleNamespace(to_file=Mock(side_effect=session_save_path)),
        _on_session_path_changed=Mock(),
    )
    if widget is not None:
        fake._session_list_widget = widget
    return fake, App.save_session(fake)


def test_save_session_redirect_updates_list(tmp_path):
    old = str(tmp_path / "a.pickle")
    new = str(tmp_path / "a.mosaic")
    widget = MagicMock()
    fake, ret = _save(old, widget)
    assert ret is None and fake._current_session_path == new
    widget.replace_paths.assert_called_once_with({old: new})
    widget.mark_saved.assert_called_once_with(new)
    fake._on_session_path_changed.assert_not_called()


def test_save_session_redirect_without_list(tmp_path):
    old = str(tmp_path / "a.pickle")
    fake, _ = _save(old, None)
    fake._on_session_path_changed.assert_called_once_with(
        old, str(tmp_path / "a.mosaic")
    )


def test_save_session_no_redirect(tmp_path):
    path = str(tmp_path / "a.mosaic")
    widget = MagicMock()
    fake, _ = _save(path, widget)
    widget.replace_paths.assert_not_called()
    widget.mark_saved.assert_called_once_with(path)


def test_save_session_declined_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "mosaic.widgets.container_list.confirm_session_overwrite",
        Mock(return_value=False),
    )
    widget = MagicMock()
    fake, ret = _save(str(tmp_path / "a.pickle"), widget)
    assert ret == -1
    fake.cdata.to_file.assert_not_called()
    widget.mark_saved.assert_not_called()


def test_redirect_of_open_session_updates_recent():
    fake = SimpleNamespace(
        _current_session_path="a.pickle",
        _add_file_to_recent=Mock(),
        status_indicator=MagicMock(),
    )
    App._on_session_path_changed(fake, "b.pickle", "b.mosaic")
    fake._add_file_to_recent.assert_not_called()
    App._on_session_path_changed(fake, "a.pickle", "a.mosaic")
    fake._add_file_to_recent.assert_called_once_with("a.mosaic")


@pytest.mark.parametrize("typed", ["x.pickle", "x", "x.mosaic"])
def test_save_as_writes_mosaic(typed, monkeypatch):
    dialog = MagicMock()
    dialog.return_value.getSaveFileName.return_value = (typed, "")
    monkeypatch.setattr("mosaic.gui.QFileDialog", dialog)
    fake = SimpleNamespace(
        _current_session_path=None,
        cdata=SimpleNamespace(to_file=Mock(side_effect=session_save_path)),
        _add_file_to_recent=Mock(),
    )
    App.save_session_as(fake)
    fake.cdata.to_file.assert_called_once_with("x.mosaic")
