"""
Tests for session file I/O (save/load roundtrips).

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import os
import pickle

import pytest

from mosaic.formats.session import (
    convert_legacy_session,
    is_session_file,
    open_session,
    prefer_mosaic_sessions,
    read_session_index,
    read_session_meta,
    read_session_section,
    session_save_path,
    update_session_meta,
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


class TestSessionRewrite:
    def test_update_meta_preserves_other_sections(self, tmp_path):
        path = str(tmp_path / "s.mosaic")
        write_session(
            path,
            {"_data": 1},
            sections={"thumbnail": ("png", b"PNG"), "meta": ("json", b'{"a":1}')},
        )
        before = read_session_section(path, "state")
        update_session_meta(path, {"tomogram": "/t.mrc", "a": None})
        assert read_session_meta(path) == {"tomogram": "/t.mrc"}
        assert read_session_section(path, "state") == before
        assert read_session_section(path, "thumbnail") == b"PNG"
        assert sorted(os.listdir(tmp_path)) == ["s.mosaic"]

    def test_update_meta_missing_file_leaves_nothing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            update_session_meta(str(tmp_path / "gone.mosaic"), {"tomogram": "/t"})
        assert os.listdir(tmp_path) == []

    def test_update_meta_rejects_legacy(self, tmp_path):
        path = tmp_path / "old.pickle"
        path.write_bytes(pickle.dumps({}))
        with pytest.raises(ValueError):
            update_session_meta(str(path), {"tomogram": "/t"})

    def test_failed_write_keeps_existing_file(self, tmp_path):
        path = str(tmp_path / "s.mosaic")
        write_session(path, {"_data": 1})
        before = (tmp_path / "s.mosaic").read_bytes()
        with pytest.raises(TypeError):
            write_session(path, {"_data": 2}, sections={"meta": ("json", "text")})
        assert (tmp_path / "s.mosaic").read_bytes() == before
        assert os.listdir(tmp_path) == ["s.mosaic"]

    def test_convert_legacy_is_byte_copy(self, tmp_path):
        raw = pickle.dumps({"_data": [1, 2, 3]})
        (tmp_path / "old.pickle").write_bytes(raw)
        new = convert_legacy_session(str(tmp_path / "old.pickle"))
        assert new.endswith("old.mosaic")
        assert read_session_section(new, "state") == raw
        assert open_session(new)["_data"] == [1, 2, 3]
        assert (tmp_path / "old.pickle").exists()

    def test_convert_refuses_existing_target(self, tmp_path):
        (tmp_path / "x.pickle").write_bytes(pickle.dumps({}))
        (tmp_path / "x.mosaic").write_bytes(b"newer work")
        with pytest.raises(FileExistsError):
            convert_legacy_session(str(tmp_path / "x.pickle"))
        assert (tmp_path / "x.mosaic").read_bytes() == b"newer work"

    def test_prefer_mosaic_sessions(self, tmp_path):
        (tmp_path / "a.mosaic").write_bytes(b"")
        paths = [
            str(tmp_path / "a.pickle"),
            str(tmp_path / "b.pickle"),
            str(tmp_path / "c.mosaic"),
            str(tmp_path / "c.pickle"),
        ]
        assert prefer_mosaic_sessions(paths) == [
            str(tmp_path / "b.pickle"),
            str(tmp_path / "c.mosaic"),
        ]
