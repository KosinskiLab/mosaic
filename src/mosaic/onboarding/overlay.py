"""
Semi-modal spotlight overlay for onboarding.

Uses a top-level translucent window so the overlay renders above VTK's
OpenGL surface, which would otherwise paint over any sibling QWidget.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtCore import (
    Qt,
    Signal,
    QRect,
    QRectF,
    QPoint,
    QPointF,
    QEvent,
    QTimer,
    QCoreApplication,
)
from qtpy.QtGui import QPainter, QColor, QPainterPath, QBrush, QPen, QMouseEvent
from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
)


class TooltipPanel(QFrame):
    action_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("onboarding_tooltip")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFixedWidth(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        self._title = QLabel()
        self._title.setObjectName("onboarding_title")
        self._title.setWordWrap(True)
        layout.addWidget(self._title)

        self._body = QLabel()
        self._body.setObjectName("onboarding_body")
        self._body.setWordWrap(True)
        layout.addWidget(self._body)

        layout.addSpacing(8)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        self._progress = QLabel()
        self._progress.setObjectName("onboarding_progress")
        bottom.addWidget(self._progress)

        bottom.addStretch()

        self._action_btn = QPushButton("Next")
        self._action_btn.setObjectName("onboarding_action")
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_btn.clicked.connect(self.action_clicked.emit)
        bottom.addWidget(self._action_btn)

        layout.addLayout(bottom)

        self._apply_style()

    def _apply_style(self):
        from mosaic.stylesheets import Colors

        self.setStyleSheet(
            f"""
            #onboarding_tooltip {{
                background: {Colors.SURFACE};
                border: 1px solid {Colors.BORDER_DARK};
                border-radius: 12px;
            }}
            #onboarding_title {{
                font-size: 15px;
                font-weight: 600;
                color: {Colors.TEXT_PRIMARY};
            }}
            #onboarding_body {{
                font-size: 13px;
                color: {Colors.TEXT_SECONDARY};
                line-height: 1.4;
            }}
            #onboarding_progress {{
                font-size: 12px;
                color: {Colors.TEXT_MUTED};
            }}
            #onboarding_action {{
                font-size: 13px;
                font-weight: 500;
                color: white;
                background: {Colors.PRIMARY};
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
            }}
            #onboarding_action:hover {{
                background: {Colors.alpha("PRIMARY", 0.85)};
            }}
        """
        )

    def set_content(self, title: str, body: str, progress: str, button_text: str):
        self._title.setText(title)
        self._body.setText(body)
        self._progress.setText(progress)
        self._action_btn.setText(button_text)
        # 320px wide, 20px side margins, 16px top/bottom, 8px layout spacing
        inner_w = 280
        h = (
            16
            + self._title.heightForWidth(inner_w)
            + 8
            + self._body.heightForWidth(inner_w)
            + 8
            + 8  # addSpacing between body and bottom row
            + max(
                self._progress.sizeHint().height(), self._action_btn.sizeHint().height()
            )
            + 16
        )
        self.setFixedHeight(h)

    def set_action_enabled(self, enabled: bool):
        self._action_btn.setEnabled(enabled)
        self._action_btn.setVisible(enabled)


class SpotlightOverlay(QWidget):
    """Top-level translucent window that dims everything except a spotlight hole."""

    skip_requested = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)

        self._host = parent
        self._spotlight_rect: QRect | None = None
        self._spotlight_global: QRect | None = None
        self._highlight_padding = 8
        self._dim_color = QColor(0, 0, 0, 153)
        self._dim_enabled = True
        self._spotlight_widget: QWidget | None = None
        self._spotlight_position: str = "auto"
        self._show_spotlight: bool = True

        self._spotlight_resize_timer = QTimer(self)
        self._spotlight_resize_timer.setSingleShot(True)
        self._spotlight_resize_timer.setInterval(0)
        self._spotlight_resize_timer.timeout.connect(self._reapply_spotlight)

        self._tooltip = TooltipPanel(self)
        self._tooltip.hide()

        self._host.installEventFilter(self)
        self.hide()

    def activate(self):
        self._sync_geometry()
        self.show()
        self.raise_()

    def deactivate(self):
        self.hide()
        self._spotlight_rect = None
        self._spotlight_global = None
        if self._spotlight_widget is not None:
            try:
                self._spotlight_widget.removeEventFilter(self)
            except RuntimeError:
                pass  # Underlying C++ object already deleted
            self._spotlight_widget = None

    def _sync_geometry(self):
        """Match the overlay to the host window's frame geometry."""
        geo = self._host.geometry()
        self.setGeometry(geo)

    def eventFilter(self, obj, event):
        if obj is self._host:
            if event.type() in (
                QEvent.Type.Move,
                QEvent.Type.Resize,
                QEvent.Type.WindowStateChange,
            ):
                if self.isVisible():
                    self._sync_geometry()
                    if self._spotlight_global:
                        local = self.mapFromGlobal(self._spotlight_global.topLeft())
                        self._spotlight_rect = QRect(
                            local, self._spotlight_global.size()
                        )
                        self.update()
        elif obj is self._spotlight_widget and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Move,
            QEvent.Type.Show,
        ):
            if self.isVisible():
                self._spotlight_resize_timer.start()
        return False

    def _reapply_spotlight(self):
        if self._spotlight_widget is not None and self.isVisible():
            self.spotlight(
                self._spotlight_widget,
                self._highlight_padding,
                self._spotlight_position,
                self._show_spotlight,
                self._dim_enabled,
            )

    def spotlight(
        self,
        widget: QWidget,
        padding: int = 8,
        position: str = "auto",
        show_spotlight: bool = True,
        dim: bool = True,
    ):
        if self._spotlight_widget is not widget:
            if self._spotlight_widget is not None:
                try:
                    self._spotlight_widget.removeEventFilter(self)
                except RuntimeError:
                    pass  # Underlying C++ object already deleted
            self._spotlight_widget = widget
            widget.installEventFilter(self)
        self._spotlight_position = position
        self._show_spotlight = show_spotlight
        self._dim_enabled = dim
        self._highlight_padding = padding

        # When not dimming, let clicks pass through naturally; no need to
        # forward through the spotlight rect.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not dim)

        self._sync_geometry()

        widget_rect = widget.rect()
        top_left_global = widget.mapToGlobal(widget_rect.topLeft())
        top_left_local = self.mapFromGlobal(top_left_global)

        self._spotlight_rect = QRect(top_left_local, widget_rect.size()).adjusted(
            -padding, -padding, padding, padding
        )
        self._spotlight_global = QRect(top_left_global, widget_rect.size()).adjusted(
            -padding, -padding, padding, padding
        )

        self._position_tooltip(position)
        self.update()

    def _position_tooltip(self, position: str):
        if self._spotlight_rect is None:
            return

        self._tooltip.adjustSize()
        tip_size = self._tooltip.size()
        sr = self._spotlight_rect
        parent_rect = self.rect()
        margin = 16

        candidates = {
            "right": QPoint(
                sr.right() + margin,
                sr.center().y() - tip_size.height() // 2,
            ),
            "below": QPoint(
                sr.center().x() - tip_size.width() // 2,
                sr.bottom() + margin,
            ),
            "left": QPoint(
                sr.left() - tip_size.width() - margin,
                sr.center().y() - tip_size.height() // 2,
            ),
            "above": QPoint(
                sr.center().x() - tip_size.width() // 2,
                sr.top() - tip_size.height() - margin,
            ),
            "center": QPoint(
                parent_rect.center().x() - tip_size.width() // 2,
                parent_rect.center().y() - tip_size.height() // 2,
            ),
        }

        if position == "auto":
            order = ["right", "below", "left", "above"]
        else:
            order = [position, "right", "below", "left", "above"]

        for key in order:
            pos = candidates[key]
            tip_rect = QRect(pos, tip_size)
            if parent_rect.contains(tip_rect):
                self._tooltip.move(pos)
                self._tooltip.show()
                return

        # Nothing fits perfectly so clamp to stay in bounds
        pos = candidates[order[0]]
        pos.setX(
            max(margin, min(pos.x(), parent_rect.width() - tip_size.width() - margin))
        )
        pos.setY(
            max(margin, min(pos.y(), parent_rect.height() - tip_size.height() - margin))
        )
        self._tooltip.move(pos)
        self._tooltip.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # WA_TranslucentBackground requires an explicit alpha clear on every frame;
        # skipping it leaves the backing store undefined and corrupts the compositor.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        if self._dim_enabled:
            path = QPainterPath()
            path.addRect(QRectF(self.rect()))

            if self._spotlight_rect:
                sr = QRectF(self._spotlight_rect.intersected(self.rect()))
                hole = QPainterPath()
                hole.addRoundedRect(sr, 8, 8)
                path = path.subtracted(hole)

            painter.fillPath(path, QBrush(self._dim_color))

        if self._show_spotlight and self._spotlight_rect:
            sr = QRectF(self._spotlight_rect.intersected(self.rect()))
            border_path = QPainterPath()
            border_path.addRoundedRect(sr, 8, 8)
            pen = QPen(QColor(99, 102, 241, 180), 2)
            painter.setPen(pen)
            painter.drawPath(border_path)

        painter.end()

    def mousePressEvent(self, event):
        if self._spotlight_rect and self._spotlight_rect.contains(event.pos()):
            global_pos = self.mapToGlobal(event.pos())
            target = self._host.childAt(self._host.mapFromGlobal(global_pos))
            if target:
                forwarded = QMouseEvent(
                    event.type(),
                    QPointF(target.mapFromGlobal(global_pos)),
                    QPointF(global_pos),
                    event.button(),
                    event.buttons(),
                    event.modifiers(),
                )
                QCoreApplication.sendEvent(target, forwarded)
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mouseMoveEvent(self, event):
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.skip_requested.emit()
        else:
            QCoreApplication.sendEvent(self._host, event)
