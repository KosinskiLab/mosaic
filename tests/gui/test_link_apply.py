from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from mosaic.formats.tomogram_matching import LinkWriteResult
from mosaic.gui import App


def _apply(errors):
    fake = SimpleNamespace(
        _current_session_path="a.mosaic",
        _tomogram_link=MagicMock(),
        status_indicator=MagicMock(),
    )
    result = LinkWriteResult(paths={"a.mosaic": "a.mosaic"}, errors=errors)
    App._apply_link_result(fake, MagicMock(), {"a.mosaic": "t.mrc"}, result)
    return fake._tomogram_link


def test_open_session_link_updated_on_success():
    _apply({}).set.assert_called_once_with("t.mrc", load=True)


def test_open_session_link_kept_when_write_failed():
    _apply({"a.mosaic": "disk full"}).set.assert_not_called()
