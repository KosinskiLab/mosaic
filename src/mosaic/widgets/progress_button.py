""" Variety of widgets used throughout the GUI.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtWidgets import QPushButton
from qtpy.QtGui import QPainter, QColor
from qtpy.QtCore import Qt, QTimer, QPropertyAnimation, Property, Signal


class ProgressButton(QPushButton):
    cancel = Signal()

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._progress = 0
        self._is_progressing = False
        self._original_text = text
        self._fade_opacity = 1.0

        # Re-clicking the progress button should allow cancelling the operation
        self._cancel_button = QPushButton(parent=self)
        self._cancel_button.setStyleSheet(
            """
            QPushButton {
                background-color: transparent;
                border: none;
            }
        """
        )

        self._cancel_button.clicked.connect(self._handle_cancel_click)
        self._cancel_button.setEnabled(False)
        self._cancel_button.hide()

        self._fade_animation = QPropertyAnimation(self, b"fadeOpacity")
        self._fade_animation.setDuration(200)
        self._fade_animation.finished.connect(self._cleanup)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._cancel_button:
            self._cancel_button.setGeometry(self.rect())

    @Property(float)
    def fadeOpacity(self):
        return self._fade_opacity

    @fadeOpacity.setter
    def fadeOpacity(self, opacity):
        self._fade_opacity = max(0.0, min(1.0, opacity))
        if not self._is_progressing:
            return None
        self.update()

    def listen(self, signal):
        self.setEnabled(False)

        # self._cancel_button.setEnabled(True)
        # self._cancel_button.show()

        self.signal = signal
        self.signal.connect(self._update_progress)

        self._fade_opacity, self._is_progressing = 1.0, True
        self.update()

    def _update_progress(self, value):
        if not self._is_progressing:
            return None

        self._progress = max(0.0, min(1.0, value)) * 100

        self.update()
        if self._progress >= 100:
            QTimer.singleShot(200, self._exit)

    def _handle_cancel_click(self):
        if self._is_progressing:
            self.cancel.emit()
            self._exit()
            return None

    def _exit(self):
        self._fade_animation.stop()
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.start()

    def _cleanup(self):
        self._is_progressing = False
        self._fade_opacity = 0.0

        self.setEnabled(True)
        self._cancel_button.setEnabled(False)
        self._cancel_button.hide()

        if hasattr(self, "signal") and self.signal is not None:
            self.signal.disconnect(self._update_progress)
            self.signal = None

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        super().paintEvent(event)

        if not self._is_progressing:
            return None

        painter.save()
        painter.setOpacity(self._fade_opacity)

        bg_color = QColor(200, 200, 200)
        painter.fillRect(self.rect(), bg_color)
        if self._progress > 0:
            progress_width = int(self.width() * (self._progress / 100))
            progress_color = QColor(76, 175, 80)
            painter.fillRect(0, 0, progress_width, self.height(), progress_color)

        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(
            self.rect(), Qt.AlignmentFlag.AlignCenter, f"{int(self._progress)}%"
        )
        painter.restore()
