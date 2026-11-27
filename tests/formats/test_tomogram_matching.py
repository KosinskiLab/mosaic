import os
import pickle

import pytest

from mosaic.formats.session import read_session_meta, write_session
from mosaic.formats.tomogram_matching import (
    NO_TOMOGRAM,
    LinkRow,
    LinkWriteResult,
    Match,
    build_rows,
    detected_key,
    entries,
    initial_folder,
    is_warning,
    link_summary,
    match_tomograms,
    pending_changes,
    resolve_note,
    scan_tomograms,
    status_text,
    write_tomogram_links,
)


@pytest.mark.parametrize(
    "session, tomos, expected",
    [
        ("TS_012_membrane", ["TS_012", "TS_013"], "TS_012"),
        (
            "TS_012_rec_bin4_seg",
            ["TS_012_rec_bin4", "TS_013_rec_bin4"],
            "TS_012_rec_bin4",
        ),
        ("TS_012_seg", ["TS_012_bin4", "TS_013_bin4"], "TS_012_bin4"),
        ("TS_12_seg", ["TS_012", "TS_013"], "TS_012"),
        ("ts_012_SEG", ["TS_012.MRC", "TS_013.MRC"], "TS_012.MRC"),
        ("2024_TS_002_seg", ["2024_TS_001", "2024_TS_002"], "2024_TS_002"),
        ("TS_012_seg", ["TS_012"], "TS_012"),
    ],
)
def test_auto_matches(session, tomos, expected):
    paths = [f"/t/{t}" if "." in t else f"/t/{t}.mrc" for t in tomos]
    (m,) = match_tomograms([f"/s/{session}.mosaic"], paths)
    assert m.status == "matched" and os.path.basename(m.tomogram).startswith(expected)


def test_tie_is_ambiguous():
    (m,) = match_tomograms(
        ["/s/TS_012_seg.mosaic"], ["/t/TS_012_a.mrc", "/t/TS_012_b.mrc"]
    )
    assert m.status == "ambiguous" and len(m.candidates) == 2 and m.tomogram is None


@pytest.mark.parametrize(
    "session, tomos",
    [
        ("TS_099_seg", ["TS_012", "TS_013"]),
        ("2024_TS_099_seg", ["2024_TS_001", "2024_TS_002"]),
        ("TS_013_seg", ["TS_012"]),
        ("TS_seg", ["TS_012", "TS_013"]),
    ],
)
def test_missing(session, tomos):
    (m,) = match_tomograms([f"/s/{session}.mosaic"], [f"/t/{t}.mrc" for t in tomos])
    assert m.status == "missing" and m.tomogram is None


def test_results_follow_session_order():
    ms = match_tomograms(
        ["/s/TS_013_x.mosaic", "/s/TS_012_x.mosaic"],
        ["/t/TS_012.mrc", "/t/TS_013.mrc"],
    )
    assert [m.tomogram for m in ms] == ["/t/TS_013.mrc", "/t/TS_012.mrc"]


def test_nested_folder_names(tmp_path):
    for run in ("TS_012", "TS_013"):
        (tmp_path / run).mkdir()
        (tmp_path / run / "tomogram.mrc").write_bytes(b"")
    tomos = scan_tomograms(str(tmp_path), recursive=True)
    (m,) = match_tomograms(["/s/TS_013_membrane.mosaic"], tomos, root=str(tmp_path))
    assert m.tomogram == str(tmp_path / "TS_013" / "tomogram.mrc")


def test_scan_skips_non_volumes_and_keeps_zarr(tmp_path):
    for name in ("a.mrc", "b.star", "c.mosaic", "d.txt", "F.MRC"):
        (tmp_path / name).write_bytes(b"")
    (tmp_path / "e.zarr" / "0").mkdir(parents=True)
    (tmp_path / "e.zarr" / "0" / "chunk.mrc").write_bytes(b"")
    found = scan_tomograms(str(tmp_path), recursive=True)
    assert [os.path.basename(p) for p in found] == ["a.mrc", "e.zarr", "F.MRC"]


def test_scan_not_recursive(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.mrc").write_bytes(b"")
    (tmp_path / "b.mrc").write_bytes(b"")
    assert scan_tomograms(str(tmp_path)) == [str(tmp_path / "b.mrc")]


def test_dotted_names_match():
    (m,) = match_tomograms(
        ["/s/TS_013.v2_seg.mosaic"], ["/t/TS_012.v2.MRC", "/t/TS_013.v2.MRC"]
    )
    assert m.tomogram == "/t/TS_013.v2.MRC"


def test_zarr_name_strips_suffix():
    (m,) = match_tomograms(
        ["/s/TS_013_seg.mosaic"], ["/t/TS_012.zarr", "/t/TS_013.zarr"]
    )
    assert m.tomogram == "/t/TS_013.zarr"


def test_pattern_mode():
    (m,) = match_tomograms(
        ["/s/TS_012_membrane.mosaic"],
        ["/t/TS_012_rec_bin4.mrc", "/t/TS_013_rec_bin4.mrc"],
        pattern=("{key}_membrane", "{key}_rec*"),
    )
    assert m.tomogram == "/t/TS_012_rec_bin4.mrc"


def test_pattern_ambiguous_and_missing():
    ms = match_tomograms(
        ["/s/A_seg.mosaic", "/s/B_seg.mosaic"],
        ["/t/A_1.mrc", "/t/A_2.mrc"],
        pattern=("{key}_seg", "{key}_*"),
    )
    assert [m.status for m in ms] == ["ambiguous", "missing"]
    assert len(ms[0].candidates) == 2


def test_pattern_without_key_raises():
    with pytest.raises(ValueError):
        match_tomograms(["/s/a.mosaic"], ["/t/a.mrc"], pattern=("*", "{key}"))


@pytest.mark.parametrize(
    "current, candidates, selection, expected",
    [
        (None, ("/t/a.mrc",), "/t/a.mrc", "New"),
        ("/t/a.mrc", ("/t/a.mrc",), "/t/a.mrc", "Linked"),
        ("/t/old.mrc", ("/t/a.mrc",), "/t/a.mrc", "Replaced"),
        ("/t/old.mrc", (), NO_TOMOGRAM, "Removed"),
        (None, ("/t/a.mrc",), NO_TOMOGRAM, "Skipped"),
        (None, ("/t/a.mrc", "/t/b.mrc"), None, "2 candidates"),
        (None, (), None, "No match"),
    ],
)
def test_status_text(current, candidates, selection, expected):
    row = LinkRow("/s/x.mosaic", current, candidates, selection)
    assert status_text(row) == expected
    assert is_warning(row) == (expected in ("2 candidates", "No match"))


def test_entries_order():
    row = LinkRow(
        "/s/x.mosaic", "/old/x.mrc", ("/t/a.mrc", "/t/b.mrc"), "/elsewhere/c.mrc"
    )
    assert entries(row) == ["/t/a.mrc", "/t/b.mrc", "/old/x.mrc", "/elsewhere/c.mrc"]
    row = LinkRow("/s/x.mosaic", "/t/a.mrc", ("/t/a.mrc",), "/t/a.mrc")
    assert entries(row) == ["/t/a.mrc"]


def test_build_rows_replaces_by_default_and_sorts_attention_first():
    matches = [
        Match("/s/TS_2.mosaic", "/t/2.mrc", ("/t/2.mrc",), "matched"),
        Match("/s/TS_10.mosaic", None, (), "missing"),
        Match("/s/TS_1.mosaic", "/t/1.mrc", ("/t/1.mrc",), "matched"),
        Match("/s/TS_3.mosaic", None, ("/t/a", "/t/b"), "ambiguous"),
        Match("/s/TS_4.mosaic", "/t/4_new.mrc", ("/t/4_new.mrc",), "matched"),
    ]
    rows = build_rows(
        matches, {"/s/TS_4.mosaic": "/t/4_old.mrc", "/s/TS_2.mosaic": "/t/2.mrc"}
    )
    assert [r.session for r in rows] == [
        "/s/TS_3.mosaic",
        "/s/TS_4.mosaic",
        "/s/TS_10.mosaic",
        "/s/TS_1.mosaic",
        "/s/TS_2.mosaic",
    ]
    assert [status_text(r) for r in rows] == [
        "2 candidates",
        "Replaced",
        "No match",
        "New",
        "Linked",
    ]
    assert pending_changes(rows) == {
        "/s/TS_4.mosaic": "/t/4_new.mrc",
        "/s/TS_1.mosaic": "/t/1.mrc",
    }
    assert resolve_note(rows) == "2 to resolve"


def test_choosing_again_is_the_undo():
    (row,) = build_rows(
        [Match("/s/a.mosaic", "/t/new.mrc", ("/t/new.mrc",), "matched")],
        {"/s/a.mosaic": "/t/old.mrc"},
    )
    row.selection = NO_TOMOGRAM
    assert pending_changes([row]) == {"/s/a.mosaic": None}
    row.selection = "/t/old.mrc"
    assert pending_changes([row]) == {} and status_text(row) == "Linked"


def test_resolve_note_hidden_when_resolved():
    (row,) = build_rows([Match("/s/a.mosaic", None, (), "missing")], {})
    row.selection = "/t/picked.mrc"
    assert resolve_note([row]) is None and status_text(row) == "New"


def test_initial_folder():
    links = {
        "/s/a.mosaic": "/data/tomos/TS_1/tomogram.mrc",
        "/s/b.mosaic": "/data/tomos/TS_2/tomogram.mrc",
        "/s/c.mosaic": None,
    }
    assert initial_folder(links, "/last") == "/data/tomos"
    assert initial_folder({"/s/a.mosaic": None}, "/last") == "/last"
    assert initial_folder({}, "") is None


def test_detected_key():
    matches = match_tomograms(
        ["/s/TS_013_membrane.mosaic", "/s/TS_012_membrane.mosaic"],
        ["/t/TS_012_rec.mrc", "/t/TS_013_rec.mrc"],
    )
    assert detected_key(matches) == ("TS_###", "TS_012_membrane", "TS_012_rec.mrc")
    assert detected_key([Match("/s/a.mosaic", None, (), "missing")]) is None


def test_detected_key_nested_folders(tmp_path):
    for run in ("TS_012", "TS_013"):
        (tmp_path / run).mkdir()
        (tmp_path / run / "tomogram.mrc").write_bytes(b"")
    tomos = scan_tomograms(str(tmp_path), recursive=True)
    matches = match_tomograms(["/s/ts_12-seg.mosaic"], tomos, root=str(tmp_path))
    assert detected_key(matches) == ("ts_##", "ts_12-seg", "TS_012/tomogram.mrc")


def test_write_links_converts_legacy_and_continues_on_error(tmp_path):
    good = str(tmp_path / "a.mosaic")
    write_session(good, {})
    legacy = tmp_path / "b.pickle"
    legacy.write_bytes(pickle.dumps({}))
    blocked = tmp_path / "c.pickle"
    blocked.write_bytes(pickle.dumps({}))
    (tmp_path / "c.mosaic").write_bytes(b"newer")
    gone = str(tmp_path / "gone.mosaic")
    changes = {
        good: "/t/a.mrc",
        str(legacy): "/t/b.mrc",
        str(blocked): "/t/c.mrc",
        gone: "/t/d.mrc",
    }
    result = write_tomogram_links(changes)
    assert read_session_meta(good)["tomogram"] == "/t/a.mrc"
    assert result.paths == {str(legacy): str(tmp_path / "b.mosaic")}
    assert read_session_meta(str(tmp_path / "b.mosaic"))["tomogram"] == "/t/b.mrc"
    assert set(result.errors) == {str(blocked), gone}
    assert (tmp_path / "c.mosaic").read_bytes() == b"newer"
    assert link_summary(result, len(changes)) == (
        "Updated 2 sessions, 1 converted to .mosaic, 2 failed",
        True,
    )
    assert link_summary(LinkWriteResult({}, {}), 1) == ("Updated 1 session", False)


def test_write_links_removes_link(tmp_path):
    path = str(tmp_path / "a.mosaic")
    write_session(path, {}, sections={"meta": ("json", b'{"tomogram": "/t/a.mrc"}')})
    result = write_tomogram_links({path: None})
    assert "tomogram" not in read_session_meta(path) and not result.errors
