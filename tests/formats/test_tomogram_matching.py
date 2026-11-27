import os

import pytest

from mosaic.formats.tomogram_matching import match_tomograms, scan_tomograms


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
    (m,) = match_tomograms(
        [f"/s/{session}.mosaic"], [f"/t/{t}.mrc" for t in tomos]
    )
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
