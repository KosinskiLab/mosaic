"""
Tests for session file I/O (save/load roundtrips).

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from mosaic.formats.session import (
    open_session,
    read_session_index,
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
