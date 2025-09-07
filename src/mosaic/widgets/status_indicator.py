"""
StatusIndicator widget for visualization of current viewer modes.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import enum

from vtk import vtkTextActor
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QWidget, QApplication

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
        self.update_status()

    def show(self, render: bool = True):
        """Show the status indicator."""
        self.visible = True
        self.renderer.AddActor(self.text_actor)
        if render:
            return self.interactor.GetRenderWindow().Render()

    def hide(self, render: bool = True):
        """Hide the status indicator."""
        self.visible = False
        try:
            self.renderer.RemoveActor(self.text_actor)
        except Exception:
            pass
        if render:
            return self.interactor.GetRenderWindow().Render()

    def _create_actor(self, text):
        text_actor = vtkTextActor()
        text_actor.SetInput(text)

        text_actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedViewport()
        text_actor.GetPositionCoordinate().SetValue(0.99, 0.01)

        app = QApplication.instance()
        font = app.font()

        text_prop = text_actor.GetTextProperty()
        text_prop.SetFontSize(14)
        text_prop.SetFontFamilyAsString(font.family())
        text_prop.SetColor(107 / 255, 114 / 255, 128 / 255)
        text_prop.SetBackgroundOpacity(0.0)
        text_prop.SetBold(0)
        text_prop.SetJustificationToRight()
        text_prop.SetVerticalJustificationToBottom()
        return text_actor

    def update_status(self, interaction="Viewing", status="Ready", **kwargs):
        """Update the status indicator with current mode and task status."""
        self.hide(render=False)

        # Create a new actor to prevent odd-line breaks from spacing
        self.text_actor = self._create_actor(f"Mode: {interaction} - {status}")
        return self.show(render=True)


class CursorModeHandler:
    def __init__(self, widget: QWidget):
        self.widget = widget
        self._current_mode = ViewerModes.VIEWING

        # Custom cursors did not work well with macOS
        self.cursors = {
            ViewerModes.VIEWING: Qt.CursorShape.ArrowCursor,
            ViewerModes.SELECTION: Qt.CursorShape.CrossCursor,
            ViewerModes.DRAWING: Qt.CursorShape.PointingHandCursor,
            ViewerModes.PICKING: Qt.CursorShape.WhatsThisCursor,
            ViewerModes.MESH_DELETE: Qt.CursorShape.ForbiddenCursor,
            ViewerModes.MESH_ADD: Qt.CursorShape.PointingHandCursor,
            ViewerModes.CURVE: Qt.CursorShape.CrossCursor,
        }

    def update_mode(self, mode: ViewerModes):
        self._current_mode = mode
        self.widget.setCursor(self.cursors[mode])

    @property
    def current_mode(self):
        return self._current_mode
