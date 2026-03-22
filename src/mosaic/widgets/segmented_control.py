"""
Segmented button control — mutually exclusive toggle group.

Copyright (c) 2026 European Molecular Biology Laboratory

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

        n = len(options)
        for i, text in enumerate(options):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setChecked(i == default)
            rl = "4px" if i == 0 else "0px"
            rr = "4px" if i == n - 1 else "0px"
            ml = "0px" if i == 0 else "-1px"
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    border: 1px solid {Colors.BORDER_DARK};
                    border-radius: 0px;
                    border-top-left-radius: {rl};
                    border-bottom-left-radius: {rl};
                    border-top-right-radius: {rr};
                    border-bottom-right-radius: {rr};
                    padding: 6px 12px;
                    font-size: 12px;
                    color: {Colors.TEXT_SECONDARY};
                    background: transparent;
                    margin-left: {ml};
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
            btn.clicked.connect(lambda _, idx=i: self._select(idx))
            layout.addWidget(btn)
            self._buttons.append(btn)

    def _select(self, index):
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == index)
        self._selected = index
        self.selectionChanged.emit(self._buttons[index].text())

    def currentText(self):
        return self._buttons[self._selected].text()

    def currentIndex(self):
        return self._selected
