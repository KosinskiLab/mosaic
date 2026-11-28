"""
Batch rename dialog for renaming multiple geometry items at once.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import re

from qtpy.QtWidgets import (
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from ..stylesheets import Colors, Typography
from ..widgets import DialogFooter

__all__ = ["BatchRenameDialog", "rename"]

_TOKEN = re.compile(r"\{name\}|\{i(?::(\d{1,3}))?\}")


def _expand(template: str, name: str, index: int, match=None) -> str:
    parts, pos = [], 0
    for token in _TOKEN.finditer(template):
        literal = template[pos : token.start()]
        parts.append(match.expand(literal) if match else literal)
        if token.group(0) == "{name}":
            parts.append(name)
        else:
            parts.append(str(index).zfill(int(token.group(1) or 0)))
        pos = token.end()
    literal = template[pos:]
    parts.append(match.expand(literal) if match else literal)
    return "".join(parts)


def rename(
    names: list[str],
    find: str,
    replace: str,
    regex: bool = False,
    case_sensitive: bool = True,
) -> list[str]:
    """Rename names by replacing ``find`` with ``replace``.

    ``replace`` may contain ``{name}`` (original name), ``{i}`` (1-based
    number) and ``{i:03}`` (zero-padded number). An empty ``find`` matches
    the whole name.

    Parameters
    ----------
    names : list of str
        Names in display order.
    find : str
        Text or regular expression to replace. Empty replaces the whole name.
    replace : str
        Replacement text with optional tokens. With ``regex``, group
        references such as ``\\1`` are expanded too.
    regex : bool, optional
        Treat ``find`` as a regular expression, by default False.
    case_sensitive : bool, optional
        Match case, by default True.

    Returns
    -------
    list of str
        New names, unchanged when both ``find`` and ``replace`` are empty.

    Raises
    ------
    re.error
        If ``find`` is an invalid regular expression.
    """
    if not find and not replace:
        return list(names)

    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = find if regex else re.escape(find)
    compiled = re.compile(pattern or r"^.*$", flags)

    result = []
    for index, name in enumerate(names, start=1):
        if regex:
            new = compiled.sub(
                lambda m, n=name, i=index: _expand(replace, n, i, m), name
            )
        else:
            text = _expand(replace, name, index)
            new = compiled.sub(lambda _, t=text: t, name)
        result.append(new)
    return result


class BatchRenameDialog(QDialog):
    """Dialog for batch renaming with find and replace.

    Parameters
    ----------
    names : list of str
        Current names of items in tree order.
    parent : QWidget, optional
        Parent widget.
    """

    def __init__(self, names: list[str], parent=None):
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

        label_style = (
            f"color: {Colors.TEXT_SECONDARY}; font-size: {Typography.LABEL}px;"
        )
        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setContentsMargins(0, 0, 0, 0)

        find_label = QLabel("Find")
        find_label.setStyleSheet(label_style)
        grid.addWidget(find_label, 0, 0)
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Text to find, empty for the whole name")
        grid.addWidget(self.find_input, 0, 1)

        replace_label = QLabel("Replace")
        replace_label.setStyleSheet(label_style)
        grid.addWidget(replace_label, 1, 0)
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("Replacement (leave empty to delete)")
        self.replace_input.setToolTip(
            "{name} = original name · {i} = number · {i:03} = zero-padded number"
        )
        grid.addWidget(self.replace_input, 1, 1)

        self.error_label = QLabel()
        self.error_label.setStyleSheet(
            f"color: {Colors.ERROR}; font-size: {Typography.CAPTION}px; padding: 0;"
        )
        self.error_label.hide()
        grid.addWidget(self.error_label, 2, 1)

        options_row = QHBoxLayout()
        self.case_sensitive_check = QCheckBox("Case sensitive")
        self.case_sensitive_check.setChecked(True)
        options_row.addWidget(self.case_sensitive_check)

        self.regex_check = QCheckBox("Regular expression")
        options_row.addWidget(self.regex_check)
        options_row.addStretch()
        grid.addLayout(options_row, 3, 1)

        main_layout.addLayout(grid)
        main_layout.addSpacing(10)

        self.preview_label = QLabel()
        self.preview_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: {Typography.SMALL}px;"
        )
        main_layout.addWidget(self.preview_label)
        main_layout.addSpacing(8)

        footer = DialogFooter(dialog=self, margin=(0, 4, 0, 0))
        footer.accept_button.setText("Rename")
        main_layout.addWidget(footer)
        return None

    def _connect_signals(self):
        self.find_input.textChanged.connect(self._update_result)
        self.replace_input.textChanged.connect(self._update_result)
        self.case_sensitive_check.stateChanged.connect(self._update_result)
        self.regex_check.stateChanged.connect(self._update_result)
        return None

    def _update_result(self):
        try:
            self.result_names = rename(
                self.names,
                self.find_input.text(),
                self.replace_input.text(),
                regex=self.regex_check.isChecked(),
                case_sensitive=self.case_sensitive_check.isChecked(),
            )
            self.error_label.hide()
        except re.error as e:
            self.error_label.setText(f"Invalid pattern: {e}")
            self.error_label.show()
            self.result_names = list(self.names)

        edited = self.find_input.text() or self.replace_input.text()
        if edited and self.error_label.isHidden():
            self.preview_label.setText(
                f"Example: {self.names[0]}  →  {self.result_names[0]}"
            )
        else:
            self.preview_label.setText("")
        return None
