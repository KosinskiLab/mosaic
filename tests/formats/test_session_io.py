"""
Tests for session file I/O (save/load roundtrips).

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import pickle

from mosaic.formats.session import (
    is_session_file,
    open_session,
    read_session_index,
    session_save_path,
    write_session,
)


class TestSessionRoundTrip:
    def test_write_read(self, tmp):
        path = f"{tmp}.session"
        state = {"_data": "test", "shape": (64, 64, 64)}
        write_session(path, state)

        index = read_session_index(path)
        assert "version" in index

        loaded = open_session(path)
        assert loaded["_data"] == "test"
        assert loaded["shape"] == (64, 64, 64)


class TestSessionPaths:
    def test_is_session_file_accepts_both(self):
        assert is_session_file("a.mosaic") and is_session_file("a.pickle")
        assert is_session_file("A.PICKLE")
        assert not is_session_file("a.star")

    def test_session_save_path(self):
        assert session_save_path("/d/TS_012.rec.pickle") == "/d/TS_012.rec.mosaic"
        assert session_save_path("/d/A.PICKLE") == "/d/A.mosaic"
        assert session_save_path("/d/a.mosaic") == "/d/a.mosaic"

    def test_legacy_plain_pickle_still_loads(self, tmp_path):
        path = tmp_path / "old.pickle"
        path.write_bytes(pickle.dumps({"_data": "x"}))
        assert open_session(str(path))["_data"] == "x"
