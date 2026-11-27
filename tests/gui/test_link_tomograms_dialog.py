from unittest.mock import Mock

import pytest
from qtpy.QtCore import Qt

from mosaic.dialogs.link_tomograms import LinkTomogramsDialog
from mosaic.formats.session import update_session_meta, write_session
from mosaic.formats.tomogram_matching import NO_TOMOGRAM
from mosaic.settings import Settings


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(Settings.ui, "last_tomogram_folder", "")
    sessions = []
    for name in ("TS_012_membrane", "TS_013_membrane", "TS_099_membrane"):
        p = str(tmp_path / f"{name}.mosaic")
        write_session(p, {})
        sessions.append(p)
    tomos = tmp_path / "tomos"
    tomos.mkdir()
    for name in ("TS_012.mrc", "TS_013.mrc"):
        (tomos / name).write_bytes(b"")
    return sessions, tomos


def test_dialog_matches_and_notes_unresolved(qapp, dataset):
    sessions, tomos = dataset
    dlg = LinkTomogramsDialog(sessions)
    dlg.set_folder(str(tomos))
    assert dlg.rows()[0].session == sessions[2] and dlg._status(0) == "No match"
    assert dlg._combo(0).currentIndex() == -1
    assert dlg._combo(0).placeholderText() == "Choose…"
    assert dlg.footer.accept_button.text() == "Apply"
    assert dlg.footer.info_label.text() == "1 to resolve"
    assert set(dlg.changes()) == {sessions[0], sessions[1]}


def test_folder_prefilled_from_existing_links(qapp, dataset):
    sessions, tomos = dataset
    update_session_meta(sessions[0], {"tomogram": str(tomos / "TS_012.mrc")})
    dlg = LinkTomogramsDialog(sessions)
    i = [r.session for r in dlg.rows()].index(sessions[0])
    assert dlg._status(i) == "Linked"
    assert set(dlg.changes()) == {sessions[1]}


def test_none_entry_removes_and_rows_stay_put(qapp, dataset):
    sessions, tomos = dataset
    update_session_meta(sessions[0], {"tomogram": "/old/TS_012_bin8.mrc"})
    dlg = LinkTomogramsDialog(sessions)
    dlg.set_folder(str(tomos))
    order = [r.session for r in dlg.rows()]
    i = order.index(sessions[0])
    assert dlg._status(i) == "Replaced"
    combo = dlg._combo(i)
    combo.setCurrentIndex(combo.findText("None"))
    assert dlg._status(i) == "Removed" and dlg.changes()[sessions[0]] is None
    assert [r.session for r in dlg.rows()] == order


def test_current_link_entry_restores_it(qapp, dataset):
    sessions, tomos = dataset
    update_session_meta(sessions[0], {"tomogram": "/old/TS_012_bin8.mrc"})
    dlg = LinkTomogramsDialog(sessions)
    dlg.set_folder(str(tomos))
    i = [r.session for r in dlg.rows()].index(sessions[0])
    combo = dlg._combo(i)
    labels = [combo.itemText(k) for k in range(combo.count())]
    assert labels[1] == "…/old/TS_012_bin8.mrc (current)"
    combo.setCurrentIndex(1)
    assert dlg._status(i) == "Linked" and sessions[0] not in dlg.changes()


def test_choose_file_cancel_keeps_selection(qapp, dataset, monkeypatch):
    sessions, tomos = dataset
    dlg = LinkTomogramsDialog(sessions)
    dlg.set_folder(str(tomos))
    monkeypatch.setattr(
        "mosaic.dialogs.link_tomograms.QFileDialog.getOpenFileName",
        cancel := Mock(return_value=("", "")),
    )
    i = [r.session for r in dlg.rows()].index(sessions[0])
    combo = dlg._combo(i)
    combo.setCurrentIndex(combo.findText("Choose file…"))
    assert combo.currentText() == "TS_012.mrc" and dlg._status(i) == "New"
    cancel.assert_called_once()

    combo = dlg._combo(0)

    picked = (tomos / "TS_099_manual.mrc").as_posix()
    monkeypatch.setattr(
        "mosaic.dialogs.link_tomograms.QFileDialog.getOpenFileName",
        Mock(return_value=(picked, "")),
    )
    combo.setCurrentIndex(combo.findText("Choose file…"))
    assert dlg._status(0) == "New" and dlg.changes()[sessions[2]] == picked
    assert dlg._combo(0).currentText() == "TS_099_manual.mrc"
    assert dlg.footer.info_label.isHidden()


def test_key_rematches_without_rescan(qapp, dataset, monkeypatch):
    sessions, tomos = dataset
    dlg = LinkTomogramsDialog(sessions)
    dlg.set_folder(str(tomos))
    monkeypatch.setattr(
        "mosaic.dialogs.link_tomograms.scan_tomograms",
        Mock(side_effect=AssertionError),
    )
    dlg.set_key(r"TS_\d+_seg")
    assert dlg.footer.info_label.text() == "3 to resolve"
    dlg.set_key(r"ts_\d+")
    assert dlg.footer.info_label.text() == "1 to resolve"
    dlg.case_sensitive.setChecked(True)
    assert dlg.footer.info_label.text() == "3 to resolve"


def test_scan_fills_key_and_detect_restores_it(qapp, dataset):
    sessions, tomos = dataset
    dlg = LinkTomogramsDialog(sessions)
    assert dlg.key_input.text() == ""
    dlg.set_folder(str(tomos))
    assert dlg.key_input.text() == r"TS_\d+"
    dlg.set_key("TS_099")
    dlg.detect_button.click()
    assert dlg.key_input.text() == r"TS_\d+" and not dlg.key_input.isModified()
    assert dlg.footer.info_label.text() == "1 to resolve"


def test_edited_key_survives_rescan(qapp, dataset):
    sessions, tomos = dataset
    dlg = LinkTomogramsDialog(sessions)
    dlg.set_folder(str(tomos))
    dlg.set_key(r"TS_(\d+)_membrane")
    dlg.set_folder(str(tomos), recursive=True)
    assert dlg.key_input.text() == r"TS_(\d+)_membrane"
    assert dlg.footer.info_label.text() == "3 to resolve"


def test_invalid_key_keeps_rows(qapp, dataset):
    sessions, tomos = dataset
    dlg = LinkTomogramsDialog(sessions)
    dlg.set_folder(str(tomos))
    rows = dlg.rows()
    statuses = [dlg._status(i) for i in range(len(rows))]
    dlg.set_key("TS_(")
    assert dlg.rows() is rows
    assert [dlg._status(i) for i in range(len(rows))] == statuses
    assert dlg.caption.text().startswith("Invalid pattern")
    dlg.set_key(r"TS_\d+")
    assert dlg.caption.text() == "Example: TS_012_membrane  →  TS_012.mrc"


def test_session_column_shows_stems(qapp, dataset):
    sessions, tomos = dataset
    dlg = LinkTomogramsDialog(sessions)
    dlg.set_folder(str(tomos))
    item = dlg.table.item(0, 0)
    assert item.text() == "TS_099_membrane" and item.toolTip() == sessions[2]


def test_accept_stores_folder(qapp, dataset):
    sessions, tomos = dataset
    dlg = LinkTomogramsDialog(sessions)
    dlg.set_folder(str(tomos))
    dlg.accept()
    assert Settings.ui.last_tomogram_folder == str(tomos)


def test_combo_popup_shows_separator(qapp, dataset):
    from mosaic.stylesheets import build_appstyle

    sessions, tomos = dataset
    dlg = LinkTomogramsDialog(sessions)
    dlg.set_folder(str(tomos))
    combo = dlg._combo(0)
    combo.setStyle(build_appstyle())
    combo.showPopup()
    actions = combo._popup_menu.actions()
    assert [a.isSeparator() for a in actions] == [True, False, False]
    assert [a.text() for a in actions[1:]] == ["Choose file…", "None"]
    combo._popup_menu.close()


def test_unchanged_folder_keeps_choices(qapp, dataset):
    sessions, tomos = dataset
    dlg = LinkTomogramsDialog(sessions)
    dlg.set_folder(str(tomos))
    combo = dlg._combo(1)
    combo.setCurrentIndex(combo.findText("None"))
    dlg.folder_picker.path_input.editingFinished.emit()
    assert dlg._status(1) == "Skipped"


def test_typing_waits_for_editing_finished(qapp, dataset, monkeypatch):
    from qtpy.QtTest import QTest

    sessions, tomos = dataset
    dlg = LinkTomogramsDialog(sessions)
    scan = Mock(return_value=[])
    monkeypatch.setattr("mosaic.dialogs.link_tomograms.scan_tomograms", scan)
    QTest.keyClicks(dlg.folder_picker.path_input, str(tomos))
    scan.assert_not_called()
    dlg.folder_picker.set_path(str(tomos / "sub"))
    scan.assert_called_once_with(str(tomos / "sub"), False)


def test_no_folder_shows_no_statuses(qapp, dataset):
    sessions, tomos = dataset
    dlg = LinkTomogramsDialog(sessions)
    assert [dlg._status(i) for i in range(len(sessions))] == ["", "", ""]
    assert dlg.footer.info_label.isHidden()
    assert dlg.caption.text() == "Example: no match yet"


def test_rematch_leaves_one_combo_per_row(qapp, dataset):
    sessions, tomos = dataset
    dlg = LinkTomogramsDialog(sessions)
    dlg.show()
    dlg.set_folder(str(tomos))
    dlg.set_folder(str(tomos), recursive=True)
    viewport = dlg.table.viewport()
    shown = [w for w in viewport.children() if w.isWidgetType() and not w.isHidden()]
    combos = [dlg._combo(i) for i in range(dlg.table.rowCount())]
    assert len(combos) == len(sessions) and set(shown) == set(combos)
    dlg.close()


def test_wheel_leaves_combo_selection(qapp, dataset, monkeypatch):
    from qtpy.QtCore import QPoint, QPointF
    from qtpy.QtGui import QWheelEvent

    from mosaic.stylesheets import build_appstyle

    choose = Mock(return_value=("", ""))
    monkeypatch.setattr(
        "mosaic.dialogs.link_tomograms.QFileDialog.getOpenFileName", choose
    )
    sessions, tomos = dataset
    dlg = LinkTomogramsDialog(sessions)
    dlg.set_folder(str(tomos))
    combo = dlg._combo(1)
    combo.setStyle(build_appstyle())
    combo.setCurrentIndex(combo.findText("None"))
    index = combo.currentIndex()
    center = QPointF(combo.rect().center())
    wheel = QWheelEvent(
        center,
        QPointF(combo.mapToGlobal(center.toPoint())),
        QPoint(),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    qapp.sendEvent(combo, wheel)
    assert combo.currentIndex() == index
    choose.assert_not_called()


def test_empty_folder_shows_unresolved(qapp, dataset, tmp_path):
    sessions, tomos = dataset
    empty = tmp_path / "empty"
    empty.mkdir()
    dlg = LinkTomogramsDialog(sessions)
    dlg.set_folder(str(empty))
    assert [dlg._status(i) for i in range(len(sessions))] == ["No match"] * 3
    assert dlg.footer.info_label.text() == "3 to resolve"


def test_cleared_folder_hides_all_statuses(qapp, dataset):
    sessions, tomos = dataset
    update_session_meta(sessions[0], {"tomogram": str(tomos / "TS_012.mrc")})
    dlg = LinkTomogramsDialog(sessions)
    dlg.set_folder("")
    assert [dlg._status(i) for i in range(len(sessions))] == ["", "", ""]
    assert dlg.footer.info_label.isHidden()


def test_cleared_key_uses_auto_matcher(qapp, dataset):
    sessions, tomos = dataset
    dlg = LinkTomogramsDialog(sessions)
    dlg.set_folder(str(tomos))
    dlg.set_key(r"TS_\d+_seg")
    assert dlg.footer.info_label.text() == "3 to resolve"
    dlg.set_key("")
    assert dlg.footer.info_label.text() == "1 to resolve"


def _pick(dlg, session, text):
    i = [r.session for r in dlg.rows()].index(session)
    combo = dlg._combo(i)
    combo.setCurrentIndex(combo.findText(text))
    return None


def _selection(dlg, session):
    return next(r.selection for r in dlg.rows() if r.session == session)


def test_manual_pick_survives_key_change_and_detect(qapp, dataset, monkeypatch):
    sessions, tomos = dataset
    dlg = LinkTomogramsDialog(sessions)
    dlg.set_folder(str(tomos))
    picked = (tomos / "TS_099_manual.mrc").as_posix()
    monkeypatch.setattr(
        "mosaic.dialogs.link_tomograms.QFileDialog.getOpenFileName",
        Mock(return_value=(picked, "")),
    )
    _pick(dlg, sessions[2], "Choose file…")
    dlg.set_key(r"TS_\d+_seg")
    assert _selection(dlg, sessions[2]) == picked
    dlg.detect_button.click()
    assert _selection(dlg, sessions[2]) == picked


def test_none_survives_key_change(qapp, dataset):
    sessions, tomos = dataset
    dlg = LinkTomogramsDialog(sessions)
    dlg.set_folder(str(tomos))
    _pick(dlg, sessions[0], "None")
    dlg.set_key(r"TS_\d+")
    assert _selection(dlg, sessions[0]) == NO_TOMOGRAM


def test_rows_keep_order_on_key_change_but_resort_on_folder(qapp, dataset):
    sessions, tomos = dataset
    dlg = LinkTomogramsDialog(sessions)
    dlg.set_folder(str(tomos))
    order = [r.session for r in dlg.rows()]
    assert order[0] == sessions[2]
    dlg.set_key(r"TS_\d+_seg")
    assert [r.session for r in dlg.rows()] == order
    dlg.set_key("TS_012")
    assert [r.session for r in dlg.rows()] == order

    (tomos / "TS_099.mrc").write_bytes(b"")
    dlg.set_folder(str(tomos), recursive=True)
    assert [r.session for r in dlg.rows()] != order
