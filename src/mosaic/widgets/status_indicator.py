"""
StatusIndicator widget for visualization of current viewer modes.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import enum
from collections import Counter

from qtpy.QtCore import Qt, QTimer, Signal
from qtpy.QtWidgets import (
    QWidget,
    QLabel,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QPushButton,
    QFrame,
    QGroupBox,
    QTextEdit,
    QProgressBar,
    QMessageBox,
)
from qtpy.QtGui import QFont, QTextCursor
import qtawesome as qta

from ..stylesheets import Colors, QPushButton_style, QScrollArea_style
from ..parallel import BackgroundTaskManager


class ViewerModes(enum.Enum):
    VIEWING = "Viewing"
    SELECTION = "Selection"
    DRAWING = "Drawing"
    PICKING = "Picking"
    MESH_DELETE = "MeshEdit"
    MESH_ADD = "MeshAdd"
    CURVE = "Curve"


class TextSpinnerLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.current_frame = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.next_frame)
        self.setStyleSheet(
            f"QLabel {{ color: {Colors.WARNING_DARK}; font-weight: bold; }}"
        )

    def start(self):
        self.timer.start(60)

    def stop(self):
        self.timer.stop()
        self.setText("✓")

    def next_frame(self):
        self.setText(self.frames[self.current_frame])
        self.current_frame = (self.current_frame + 1) % len(self.frames)


class TaskCard(QFrame):
    cancel_requested = Signal(str)  # task_id

    STATUS_COLORS = {
        "running": (Colors.WARNING, Colors.WARNING_BG, Colors.WARNING_TEXT),
        "queued": (Colors.NEUTRAL, Colors.NEUTRAL_BG, Colors.NEUTRAL_TEXT),
        "completed": (Colors.SUCCESS, Colors.SUCCESS_BG, Colors.SUCCESS_TEXT),
        "failed": (Colors.ERROR, Colors.ERROR_BG, Colors.ERROR_TEXT),
    }

    def __init__(self, task_data, compact=False, parent=None):
        super().__init__(parent)
        self.task_data = task_data
        self.task_id = task_data.get("id", "unknown")
        self.status = task_data.get("status", "running")
        self.compact = compact
        self.expanded = False
        self._stdout_buffer = []
        self._stderr_buffer = []

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._setup_ui()
        self._update_styling()

    def _setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(8, 6, 8, 6)
        self.main_layout.setSpacing(4)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self.status_dot = QLabel("●")
        self.status_dot.setFixedWidth(10)
        header_layout.addWidget(self.status_dot)

        self.name_label = QLabel(self.task_data.get("name", "Unnamed Task"))
        self.name_label.setFont(self._font(9))
        header_layout.addWidget(self.name_label)

        if self.compact:
            header_layout.addStretch()
        else:
            self.name_label.setFixedWidth(200)
            self.progress_bar = QProgressBar()
            self.progress_bar.setMaximumHeight(4)
            self.progress_bar.setTextVisible(False)
            header_layout.addWidget(self.progress_bar, 1)

            self.progress_text = QLabel()
            self.progress_text.setFont(self._font(7))
            self.progress_text.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
            self.progress_text.setMinimumWidth(35)
            header_layout.addWidget(self.progress_text)

            self.message_label = QLabel()
            self.message_label.setFont(self._font(8, italic=True))
            self.message_label.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
            self.message_label.setFixedWidth(70)
            header_layout.addWidget(self.message_label)

        self.status_badge = QLabel(self.status.upper())
        self.status_badge.setFont(self._font(7, bold=True, spacing=0.5))
        header_layout.addWidget(self.status_badge)

        if not self.compact:
            self.cancel_btn = QPushButton()
            self.cancel_btn.setIcon(qta.icon("ph.x", color=Colors.ERROR))
            self.cancel_btn.setToolTip("Cancel task")
            self.cancel_btn.setFixedSize(18, 18)
            self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.cancel_btn.clicked.connect(self._cancel_task)
            self.cancel_btn.setStyleSheet(
                f"""
                QPushButton {{
                    border: none;
                    border-radius: 3px;
                    background: transparent;
                }}
                QPushButton:hover {{ background: {Colors.ERROR_BG}; }}
            """
            )
            header_layout.addWidget(self.cancel_btn)

        self.main_layout.addLayout(header_layout)

        self.output_view = QTextEdit()
        self.output_view.setReadOnly(True)
        self.output_view.setMinimumHeight(250)
        self.output_view.setVisible(False)
        self.output_view.setStyleSheet(
            f"""
            QTextEdit {{
                background: transparent; font-size: 9pt;
                border: 1px solid {Colors.BORDER_DARK};
                border-radius: 3px;
                padding: 4px;
            }}
        """
        )
        self.main_layout.addWidget(self.output_view)

    @staticmethod
    def _font(size, bold=False, italic=False, spacing=None):
        font = QFont()
        font.setPointSize(size)
        if bold:
            font.setBold(True)
        if italic:
            font.setItalic(True)
        if spacing is not None:
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
        return font

    def _update_styling(self):
        color, bg, text = self.STATUS_COLORS.get(
            self.status, self.STATUS_COLORS["queued"]
        )
        border_color = Colors.ICON_MUTED if self.status == "queued" else color

        self.status_dot.setStyleSheet(f"color: {color}; font-size: 12px;")
        self.status_badge.setStyleSheet(
            f"background: {bg}; color: {text}; padding: 2px 6px; border-radius: 3px;"
        )
        self.setStyleSheet(
            f"""
            TaskCard {{
                border: 1px solid {Colors.NEUTRAL_BG};
                border-left: 2px solid {border_color};
                border-radius: 4px; padding: 2px;
            }}
            TaskCard:hover {{ background-color: rgba(107, 114, 128, 0.05); }}
        """
        )

        if self.compact:
            return

        is_active = self.status in ("running", "queued")
        bar_color = Colors.WARNING if is_active else Colors.ICON_MUTED
        self.progress_bar.setStyleSheet(
            f"""
            QProgressBar {{
                border: none;
                border-radius: 2px;
                background: {Colors.BORDER_DARK};
            }}
            QProgressBar::chunk {{ border-radius: 2px; background: {bar_color}; }}
        """
        )
        self.cancel_btn.setVisible(is_active)

        if self.status == "completed":
            self.progress_bar.setValue(100)
        if not is_active:
            self.message_label.setText("")
            self.progress_text.setText("")

    def update_task_data(self, task_data):
        self.task_data = task_data
        self.status = task_data.get("status", "running")
        self.name_label.setText(task_data.get("name", "Unnamed Task"))
        self.status_badge.setText(self.status.upper())
        self._update_styling()
        if self.expanded:
            self._update_output()

    def update_progress(self, progress: float, current: int = 0, total: int = 0):
        """Update the progress bar and text."""
        if self.compact or self.status != "running":
            return

        self.progress_bar.setValue(int(progress * 100))

        if total > 0:
            self.progress_text.setText(f"{current} / {total}")
        elif progress > 0:
            self.progress_text.setText(f"{int(progress * 100)}%")

    def update_message(self, message: str):
        """Update the status message."""
        if self.compact or self.status != "running":
            return
        self.message_label.setText(message)

    def append_output(self, stream_type: str, text: str):
        """Append output text from worker."""
        if stream_type == "stdout":
            self._stdout_buffer.append(text)
        else:
            self._stderr_buffer.append(text)

        if self.expanded:
            self._append_to_view(stream_type, text)

    def _append_to_view(self, stream_type: str, text: str):
        cursor = self.output_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output_view.setTextCursor(cursor)
        self.output_view.insertPlainText(text)
        scrollbar = self.output_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.compact or not self.cancel_btn.geometry().contains(event.pos()):
                self._toggle_expanded()
        super().mousePressEvent(event)

    def _toggle_expanded(self):
        """Toggle the output view visibility."""
        self.expanded = not self.expanded
        self.output_view.setVisible(self.expanded)

        if self.expanded:
            self._update_output()

    def _cancel_task(self):
        """Request cancellation of this task."""
        self.cancel_requested.emit(self.task_id)

    def mark_cancelled(self):
        """Update UI to show task was cancelled."""
        self.task_data["status"] = "failed"
        self.status = "failed"
        self.status_badge.setText("CANCELLED")
        self._update_styling()

    def _update_output(self):
        output = ""
        stdout = "".join(self._stdout_buffer) or self.task_data.get("stdout", "")
        if stdout:
            output += f"--- STDOUT ---\n\n{stdout}\n"

        stderr = "".join(self._stderr_buffer) or self.task_data.get("stderr", "")
        if stderr:
            output += f"--- STDERR ---\n\n{stderr}"

        if not output.strip():
            output = "No output available"
        self.output_view.setPlainText(output)


class TaskMonitorDialog(QDialog):
    cancel_task_requested = Signal(str)  # task_id
    clear_finished_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Task Monitor")
        self.setMinimumSize(700, 500)
        self.resize(800, 600)

        self.task_cards = {}
        self._setup_ui()

    def on_task_progress(
        self, task_id: str, task_name: str, progress: float, current: int, total: int
    ):
        """Handle progress updates from workers."""
        card = self.task_cards.get(task_id)
        if card is not None:
            card.update_progress(progress, current, total)

    def on_task_message(self, task_id: str, task_name: str, message: str):
        """Handle status message updates from workers."""
        card = self.task_cards.get(task_id)
        if card is not None:
            card.update_message(message)

    def on_task_output(self, task_id: str, stream_type: str, text: str):
        """Handle stdout/stderr output from workers."""
        card = self.task_cards.get(task_id)
        if card is not None:
            card.append_output(stream_type, text)

    def on_task_started(self, task_id: str, task_name: str):
        """Handle task started - create a new card."""
        if task_id in self.task_cards:
            return

        task_data = {"id": task_id, "name": task_name, "status": "running"}
        card = TaskCard(task_data, compact=False)
        card.cancel_requested.connect(self.cancel_task_requested)
        self.task_cards[task_id] = card
        self.active_tasks_layout.insertWidget(0, card)
        self._update_counts()

    def on_task_completed(self, task_id: str, task_name: str, result: object):
        """Handle task completed - update card status."""
        card = self.task_cards.get(task_id)
        if card is None:
            return

        card.task_data["status"] = "completed"
        card.status = "completed"
        card.status_badge.setText("COMPLETED")
        card._update_styling()
        self._move_card_to_section(task_id, self.completed_tasks_layout)

    def on_task_failed(self, task_id: str, task_name: str, error: str):
        """Handle task failed - update card status."""
        card = self.task_cards.get(task_id)
        if card is None:
            return

        card.task_data["status"] = "failed"
        card.status = "failed"
        card.status_badge.setText("FAILED")
        card._update_styling()
        self._move_card_to_section(task_id, self.failed_tasks_layout)

    def _move_card_to_section(self, task_id: str, target_layout):
        """Move a card to a different section, recreating as compact."""
        old_card = self.task_cards.get(task_id)
        if old_card is None:
            return

        # Create compact version for finished section
        task_data = old_card.task_data.copy()
        task_data["id"] = task_id
        new_card = TaskCard(task_data, compact=True)
        new_card.cancel_requested.connect(self.cancel_task_requested)

        # Copy output buffers
        new_card._stdout_buffer = old_card._stdout_buffer
        new_card._stderr_buffer = old_card._stderr_buffer

        old_card.deleteLater()
        self.task_cards[task_id] = new_card
        target_layout.insertWidget(0, new_card)
        self._update_counts()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(12, 12, 12, 12)

        self.active_section, self.active_tasks_layout = self._create_section("Active")
        main_layout.addWidget(self.active_section, 1)

        finished_layout = QHBoxLayout()
        finished_layout.setSpacing(12)

        self.completed_section, self.completed_tasks_layout = self._create_section(
            "Completed"
        )
        finished_layout.addWidget(self.completed_section)

        self.failed_section, self.failed_tasks_layout = self._create_section("Failed")
        finished_layout.addWidget(self.failed_section)

        main_layout.addLayout(finished_layout, 1)

        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(8)

        clear_btn = QPushButton("Clear Finished")
        clear_btn.setIcon(qta.icon("ph.trash", color=Colors.TEXT_MUTED))
        clear_btn.clicked.connect(self._clear_finished_tasks)
        footer_layout.addWidget(clear_btn)

        footer_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_btn.setDefault(True)
        footer_layout.addWidget(close_btn)

        main_layout.addLayout(footer_layout)
        self.setStyleSheet(QPushButton_style + QScrollArea_style)

    def _create_section(self, title):
        section = QGroupBox(f"{title} (0)")
        section._title_base = title  # Store for updates

        section_layout = QVBoxLayout()
        section_layout.setContentsMargins(8, 8, 8, 8)
        section_layout.setSpacing(4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(QScrollArea_style)

        task_container = QWidget()
        task_layout = QVBoxLayout(task_container)
        task_layout.setContentsMargins(0, 0, 0, 0)
        task_layout.setSpacing(4)
        task_layout.addStretch()

        scroll.setWidget(task_container)
        section_layout.addWidget(scroll)
        section.setLayout(section_layout)

        return section, task_layout

    def sync_tasks(self, task_info: dict):
        """Sync task cards with provided task info snapshot."""
        for task_id, task_data in task_info.items():
            self._update_task_card(task_id, task_data)

        # Mark tasks that disappeared (crashed) as failed
        for task_id in list(self.task_cards.keys()):
            if task_id in task_info:
                continue

            task_data = self.task_cards[task_id].task_data
            if task_data["status"] in ("running", "queued"):
                self._update_task_card(task_id, task_data | {"status": "failed"})

        self._update_counts()

    def _update_task_card(self, task_id, task_data):
        status = task_data["status"]
        card = self.task_cards.get(task_id)

        if card is not None and card.task_data["status"] == status:
            return None

        task_data = task_data.copy()
        task_data["id"] = task_id
        is_finished = status in ("completed", "failed")

        if card is None:
            card = TaskCard(task_data, compact=is_finished)
            card.cancel_requested.connect(self.cancel_task_requested)
        else:
            # If switching between active and finished, recreate the card
            if card.compact != is_finished:
                card.deleteLater()
                card = TaskCard(task_data, compact=is_finished)
                card.cancel_requested.connect(self.cancel_task_requested)
            else:
                card.update_task_data(task_data)

        if status in ("running", "queued"):
            layout = self.active_tasks_layout
        elif status == "completed":
            layout = self.completed_tasks_layout
        elif status == "failed":
            layout = self.failed_tasks_layout
        else:
            return None

        self.task_cards[task_id] = card
        return layout.insertWidget(0, card)

    def _update_counts(self):
        status_counts = Counter(c.status for c in self.task_cards.values())
        counts = {
            self.active_section: status_counts["running"] + status_counts["queued"],
            self.completed_section: status_counts["completed"],
            self.failed_section: status_counts["failed"],
        }
        for section, count in counts.items():
            section.setTitle(f"{section._title_base} ({count})")

    def _clear_finished_tasks(self):
        """Request clearing of finished tasks."""
        self.clear_finished_requested.emit()

    def remove_finished_cards(self, removed_task_ids: list):
        """Remove cards for finished tasks from UI."""
        for task_id in removed_task_ids:
            card = self.task_cards.pop(task_id, None)
            if card is not None:
                card.deleteLater()
        self._update_counts()

    def get_card(self, task_id: str):
        """Get task card by ID."""
        return self.task_cards.get(task_id)


class StatusIndicator:
    def __init__(self, main_window):
        self.main_window = main_window
        self.visible = True
        self.current_target = "Clusters"

        self.task_monitor = TaskMonitorDialog(self.main_window)
        self._setup_status_bar()
        self.update_status()

    def connect_signals(self):
        """Connect all BackgroundTaskManager signals to StatusIndicator and TaskMonitorDialog."""
        manager = BackgroundTaskManager.instance()

        # StatusIndicator signals - busy/idle status only
        manager.running_tasks.connect(self._on_running_tasks_changed)

        # Task lifecycle signals - forwarded to dialog for card management
        manager.task_started.connect(self._on_task_started)
        manager.task_completed.connect(self.task_monitor.on_task_completed)
        manager.task_failed.connect(self.task_monitor.on_task_failed)

        # Task update signals - forwarded directly to dialog
        manager.task_progress.connect(self.task_monitor.on_task_progress)
        manager.task_message.connect(self.task_monitor.on_task_message)
        manager.task_output.connect(self.task_monitor.on_task_output)

        # Dialog action signals
        self.task_monitor.cancel_task_requested.connect(self._on_cancel_task_requested)
        self.task_monitor.clear_finished_requested.connect(
            self._on_clear_finished_requested
        )

    def _on_task_started(self, task_id: str, task_name: str):
        """Handle task started signal - update status and forward to dialog."""
        self.update_status(busy=True, task=task_name)
        self.task_monitor.on_task_started(task_id, task_name)

    def _on_running_tasks_changed(self, count: int):
        """Handle running tasks count change - busy/idle status only."""
        self._update_task_styling(busy=count >= 1)

    def _on_cancel_task_requested(self, task_id: str):
        """Handle task cancellation request from dialog."""
        manager = BackgroundTaskManager.instance()
        task_info = manager.task_info.get(task_id, {})
        task_name = task_info.get("name", "Unknown")

        cancelled = manager.cancel_task(task_id)
        card = self.task_monitor.get_card(task_id)

        if cancelled and card is not None:
            card.mark_cancelled()
        elif not cancelled:
            QMessageBox.warning(
                self.task_monitor,
                "Cannot Cancel",
                f"Task '{task_name}' is already running and cannot be cancelled.",
            )

    def _on_clear_finished_requested(self):
        """Handle clear finished tasks request from dialog."""
        manager = BackgroundTaskManager.instance()
        removed = manager.clear_finished_tasks()
        self.task_monitor.remove_finished_cards(removed)

    def _setup_status_bar(self):
        status_bar = self.main_window.statusBar()
        status_bar.setStyleSheet(
            f"""
            QStatusBar {{ border-top: 1px solid {Colors.BORDER_DARK}; }}
            QStatusBar::item {{ border: none; }}
        """
        )

        def separator():
            lbl = QLabel("•")
            lbl.setStyleSheet(
                f"QLabel {{ color: {Colors.ICON_MUTED}; padding: 0 10px; }}"
            )
            return lbl

        self.mode_label = QLabel("Mode: Viewing")
        self.mode_label.setMinimumWidth(50)

        self.target_label = QLabel("Clusters")
        self.target_label.setMinimumWidth(50)

        self.spinner = TextSpinnerLabel()
        self.spinner.setFixedWidth(12)

        self.task_button = QPushButton("Idle")
        self.task_button.setIcon(qta.icon("ph.caret-up", color=Colors.ICON_MUTED))
        self.task_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.task_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.task_button.setFlat(True)
        self.task_button.setContentsMargins(0, 0, 0, 0)
        self.task_button.setStyleSheet(
            f"""
            QPushButton {{ padding: 0px; margin: 0px; border-radius: 4px; }}
            QPushButton:hover {{
                background: {Colors.BG_HOVER};
                border: 1px solid rgba(0, 0, 0, 0.08);
            }}
            QPushButton:pressed {{
                background: {Colors.BG_PRESSED};
                border: 1px solid rgba(0, 0, 0, 0.12);
            }}
            QPushButton:focus {{ outline: none; }}
        """
        )
        self.task_button.clicked.connect(self._show_task_monitor)

        status_bar.addPermanentWidget(self.mode_label)
        status_bar.addPermanentWidget(separator())
        status_bar.addPermanentWidget(self.target_label)
        status_bar.addPermanentWidget(separator())
        status_bar.addPermanentWidget(self.spinner)
        status_bar.addPermanentWidget(self.task_button)

        self.spinner.stop()

    def update_status(
        self,
        interaction=None,
        target=None,
        busy: bool = None,
        task: str = None,
        **kwargs,
    ):
        if not self.visible:
            return

        if interaction is not None:
            self.mode_label.setText(f"Mode: {interaction}")

        if target is not None:
            self.current_target = target
            self.target_label.setText(target)

        if busy is not None:
            self._update_task_styling(busy)

        if task is not None:
            self.main_window.statusBar().showMessage(task, 3000)

    def _update_task_styling(self, busy: bool = False):
        self.task_button.setText("Busy" if busy else "Idle")

        if not busy:
            return self.spinner.stop()
        return self.spinner.start()

    def _show_task_monitor(self):
        manager = BackgroundTaskManager.instance()
        self.task_monitor.sync_tasks(manager.get_task_info_snapshot())
        self.task_monitor.show()
        self.task_monitor.raise_()
        self.task_monitor.activateWindow()

    def show(self, *args, **kwargs):
        self.visible = True
        self.main_window.statusBar().show()

    def hide(self, *args, **kwargs):
        self.visible = False
        self.main_window.statusBar().hide()


class CursorModeHandler:
    def __init__(self, widget: QWidget):
        self.widget = widget
        self._current_mode = ViewerModes.VIEWING

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
