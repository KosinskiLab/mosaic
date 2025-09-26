"""
StatusIndicator widget for visualization of current viewer modes.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import enum

from qtpy.QtCore import Qt, QTimer
from qtpy.QtWidgets import QWidget, QLabel


class ViewerModes(enum.Enum):
    VIEWING = "Viewing"
    SELECTION = "Selection"
    DRAWING = "Drawing"
    PICKING = "Picking"
    MESH_DELETE = "MeshEdit"
    MESH_ADD = "MeshAdd"
    CURVE = "Curve"


class TextSpinnerLabel(QLabel):
    """Text-based spinner using Unicode characters."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

        self.current_frame = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.next_frame)

        self.setStyleSheet(
            """
            QLabel {
                color: #d97706;
                font-weight: bold;
            }
        """
        )

    def start(self):
        self.timer.start(60)

    def stop(self):
        self.timer.stop()
        self.setText("✓")

    def next_frame(self):
        self.setText(self.frames[self.current_frame])
        self.current_frame = (self.current_frame + 1) % len(self.frames)


class StatusIndicator:
    """Status indicator using QMainWindownWindow status bar."""

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
        self.current_target = "Clusters"

        self._setup_status_bar()
        self.update_status()

    def _setup_status_bar(self):
        """Set up the status bar with minimal styling."""
        status_bar = self.main_window.statusBar()
        status_bar.setStyleSheet(
            """
            QStatusBar {
                border-top: 1px solid #6b7280;
                color: #374151;
            }
            QStatusBar::item {
                border: none;
            }
        """
        )

        self.mode_label = QLabel("Viewing")
        self.mode_label.setMinimumWidth(50)

        self.target_label = QLabel("Clusters")
        self.target_label.setMinimumWidth(50)

        self.spinner = TextSpinnerLabel()
        self.spinner.setFixedWidth(10)
        self.task_label = QLabel("Idle")
        self.task_label.setMinimumWidth(50)

        separator1 = QLabel("•")
        separator1.setStyleSheet("QLabel { color: #9ca3af; padding: 0 10px; }")
        separator2 = QLabel("•")
        separator2.setStyleSheet("QLabel { color: #9ca3af; padding: 0 10px; }")

        status_bar.addPermanentWidget(self.mode_label)
        status_bar.addPermanentWidget(separator1)
        status_bar.addPermanentWidget(self.target_label)
        status_bar.addPermanentWidget(separator2)
        status_bar.addPermanentWidget(self.spinner)
        status_bar.addPermanentWidget(self.task_label)

        self.spinner.stop()

    def update_status(
        self,
        interaction="Viewing",
        target=None,
        busy: bool = False,
        task: str = None,
        **kwargs,
    ):
        """
        Update the status indicator with current mode, target, and task status.

        Parameters
        ----------
        interaction: str
            Current interaction mode
        target: str, optional
            Current interaction target
        status: bool
            Current task status
        task: str
            Name of most recent task
        """
        if not self.visible:
            return

        self.mode_label.setText(f"Mode: {interaction}")
        if target is not None:
            self.current_target = target
            self.target_label.setText(target)

        self._update_task_styling(busy)
        if task is not None:
            self.main_window.statusBar().showMessage(task, 3000)

    def _update_task_styling(self, busy: bool = False):
        """Update task status - spinner handles the visual indication."""
        self.task_label.setText("Busy" if busy else "Idle")

        if not busy:
            return self.spinner.stop()
        return self.spinner.start()

    def show(self, *args, **kwargs):
        """Show the status indicator."""
        self.visible = True
        self.main_window.statusBar().show()

    def hide(self, *args, **kwargs):
        """Hide the status indicator."""
        self.visible = False
        self.main_window.statusBar().hide()


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
