"""
Base class for HUD panels that float over the viewport.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtCore import (
    QCoreApplication,
    QEvent,
    QObject,
    QPoint,
    QRect,
    QSize,
    Qt,
    QTimer,
)
from qtpy.QtGui import QColor, QEnterEvent, QPainter, QPaintEvent, QPen, QShowEvent
from qtpy.QtWidgets import QWidget

__all__ = ["ViewportHUD", "paint_hud_panel"]

_BG_IDLE = QColor(30, 32, 38, 160)
_BG_HOVER = QColor(36, 38, 46, 235)
_BORDER = QColor(255, 255, 255, 25)
_RADIUS = 6


def paint_hud_panel(widget: QWidget, hovered: bool) -> None:
    """Paint the translucent rounded HUD panel behind a widget's content.

    Parameters
    ----------
    widget : QWidget
        Widget whose full rect is painted.
    hovered : bool
        Use the more opaque hover background.
    """
    p = QPainter(widget)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = widget.rect().adjusted(1, 1, -1, -1)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_BG_HOVER if hovered else _BG_IDLE)
    p.drawRoundedRect(r, _RADIUS, _RADIUS)
    p.setPen(QPen(_BORDER, 0.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(r, _RADIUS, _RADIUS)
    p.end()
    return None


class ViewportHUD(QWidget):
    """Frameless tool window kept at a fixed place over the viewport.

    Top-level ARGB windows are composited reliably, unlike translucent child
    widgets over the native VTK surface, which froze X11 compositors. The HUD
    follows the viewport and hides with the main window. Subclasses place
    themselves through :meth:`anchor`.

    Parameters
    ----------
    parent : QWidget, optional
        Transient parent, the main window.
    """

    _MARGIN = 12

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)

        self._viewport_parent = None
        self._top_window = None
        self._hovered = False
        self._was_visible = False

    def attach_to_viewport(self, viewport: QWidget) -> None:
        """Follow ``viewport`` and the main window.

        Parameters
        ----------
        viewport : QWidget
            Widget the HUD is anchored to.
        """
        self._viewport_parent = viewport
        viewport.installEventFilter(self)

        self._top_window = self.parent()
        if self._top_window is not None:
            self._top_window.installEventFilter(self)
        self._on_viewport_resized()
        return None

    def anchor(self, viewport: QRect, size: QSize) -> QPoint:
        """Return the global top-left position of the HUD.

        Parameters
        ----------
        viewport : QRect
            Viewport geometry in global coordinates.
        size : QSize
            Size the HUD will take.

        Returns
        -------
        QPoint
            Global position of the HUD's top-left corner.
        """
        raise NotImplementedError

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        # Qt keeps filtering while the Python side is torn down, after its
        # attributes are already gone.
        viewport = getattr(self, "_viewport_parent", None)
        top_window = getattr(self, "_top_window", None)
        etype = event.type()
        if obj is viewport and etype == QEvent.Type.Resize:
            self._on_viewport_resized()
        elif obj is top_window:
            if etype in (
                QEvent.Type.Move,
                QEvent.Type.Resize,
                QEvent.Type.WindowStateChange,
            ):
                self._reposition()
            elif etype == QEvent.Type.Hide and self.isVisible():
                self._was_visible = True
                self.hide()
            elif etype == QEvent.Type.Show and self._was_visible:
                self._was_visible = False
                self.show()
        return super().eventFilter(obj, event)

    def _on_viewport_resized(self) -> None:
        self._reposition()
        return None

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._reposition()
        return None

    def _refresh_layout(self) -> None:
        layout = self.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
        return None

    def _reposition(self) -> None:
        if self._viewport_parent is None or not self.isVisible():
            return None
        viewport = self._viewport_parent

        # An unsized viewport maps to the wrong monitor, so try again shortly.
        if viewport.width() <= 0 or viewport.height() <= 0:
            QTimer.singleShot(50, self._reposition)
            return None

        self._refresh_layout()
        size = self.sizeHint()
        # Relax any stale minimum that would prevent shrinking back.
        self.setMinimumSize(self.minimumSizeHint())
        rect = QRect(viewport.mapToGlobal(QPoint(0, 0)), viewport.size())
        self.setGeometry(QRect(self.anchor(rect, size), size))
        return None

    def enterEvent(self, event: QEnterEvent) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)
        return None

    def leaveEvent(self, event: QEvent) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)
        return None

    def paintEvent(self, event: QPaintEvent) -> None:
        paint_hud_panel(self, self._hovered)
        return None
