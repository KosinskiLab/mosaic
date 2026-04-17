"""
Tab bar and tab widget with animated pill indicator.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import Tuple

from qtpy.QtCore import Qt, Signal, QRect, QTimer
from qtpy.QtGui import QPainter, QColor
from qtpy.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton,
    QButtonGroup,
    QStackedWidget,
    QVBoxLayout,
)
from qtpy.QtCore import QPropertyAnimation, QEasingCurve

from ..stylesheets import Colors, Typography


class _PillIndicator(QWidget):
    """Subtle rounded background behind the active tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        c = QColor(255, 255, 255, 15) if Colors.is_dark() else QColor(0, 0, 0, 10)
        p.setBrush(c)
        p.drawRoundedRect(self.rect(), 6, 6)
        p.end()


class TabBar(QWidget):
    """Tab bar with animated pill selection indicator.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget.
    margins : tuple of int, optional
        Content margins ``(left, top, right, bottom)`` for the tab row.
        Defaults to ``(8, 0, 8, 0)``.
    """

    currentChanged = Signal(int)

    def __init__(
        self,
        parent=None,
        margins: Tuple[int, int, int, int] = (8, 0, 8, 0),
    ):
        super().__init__(parent)
        self.setFixedHeight(38)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(*margins)
        self._layout.setSpacing(4)

        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)

        self._buttons = {}
        self._indicator = _PillIndicator(self)
        self._indicator.setFixedHeight(28)
        self._indicator.lower()

        self._anim = QPropertyAnimation(self._indicator, b"geometry")
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._button_group.idClicked.connect(self._on_tab_clicked)
        self._stretch_added = False

    def addTab(self, label, icon=None):
        """Add a tab button.

        Parameters
        ----------
        label : str
            Tab label text.
        icon : QIcon, optional
            Icon for the tab button.

        Returns
        -------
        int
            Index of the added tab.
        """
        index = len(self._buttons)
        btn = QPushButton(label) if icon is None else QPushButton(icon, label)
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._button_group.addButton(btn, index)

        if not self._stretch_added:
            self._layout.addWidget(btn)
        else:
            self._layout.insertWidget(self._layout.count() - 1, btn)

        self._buttons[index] = btn
        self._apply_button_style(btn)

        if index == 0:
            btn.setChecked(True)
            QTimer.singleShot(0, lambda: self._animate_indicator(btn))

        return index

    def finalize(self):
        """Add trailing stretch. Call after all tabs are added."""
        if not self._stretch_added:
            self._layout.addStretch()
            self._stretch_added = True

    def setCurrentIndex(self, index):
        if index in self._buttons:
            self._buttons[index].setChecked(True)
            self._on_tab_clicked(index)

    def _on_tab_clicked(self, index):
        btn = self._buttons[index]
        QTimer.singleShot(0, lambda: self._animate_indicator(btn))
        self.currentChanged.emit(index)

    def _animate_indicator(self, btn):
        h = 28
        target = QRect(btn.x(), (self.height() - h) // 2, btn.width(), h)

        if self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()

        self._anim.setStartValue(self._indicator.geometry())
        self._anim.setEndValue(target)
        self._anim.start()

    def _apply_button_style(self, btn):
        btn.setStyleSheet(
            f"""
            QPushButton {{
                border: none;
                padding: 6px 14px;
                font-size: {Typography.BODY}px;
                background: transparent;
                border-radius: 6px;
                color: {Colors.TEXT_MUTED};
            }}
            QPushButton:checked {{
                color: {Colors.TEXT_PRIMARY};
            }}
            QPushButton:hover:!checked {{
                color: {Colors.TEXT_SECONDARY};
            }}
            QPushButton:focus {{
                outline: none;
            }}
        """
        )

    def _on_theme_changed(self):
        for btn in self._buttons.values():
            self._apply_button_style(btn)
        checked = self._button_group.checkedButton()
        if checked:
            QTimer.singleShot(0, lambda: self._animate_indicator(checked))


class TabWidget(QWidget):
    """Tab widget combining TabBar with a QStackedWidget.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget.
    tab_bar_margins : tuple of int, optional
        Content margins forwarded to the underlying :class:`TabBar`.
        Defaults to ``(8, 0, 8, 0)``.
    """

    currentChanged = Signal(int)

    def __init__(
        self,
        parent=None,
        tab_bar_margins: Tuple[int, int, int, int] = (8, 0, 8, 0),
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tab_bar = TabBar(margins=tab_bar_margins)
        self._stack = QStackedWidget()

        layout.addWidget(self.tab_bar)
        layout.addWidget(self._stack)

        self.tab_bar.currentChanged.connect(self._on_tab_changed)

    def addTab(self, widget, label, icon=None):
        """Add a tab with its content widget.

        Parameters
        ----------
        widget : QWidget
            Content widget for this tab.
        label : str
            Tab label text.
        icon : QIcon, optional
            Icon for the tab button.

        Returns
        -------
        int
            Index of the added tab.
        """
        index = self.tab_bar.addTab(label, icon)
        self._stack.addWidget(widget)
        return index

    def finalize(self):
        """Call after all tabs are added."""
        self.tab_bar.finalize()

    def setCurrentIndex(self, index):
        self.tab_bar.setCurrentIndex(index)

    def currentIndex(self):
        return self._stack.currentIndex()

    def widget(self, index):
        return self._stack.widget(index)

    def _on_tab_changed(self, index):
        self._stack.setCurrentIndex(index)
        self.currentChanged.emit(index)

    def _on_theme_changed(self):
        self.tab_bar._on_theme_changed()
