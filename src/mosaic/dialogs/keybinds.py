""" Defines KeybindDialog and the underlying KEYBIND_REGISTRY, which
    can be modified to change the Keybind Dialog window.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QDialog,
    QLabel,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
)

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
        ("P", "Toggle Picking Mode"),
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
        self._layout = QVBoxLayout()
        self.setLayout(self._layout)

    def create_section(self, title, keybinds):
        frame = QFrame()
        frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Sunken)

        section_layout = QVBoxLayout()
        title_label = QLabel(
            f"<span style='color: #314f78; font-weight: 600;'>{title}</span>"
        )
        section_layout.addWidget(title_label)

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
        while self._layout.count():
            child = self._layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for title, keybinds in KEYBIND_REGISTRY.items():
            self._layout.addWidget(self.create_section(title, keybinds))

        close_button = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        close_button.accepted.connect(self.accept)
        self._layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignCenter)

        super().show()
