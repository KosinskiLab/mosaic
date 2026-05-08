"""
Trailing tab-bar widget announcing an available release.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import QPushButton

from ..stylesheets import Colors, Typography


class UpdatePill(QPushButton):
    """Hidden until ``show_update`` is called; appears statically in accent.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget.
    """

    update_clicked = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__("Update Mosaic", parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(26)
        self.setVisible(False)
        self._latest = ""
        self._notes = ""
        self.clicked.connect(self._emit_clicked)
        self._on_theme_changed()

    def show_update(self, latest: str, notes: str = "") -> None:
        """Reveal the pill, recording version and notes for the click handler."""
        self._latest = latest
        self._notes = notes
        self.setVisible(True)

    def _emit_clicked(self) -> None:
        if self._latest:
            self.update_clicked.emit(self._latest, self._notes)

    def _on_theme_changed(self) -> None:
        self.setStyleSheet(
            f"""
            QPushButton {{
                background: {Colors.alpha("PRIMARY", 0.08)};
                color: {Colors.PRIMARY};
                border: 1px solid transparent;
                border-radius: 6px;
                padding: 3px 10px;
                font-size: {Typography.BODY}px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                border-color: {Colors.PRIMARY};
            }}
            QPushButton:pressed {{
                background: {Colors.alpha("PRIMARY", 0.12)};
            }}
            QPushButton:focus {{ outline: none; }}
            """
        )
