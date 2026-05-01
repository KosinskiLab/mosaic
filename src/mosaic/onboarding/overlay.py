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
from qtpy.QtGui import (
    QPainter,
    QColor,
    QPainterPath,
    QBrush,
    QPen,
    QMouseEvent,
    QRegion,
)
from qtpy.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
)


# Spotlight geometry. _MASK_INSET keeps the rectangular mask hole's
# corners inside the painted rounded curve and inside the inner edge
# of the border stroke: (r - inset) * sqrt(2) <= r - 1 yields
# inset >= r * (1 - 1/sqrt(2)) + 1/sqrt(2) ≈ 3.05 for r=8.
_SPOTLIGHT_RADIUS = 8
_BORDER_WIDTH = 2
_BORDER_COLOR = QColor(99, 102, 241, 180)
_DIM_COLOR = QColor(0, 0, 0, 153)
_MASK_INSET = 4
_MASK_RING = 3
_TOOLTIP_MARGIN = 16


class TooltipPanel(QFrame):
    action_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("onboarding_tooltip")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFixedWidth(320)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 16, 20, 16)
        self._layout.setSpacing(8)

        self._title = QLabel()
        self._title.setObjectName("onboarding_title")
        self._title.setWordWrap(True)
        self._layout.addWidget(self._title)

        self._body = QLabel()
        self._body.setObjectName("onboarding_body")
        self._body.setWordWrap(True)
        self._layout.addWidget(self._body)

        self._layout.addSpacing(8)

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

        self._layout.addLayout(bottom)

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

        # Sum heights directly off each widget. `QBoxLayout.heightForWidth`
        # depends on a setupGeom() pass that hasn't run before first show,
        # so it returns wrong values here. `QLabel.heightForWidth` is
        # geometry-independent.
        margins = self._layout.contentsMargins()
        spacing = self._layout.spacing()
        inner_w = self.minimumWidth() - margins.left() - margins.right()
        bottom_h = max(
            self._progress.sizeHint().height(), self._action_btn.sizeHint().height()
        )
        self.setFixedHeight(
            margins.top()
            + self._title.heightForWidth(inner_w)
            + spacing
            + self._body.heightForWidth(inner_w)
            + spacing
            + 8  # layout.addSpacing(8) before the bottom row
            + spacing
            + bottom_h
            + margins.bottom()
        )

    def set_action_text(self, text: str):
        self._action_btn.setText(text)

    def set_action_enabled(self, enabled: bool):
        self._action_btn.setEnabled(enabled)
        self._action_btn.setVisible(enabled)


class SpotlightOverlay(QWidget):
    """Top-level translucent window that dims everything except a spotlight hole."""

    skip_requested = Signal()
    action_clicked = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)

        self._host = parent
        self._was_visible = False
        self._spotlight_rect: QRect | None = None
        self._spotlight_global: QRect | None = None
        self._highlight_padding = 8
        self._dim_enabled = True
        self._spotlight_widget: QWidget | None = None
        self._spotlight_position: str = "auto"
        self._show_spotlight: bool = True

        self._spotlight_resize_timer = QTimer(self)
        self._spotlight_resize_timer.setSingleShot(True)
        self._spotlight_resize_timer.setInterval(0)
        self._spotlight_resize_timer.timeout.connect(self._reapply_spotlight)

        self.tooltip = TooltipPanel(self)
        self.tooltip.hide()
        self.tooltip.action_clicked.connect(self.action_clicked.emit)

        self._host.installEventFilter(self)
        QApplication.instance().applicationStateChanged.connect(
            self._on_application_state_changed
        )
        self.hide()

    def _on_application_state_changed(self, state):
        if state == Qt.ApplicationState.ApplicationActive:
            if self._was_visible:
                self._was_visible = False
                self.show()
                self.raise_()
        elif state == Qt.ApplicationState.ApplicationInactive:
            if self.isVisible():
                self._was_visible = True
                self.hide()

    def activate(self):
        self._sync_geometry()
        self.show()
        self.raise_()

    def deactivate(self):
        self.hide()
        self._was_visible = False
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
                        self._update_input_mask()
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
        self._update_input_mask()
        self.update()

    def _update_input_mask(self):
        """Define which pixels absorb mouse input via a region mask.

        Toggling ``WA_TransparentForMouseEvents`` on a top-level
        translucent window has no effect on X11 once the window is
        shown, so click pass-through must come from the window mask.
        The mask hole is inset slightly relative to the painted
        rounded subtraction so the antialiased visible edge stays
        inside the mask region; the mask's own 1-bit straight edge
        sits in pixels that are transparent on both sides and is
        invisible.
        """
        if self._spotlight_rect is None:
            self.clearMask()
            return

        # Clip the spotlight to the window before insetting so the mask's
        # straight edges sit inside the painted rounded curve at every
        # corner, including corners that fall on the window border. The
        # painter uses the same intersection in `paintEvent` for the
        # dim cut-out and the border stroke.
        sr = self._spotlight_rect.intersected(self.rect())
        if sr.isEmpty():
            self.clearMask()
            return

        if self._dim_enabled:
            hole = sr.adjusted(_MASK_INSET, _MASK_INSET, -_MASK_INSET, -_MASK_INSET)
            region = QRegion(self.rect()).subtracted(QRegion(hole))
        else:
            region = QRegion()
            if self._show_spotlight:
                outer = QRegion(
                    sr.adjusted(-_MASK_RING, -_MASK_RING, _MASK_RING, _MASK_RING)
                ).intersected(QRegion(self.rect()))
                inner = QRegion(
                    sr.adjusted(_MASK_RING, _MASK_RING, -_MASK_RING, -_MASK_RING)
                )
                region = outer.subtracted(inner)

        if self.tooltip.isVisible():
            region = region.united(QRegion(self.tooltip.geometry()))

        if region.isEmpty():
            # An empty region resolves to clearMask() on some platforms,
            # which would make the entire window absorb input again.
            # A 1x1 mask off-screen keeps the window effectively click-through.
            region = QRegion(-1, -1, 1, 1)

        self.setMask(region)

    def _position_tooltip(self, position: str):
        if self._spotlight_rect is None:
            return

        self.tooltip.adjustSize()
        tip = self.tooltip.size()
        sr = self._spotlight_rect
        pr = self.rect()
        m = _TOOLTIP_MARGIN

        cx_sr = sr.center().x() - tip.width() // 2
        cy_sr = sr.center().y() - tip.height() // 2
        candidates = {
            "right": QPoint(sr.right() + m, cy_sr),
            "below": QPoint(cx_sr, sr.bottom() + m),
            "left": QPoint(sr.left() - tip.width() - m, cy_sr),
            "above": QPoint(cx_sr, sr.top() - tip.height() - m),
            "center": QPoint(
                pr.center().x() - tip.width() // 2,
                pr.center().y() - tip.height() // 2,
            ),
        }

        order = ["right", "below", "left", "above"]
        if position != "auto":
            order = [position] + [s for s in order if s != position]

        for key in order:
            pos = candidates[key]
            if pr.contains(QRect(pos, tip)):
                self.tooltip.move(pos)
                self.tooltip.show()
                return

        pos = candidates[order[0]]
        pos.setX(max(m, min(pos.x(), pr.width() - tip.width() - m)))
        pos.setY(max(m, min(pos.y(), pr.height() - tip.height() - m)))
        self.tooltip.move(pos)
        self.tooltip.show()

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
                hole.addRoundedRect(sr, _SPOTLIGHT_RADIUS, _SPOTLIGHT_RADIUS)
                path = path.subtracted(hole)

            painter.fillPath(path, QBrush(_DIM_COLOR))

        if self._show_spotlight and self._spotlight_rect:
            sr = QRectF(self._spotlight_rect.intersected(self.rect()))
            border_path = QPainterPath()
            border_path.addRoundedRect(sr, _SPOTLIGHT_RADIUS, _SPOTLIGHT_RADIUS)
            painter.setPen(QPen(_BORDER_COLOR, _BORDER_WIDTH))
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
