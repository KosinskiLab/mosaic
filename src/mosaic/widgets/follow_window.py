"""
Keep floating panels at their anchor while the main window moves.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from collections.abc import Callable

from qtpy.QtCore import QEvent, QObject
from qtpy.QtWidgets import QWidget

__all__ = ["follow_window"]


class _WindowFollower(QObject):
    def __init__(self, panel: QWidget, place: Callable[[], None]):
        super().__init__(panel)
        self._panel = panel
        self._place = place
        panel.parentWidget().installEventFilter(self)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if self._panel.isVisible() and event.type() in (
            QEvent.Type.Move,
            QEvent.Type.Resize,
            QEvent.Type.WindowStateChange,
        ):
            self._place()
        return False


def follow_window(panel: QWidget, place: Callable[[], None]) -> None:
    """Call ``place`` while ``panel`` is shown and its window moves or resizes.

    Parameters
    ----------
    panel : QWidget
        Floating panel whose parent is the main window.
    place : callable
        Moves ``panel`` to its anchor.
    """
    _WindowFollower(panel, place)
    return None
