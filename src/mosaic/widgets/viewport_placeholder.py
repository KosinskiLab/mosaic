"""
Empty-state overlay shown over the VTK viewport when no data is loaded.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import sys
from typing import Callable, Iterable, Optional, Tuple

from qtpy.QtCore import Qt, QEvent, Signal
from qtpy.QtGui import QFont, QPainter
from qtpy.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..stylesheets import Colors

__all__ = ["ViewportPlaceholder"]


ActionSpec = Tuple[Optional[str], str, Callable[[], None]]


def _modifier_glyph() -> str:
    return "\u2318+" if sys.platform == "darwin" else "Ctrl+"


class _ActionPill(QWidget):
    """Ghost-style clickable shortcut hint."""

    clicked = Signal()

    def __init__(self, shortcut: Optional[str], label: str, parent=None):
        super().__init__(parent)
        self.setObjectName("actionPill")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(8)

        if shortcut:
            kbd = QLabel(shortcut, self)
            kbd.setObjectName("pillShortcut")
            kbd.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row.addWidget(kbd)

        text = QLabel(label, self)
        text.setObjectName("pillLabel")
        text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(text)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.pos()
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class _TickMark(QFrame):
    """Decorative horizontal line for vertical rhythm."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tickMark")
        self.setFixedSize(40, 1)


class ViewportPlaceholder(QWidget):
    """Centered empty-state text overlaying the VTK viewport.

    Parameters
    ----------
    vtk_widget : QVTKRenderWindowInteractor
        The VTK widget this overlay is drawn on top of.
    actions : iterable of (shortcut, label, callback)
        Each tuple becomes one clickable ghost pill.
    title : str, optional
        Headline text.
    subtitle : str, optional
        Muted helper line shown below the title.
    """

    def __init__(
        self,
        vtk_widget,
        actions: Iterable[ActionSpec],
        title: str = "Drop a file to begin",
        subtitle: str = "or pick a starting point below",
        parent=None,
    ):
        super().__init__(parent or vtk_widget)
        self.vtk_widget = vtk_widget
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._title_label = QLabel(title, self)
        self._title_label.setObjectName("placeholderTitle")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._subtitle_label = QLabel(subtitle, self)
        self._subtitle_label.setObjectName("placeholderSubtitle")
        self._subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._tick = _TickMark(self)

        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self._title_label, alignment=Qt.AlignmentFlag.AlignCenter)
        col.addSpacing(6)
        col.addWidget(self._subtitle_label, alignment=Qt.AlignmentFlag.AlignCenter)
        col.addSpacing(12)
        col.addWidget(self._tick, alignment=Qt.AlignmentFlag.AlignCenter)
        col.addSpacing(20)

        pills_row = QHBoxLayout()
        pills_row.setContentsMargins(0, 0, 0, 0)
        pills_row.setSpacing(6)
        for shortcut, label, callback in actions:
            pill = _ActionPill(shortcut, label, self)
            pill.clicked.connect(callback)
            pills_row.addWidget(pill)
        col.addLayout(pills_row)

        vtk_widget.installEventFilter(self)
        self._apply_theme()
        self._reposition()
        self.hide()

    def eventFilter(self, obj, event):
        if obj is self.vtk_widget and event.type() == QEvent.Type.Resize:
            self._reposition()
        return super().eventFilter(obj, event)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.PaletteChange:
            self._apply_theme()
        super().changeEvent(event)

    def set_empty(self, is_empty: bool):
        """Show the placeholder when *is_empty* is true, hide otherwise."""
        self.setVisible(is_empty)
        if is_empty:
            self.raise_()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.end()

    def _reposition(self):
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        x = (parent.width() - self.width()) // 2
        y = (parent.height() - self.height()) // 2
        self.move(x, y)

    def _apply_theme(self):
        mono = "SF Mono, Menlo, Consolas, monospace"
        self.setStyleSheet(
            f"""
            QLabel#placeholderTitle {{
                color: {Colors.TEXT_MUTED};
                font-size: 22px;
                font-weight: 400;
                letter-spacing: 0.3px;
                background: transparent;
            }}
            QLabel#placeholderSubtitle {{
                color: {Colors.TEXT_MUTED};
                font-size: 12px;
                background: transparent;
            }}
            QFrame#tickMark {{
                background: {Colors.BORDER_DARK};
                border: none;
            }}
            QWidget#actionPill {{
                background: transparent;
                border: none;
                border-radius: 6px;
            }}
            QWidget#actionPill:hover {{
                background: {Colors.BG_HOVER};
            }}
            QLabel#pillShortcut {{
                color: {Colors.TEXT_MUTED};
                font-family: {mono};
                font-size: 11px;
                background: transparent;
            }}
            QLabel#pillLabel {{
                color: {Colors.TEXT_MUTED};
                font-size: 12px;
                background: transparent;
            }}
            """
        )


def default_actions(window) -> Tuple[ActionSpec, ...]:
    """Standard pill set bound to :class:`mosaic.gui.App` methods."""
    mod = _modifier_glyph()
    return (
        (f"{mod}O", "Open file", window.open_files),
        (f"{mod}N", "Load session", window.load_session),
    )
