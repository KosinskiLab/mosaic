"""
Drop overlay widget for drag-and-drop zone highlighting.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtCore import Qt, Signal, QTimer
from qtpy.QtGui import QPainter, QColor, QFont, QPen, QCursor
from qtpy.QtWidgets import QWidget

from ..stylesheets import Colors


class DropOverlay(QWidget):
    """Self-contained drag-and-drop overlay.

    Draws a dotted outline and centered label over its parent widget.
    Handles drag enter / leave / drop internally and emits signals so
    the host can react without implementing any drag logic itself.

    Parameters
    ----------
    label : str
        Text shown at the centre of the overlay.
    parent : QWidget
        Widget this overlay covers.
    file_filter : callable, optional
        ``path -> bool`` predicate.  Only paths that pass the filter are
        accepted.  When *None* every local-file URL is accepted.
    """

    dropped = Signal(list)
    drag_ended = Signal()

    def __init__(self, label, parent, file_filter=None):
        super().__init__(parent)
        self._label = label
        self._filter = file_filter
        self._active = False
        self._leave_timer = QTimer(self)
        self._leave_timer.setSingleShot(True)
        self._leave_timer.timeout.connect(self._on_leave_timeout)
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.hide()

    @property
    def active(self):
        return self._active

    @active.setter
    def active(self, value):
        if self._active != value:
            self._active = value
            self.update()

    def refit(self):
        """Resize to match parent and bring to front."""
        self.setGeometry(self.parentWidget().rect())
        self.raise_()

    def _matching_paths(self, event):
        if not event.mimeData().hasUrls():
            return []
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if self._filter is not None:
            paths = [p for p in paths if self._filter(p)]
        return paths

    def _cursor_left_window(self):
        window = self.window()
        if window is None:
            return True
        return not window.rect().contains(window.mapFromGlobal(QCursor.pos()))

    def dragEnterEvent(self, event):
        self._leave_timer.stop()
        if self._matching_paths(event):
            event.acceptProposedAction()
            self.active = True
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.active = False
        self._leave_timer.start(80)
        super().dragLeaveEvent(event)

    def _on_leave_timeout(self):
        if self._cursor_left_window():
            self.drag_ended.emit()

    def dropEvent(self, event):
        paths = self._matching_paths(event)
        self.active = False
        if paths:
            event.acceptProposedAction()
            self.dropped.emit(paths)
        else:
            event.ignore()
        self.drag_ended.emit()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        if self._active:
            color = QColor(Colors.PRIMARY)
        else:
            color = QColor(Colors.BORDER_HOVER)

        pen = QPen(color, 1.0, Qt.PenStyle.CustomDashLine)
        pen.setDashPattern([3, 3])
        painter.setPen(pen)
        painter.drawRect(self.rect().adjusted(2, 2, -3, -3))

        font = QFont()
        font.setPointSize(10)
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._label)
        painter.end()
