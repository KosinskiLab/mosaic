import pytest
from qtpy.QtWidgets import QLabel

from mosaic.path_display import display_path, display_paths, set_path_text


@pytest.mark.parametrize(
    "path, root, expected",
    [
        ("/data/tomos/TS_012.mrc", "/data/tomos", "TS_012.mrc"),
        ("/data/tomos/TS_012/tomogram.mrc", "/data/tomos", "TS_012/tomogram.mrc"),
        ("/data/extra/TS_031_rec.mrc", "/data/tomos", "…/extra/TS_031_rec.mrc"),
        ("/data/tomos2/TS_012.mrc", "/data/tomos", "…/tomos2/TS_012.mrc"),
        ("/data/tomos/TS_012.zarr/", None, "TS_012.zarr"),
        ("s3://bucket/run/TS_012.zarr", None, "TS_012.zarr"),
        ("/data/tomos/TS_012.mrc", None, "TS_012.mrc"),
        ("C:\\tomos\\TS_012\\tomogram.mrc", "C:/tomos", "TS_012\\tomogram.mrc"),
        ("C:\\data\\extra\\TS_031.mrc", "C:/tomos/", "…/extra/TS_031.mrc"),
        ("C:\\data\\tomos\\TS_012.mrc", None, "TS_012.mrc"),
    ],
)
def test_display_path(path, root, expected):
    assert display_path(path, root) == expected


def test_display_paths_disambiguates_collisions():
    paths = ["/a/run1/tomogram.mrc", "/a/run2/tomogram.mrc", "/a/x.mrc"]
    assert display_paths(paths) == [
        "…/run1/tomogram.mrc",
        "…/run2/tomogram.mrc",
        "x.mrc",
    ]


def test_set_path_text_tooltip_is_full(qapp):
    label = QLabel()
    set_path_text(label, "/very/long/folder/TS_012_rec.mrc", prefix="Loaded ", width=60)
    assert label.toolTip() == "Loaded /very/long/folder/TS_012_rec.mrc"
    assert "…" in label.text()
