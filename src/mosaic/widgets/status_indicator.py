"""
StatusIndicator widget for visualization of current viewer modes.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import enum

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QWidget, QLabel


class ViewerModes(enum.Enum):
    VIEWING = "Viewing"
    SELECTION = "Selection"
    DRAWING = "Drawing"
    PICKING = "Picking"
    MESH_DELETE = "MeshEdit"
    MESH_ADD = "MeshAdd"
    CURVE = "Curve"


class StatusIndicator:
    """A status indicator using Qt's native status bar."""

    def __init__(self, main_window):
        """
        Initialize the status indicator.

        Parameters
        ----------
        main_window: QMainWindow
            The QMainWindow instance that owns the status bar
        """
        self.main_window = main_window
        self.visible = True

        self._setup_status_bar()
        self.update_status()

    def _setup_status_bar(self):
        """Set up the status bar with permanent widgets."""
        status_bar = self.main_window.statusBar()

        status_bar.setStyleSheet(
            """
            QStatusBar {
                background-color: #f8f9fa;
                border-top: 1px solid #e5e7eb;
                color: #374151;
            }
            QStatusBar::item {
                border: none;
            }
        """
        )

        self.mode_label = QLabel("Mode: Viewing")
        self.mode_label.setMinimumWidth(100)
        self.mode_label.setStyleSheet("QLabel { color: #374151; padding: 2px;}")

        separator = QLabel("|")
        separator.setStyleSheet("QLabel { color: #374151; padding: 0 4px; }")

        self.task_label = QLabel("Ready")
        self.task_label.setMinimumWidth(60)
        self.task_label.setStyleSheet("QLabel { color: #374151; padding: 2px; }")

        status_bar.addPermanentWidget(self.mode_label)
        status_bar.addPermanentWidget(separator)
        status_bar.addPermanentWidget(self.task_label)

    def show(self, *args, **kwargs):
        """Show the status indicator (status bar is always visible)."""
        self.visible = True
        self.main_window.statusBar().show()

    def hide(self, *args, **kwargs):
        """Hide the status indicator by hiding the entire status bar."""
        self.visible = False
        self.main_window.statusBar().hide()

    def update_status(self, interaction="Viewing", status="Ready", **kwargs):
        """
        Update the status indicator with current mode and task status.

        Parameters
        ----------
        interaction: str
            Current interaction mode (e.g., "Viewing", "Drawing")
        status: str
            Current task status (e.g., "Ready", "Processing")
        **kwargs: Additional arguments (kept for API compatibility)
        """
        if not self.visible:
            return

        self.mode_label.setText(f"Mode: {interaction}")
        self.task_label.setText(status)

        if status != "Ready":
            self.main_window.statusBar().showMessage(status, 3000)
        elif hasattr(self, "_last_message"):
            self.main_window.statusBar().clearMessage()
        self._last_message = status


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
