"""
Empty-state panel shown in place of the VTK viewport when no data is loaded.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import sys
from typing import Callable, Iterable, Optional, Tuple

from qtpy.QtCore import Qt, QEvent, Signal
from qtpy.QtGui import QPainter
from qtpy.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QStyle,
    QStyleOption,
    QVBoxLayout,
    QWidget,
)

from ..stylesheets import Colors, Typography

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
    """Centered empty-state panel shown in place of the VTK viewport.

    Designed to be used as a page in a :class:`QStackedLayout`
    alongside the VTK widget: the placeholder *replaces* the VTK
    widget when no data is loaded rather than being drawn on top of
    it.  This avoids the compositing problems that occur when
    overlaying Qt widgets on a native GL surface.

    Parameters
    ----------
    vtk_widget : QVTKRenderWindowInteractor
        The VTK widget the placeholder is paired with.  Unused
        structurally but kept in the constructor to preserve the
        existing call sites.
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
        super().__init__(parent)
        self.vtk_widget = vtk_widget
        self._applying_theme = False

        self._title_label = QLabel(title, self)
        self._title_label.setObjectName("placeholderTitle")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._subtitle_label = QLabel(subtitle, self)
        self._subtitle_label.setObjectName("placeholderSubtitle")
        self._subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._tick = _TickMark(self)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addStretch(1)

        inner = QVBoxLayout()
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(0)
        inner.addWidget(self._title_label, alignment=Qt.AlignmentFlag.AlignCenter)
        inner.addSpacing(6)
        inner.addWidget(self._subtitle_label, alignment=Qt.AlignmentFlag.AlignCenter)
        inner.addSpacing(12)
        inner.addWidget(self._tick, alignment=Qt.AlignmentFlag.AlignCenter)
        inner.addSpacing(20)

        pills_row = QHBoxLayout()
        pills_row.setContentsMargins(0, 0, 0, 0)
        pills_row.setSpacing(6)
        pills_row.addStretch(1)
        for shortcut, label, callback in actions:
            pill = _ActionPill(shortcut, label, self)
            pill.clicked.connect(callback)
            pills_row.addWidget(pill)
        pills_row.addStretch(1)
        inner.addLayout(pills_row)

        outer.addLayout(inner)
        outer.addStretch(1)

        self._apply_theme()

    def changeEvent(self, event):
        if event.type() == QEvent.Type.PaletteChange and not self._applying_theme:
            self._apply_theme()
        super().changeEvent(event)

    def set_empty(self, is_empty: bool):
        """Show the placeholder when *is_empty* is true, hide otherwise."""
        self.setVisible(is_empty)

    def paintEvent(self, event):
        # Required for QWidget subclasses so stylesheet backgrounds paint.
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, p, self)

    def _apply_theme(self):
        self._applying_theme = True
        mono = "SF Mono, Menlo, Consolas, monospace"
        self.setStyleSheet(
            f"""
            ViewportPlaceholder {{
                background: {Colors.SURFACE};
            }}
            QLabel#placeholderTitle {{
                color: {Colors.TEXT_MUTED};
                font-size: {Typography.DISPLAY}px;
                font-weight: 400;
                letter-spacing: 0.3px;
                background: transparent;
            }}
            QLabel#placeholderSubtitle {{
                color: {Colors.TEXT_MUTED};
                font-size: {Typography.LABEL}px;
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
                font-size: {Typography.SMALL}px;
                background: transparent;
            }}
            QLabel#pillLabel {{
                color: {Colors.TEXT_MUTED};
                font-size: {Typography.LABEL}px;
                background: transparent;
            }}
            """
        )
        self._applying_theme = False


def default_actions(window) -> Tuple[ActionSpec, ...]:
    """Standard pill set bound to :class:`mosaic.gui.App` methods."""
    mod = _modifier_glyph()
    return (
        (f"{mod}O", "Open file", window.open_files),
        (f"{mod}N", "Load session", window.load_session),
    )
