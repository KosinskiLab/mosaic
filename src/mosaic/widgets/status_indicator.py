"""
StatusIndicator widget for visualization of current viewer modes.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import enum
from collections import Counter

from qtpy.QtCore import Qt, QTimer
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
)
from qtpy.QtGui import QFont
import qtawesome as qta

from ..stylesheets import QPushButton_style, QScrollArea_style
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
        self.setStyleSheet("QLabel { color: #d97706; font-weight: bold; }")

    def start(self):
        self.timer.start(60)

    def stop(self):
        self.timer.stop()
        self.setText("✓")

    def next_frame(self):
        self.setText(self.frames[self.current_frame])
        self.current_frame = (self.current_frame + 1) % len(self.frames)


class TaskCard(QFrame):
    def __init__(self, task_data, parent=None):
        super().__init__(parent)
        self.task_data = task_data
        self.task_id = task_data.get("id", "unknown")
        self.status = task_data.get("status", "running")
        self.expanded = False

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._setup_ui()

    def _setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(8, 6, 8, 6)
        self.main_layout.setSpacing(4)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        self.status_colors = {
            "running": "#f59e0b",
            "queued": "#6b7280",
            "completed": "#10b981",
            "failed": "#ef4444",
        }

        self.status_dot = QLabel("●")
        self.status_dot.setFixedWidth(10)
        header_layout.addWidget(self.status_dot)

        self.name_label = QLabel(self.task_data.get("name", "Unnamed Task"))
        name_font = QFont()
        name_font.setPointSize(9)
        self.name_label.setFont(name_font)
        header_layout.addWidget(self.name_label, 1)

        self.status_badge = QLabel(self.status.upper())
        badge_font = QFont()
        badge_font.setPointSize(7)
        badge_font.setBold(True)
        badge_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.5)
        self.status_badge.setFont(badge_font)
        header_layout.addWidget(self.status_badge)

        self.chevron = QLabel()
        self.chevron.setPixmap(
            qta.icon("mdi.chevron-right", color="#9ca3af").pixmap(12, 12)
        )
        header_layout.addWidget(self.chevron)

        self.main_layout.addLayout(header_layout)

        self.output_view = QTextEdit()
        self.output_view.setReadOnly(True)
        self.output_view.setMinimumHeight(250)
        self.output_view.setVisible(False)
        self.output_view.setStyleSheet(
            """
            QTextEdit {
                font-family: 'Courier New', monospace;
                background: transparent;
                font-size: 8pt;
                border: 1px solid #d1d5db;
                border-radius: 3px;
                padding: 4px;
            }
        """
        )
        self.main_layout.addWidget(self.output_view)

        self._update_styling()

    def _update_styling(self):
        self.status_dot.setStyleSheet(
            f"color: {self.status_colors.get(self.status, '#6b7280')}; font-size: 12px;"
        )

        badge_styles = {
            "running": "background: #fef3c7; color: #92400e; padding: 2px 6px; border-radius: 3px;",
            "queued": "background: #e5e7eb; color: #374151; padding: 2px 6px; border-radius: 3px;",
            "completed": "background: #d1fae5; color: #065f46; padding: 2px 6px; border-radius: 3px;",
            "failed": "background: #fee2e2; color: #991b1b; padding: 2px 6px; border-radius: 3px;",
        }
        self.status_badge.setStyleSheet(
            badge_styles.get(self.status, badge_styles["queued"])
        )

        card_styles = {
            "running": "border-left: 2px solid #f59e0b;",
            "queued": "border-left: 2px solid #9ca3af;",
            "completed": "border-left: 2px solid #10b981;",
            "failed": "border-left: 2px solid #ef4444;",
        }

        self.setStyleSheet(
            f"""
            TaskCard {{
                border: 1px solid #e5e7eb;
                {card_styles.get(self.status, card_styles["queued"])}
                border-radius: 4px;
                padding: 2px;
            }}
            TaskCard:hover {{
                background-color: rgba(107, 114, 128, 0.05);
            }}
        """
        )

    def update_task_data(self, task_data):
        self.task_data = task_data
        self.status = task_data.get("status", "running")
        self.name_label.setText(task_data.get("name", "Unnamed Task"))
        self.status_badge.setText(self.status.upper())
        self._update_styling()

        if self.expanded:
            self._update_output()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_expanded()
        super().mousePressEvent(event)

    def _toggle_expanded(self):
        self.expanded = not self.expanded
        self.output_view.setVisible(self.expanded)

        chevron_icon = "mdi.chevron-down" if self.expanded else "mdi.chevron-right"
        self.chevron.setPixmap(qta.icon(chevron_icon, color="#9ca3af").pixmap(12, 12))

        if self.expanded:
            self._update_output()

    def _update_output(self):
        manager = BackgroundTaskManager.instance()
        task_info = manager.task_info.get(self.task_id, {})

        output = ""
        stdout = task_info.get("stdout")
        if stdout is not None and len(stdout) != 0:
            output += f"--- STDOUT --- \n\n{stdout}\n"

        stderr = task_info.get("stderr")
        if stderr is not None and len(stderr) != 0:
            output += f"--- STDERR --- \n\n {stderr}"

        if len(output.strip()) == 0:
            output = "No output available"
        self.output_view.setPlainText(output)


class TaskMonitorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Task Monitor")
        self.setMinimumSize(700, 500)
        self.resize(800, 600)

        self.task_cards = {}
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(12, 12, 12, 12)

        stats_layout = QHBoxLayout()
        self.stats_label = QLabel()
        stats_font = QFont()
        stats_font.setPointSize(9)
        self.stats_label.setFont(stats_font)
        stats_layout.addWidget(self.stats_label)
        stats_layout.addStretch()
        main_layout.addLayout(stats_layout)

        content_scroll = QScrollArea()
        content_scroll.setWidgetResizable(True)
        content_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        self.running_section = self._create_section(
            "Running", "#f59e0b", "running_tasks"
        )
        content_layout.addWidget(self.running_section)

        self.queued_section = self._create_section("Queued", "#6b7280", "queued_tasks")
        content_layout.addWidget(self.queued_section)

        self.completed_section = self._create_section(
            "Completed", "#10b981", "completed_tasks"
        )
        content_layout.addWidget(self.completed_section)

        self.failed_section = self._create_section("Failed", "#ef4444", "failed_tasks")
        content_layout.addWidget(self.failed_section)

        content_layout.addStretch()
        content_scroll.setWidget(content_widget)
        main_layout.addWidget(content_scroll, 1)

        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(8)

        clear_btn = QPushButton("Clear Finished")
        clear_btn.setIcon(qta.icon("mdi.broom", color="#6b7280"))
        clear_btn.clicked.connect(self._clear_finished_tasks)
        footer_layout.addWidget(clear_btn)

        footer_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_btn.setDefault(True)
        footer_layout.addWidget(close_btn)

        main_layout.addLayout(footer_layout)
        self.setStyleSheet(QPushButton_style + QScrollArea_style)

    def _create_section(self, title, color, attr_name):
        section = QGroupBox(title)

        section_layout = QVBoxLayout()
        section_layout.setContentsMargins(8, 8, 8, 8)
        section_layout.setSpacing(6)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        count_label = QLabel("0")
        count_font = QFont()
        count_font.setPointSize(8)
        count_font.setBold(True)
        count_label.setFont(count_font)
        count_label.setStyleSheet(
            f"background: {color}; color: #ffffff; padding: 2px 8px; border-radius: 10px;"
        )
        header_layout.addWidget(count_label)
        header_layout.addStretch()

        section_layout.addLayout(header_layout)

        task_container = QWidget()
        task_layout = QVBoxLayout(task_container)
        task_layout.setContentsMargins(0, 0, 0, 0)
        task_layout.setSpacing(4)

        section_layout.addWidget(task_container)
        section.setLayout(section_layout)

        setattr(self, f"{attr_name}_container", task_container)
        setattr(self, f"{attr_name}_layout", task_layout)
        setattr(self, f"{attr_name}_count", count_label)
        return section

    def _sync_with_task_manager(self):
        manager = BackgroundTaskManager.instance()

        active_tasks = set()
        for task_id, task_data in manager.task_info.items():
            self._update_task_card(task_id, task_data)
            if task_data.get("status") in ("queued", "running"):
                active_tasks.add(task_id)

        for task_id in self.task_cards:
            if task_id in manager.task_info:
                continue

            # task was killed by a crash in the parallel backend
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
        if card is None:
            card = TaskCard(task_data)
        else:
            card.update_task_data(task_data)

        if status == "running":
            layout = self.running_tasks_layout
        elif status == "queued":
            layout = self.queued_tasks_layout
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
        runn_count = status_counts["running"]
        qued_count = status_counts["queued"]
        comp_count = status_counts["completed"]
        fail_count = status_counts["failed"]

        self.running_tasks_count.setText(str(runn_count))
        self.queued_tasks_count.setText(str(qued_count))
        self.completed_tasks_count.setText(str(comp_count))
        self.failed_tasks_count.setText(str(fail_count))

        total = runn_count + qued_count + comp_count + fail_count
        self.stats_label.setText(
            f"Total: {total}  •  Active: {runn_count + qued_count}"
        )

    def _clear_finished_tasks(self):
        drop = set()
        for task_id, card in self.task_cards.items():
            if card.task_data.get("status") in ("completed", "failed"):
                card.deleteLater()
                drop.add(task_id)
        self.task_cards = {k: v for k, v in self.task_cards.items() if k not in drop}

        self._update_counts()


class ClickableTaskWidget(QWidget):
    def __init__(self, status_indicator, parent=None):
        super().__init__(parent)
        self.status_indicator = status_indicator
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.task_label = QLabel("Idle")
        self.task_label.setMinimumWidth(40)
        layout.addWidget(self.task_label)

        chevron_label = QLabel()
        chevron_label.setPixmap(
            qta.icon("mdi.chevron-up", color="#9ca3af").pixmap(16, 16)
        )
        layout.addWidget(chevron_label)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.status_indicator.show_task_monitor()
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self.task_label.setStyleSheet("text-decoration: underline;")
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.task_label.setStyleSheet("")
        super().leaveEvent(event)


class StatusIndicator:
    def __init__(self, main_window):
        self.main_window = main_window
        self.visible = True
        self.current_target = "Clusters"
        self.task_monitor = TaskMonitorDialog(self.main_window)

        self._setup_status_bar()
        self.update_status()

    def _setup_status_bar(self):
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

        self.task_widget = ClickableTaskWidget(self)

        separator1 = QLabel("•")
        separator1.setStyleSheet("QLabel { color: #9ca3af; padding: 0 10px; }")
        separator2 = QLabel("•")
        separator2.setStyleSheet("QLabel { color: #9ca3af; padding: 0 10px; }")

        status_bar.addPermanentWidget(self.mode_label)
        status_bar.addPermanentWidget(separator1)
        status_bar.addPermanentWidget(self.target_label)
        status_bar.addPermanentWidget(separator2)
        status_bar.addPermanentWidget(self.spinner)
        status_bar.addPermanentWidget(self.task_widget)

        self.spinner.stop()

    def update_status(
        self,
        interaction="Viewing",
        target=None,
        busy: bool = None,
        task: str = None,
        **kwargs,
    ):
        if not self.visible:
            return

        self.mode_label.setText(f"Mode: {interaction}")
        if target is not None:
            self.current_target = target
            self.target_label.setText(target)

        if busy is not None:
            self._update_task_styling(busy)

        if task is not None:
            self.main_window.statusBar().showMessage(task, 3000)

    def _update_task_styling(self, busy: bool = False):
        self.task_widget.task_label.setText("Busy" if busy else "Idle")

        if not busy:
            return self.spinner.stop()
        return self.spinner.start()

    def show_task_monitor(self):
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
