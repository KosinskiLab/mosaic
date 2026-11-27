"""
Dialog linking session files to tomograms in a folder.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import os
import re

from qtpy.QtCore import Qt
from qtpy.QtGui import QColor
from qtpy.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..formats.session import read_session_meta
from ..formats.tomogram_matching import (
    NO_TOMOGRAM,
    LinkRow,
    build_rows,
    detect_key,
    entries,
    initial_folder,
    is_warning,
    match_tomograms,
    pending_changes,
    resolve_note,
    scan_tomograms,
    status_text,
)
from ..path_display import display_paths, set_path_text
from ..settings import Settings
from ..stylesheets import Colors, Typography
from ..widgets import DialogFooter
from ..widgets.path_selector import PathSelector

__all__ = ["LinkTomogramsDialog"]

_CHOOSE_FILE = object()


def _read_link(path: str) -> str | None:
    try:
        return read_session_meta(path).get("tomogram")
    except (OSError, ValueError):
        return None


class _Combo(QComboBox):
    """Combo box that leaves wheel events to the table."""

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event) -> None:
        event.ignore()
        return None


def _field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f"color: {Colors.TEXT_SECONDARY}; font-size: {Typography.LABEL}px;"
    )
    return label


class LinkTomogramsDialog(QDialog):
    """Match sessions to tomograms in a folder and choose the links to write.

    Parameters
    ----------
    session_paths : list of str
        Session files to link.
    parent : QWidget, optional
        Parent widget.
    """

    def __init__(self, session_paths: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Link Tomograms")
        self.resize(720, 560)

        self._sessions = list(session_paths)
        self._links = {p: _read_link(p) for p in self._sessions}
        self._scanned = None
        self._tomograms = []
        self._rows = []

        self._setup_ui()

        folder = initial_folder(self._links, Settings.ui.last_tomogram_folder)
        if folder:
            self.set_folder(folder)
        else:
            self._rematch()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 10)
        layout.setSpacing(0)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnStretch(1, 1)

        self.folder_picker = PathSelector(
            placeholder="Tomogram folder", mode="directory"
        )
        grid.addWidget(_field_label("Folder"), 0, 0)
        grid.addWidget(self.folder_picker, 0, 1)

        self.subfolders = QCheckBox("Search subfolders")
        grid.addWidget(self.subfolders, 1, 1)

        self.key_input = QLineEdit()
        self.key_input.setFixedHeight(Colors.WIDGET_HEIGHT)

        # The global vertical padding clips underscores at this height.
        self.key_input.setStyleSheet("padding: 0px 8px;")
        self.key_input.setPlaceholderText(r"Regular expression, e.g. TS_\d+")
        self.detect_button = QPushButton("Detect")
        self.detect_button.setAutoDefault(False)
        self.detect_button.setFixedHeight(Colors.WIDGET_HEIGHT)
        key_row = QHBoxLayout()
        key_row.setContentsMargins(0, 0, 0, 0)
        key_row.setSpacing(8)
        key_row.addWidget(self.key_input, 1)
        key_row.addWidget(self.detect_button)
        grid.addWidget(_field_label("Key"), 2, 0)
        grid.addLayout(key_row, 2, 1)

        self.case_sensitive = QCheckBox("Case sensitive")
        grid.addWidget(self.case_sensitive, 3, 1)

        self.caption = QLabel()
        self.caption.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        grid.addWidget(self.caption, 4, 1)
        layout.addLayout(grid)
        layout.addSpacing(16)

        self.folder_picker.path_input.editingFinished.connect(self._rescan)
        self.folder_picker.path_input.textChanged.connect(self._on_folder_text)
        self.subfolders.toggled.connect(self._rescan)
        self.key_input.textChanged.connect(self._rematch)
        self.detect_button.clicked.connect(self._detect)
        self.case_sensitive.toggled.connect(self._rematch)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Session", "Status", "Tomogram"])
        self.table.setShowGrid(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        row_height = Colors.WIDGET_HEIGHT + 12
        rows = self.table.verticalHeader()
        rows.hide()
        rows.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        rows.setDefaultSectionSize(row_height)

        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setFixedHeight(Colors.WIDGET_HEIGHT)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        # Wide enough for every status, so the column keeps its width.
        status_width = self.table.fontMetrics().horizontalAdvance("99 candidates")
        header.resizeSection(1, status_width + 48)

        margin = (row_height - Colors.WIDGET_HEIGHT) // 2
        self.table.setStyleSheet(
            f"""
            QTableWidget::item {{
                padding-left: 8px;
            }}
            QTableWidget::item:hover {{
                background: transparent;
            }}
            QTableWidget QHeaderView::section {{
                background: {Colors.BG_SECONDARY};
                padding-left: 8px;
            }}
            QComboBox {{
                margin: {margin}px 8px {margin}px 0px;
            }}
            """
        )
        layout.addWidget(self.table, 1)

        self.footer = DialogFooter(info_text="", dialog=self, margin=(0, 8, 0, 0))
        self.footer.accept_button.setText("Apply")

        # Enter in the folder or key fields must not apply the links.
        self.footer.accept_button.setAutoDefault(False)
        self.footer.reject_button.setAutoDefault(False)
        layout.addWidget(self.footer)
        return None

    def set_folder(self, path: str, recursive: bool = False) -> None:
        """Scan ``path`` for tomograms and rematch."""
        for widget in (self.folder_picker.path_input, self.subfolders):
            widget.blockSignals(True)
        self.folder_picker.set_path(path)
        self.subfolders.setChecked(recursive)
        for widget in (self.folder_picker.path_input, self.subfolders):
            widget.blockSignals(False)
        return self._rescan()

    def set_key(self, text: str) -> None:
        """Match by the regular expression ``text``, kept on rescans."""
        self.key_input.setText(text)
        self.key_input.setModified(True)
        return None

    def rows(self) -> list[LinkRow]:
        """Return the rows in display order."""
        return self._rows

    def changes(self) -> dict[str, str | None]:
        """Return the links Apply writes."""
        return pending_changes(self._rows)

    def accept(self) -> None:
        Settings.ui.last_tomogram_folder = self._folder()
        super().accept()
        return None

    def _folder(self) -> str:
        return self.folder_picker.get_path().strip()

    def _root(self) -> str | None:
        return (self._scanned[0] or None) if self._scanned else None

    def _on_folder_text(self) -> None:
        # Typed text rescans on editingFinished, set_path from Browse does not emit it.
        if not self.folder_picker.path_input.isModified():
            self._rescan()
        return None

    def _rescan(self) -> None:
        scan = (self._folder(), self.subfolders.isChecked())
        if scan == self._scanned:
            return None

        self._scanned = scan
        folder, recursive = scan
        self._tomograms = scan_tomograms(folder, recursive) if folder else []
        if self.key_input.isModified():
            return self._rematch()
        return self._detect()

    def _detect(self) -> None:
        found = detect_key(
            match_tomograms(self._sessions, self._tomograms, root=self._root())
        )
        self.key_input.blockSignals(True)
        self.key_input.setText(found[0] if found else "")
        self.key_input.blockSignals(False)
        return self._rematch()

    def _rematch(self) -> None:
        try:
            matches = match_tomograms(
                self._sessions,
                self._tomograms,
                root=self._root(),
                key=self.key_input.text() or None,
                case_sensitive=self.case_sensitive.isChecked(),
            )
        except re.error as e:
            return self._set_caption(f"Invalid pattern: {e}", Colors.ERROR)

        example = detect_key(matches)
        text = "Example: no match yet"
        if example is not None:
            text = f"Example: {example[1]}  →  {example[2]}"
        self._set_caption(text, Colors.TEXT_MUTED)

        self._rows = build_rows(matches, self._links)
        self._populate()
        return self._refresh()

    def _set_caption(self, text: str, color: str) -> None:
        self.caption.setText(text)
        self.caption.setStyleSheet(
            f"color: {color}; font-size: {Typography.CAPTION}px;"
        )
        return None

    def _populate(self) -> None:
        self.table.setRowCount(len(self._rows))
        metrics = self.table.fontMetrics()
        width = metrics.horizontalAdvance("Session")
        for i, row in enumerate(self._rows):
            session = QTableWidgetItem()

            # Caps the Session column so the Tomogram column keeps room.
            set_path_text(session, os.path.splitext(row.session)[0], width=220)
            session.setToolTip(row.session)
            width = max(width, metrics.horizontalAdvance(session.text()))
            self.table.setItem(i, 0, session)
            self.table.setItem(i, 1, QTableWidgetItem())

            # A replaced cell widget stays visible until exec() returns.
            if self._combo(i) is None:
                combo = _Combo()
                combo.setPlaceholderText("Choose…")
                combo.currentIndexChanged.connect(
                    lambda index, i=i: self._on_selected(i, index)
                )
                self.table.setCellWidget(i, 2, combo)
            self._fill_combo(self._combo(i), row)
        self.table.horizontalHeader().resizeSection(0, width + 48)
        return None

    def _fill_combo(self, combo: QComboBox, row: LinkRow) -> None:
        paths = entries(row)
        labels = display_paths(paths, root=self._root())

        combo.blockSignals(True)
        combo.clear()
        for path, label in zip(paths, labels):
            suffix = " (current)" if path == row.current else ""
            combo.addItem(label + suffix, path)
        combo.insertSeparator(combo.count())
        combo.addItem("Choose file…", _CHOOSE_FILE)
        combo.addItem("None", NO_TOMOGRAM)
        combo.setCurrentIndex(
            -1 if row.selection is None else combo.findData(row.selection)
        )
        combo.setToolTip(row.selection or "")
        combo.blockSignals(False)
        return None

    def _on_selected(self, i: int, index: int) -> None:
        row, combo = self._rows[i], self._combo(i)
        selection = combo.itemData(index)
        if selection is _CHOOSE_FILE:
            selection, _ = QFileDialog.getOpenFileName(
                self, "Choose Tomogram", self._root() or ""
            )
            selection = selection or row.selection

        row.selection = selection
        self._fill_combo(combo, row)
        return self._refresh()

    def _combo(self, i: int) -> QComboBox:
        return self.table.cellWidget(i, 2)

    def _status(self, i: int) -> str:
        return self.table.item(i, 1).text()

    def _refresh(self) -> None:
        # Without tomograms there is nothing to resolve yet.
        scanned = bool(self._tomograms)
        for i, row in enumerate(self._rows):
            item = self.table.item(i, 1)
            item.setText(status_text(row) if scanned or not is_warning(row) else "")
            color = Colors.WARNING_TEXT if is_warning(row) else Colors.TEXT_SECONDARY
            item.setForeground(QColor(color))
        self.footer.set_info(resolve_note(self._rows) if scanned else None)
        return None
