"""
Batch rename dialog for renaming multiple geometry items at once.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import re
from typing import List

from qtpy.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QGridLayout,
    QCheckBox,
    QStackedWidget,
    QWidget,
    QPushButton,
)

from ..stylesheets import (
    QPushButton_style,
    QLineEdit_style,
    QCheckBox_style,
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

    MODES = ["Replace", "Format"]

    def __init__(self, names: List[str], parent=None):
        super().__init__(parent)
        self.names = names
        self.result_names = list(names)

        self.setWindowTitle("Rename")
        self.setMinimumWidth(480)

        self._setup_ui()
        self._connect_signals()
        self._update_result()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 10)
        main_layout.setSpacing(0)

        # Mode tabs as segmented control
        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        self.mode_buttons = []
        tab_container = QWidget()
        tab_layout = QHBoxLayout(tab_container)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)
        for i, mode in enumerate(self.MODES):
            btn = QPushButton(mode)
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            radius_l = "4px" if i == 0 else "0px"
            radius_r = "4px" if i == len(self.MODES) - 1 else "0px"
            margin_l = "0px" if i == 0 else "-1px"
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    border: 1px solid {Colors.BORDER_DARK};
                    border-radius: 0px;
                    border-top-left-radius: {radius_l};
                    border-bottom-left-radius: {radius_l};
                    border-top-right-radius: {radius_r};
                    border-bottom-right-radius: {radius_r};
                    padding: 5px 18px;
                    font-size: 12px;
                    color: {Colors.TEXT_SECONDARY};
                    background: transparent;
                    margin-left: {margin_l};
                }}
                QPushButton:checked {{
                    background: {Colors.BG_TERTIARY};
                    color: {Colors.TEXT_PRIMARY};
                    font-weight: 500;
                }}
                QPushButton:hover:!checked {{
                    background: {Colors.BG_HOVER};
                }}
            """
            )
            btn.clicked.connect(lambda checked, idx=i: self._on_mode_clicked(idx))
            tab_layout.addWidget(btn)
            self.mode_buttons.append(btn)

        tab_row.addWidget(tab_container)
        tab_row.addStretch()
        main_layout.addLayout(tab_row)
        main_layout.addSpacing(14)

        # Stacked options (no group box)
        self.stack = QStackedWidget()
        self._build_replace_page()
        self._build_format_page()
        main_layout.addWidget(self.stack)
        main_layout.addSpacing(10)

        self.preview_label = QLabel()
        self.preview_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 11px;"
        )
        main_layout.addWidget(self.preview_label)
        main_layout.addSpacing(8)

        footer = DialogFooter(dialog=self, margin=(0, 4, 0, 0))
        footer.accept_button.setText("Rename")
        main_layout.addWidget(footer)

        self.setStyleSheet(QPushButton_style)

    def _build_replace_page(self):
        page = QWidget()
        grid = QGridLayout(page)
        grid.setSpacing(10)
        grid.setContentsMargins(0, 0, 0, 0)

        find_label = QLabel("Find")
        find_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 12px;")
        grid.addWidget(find_label, 0, 0)
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Text to find")
        self.find_input.setStyleSheet(QLineEdit_style)
        grid.addWidget(self.find_input, 0, 1)

        replace_label = QLabel("Replace")
        replace_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 12px;")
        grid.addWidget(replace_label, 1, 0)
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

        template_label = QLabel("Template")
        template_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 12px;"
        )
        grid.addWidget(template_label, 0, 0)
        self.pattern_input = QLineEdit()
        self.pattern_input.setPlaceholderText("e.g. Mitochondrion {i}")
        self.pattern_input.setText("{name}")
        self.pattern_input.setStyleSheet(QLineEdit_style)
        self.pattern_input.selectAll()
        grid.addWidget(self.pattern_input, 0, 1)

        token_help = QLabel("{name} = original · {i} = number · {i:03} = zero-padded")
        token_help.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px;")
        grid.addWidget(token_help, 1, 1)

        self.stack.addWidget(page)

    def _connect_signals(self):
        self.find_input.textChanged.connect(self._update_result)
        self.replace_input.textChanged.connect(self._update_result)
        self.case_sensitive_check.stateChanged.connect(self._update_result)
        self.regex_check.stateChanged.connect(self._update_result)
        self.pattern_input.textChanged.connect(self._update_result)

    def _on_mode_clicked(self, index):
        for i, btn in enumerate(self.mode_buttons):
            btn.setChecked(i == index)
        self.stack.setCurrentIndex(index)
        self._update_result()

    def _compute_names(self):
        if self.stack.currentIndex() == 0:
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

    def _update_result(self):
        self.result_names = self._compute_names()
        if self.names[0] != self.result_names[0]:
            self.preview_label.setText(
                f"Example: {self.names[0]}  →  {self.result_names[0]}"
            )
        else:
            self.preview_label.setText("")
