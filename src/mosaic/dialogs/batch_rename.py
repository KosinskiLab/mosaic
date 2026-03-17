"""
Batch rename dialog for renaming multiple geometry items at once.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import re
from typing import List

from qtpy.QtCore import Qt
from qtpy.QtGui import QColor
from qtpy.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QGroupBox,
    QGridLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QHeaderView,
    QComboBox,
    QCheckBox,
    QStackedWidget,
    QWidget,
)

from ..stylesheets import (
    QGroupBox_style,
    QPushButton_style,
    QLineEdit_style,
    QTable_style,
    QComboBox_style,
    QCheckBox_style,
    QScrollArea_style,
    Colors,
)
from ..widgets import DialogFooter


class BatchRenameDialog(QDialog):
    """Dialog for batch renaming with Replace Text and Format modes.

    Modes
    -----
    Replace Text
        Find and replace within names. Supports plain text (default) and
        optional regular expressions for power users.
    Format
        Pattern template with ``{name}`` (original name), ``{i}`` (sequential
        index), and ``{i:03}`` (zero-padded index) tokens.

    Parameters
    ----------
    names : List[str]
        Current names of items in tree order.
    parent : QWidget, optional
        Parent widget.
    """

    MODES = ["Replace Text", "Format"]

    def __init__(self, names: List[str], parent=None):
        super().__init__(parent)
        self.names = names
        self.result_names = list(names)

        self.setWindowTitle("Batch Rename")
        self.setMinimumWidth(480)

        self._setup_ui()
        self._connect_signals()
        self._update_preview()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 10)
        main_layout.setSpacing(16)

        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Method:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(self.MODES)
        self.mode_combo.setStyleSheet(QComboBox_style)
        self.mode_combo.setMinimumWidth(160)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()
        main_layout.addLayout(mode_layout)

        self.options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(self.options_group)
        options_layout.setContentsMargins(10, 14, 10, 10)

        self.stack = QStackedWidget()
        self._build_replace_page()
        self._build_format_page()
        options_layout.addWidget(self.stack)

        main_layout.addWidget(self.options_group)

        preview_group = QGroupBox(f"Preview ({len(self.names)} items)")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(10, 14, 10, 10)

        self.preview_tree = QTreeWidget()
        self.preview_tree.setHeaderLabels(["Current", "New"])
        self.preview_tree.setRootIsDecorated(False)
        self.preview_tree.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        self.preview_tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.preview_tree.header().setStretchLastSection(True)
        self.preview_tree.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        _tree_style = QTable_style.replace("QTableWidget", "QTreeWidget")
        _scrollbar_style = QScrollArea_style.replace("QScrollArea", "QTreeWidget")
        _no_hover = "QTreeWidget::item:hover { background: transparent; }"
        self.preview_tree.setStyleSheet(_tree_style + _scrollbar_style + _no_hover)
        self.preview_tree.setMinimumHeight(180)
        preview_layout.addWidget(self.preview_tree)

        main_layout.addWidget(preview_group)

        footer = DialogFooter(dialog=self, margin=(0, 4, 0, 0))
        footer.accept_button.setText("Rename")
        main_layout.addWidget(footer)

        self.setStyleSheet(QGroupBox_style + QPushButton_style)

    def _build_replace_page(self):
        page = QWidget()
        grid = QGridLayout(page)
        grid.setSpacing(10)
        grid.setContentsMargins(0, 0, 0, 0)

        grid.addWidget(QLabel("Find:"), 0, 0)
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Text to find")
        self.find_input.setStyleSheet(QLineEdit_style)
        grid.addWidget(self.find_input, 0, 1)

        grid.addWidget(QLabel("Replace:"), 1, 0)
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("Replacement (leave empty to delete)")
        self.replace_input.setStyleSheet(QLineEdit_style)
        grid.addWidget(self.replace_input, 1, 1)

        self.error_label = QLabel()
        self.error_label.setStyleSheet(
            f"color: {Colors.ERROR}; font-size: 10px; padding: 0;"
        )
        self.error_label.hide()
        grid.addWidget(self.error_label, 2, 1)

        options_row = QHBoxLayout()
        self.case_sensitive_check = QCheckBox("Case sensitive")
        self.case_sensitive_check.setChecked(True)
        self.case_sensitive_check.setStyleSheet(QCheckBox_style)
        options_row.addWidget(self.case_sensitive_check)

        self.regex_check = QCheckBox("Regular expression")
        self.regex_check.setStyleSheet(QCheckBox_style)
        options_row.addWidget(self.regex_check)
        options_row.addStretch()

        grid.addLayout(options_row, 3, 1)

        self.stack.addWidget(page)

    def _build_format_page(self):
        page = QWidget()
        grid = QGridLayout(page)
        grid.setSpacing(10)
        grid.setContentsMargins(0, 0, 0, 0)

        grid.addWidget(QLabel("Template:"), 0, 0)
        self.pattern_input = QLineEdit()
        self.pattern_input.setPlaceholderText("e.g. Mitochondrion {i}")
        self.pattern_input.setText("{name}")
        self.pattern_input.setStyleSheet(QLineEdit_style)
        self.pattern_input.selectAll()
        grid.addWidget(self.pattern_input, 0, 1)

        token_help = QLabel(
            "{name} = original name, {i} = number, {i:03} = zero-padded"
        )
        token_help.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;")
        grid.addWidget(token_help, 1, 1)

        self.stack.addWidget(page)

    def _connect_signals(self):
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.find_input.textChanged.connect(self._update_preview)
        self.replace_input.textChanged.connect(self._update_preview)
        self.case_sensitive_check.stateChanged.connect(self._update_preview)
        self.regex_check.stateChanged.connect(self._update_preview)

        self.pattern_input.textChanged.connect(self._update_preview)

    def _on_mode_changed(self, index):
        self.stack.setCurrentIndex(index)
        self._update_preview()

    def _compute_names(self):
        if self.mode_combo.currentIndex() == 0:
            return self._apply_replace()
        return self._apply_format()

    def _apply_replace(self):
        find = self.find_input.text()
        replace = self.replace_input.text()
        if not find:
            return list(self.names)

        use_regex = self.regex_check.isChecked()
        case_sensitive = self.case_sensitive_check.isChecked()
        flags = 0 if case_sensitive else re.IGNORECASE

        result = []
        for name in self.names:
            try:
                if use_regex:
                    new_name = re.sub(find, replace, name, flags=flags)
                else:
                    new_name = re.sub(re.escape(find), replace, name, flags=flags)
                self.error_label.hide()
            except re.error as e:
                self.error_label.setText(f"Invalid pattern: {e}")
                self.error_label.show()
                return list(self.names)
            result.append(new_name)
        return result

    def _apply_format(self):
        pattern = self.pattern_input.text()

        result = []
        for idx, name in enumerate(self.names):
            text = pattern
            text = re.sub(
                r"\{i:(\d+)\}",
                lambda m: str(idx + 1).zfill(int(m.group(1))),
                text,
            )
            text = text.replace("{i}", str(idx + 1))
            text = text.replace("{name}", name)
            result.append(text)
        return result

    def _update_preview(self):
        self.result_names = self._compute_names()
        self.preview_tree.clear()

        muted = QColor(Colors.TEXT_SECONDARY)
        for old_name, new_name in zip(self.names, self.result_names):
            item = QTreeWidgetItem([old_name, new_name])
            item.setForeground(0, muted)
            self.preview_tree.addTopLevelItem(item)
