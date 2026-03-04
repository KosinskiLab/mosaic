"""
Batch rename dialog for renaming multiple geometry items at once.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import List

from qtpy.QtCore import Qt
from qtpy.QtGui import QColor
from qtpy.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QGroupBox,
    QGridLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QHeaderView,
)

from ..stylesheets import (
    QGroupBox_style,
    QPushButton_style,
    QLineEdit_style,
    QTable_style,
    Colors,
)
from ..widgets import DialogFooter


class BatchRenameDialog(QDialog):
    """Dialog for batch renaming selected geometry items using a pattern template.

    Supports the following tokens in the pattern string:

    - ``{name}`` — original item name
    - ``{i}`` — sequential index starting at 1

    Parameters
    ----------
    names : List[str]
        Current names of items in tree order.
    parent : QWidget, optional
        Parent widget.
    """

    def __init__(self, names: List[str], parent=None):
        super().__init__(parent)
        self.names = names
        self.result_names = list(names)

        self.setWindowTitle("Batch Rename")
        self.setMinimumWidth(480)

        self.setup_ui()
        self.connect_signals()
        self._update_preview()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 10)
        main_layout.setSpacing(16)

        pattern_group = QGroupBox("Pattern")
        pattern_grid = QGridLayout(pattern_group)
        pattern_grid.setSpacing(10)

        pattern_label = QLabel("Template:")
        self.pattern_input = QLineEdit()
        self.pattern_input.setPlaceholderText("e.g. Mitochondrion {i}")
        self.pattern_input.setText("{name}")
        self.pattern_input.setStyleSheet(QLineEdit_style)
        self.pattern_input.selectAll()
        pattern_grid.addWidget(pattern_label, 0, 0)
        pattern_grid.addWidget(self.pattern_input, 0, 1)

        token_help = QLabel("{i} = sequential number, {name} = original name")
        token_help.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;")
        pattern_grid.addWidget(token_help, 1, 1)

        main_layout.addWidget(pattern_group)

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
        self.preview_tree.setStyleSheet(
            QTable_style.replace("QTableWidget", "QTreeWidget")
        )
        self.preview_tree.setMinimumHeight(180)
        preview_layout.addWidget(self.preview_tree)

        main_layout.addWidget(preview_group)

        footer = DialogFooter(dialog=self, margin=(0, 4, 0, 0))
        footer.accept_button.setText("Rename")
        main_layout.addWidget(footer)

        self.setStyleSheet(QGroupBox_style + QPushButton_style)

    def connect_signals(self):
        self.pattern_input.textChanged.connect(self._update_preview)

    def _update_preview(self):
        pattern = self.pattern_input.text()

        self.result_names = []
        self.preview_tree.clear()

        muted = QColor(Colors.TEXT_SECONDARY)
        for idx, name in enumerate(self.names):
            new_name = pattern.replace("{i}", str(idx + 1)).replace("{name}", name)
            self.result_names.append(new_name)

            item = QTreeWidgetItem([name, new_name])
            item.setForeground(0, muted)
            self.preview_tree.addTopLevelItem(item)
