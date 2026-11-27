from unittest.mock import Mock

import pytest

from mosaic.dialogs.link_tomograms import LinkTomogramsDialog
from mosaic.formats.session import update_session_meta, write_session
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
        Mock(return_value=("", "")),
    )
    i = [r.session for r in dlg.rows()].index(sessions[0])
    combo = dlg._combo(i)
    combo.setCurrentIndex(combo.findText("Choose file…"))
    assert combo.currentText() == "TS_012.mrc" and dlg._status(i) == "New"

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


def test_pattern_rematches_without_rescan(qapp, dataset, monkeypatch):
    sessions, tomos = dataset
    dlg = LinkTomogramsDialog(sessions)
    dlg.set_folder(str(tomos))
    monkeypatch.setattr(
        "mosaic.dialogs.link_tomograms.scan_tomograms",
        Mock(side_effect=AssertionError),
    )
    dlg.set_pattern(("{key}_membrane", "{key}"))
    assert dlg.footer.info_label.text() == "1 to resolve"
    dlg.set_pattern(("{key}_seg", "{key}"))
    assert dlg.footer.info_label.text() == "3 to resolve"


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


def test_key_line_hidden_without_match(qapp, dataset):
    sessions, tomos = dataset
    dlg = LinkTomogramsDialog(sessions)
    assert dlg.key_label.isHidden()
    dlg.set_folder(str(tomos))
    assert not dlg.key_label.isHidden()


def test_row_hover_outlines_combo(qapp, dataset):
    from qtpy.QtGui import QColor

    from mosaic.stylesheets import Colors

    sessions, tomos = dataset
    dlg = LinkTomogramsDialog(sessions)
    dlg.set_folder(str(tomos))
    combo = dlg._combo(1)

    def border():
        image = combo.grab().toImage()
        return QColor(image.pixel(0, image.height() // 2)).name()

    dlg._set_hovered(1)
    assert border() == QColor(Colors.BORDER_HOVER).name()
    dlg._set_hovered(0)
    assert border() != QColor(Colors.BORDER_HOVER).name()
