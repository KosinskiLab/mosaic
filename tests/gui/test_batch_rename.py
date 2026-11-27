import re

import pytest

from mosaic.dialogs.batch_rename import BatchRenameDialog, rename

NAMES = ["TS_001_seg", "TS_002_seg", "TS_010_seg"]


def test_plain_find_replace():
    assert rename(NAMES, "_seg", "_membrane") == [
        "TS_001_membrane",
        "TS_002_membrane",
        "TS_010_membrane",
    ]


def test_empty_find_with_tokens_is_format():
    assert rename(NAMES, "", "Mito {i:03}") == ["Mito 001", "Mito 002", "Mito 003"]


def test_empty_find_plain_text():
    assert rename(NAMES, "", "Membrane") == ["Membrane"] * 3


def test_tokens_with_find():
    assert rename(NAMES, "_seg", "_{i}") == ["TS_001_1", "TS_002_2", "TS_010_3"]


def test_name_token():
    assert rename(["a"], "", "{name}_copy") == ["a_copy"]


def test_regex_groups_and_tokens():
    assert rename(NAMES, r"TS_(\d+)_seg", r"\1_{i}", regex=True) == [
        "001_1",
        "002_2",
        "010_3",
    ]


def test_literal_replace_keeps_backslashes():
    assert rename(["a"], "a", r"b\1") == [r"b\1"]


def test_both_empty_unchanged():
    assert rename(NAMES, "", "") == NAMES


def test_find_with_empty_replace_deletes():
    assert rename(NAMES, "_seg", "") == ["TS_001", "TS_002", "TS_010"]


def test_case_sensitivity():
    assert rename(["TS_SEG"], "_seg", "_x", case_sensitive=False) == ["TS_x"]
    assert rename(["TS_SEG"], "_seg", "_x", case_sensitive=True) == ["TS_SEG"]


def test_unknown_brace_kept():
    assert rename(["a"], "", "{x}_{i}") == ["{x}_1"]


def test_invalid_regex_raises():
    with pytest.raises(re.error):
        rename(NAMES, "TS_(", "x", regex=True)


def test_dialog_has_one_mode_and_tooltip(qapp):
    dlg = BatchRenameDialog(NAMES)
    assert not hasattr(dlg, "mode_buttons")
    assert "{i:03}" in dlg.replace_input.toolTip()
    dlg.find_input.setText("_seg")
    dlg.replace_input.setText("_m{i}")
    assert dlg.result_names == ["TS_001_m1", "TS_002_m2", "TS_010_m3"]


def test_dialog_invalid_regex_keeps_names(qapp):
    dlg = BatchRenameDialog(NAMES)
    dlg.regex_check.setChecked(True)
    dlg.find_input.setText("TS_(")
    assert dlg.result_names == NAMES
    assert not dlg.error_label.isHidden()


def test_group_followed_by_number_token():
    assert rename(["TS_001"], r"TS_(\d+)", r"\1{i}", regex=True) == ["0011"]
    assert rename(["TS_001"], r"TS_(\d+)", r"\1{i:03}", regex=True) == ["001001"]


def test_name_token_with_backslash_in_regex_mode():
    assert rename([r"C:\tmp"], "", "{name}", regex=True) == [r"C:\tmp"]
    assert rename([r"a\d"], "", "{name}_x", regex=True) == [r"a\d_x"]


def test_huge_width_stays_literal():
    assert rename(["a"], "", "{i:9999999999}") == ["{i:9999999999}"]
