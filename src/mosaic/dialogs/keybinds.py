""" Defines KeybindDialog and the underlying KEYBIND_REGISTRY, which
    can be modified to change the Keybind Dialog window.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtWidgets import (
    QVBoxLayout,
    QDialog,
    QLabel,
    QGridLayout,
    QGroupBox,
)
from ..widgets import DialogFooter
from ..stylesheets import QGroupBox_style, QPushButton_style


KEYBIND_REGISTRY = {
    "Navigation": [
        ("Z", "Set Camera View along Z-axis"),
        ("X", "Set Camera View along X-axis"),
        ("C", "Set Camera View along Y-axis"),
        ("Left Mouse", "Rotate Scene"),
        ("Shift+Left Mouse", "Translate Scene"),
    ],
    "Visualization": [
        ("A", "Toggle Drawing Mode"),
        ("D", "Toggle Renderer Background Color"),
        ("H", "Toggle Visibility of Selected Clusters"),
    ],
    "Selection Operations": [
        ("M", "Merge Selected Cluster or Points"),
        ("Delete", "Remove Selected Cluster or Points"),
        ("R", "Toggle Area Selector"),
        ("E", "Toggle Picking Mode"),
        ("S", "Swap Selector to Fits"),
        ("E", "Expand Selection"),
        ("Right Mouse", "Deselect Cluster or Points"),
    ],
    "File Operations": [
        ("Ctrl+N", "New Session"),
        ("Ctrl+O", "Import Files"),
        ("Ctrl+S", "Save Session"),
        ("Ctrl+P", "Save Screenshot"),
        ("Shift+Ctrl+P", "Save Screenshot to Clipboard"),
        ("Ctrl+E", "Export Animation"),
        ("Ctrl+H", "Show Keybinds"),
    ],
}


class KeybindsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keybinds")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)

        self.setStyleSheet(QGroupBox_style + QPushButton_style)

    def create_section(self, title, keybinds):
        frame = QGroupBox(title)
        section_layout = QVBoxLayout(frame)

        grid = QGridLayout()
        for row, (key, description) in enumerate(keybinds):
            key_label = QLabel(key)
            desc_label = QLabel(description)
            grid.addWidget(key_label, row, 0)
            grid.addWidget(desc_label, row, 1)

        section_layout.addLayout(grid)
        frame.setLayout(section_layout)
        return frame

    def show(self):
        while self.layout.count():
            child = self.layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for title, keybinds in KEYBIND_REGISTRY.items():
            self.layout.addWidget(self.create_section(title, keybinds))

        footer = DialogFooter(dialog=self, margin=(0, 8, 0, 0))
        self.layout.addWidget(footer)

        super().show()
