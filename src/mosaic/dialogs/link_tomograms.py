"""
Dialog linking session files to tomograms in a folder.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import html

from qtpy.QtCore import Qt
from qtpy.QtGui import QColor
from qtpy.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..formats.session import read_session_meta
from ..formats.tomogram_matching import (
    NO_TOMOGRAM,
    LinkRow,
    build_rows,
    detected_key,
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


def _text_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setFlat(True)
    button.setAutoDefault(False)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setStyleSheet(
        f"""
        QPushButton {{
            border: none;
            background: transparent;
            padding: 2px 6px;
            color: {Colors.TEXT_SECONDARY};
            font-size: {Typography.LABEL}px;
        }}
        QPushButton:hover {{
            color: {Colors.TEXT_PRIMARY};
        }}
        """
    )
    return button


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
        self.resize(640, 440)

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
        layout.setSpacing(10)

        folder_row = QHBoxLayout()
        self.folder_picker = PathSelector(
            placeholder="Tomogram folder", mode="directory"
        )
        self.subfolders = QCheckBox("Subfolders")
        folder_row.addWidget(self.folder_picker, 1)
        folder_row.addWidget(self.subfolders)
        layout.addLayout(folder_row)

        self.folder_picker.path_input.editingFinished.connect(self._rescan)
        self.folder_picker.path_input.textChanged.connect(self._on_folder_text)
        self.subfolders.toggled.connect(self._rescan)

        match_row = QHBoxLayout()
        match_row.setContentsMargins(0, 0, 0, 0)

        self._auto_row = QWidget()
        auto_layout = QHBoxLayout(self._auto_row)
        auto_layout.setContentsMargins(0, 0, 0, 0)
        self.key_label = QLabel()
        self.key_label.setTextFormat(Qt.TextFormat.RichText)
        self.key_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self.key_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: {Typography.LABEL}px;"
        )
        self.edit_button = _text_button("Edit")
        self.edit_button.clicked.connect(self._edit_pattern)
        auto_layout.addWidget(self.key_label, 1)
        auto_layout.addWidget(self.edit_button)

        self._pattern_row = QWidget()
        pattern_layout = QHBoxLayout(self._pattern_row)
        pattern_layout.setContentsMargins(0, 0, 0, 0)
        hint = "{key} is the shared part, * matches anything"
        self.session_pattern = QLineEdit()
        self.session_pattern.setPlaceholderText("{key}_seg")
        self.session_pattern.setToolTip(hint)
        self.tomogram_pattern = QLineEdit()
        self.tomogram_pattern.setPlaceholderText("{key}_rec*")
        self.tomogram_pattern.setToolTip(hint)
        self.auto_button = _text_button("Auto")
        self.auto_button.clicked.connect(lambda: self.set_pattern(None))
        pattern_layout.addWidget(_field_label("Session"))
        pattern_layout.addWidget(self.session_pattern, 1)
        pattern_layout.addWidget(_field_label("Tomogram"))
        pattern_layout.addWidget(self.tomogram_pattern, 1)
        pattern_layout.addWidget(self.auto_button)
        self._pattern_row.hide()

        self.session_pattern.textChanged.connect(self._rematch)
        self.tomogram_pattern.textChanged.connect(self._rematch)

        match_row.addWidget(self._auto_row, 1)
        match_row.addWidget(self._pattern_row, 1)
        layout.addLayout(match_row)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Session", "Status", "Tomogram"])
        self.table.setShowGrid(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        rows = self.table.verticalHeader()
        rows.hide()
        rows.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        rows.setDefaultSectionSize(Colors.WIDGET_HEIGHT + 4)

        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        self.table.setStyleSheet(
            f"""
            QTableWidget QHeaderView::section {{
                background: {Colors.BG_SECONDARY};
            }}
            QComboBox {{
                margin: 2px 0px;
            }}
            """
        )
        layout.addWidget(self.table, 1)

        self.footer = DialogFooter(info_text="", dialog=self, margin=(0, 4, 0, 0))
        self.footer.accept_button.setText("Apply")

        # Enter in the folder or pattern fields must not apply the links.
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

    def set_pattern(self, pattern: tuple[str, str] | None) -> None:
        """Match by session and tomogram templates, or automatically if None."""
        self._auto_row.setVisible(pattern is None)
        self._pattern_row.setVisible(pattern is not None)
        if pattern is not None:
            for edit, text in zip(
                (self.session_pattern, self.tomogram_pattern), pattern
            ):
                edit.blockSignals(True)
                edit.setText(text)
                edit.blockSignals(False)
        return self._rematch()

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

    def _pattern(self) -> tuple[str, str] | None:
        if self._pattern_row.isHidden():
            return None
        return self.session_pattern.text(), self.tomogram_pattern.text()

    def _on_folder_text(self) -> None:
        # Typed text rescans on editingFinished, set_path from Browse does not emit it.
        if not self.folder_picker.path_input.isModified():
            self._rescan()
        return None

    def _edit_pattern(self) -> None:
        self._auto_row.hide()
        self._pattern_row.show()
        self.session_pattern.setFocus()
        return None

    def _rescan(self) -> None:
        scan = (self._folder(), self.subfolders.isChecked())
        if scan == self._scanned:
            return None

        self._scanned = scan
        folder, recursive = scan
        self._tomograms = scan_tomograms(folder, recursive) if folder else []
        return self._rematch()

    def _rematch(self) -> None:
        try:
            matches = match_tomograms(
                self._sessions,
                self._tomograms,
                root=self._root(),
                pattern=self._pattern(),
            )
        except ValueError:
            return None

        key = detected_key(matches)
        self.key_label.setVisible(key is not None)
        if key is not None:
            key, stem, name = (html.escape(k) for k in key)
            self.key_label.setText(
                f"Key <span style='color: {Colors.TEXT_PRIMARY}; font-weight: 600'>"
                f"{key}</span> · {stem} → {name}"
            )

        self._rows = build_rows(matches, self._links)
        self._populate()
        return self._refresh()

    def _populate(self) -> None:
        self.table.setRowCount(len(self._rows))
        for i, row in enumerate(self._rows):
            session = QTableWidgetItem()

            # Caps the content-sized column so the Tomogram column keeps room.
            set_path_text(session, row.session, width=220)
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
        for i, row in enumerate(self._rows):
            item = self.table.item(i, 1)
            item.setText(status_text(row))
            color = Colors.WARNING_TEXT if is_warning(row) else Colors.TEXT_SECONDARY
            item.setForeground(QColor(color))
        self.footer.set_info(resolve_note(self._rows))
        return None
