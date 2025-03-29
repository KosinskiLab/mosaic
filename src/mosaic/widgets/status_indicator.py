""" StatusIndicator widget for visualization of current viewer modes.

    Copyright (c) 2025 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import enum

import vtk
from qtpy.QtCore import Qt, QPoint
from qtpy.QtWidgets import QWidget, QApplication
from qtpy.QtGui import (
    QCursor,
    QColor,
    QPixmap,
    QPainter,
    QPen,
)


class ViewerModes(enum.Enum):
    VIEWING = "Viewing"
    SELECTION = "Selection"
    DRAWING = "Drawing"
    PICKING = "Picking"
    MESH_DELETE = "MeshEdit"
    MESH_ADD = "MeshAdd"
    CURVE = "Curve"


class StatusIndicator:
    """A status indicator fpr current view vtk viewer and interaction mode."""

    def __init__(self, renderer, interactor):
        self.renderer = renderer
        self.interactor = interactor

        self.visible = True
        self.update_status()

    def show(self):
        """Show the status indicator."""
        self.visible = True
        self.text_actor.VisibilityOn()
        self.interactor.GetRenderWindow().Render()

    def hide(self):
        """Hide the status indicator."""
        self.visible = False
        self.text_actor.VisibilityOff()
        self.interactor.GetRenderWindow().Render()

    def _create_actor(self, text):
        text_actor = vtk.vtkTextActor()
        text_actor.SetInput(text)

        text_actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedViewport()
        text_actor.GetPositionCoordinate().SetValue(0.99, 0.01)

        app = QApplication.instance()
        font = app.font()

        text_prop = text_actor.GetTextProperty()
        text_prop.SetFontSize(12)
        text_prop.SetFontFamilyAsString(font.family())
        text_prop.SetColor(107 / 255, 114 / 255, 128 / 255)
        text_prop.SetBackgroundOpacity(0.0)
        text_prop.SetBold(0)
        text_prop.SetJustificationToRight()
        text_prop.SetVerticalJustificationToBottom()
        return text_actor

    def update_status(self, interaction="Viewing", status="Ready", **kwargs):
        """Update the status indicator with current mode and task status."""
        try:
            self.renderer.RemoveActor(self.text_actor)
        except Exception:
            pass

        # Create a new actor to prevent odd-line breaks from spacing
        self.text_actor = self._create_actor(f"Mode: {interaction} - {status}")
        if self.visible:
            self.renderer.AddActor(self.text_actor)
            self.interactor.GetRenderWindow().Render()


class CursorModeHandler:
    def __init__(self, widget: QWidget):
        self.widget = widget
        self._current_mode = ViewerModes.VIEWING

        self.cursor_colors = {
            ViewerModes.VIEWING: None,
            ViewerModes.SELECTION: QColor("#2196F3"),
            ViewerModes.DRAWING: QColor("#FFC107"),
            ViewerModes.PICKING: QColor("#9C27B0"),
            ViewerModes.MESH_DELETE: QColor("#FFFFFF"),
            ViewerModes.MESH_ADD: QColor("#CACACA"),
            ViewerModes.CURVE: QColor("#ABABAB"),
        }

        self.cursors = {
            k: self._create_custom_cursor(v) for k, v in self.cursor_colors.items()
        }

    def _create_custom_cursor(self, color: QColor, size: int = 16) -> QCursor:
        if color is None:
            return Qt.CursorShape.ArrowCursor

        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(color)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawEllipse(1, 1, size - 2, size - 2)

        pen.setWidth(1)
        painter.setPen(pen)
        center = size // 2
        painter.drawLine(QPoint(center - 3, center), QPoint(center + 3, center))
        painter.drawLine(QPoint(center, center - 3), QPoint(center, center + 3))
        painter.end()

        return QCursor(pixmap, size // 2, size // 2)

    def update_mode(self, mode: ViewerModes):
        self._current_mode = mode
        self.widget.setCursor(self.cursors[mode])

    @property
    def current_mode(self):
        return self._current_mode
