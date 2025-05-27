""" Implements ProgressDialog, wrapping a ProgressBar in a dialog window.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtCore import Qt
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
        self.dialog.show()

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

        container_layout.addWidget(self.status_label)
        container_layout.addWidget(self.progress_bar)

        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(container)
        self.dialog.setFixedSize(300, 100)

    def update_progress(self):
        self.progress_bar.setValue(self.current)
        self.status_label.setText(f"Processing {self.current}/{self.total}")
        QApplication.processEvents()

    def __iter__(self):
        return self

    def __next__(self):
        try:
            # Draw progress bar before processing first element
            self.update_progress()
            item = next(self.iterator)
            self.current += 1
            self.update_progress()
            return item
        except StopIteration:
            self.dialog.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.dialog.close()
        if exc_type is not None:
            QMessageBox.warning(None, "Error", str(exc_value))
