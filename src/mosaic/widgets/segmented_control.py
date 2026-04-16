"""
Segmented button control — mutually exclusive toggle group.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtCore import Signal
from qtpy.QtWidgets import QWidget, QHBoxLayout, QPushButton

from ..stylesheets import Colors


class SegmentedControl(QWidget):
    """Inline mutually exclusive button group.

    Parameters
    ----------
    options : list of str
        Button labels.
    default : int, optional
        Initially selected index, by default 0.
    parent : QWidget, optional
        Parent widget.
    """

    selectionChanged = Signal(str)

    def __init__(self, options, default=0, parent=None):
        super().__init__(parent)
        self._buttons = []
        self._selected = default

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        last = len(options) - 1
        for i, text in enumerate(options):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setChecked(i == default)
            btn.clicked.connect(lambda _, idx=i: self._select(idx))
            if i == 0:
                position = "first" if last > 0 else "only"
            elif i == last:
                position = "last"
            else:
                position = "middle"
            btn.setProperty("position", position)
            layout.addWidget(btn)
            self._buttons.append(btn)

        self._on_theme_changed()

    def _select(self, index):
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == index)
        self._selected = index
        self.selectionChanged.emit(self._buttons[index].text())

    def currentText(self):
        return self._buttons[self._selected].text()

    def _on_theme_changed(self):
        # Buttons share a single outer border: each carries top/bottom/left, and
        # only the trailing button adds the right edge. Corners are rounded only
        # on the outermost ends so the control reads as one continuous surface.
        border = f"1px solid {Colors.BORDER_DARK}"
        self.setStyleSheet(
            f"""
            QPushButton {{
                border-top: {border};
                border-bottom: {border};
                border-left: {border};
                border-right: none;
                border-radius: 0;
                padding: 6px 12px;
                color: {Colors.TEXT_SECONDARY};
                background: transparent;
            }}
            QPushButton[position="only"] {{
                border-right: {border};
                border-radius: 4px;
            }}
            QPushButton[position="first"] {{
                border-top-left-radius: 4px;
                border-bottom-left-radius: 4px;
            }}
            QPushButton[position="last"] {{
                border-right: {border};
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
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

    def currentIndex(self):
        return self._selected
