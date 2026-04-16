"""
StatusIndicator widget for visualization of current viewer modes.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import enum
from collections import Counter

from qtpy.QtCore import Qt, QTimer, Signal
from qtpy.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QPushButton,
    QFrame,
    QGroupBox,
    QTextEdit,
    QProgressBar,
    QMessageBox,
    QApplication,
)
from qtpy.QtGui import QTextCursor, QPainter, QColor
from ..stylesheets import Colors, QScrollArea_style
from ..icons import icon
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
        self.setStyleSheet(f"QLabel {{ color: {Colors.PRIMARY}; font-weight: bold; }}")

    def start(self):
        self.timer.start(60)

    def stop(self):
        self.timer.stop()
        self.clear()

    def next_frame(self):
        self.setText(self.frames[self.current_frame])
        self.current_frame = (self.current_frame + 1) % len(self.frames)


class TaskCard(QFrame):
    """Single-row task card with background-fill progress indicator."""

    cancel_requested = Signal(str)

    _ACCENT = {
        "running": Colors.WARNING,
        "queued": Colors.BORDER_DARK,
        "completed": Colors.SUCCESS,
        "failed": Colors.ERROR,
    }
    _FILL_ALPHA = {
        "running": 0.08,
        "queued": 0.0,
        "completed": 0.05,
        "failed": 0.06,
    }
    _ICONS = {
        "queued": "ph.clock",
        "completed": "ph.check",
        "failed": "ph.x-circle",
    }

    def __init__(self, task_data, parent=None):
        super().__init__(parent)
        self.task_data = task_data
        self.task_id = task_data.get("id", "unknown")
        self.status = task_data.get("status", "running")
        self.expanded = False
        self._progress = 0.0
        self._stdout_buffer = []
        self._stderr_buffer = []

        self.setFrameShape(QFrame.Shape.NoFrame)
        self._setup_ui()
        self._apply_status()

    def _setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 0, 8, 0)
        self.main_layout.setSpacing(0)

        row_widget = QWidget()
        row_widget.setFixedHeight(32)
        row = QHBoxLayout(row_widget)
        row.setSpacing(8)
        row.setContentsMargins(0, 0, 0, 0)

        self.icon_label = QLabel()
        self.icon_label.setFixedWidth(16)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.icon_label)

        self.spinner = TextSpinnerLabel()
        self.spinner.setFixedWidth(14)
        self.spinner.setVisible(False)
        row.addWidget(self.spinner)

        self.name_label = QLabel(self.task_data.get("name", "Unnamed Task"))
        row.addWidget(self.name_label, 1)

        self.message_label = QLabel()
        self.message_label.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        self.message_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
        )
        row.addWidget(self.message_label)

        self.progress_text = QLabel()
        self.progress_text.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        self.progress_text.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
        )
        row.addWidget(self.progress_text)

        self.cancel_btn = QPushButton()
        self.cancel_btn.setIcon(icon("ph.x", role="muted"))
        self.cancel_btn.setFixedSize(20, 20)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self._cancel_task)
        self.cancel_btn.setStyleSheet(
            f"""
            QPushButton {{
                border: none; border-radius: 3px; background: transparent;
            }}
            QPushButton:hover {{ background: {Colors.alpha("ERROR", 0.15)}; }}
        """
        )
        row.addWidget(self.cancel_btn)

        self.main_layout.addWidget(row_widget)

        self._output_container = QWidget()
        self._output_container.setVisible(False)
        output_layout = QHBoxLayout(self._output_container)
        output_layout.setContentsMargins(0, 4, 0, 4)
        output_layout.setSpacing(4)

        _text_style = f"""
            QTextEdit {{
                background: transparent;
                font-size: 10px;
                border: none; padding: 4px;
            }}
        """

        self._stdout_group = QGroupBox("stdout")
        stdout_layout = QVBoxLayout(self._stdout_group)
        stdout_layout.setContentsMargins(4, 4, 4, 4)
        self._stdout_view = QTextEdit()
        self._stdout_view.setReadOnly(True)
        self._stdout_view.setMaximumHeight(120)
        self._stdout_view.setStyleSheet(_text_style)
        stdout_layout.addWidget(self._stdout_view)
        output_layout.addWidget(self._stdout_group)

        self._stderr_group = QGroupBox("stderr")
        stderr_layout = QVBoxLayout(self._stderr_group)
        stderr_layout.setContentsMargins(4, 4, 4, 4)
        self._stderr_view = QTextEdit()
        self._stderr_view.setReadOnly(True)
        self._stderr_view.setMaximumHeight(120)
        self._stderr_view.setStyleSheet(_text_style)
        stderr_layout.addWidget(self._stderr_view)
        output_layout.addWidget(self._stderr_group)

        self.main_layout.addWidget(self._output_container)

    def _apply_status(self):
        accent = self._ACCENT.get(self.status, Colors.BORDER_DARK)

        # Left accent border + base styling
        self.setStyleSheet(
            f"""
            TaskCard {{
                border: none;
                border-left: 3px solid {accent};
                border-radius: 0px;
                background: transparent;
            }}
        """
        )

        # Icon vs spinner
        if self.status == "running":
            self.icon_label.setVisible(False)
            self.spinner.setVisible(True)
            self.spinner.setStyleSheet(
                f"QLabel {{ color: {accent}; font-weight: bold; }}"
            )
            self.spinner.start()
        else:
            self.spinner.setVisible(False)
            self.spinner.stop()
            self.icon_label.setVisible(True)
            icon_name = self._ICONS.get(self.status, "ph.clock")
            self.icon_label.setText("")
            status_icon = icon(icon_name, color=accent)
            self.icon_label.setPixmap(status_icon.pixmap(14, 14))

        self.cancel_btn.setVisible(self.status in ("running", "queued"))

        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Progress / message text
        if self.status == "completed":
            self._progress = 1.0
            self.progress_text.setText("")
            self.message_label.setText("")
        elif self.status == "failed":
            self._progress = 1.0
            self.progress_text.setText("")
            self.message_label.setText("")
        elif self.status == "queued":
            self._progress = 0.0
            self.progress_text.setText("")
            self.message_label.setText("")

        self.setMinimumHeight(32)
        self.update()

    def paintEvent(self, event):
        """Draw the progress fill behind the card content."""
        if self._progress > 0:
            painter = QPainter(self)
            alpha = self._FILL_ALPHA.get(self.status, 0.0)
            if alpha > 0:
                color = QColor(self._ACCENT.get(self.status, Colors.BORDER_DARK))
                color.setAlphaF(alpha)
                fill_width = int(self.width() * self._progress)
                painter.fillRect(0, 0, fill_width, self.height(), color)
            painter.end()
        super().paintEvent(event)

    def update_task_data(self, task_data):
        self.task_data = task_data
        self.status = task_data.get("status", "running")
        self.name_label.setText(task_data.get("name", "Unnamed Task"))
        self._apply_status()
        if self.expanded:
            self._update_output()

    def update_progress(self, progress: float, current: int = 0, total: int = 0):
        if self.status != "running":
            return
        self._progress = max(0.0, min(1.0, progress))
        if total > 0:
            self.progress_text.setText(f"{current}/{total}")
        elif progress > 0:
            self.progress_text.setText(f"{int(progress * 100)}%")
        self.update()

    def update_message(self, message: str):
        if self.status != "running":
            return
        self.message_label.setText(message)

    def append_output(self, stream_type: str, text: str):
        if stream_type == "stdout":
            self._stdout_buffer.append(text)
        else:
            self._stderr_buffer.append(text)
        if self.expanded:
            self._append_to_view(stream_type, text)

    def _append_to_view(self, stream_type: str, text: str):
        view = self._stdout_view if stream_type == "stdout" else self._stderr_view
        cursor = view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        view.setTextCursor(cursor)
        view.insertPlainText(text)
        scrollbar = view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.cancel_btn.geometry().contains(event.pos()):
                self._toggle_expanded()
        super().mousePressEvent(event)

    def _toggle_expanded(self):
        self.expanded = not self.expanded
        if self.expanded:
            self._update_output()
            self.setMinimumHeight(0)
        else:
            self.setMinimumHeight(32)
        self._output_container.setVisible(self.expanded)

    def _cancel_task(self):
        self.cancel_requested.emit(self.task_id)

    def mark_cancelled(self):
        self.task_data["status"] = "failed"
        self.status = "failed"
        self._apply_status()

    def _update_output(self):
        stdout = "".join(self._stdout_buffer) or self.task_data.get("stdout", "")
        stderr = "".join(self._stderr_buffer) or self.task_data.get("stderr", "")
        self._stdout_view.setPlainText(stdout)
        self._stderr_view.setPlainText(stderr)


class TaskMonitorPanel(QFrame):
    """Floating task monitor panel anchored to the status bar."""

    cancel_task_requested = Signal(str)
    clear_finished_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(450, 300)
        self.resize(500, 360)
        self.task_cards = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QWidget()
        header.setStyleSheet(f"border-bottom: 1px solid {Colors.BORDER_DARK};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 6, 10, 6)

        self._summary_label = QLabel()
        self._summary_label.setStyleSheet("border: none;")
        header_layout.addWidget(self._summary_label)
        header_layout.addStretch()

        clear_btn = QPushButton()
        clear_btn.setIcon(icon("ph.trash", role="muted"))
        clear_btn.setToolTip("Clear finished tasks")
        clear_btn.setFixedSize(Colors.WIDGET_HEIGHT, Colors.WIDGET_HEIGHT)
        clear_btn.clicked.connect(self._clear_finished_tasks)
        header_layout.addWidget(clear_btn)

        close_btn = QPushButton()
        close_btn.setIcon(icon("ph.x", role="muted"))
        close_btn.setToolTip("Close task manager")
        close_btn.setFixedSize(Colors.WIDGET_HEIGHT, Colors.WIDGET_HEIGHT)
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(close_btn)

        layout.addWidget(header)

        # Task list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(QScrollArea_style)

        self._task_container = QWidget()
        self._task_layout = QVBoxLayout(self._task_container)
        self._task_layout.setContentsMargins(8, 8, 8, 8)
        self._task_layout.setSpacing(2)
        self._task_layout.addStretch()

        scroll.setWidget(self._task_container)
        layout.addWidget(scroll, 1)

        self.setStyleSheet(
            f"""TaskMonitorPanel {{
                border: 1px solid {Colors.BORDER_DARK};
                border-bottom: none;
            }}"""
        )
        self._update_summary()

    def _insert_card(self, card):
        """Insert card at the right position: running > queued > completed > failed."""
        priority = {"running": 0, "queued": 1, "completed": 2, "failed": 3}
        card_prio = priority.get(card.status, 4)

        insert_idx = 0
        for i in range(self._task_layout.count()):
            item = self._task_layout.itemAt(i)
            if item is None or item.widget() is None:
                continue
            widget = item.widget()
            if not isinstance(widget, TaskCard):
                continue
            existing_prio = priority.get(widget.status, 4)
            if card_prio < existing_prio:
                break
            insert_idx = i + 1

        self._task_layout.insertWidget(insert_idx, card)

    def on_task_queued(self, task_id: str, task_name: str):
        if task_id in self.task_cards:
            return
        task_data = {"id": task_id, "name": task_name, "status": "queued"}
        card = TaskCard(task_data)
        card.cancel_requested.connect(self.cancel_task_requested)
        self.task_cards[task_id] = card
        self._insert_card(card)
        self._update_summary()

    def on_task_started(self, task_id: str, task_name: str):
        card = self.task_cards.get(task_id)
        if card and card.status == "running":
            return

        if card:
            # Preserve output buffers
            stdout = card._stdout_buffer
            stderr = card._stderr_buffer
            card.deleteLater()
        else:
            stdout, stderr = [], []

        task_data = {"id": task_id, "name": task_name, "status": "running"}
        card = TaskCard(task_data)
        card._stdout_buffer = stdout
        card._stderr_buffer = stderr
        card.cancel_requested.connect(self.cancel_task_requested)
        self.task_cards[task_id] = card
        self._insert_card(card)
        self._update_summary()

    def on_task_completed(self, task_id: str, task_name: str, result: object):
        card = self.task_cards.get(task_id)
        if card is None:
            return
        card.task_data["status"] = "completed"
        card.status = "completed"
        card._apply_status()
        self._update_summary()

    def on_task_failed(self, task_id: str, task_name: str, error: str):
        card = self.task_cards.get(task_id)
        if card is None:
            return
        card.task_data["status"] = "failed"
        card.status = "failed"
        card._apply_status()
        self._update_summary()

    def on_task_progress(
        self, task_id: str, task_name: str, progress: float, current: int, total: int
    ):
        card = self.task_cards.get(task_id)
        if card is not None:
            card.update_progress(progress, current, total)

    def on_task_message(self, task_id: str, task_name: str, message: str):
        card = self.task_cards.get(task_id)
        if card is not None:
            card.update_message(message)

    def on_task_output(self, task_id: str, stream_type: str, text: str):
        card = self.task_cards.get(task_id)
        if card is not None:
            card.append_output(stream_type, text)

    def _update_summary(self):
        counts = Counter(c.status for c in self.task_cards.values())
        parts = []
        if counts["running"]:
            parts.append(f"{counts['running']} running")
        if counts["queued"]:
            parts.append(f"{counts['queued']} queued")
        if counts["completed"]:
            parts.append(f"{counts['completed']} completed")
        if counts["failed"]:
            parts.append(f"{counts['failed']} failed")
        self._summary_label.setText(" · ".join(parts) if parts else "No tasks")

    def _clear_finished_tasks(self):
        self.clear_finished_requested.emit()

    def remove_finished_cards(self, removed_task_ids: list):
        for task_id in removed_task_ids:
            card = self.task_cards.pop(task_id, None)
            if card is not None:
                card.deleteLater()
        self._update_summary()

    def get_card(self, task_id: str):
        return self.task_cards.get(task_id)


class StatusIndicator:
    _instance = None

    def __init__(self, main_window):
        self.main_window = main_window
        self.visible = True
        self.current_target = "Clusters"

        self.task_monitor = TaskMonitorPanel(self.main_window)

        self._setup_status_bar()
        self.update_status()
        StatusIndicator._instance = self

    @classmethod
    def instance(cls):
        return cls._instance

    def connect_signals(self):
        """Connect all BackgroundTaskManager signals to StatusIndicator and TaskMonitorDialog."""
        manager = BackgroundTaskManager.instance()

        manager.running_tasks.connect(self._on_running_tasks_changed)
        manager.task_started.connect(self._on_task_started)
        manager.task_queued.connect(self.task_monitor.on_task_queued)
        manager.task_completed.connect(self.task_monitor.on_task_completed)
        manager.task_failed.connect(self.task_monitor.on_task_failed)
        manager.task_progress.connect(self.task_monitor.on_task_progress)
        manager.task_message.connect(self.task_monitor.on_task_message)
        manager.task_output.connect(self.task_monitor.on_task_output)

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
                f"Task '{task_name}' cannot be cancelled.",
            )

    def _on_clear_finished_requested(self):
        """Handle clear finished tasks request from dialog."""
        manager = BackgroundTaskManager.instance()
        removed = manager.clear_finished_tasks()
        self.task_monitor.remove_finished_cards(removed)

    def _on_theme_changed(self):
        self._setup_status_bar_style()

    def _setup_status_bar_style(self):
        """Re-apply theme-dependent styles to status bar widgets."""
        status_bar = self.main_window.statusBar()
        status_bar.setStyleSheet(
            f"""
            QStatusBar {{ font-size: 11px; }}
            QStatusBar::item {{ border: none; }}
        """
        )
        if hasattr(self, "progress_bar"):
            self.progress_bar.setStyleSheet(
                f"""
                QProgressBar {{
                    border: none;
                    background-color: {Colors.BORDER_DARK};
                    border-radius: 2px;
                }}
                QProgressBar::chunk {{
                    background-color: {Colors.PRIMARY};
                    border-radius: 2px;
                }}
            """
            )
        if hasattr(self, "task_button"):
            self.task_button.setIcon(icon("ph.caret-up", role="muted"))
            self.task_button.setStyleSheet(
                f"""
                QPushButton {{
                    padding: 0px; margin: 0px; border: none; border-radius: 4px;
                    color: {Colors.TEXT_MUTED}; font-size: 11px;
                }}
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
        for label in ("mode_label", "target_label", "task_label"):
            if hasattr(self, label):
                getattr(self, label).setStyleSheet(
                    f"color: {Colors.TEXT_MUTED}; font-size: 11px;"
                )

    def _setup_status_bar(self):
        status_bar = self.main_window.statusBar()
        status_bar.setFixedHeight(24)
        status_bar.setStyleSheet(
            f"""
            QStatusBar {{ font-size: 11px; }}
            QStatusBar::item {{ border: none; }}
        """
        )

        self.task_label = QLabel()
        self.task_label.setFixedWidth(150)
        self.task_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
        self._task_timer = QTimer()
        self._task_timer.setSingleShot(True)
        self._task_timer.timeout.connect(lambda: self.task_label.clear())

        self.progress_label = QLabel()
        self.progress_label.setFixedWidth(120)
        self.progress_label.setVisible(False)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(250)
        self.progress_bar.setMaximumHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet(
            f"""
            QProgressBar {{
                border: none;
                background-color: {Colors.BORDER_DARK};
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {Colors.PRIMARY};
                border-radius: 2px;
            }}
        """
        )

        self.progress_count = QLabel()
        self.progress_count.setFixedWidth(35)
        self.progress_count.setVisible(False)

        self.mode_label = QLabel("Viewing")
        self.mode_label.setFixedWidth(55)
        self.mode_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")

        self.target_label = QLabel("Clusters")
        self.target_label.setFixedWidth(55)
        self.target_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")

        self.spinner = TextSpinnerLabel()
        self.spinner.setFixedWidth(14)
        self.spinner.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.task_button = QPushButton("Idle")
        self.task_button.setIcon(icon("ph.caret-up", role="muted"))
        self.task_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.task_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.task_button.setFlat(True)
        self.task_button.setFixedWidth(50)
        self.task_button.setContentsMargins(0, 0, 0, 0)
        self.task_button.setStyleSheet(
            f"""
            QPushButton {{
                padding: 0px; margin: 0px; border: none; border-radius: 4px;
                color: {Colors.TEXT_MUTED}; font-size: 11px;
            }}
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

        # Right-side status group in a fixed-width container
        right_group = QWidget()
        right_group.setContentsMargins(0, 0, 0, 0)
        right_layout = QHBoxLayout(right_group)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)
        right_layout.addWidget(self.mode_label)
        right_layout.addWidget(self.target_label)

        task_group = QWidget()
        task_group.setContentsMargins(0, 0, 0, 0)
        task_layout = QHBoxLayout(task_group)
        task_layout.setContentsMargins(0, 0, 0, 0)
        task_layout.setSpacing(2)
        task_layout.addWidget(self.spinner)
        task_layout.addWidget(self.task_button)
        right_layout.addWidget(task_group)

        left_spacer = QWidget()
        right_spacer = QWidget()
        status_bar.addWidget(self.task_label)
        status_bar.addWidget(left_spacer, 1)
        status_bar.addWidget(self.progress_label)
        status_bar.addWidget(self.progress_bar)
        status_bar.addWidget(self.progress_count)
        status_bar.addWidget(right_spacer, 1)
        status_bar.addPermanentWidget(right_group)

        self.spinner.stop()
        self.spinner.setStyleSheet(
            f"QLabel {{ color: {Colors.TEXT_MUTED}; font-weight: bold; }}"
        )
        self.spinner.setText("✓")

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
            self.mode_label.setText(interaction)

        if target is not None:
            self.current_target = target
            self.target_label.setText(target)

        if busy is not None:
            self._update_task_styling(busy)

        if task is not None:
            self.task_label.setText(task)
            self._task_timer.start(3000)

    def _update_task_styling(self, busy: bool = False):
        if not busy:
            self.spinner.stop()
            self.spinner.setStyleSheet(
                f"QLabel {{ color: {Colors.TEXT_MUTED}; font-weight: bold; }}"
            )
            self.spinner.setText("✓")
            self.task_button.setText("Idle")
        else:
            self.spinner.setStyleSheet(
                f"QLabel {{ color: {Colors.PRIMARY}; font-weight: bold; }}"
            )
            self.spinner.start()
            self.task_button.setText("Busy")

    def show_progress(self, title: str, total: int):
        """Show the center progress bar for a foreground operation."""
        self.progress_label.setText(title)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(0)
        self.progress_count.setText("0%")
        self.progress_label.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_count.setVisible(True)
        QApplication.processEvents()

    def update_progress(self, current: int, total: int):
        """Update the center progress bar."""
        self.progress_bar.setValue(current)
        pct = int(current / total * 100) if total > 0 else 0
        self.progress_count.setText(f"{pct}%")
        QApplication.processEvents()

    def hide_progress(self):
        """Hide the center progress bar."""
        self.progress_label.setVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_count.setVisible(False)

    def _show_task_monitor(self):
        if self.task_monitor.isVisible():
            self.task_monitor.hide()
            return

        # Position flush above the status bar, right-aligned
        status_bar = self.main_window.statusBar()
        bar_top_right = status_bar.mapToGlobal(status_bar.rect().topRight())
        panel = self.task_monitor
        x = bar_top_right.x() - panel.width()
        y = bar_top_right.y() - panel.height()
        panel.move(x, y)
        panel.show()
        panel.raise_()

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
