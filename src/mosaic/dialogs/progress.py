"""
Implements ProgressDialog, wrapping a ProgressBar in a dialog window.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtCore import Qt, QTimer
from qtpy.QtWidgets import (
    QVBoxLayout,
    QFrame,
    QProgressBar,
    QLabel,
    QDialog,
    QApplication,
    QMessageBox,
)


class ProgressDialog:
    def __init__(self, iterable, title="Processing", parent=None):
        self.total = len(iterable)
        self.iterator = iter(iterable)
        self.current = 0
        self.dialog = QDialog(parent)
        self.dialog.setWindowTitle(title)
        self.dialog.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        self.dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setup_ui()

        QTimer.singleShot(50, self._show_dialog)

    def _show_dialog(self):
        if not self.dialog.isVisible():
            self.dialog.show()
            QApplication.processEvents()

    def setup_ui(self):
        from ..stylesheets import QProgressBar_style

        layout = QVBoxLayout(self.dialog)
        container = QFrame()
        container.setStyleSheet(
            """
            QFrame {
                background-color: white;
                border-radius: 10px;
                border: 1px solid #e5e7eb;
            }
        """
        )
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(15)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(QProgressBar_style)
        self.progress_bar.setMaximum(self.total)
        self.progress_bar.setValue(0)

        self.status_label = QLabel()
        self.status_label.setStyleSheet(
            """
            QLabel {
                color: #374151;
                font-size: 13px;
            }
        """
        )
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setText(f"Processing 0/{self.total}")  # Initialize text

        container_layout.addWidget(self.status_label)
        container_layout.addWidget(self.progress_bar)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(container)
        self.dialog.setFixedSize(300, 100)

    def update_progress(self, value: int = None):
        """Update progress bar and status label."""
        if value is None:
            value = self.current

        # Ensure dialog is visible before updating
        if not self.dialog.isVisible():
            self.dialog.show()

        self.progress_bar.setValue(value)
        self.status_label.setText(f"Processing {value}/{self.total}")
        QApplication.processEvents()

    def __iter__(self):
        return self

    def __next__(self):
        try:
            item = next(self.iterator)
            self.current += 1
            self.update_progress()  # Update after increment
            return item
        except StopIteration:
            self.update_progress()
            self.dialog.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.dialog.close()
        if exc_type is not None:
            QMessageBox.warning(None, "Error", str(exc_value))
            # Omit traceback
            return True

    def close(self):
        """Explicitly close the dialog."""
        self.dialog.close()
