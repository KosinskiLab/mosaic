"""
Reusable card widgets and flow layout for gallery UIs.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtWidgets import (
    QVBoxLayout,
    QLabel,
    QFrame,
    QWidget,
    QSizePolicy,
)
from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QPixmap, QPainter, QPainterPath

from ..stylesheets import Colors

__all__ = [
    "CARD_WIDTH",
    "THUMB_HEIGHT",
    "Card",
    "FlowLayout",
    "clip_thumbnail",
    "place_pill",
]

CARD_WIDTH = 232
THUMB_HEIGHT = 150
_TEXT_H = 56
_R = 8
_CONTENT_W = CARD_WIDTH - 2

_PILL = (
    f"background: rgba(0,0,0,0.45); color: #ffffff; "
    f"font-size: 9px; font-weight: 600; border-radius: 3px; "
    f"padding: 2px 6px;"
)


def _card_qss(cls_name):
    return f"""
        {cls_name} {{
            border: 1px solid {Colors.BORDER_DARK};
            border-radius: {_R}px;
            background: transparent;
        }}
        {cls_name}:hover {{
            border-color: {Colors.BORDER_HOVER};
        }}
    """


def _card_qss_selected(cls_name):
    return f"""
        {cls_name} {{
            border: 1px solid {Colors.PRIMARY};
            border-radius: {_R}px;
            background: transparent;
        }}
    """


def place_pill(
    text,
    parent,
    *,
    top=None,
    bottom=None,
    left=None,
    right=None,
    style=None,
    pw=None,
    ph=None,
):
    pill = QLabel(text, parent)
    pill.setStyleSheet(style or _PILL)
    pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
    pill.adjustSize()
    pw = pw or parent.maximumWidth()
    ph = ph or parent.maximumHeight()
    if pw > 10000:
        pw = _CONTENT_W
    if ph > 10000:
        ph = THUMB_HEIGHT
    x = left if left is not None else (pw - pill.width() - right)
    y = top if top is not None else (ph - pill.height() - bottom)
    pill.move(x, y)
    return pill


def clip_thumbnail(pixmap, w=_CONTENT_W, h=THUMB_HEIGHT):
    """Scale, center-crop, clip top corners rounded, bottom flat."""
    out = QPixmap(w, h)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.moveTo(0, h)
    path.lineTo(0, _R)
    path.quadTo(0, 0, _R, 0)
    path.lineTo(w - _R, 0)
    path.quadTo(w, 0, w, _R)
    path.lineTo(w, h)
    path.closeSubpath()
    p.setClipPath(path)
    sc = pixmap.scaled(
        w,
        h,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    p.drawPixmap(
        0,
        0,
        sc,
        (sc.width() - w) // 2,
        (sc.height() - h) // 2,
        w,
        h,
    )
    p.end()
    return out


def _apply_thumb(thumb_label, pixmap):
    if pixmap is None or pixmap.isNull():
        return None
    clipped = clip_thumbnail(pixmap)
    thumb_label.setPixmap(clipped)
    thumb_label.setStyleSheet("background: transparent;")
    return clipped


class Card(QFrame):
    """Base card widget: thumbnail image on top, subtitle and title below."""

    clicked = Signal(object)
    double_clicked = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected = False
        self._pixmap = None

        cls_name = type(self).__name__
        self._qss_normal = _card_qss(cls_name)
        self._qss_selected = _card_qss_selected(cls_name)

        self.setFixedWidth(CARD_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(self._qss_normal)

        lay = QVBoxLayout(self)
        lay.setSpacing(0)
        lay.setContentsMargins(0, 0, 0, 0)

        self._img = QWidget()
        self._img.setFixedSize(_CONTENT_W, THUMB_HEIGHT)
        self._img.setStyleSheet("background: transparent;")
        self._thumb = QLabel(self._img)
        self._thumb.setFixedSize(_CONTENT_W, THUMB_HEIGHT)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setStyleSheet(
            f"background: {Colors.BG_TERTIARY}; "
            f"border-top-left-radius: {_R}px; "
            f"border-top-right-radius: {_R}px;"
        )
        lay.addWidget(self._img)

        txt = QWidget()
        txt.setFixedHeight(_TEXT_H)
        txt.setStyleSheet("background: transparent;")
        tl = QVBoxLayout(txt)
        tl.setSpacing(1)
        tl.setContentsMargins(8, 4, 8, 6)

        self._sub = QLabel("")
        self._sub.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px;")
        self._sub.setAlignment(Qt.AlignmentFlag.AlignLeft)
        tl.addWidget(self._sub)

        self._title = QLabel("")
        self._title.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 12px; font-weight: 600;"
        )
        self._title.setWordWrap(True)
        self._title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        tl.addWidget(self._title)

        tl.addStretch(1)
        lay.addWidget(txt)

    def set_thumbnail(self, pixmap):
        self._pixmap = _apply_thumb(self._thumb, pixmap)

    def set_selected(self, sel):
        if self._selected == sel:
            return
        self._selected = sel
        self.setStyleSheet(self._qss_selected if sel else self._qss_normal)

    def is_selected(self):
        return self._selected

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self)
        ev.accept()

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self)
        ev.accept()


class FlowLayout:
    """Position cards manually via ``move()`` for O(n) performance.

    Cards are placed as absolute-positioned children of the parent widget.
    The parent's minimum height is set to contain all rows.
    """

    _SPACING = 10
    _MARGIN = 10

    def __init__(self, parent_widget, card_width=CARD_WIDTH, card_height=None):
        self._parent = parent_widget
        self._card_w = card_width
        self._card_h = card_height or (THUMB_HEIGHT + _TEXT_H)
        self._items = []
        self._cols = 0

    def build(self, cards, container_width):
        """Place all cards using manual positioning."""
        self._items = list(cards)
        self._reposition(container_width, show_all=True)

    def clear(self):
        self._items.clear()

    def reflow(self, container_width):
        cols = max(
            1, (container_width - 2 * self._MARGIN) // (self._card_w + self._SPACING)
        )
        if cols == self._cols:
            return
        self._reposition(container_width)

    def reflow_visibility(self, container_width):
        self._reposition(container_width)

    def _reposition(self, container_width, show_all=False):
        cols = max(
            1, (container_width - 2 * self._MARGIN) // (self._card_w + self._SPACING)
        )
        self._cols = cols

        grid_width = cols * self._card_w + (cols - 1) * self._SPACING
        x_offset = max(self._MARGIN, (container_width - grid_width) // 2)

        row_idx = 0
        col_idx = 0
        for card in self._items:
            if not show_all and card.isHidden():
                continue
            x = x_offset + col_idx * (self._card_w + self._SPACING)
            y = self._MARGIN + row_idx * (self._card_h + self._SPACING)
            card.move(x, y)
            card.show()
            col_idx += 1
            if col_idx >= cols:
                col_idx = 0
                row_idx += 1

        total_rows = row_idx + (1 if col_idx > 0 else 0)
        total_h = 2 * self._MARGIN + total_rows * (self._card_h + self._SPACING)
        self._parent.setMinimumHeight(max(total_h, 0))
