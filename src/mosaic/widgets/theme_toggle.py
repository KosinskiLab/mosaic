"""
Theme toggle widget.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtCore import Qt, QPropertyAnimation, QEasingCurve, Property
from qtpy.QtGui import QColor, QFont, QPainter
from qtpy.QtWidgets import QPushButton

from ..stylesheets import Colors


class ThemeToggle(QPushButton):
    """Animated toggle switch for light/dark theme."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(48, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Toggle theme")
        self._knob = 2.0

        self._anim = QPropertyAnimation(self, b"knob_x")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.toggled.connect(self._animate)

    def _get_knob_x(self):
        return self._knob

    def _set_knob_x(self, v):
        self._knob = v
        self.update()

    knob_x = Property(float, _get_knob_x, _set_knob_x)

    def _animate(self, checked):
        self._anim.stop()
        self._anim.setStartValue(self._knob)
        self._anim.setEndValue(24.0 if checked else 2.0)
        self._anim.start()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_dark = Colors.is_dark()
        track = "#3f3f46" if is_dark else "#e4e4e7"
        knob = "#18181b" if is_dark else "#ffffff"
        glyph_color = Colors.TEXT_MUTED

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(track))
        p.drawRoundedRect(0, 0, self.width(), self.height(), 13, 13)

        p.setBrush(QColor(knob))
        p.drawEllipse(int(self._knob), 2, 22, 22)

        glyph = "\u263e" if self.isChecked() else "\u2600"
        p.setPen(QColor(glyph_color))
        p.setFont(QFont(self.font().family(), 10))
        p.drawText(int(self._knob), 2, 22, 22, Qt.AlignmentFlag.AlignCenter, glyph)
        p.end()
