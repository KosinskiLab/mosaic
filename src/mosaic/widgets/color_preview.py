"""
ColorPreviewWidget widget for visualization of color maps.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import List

from qtpy.QtCore import Qt, Signal, QPointF
from qtpy.QtGui import QColor, QPainter, QLinearGradient
from qtpy.QtWidgets import (
    QWidget,
    QPushButton,
    QColorDialog,
    QStyledItemDelegate,
    QComboBox,
)


class ColorPreview(QComboBox):
    def __init__(self, colormaps: List[str], *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.set_colormaps(colormaps)
        delegate = ColormapItemDelegate(self)
        self.setItemDelegate(delegate)

    def set_colormaps(self, colormaps: List[str]):
        self.clear()
        self.addItems(colormaps)

    def generate_gradient(self, cmap_name: str, n_colors: int = None):
        from ..utils import get_cmap

        cmap = get_cmap(cmap_name)

        count = cmap.N
        if n_colors is not None:
            count = min(n_colors + 1, count)

        ret = []
        for i in range(count):
            pos = int(cmap.N * i / (count - 1))
            ret.append(QColor(*(int(x * 255) for x in cmap(pos))))
        return ret


class ColormapItemDelegate(QStyledItemDelegate):
    """Custom delegate to show colormap preview in combobox items"""

    def __init__(self, color_preview: ColorPreview):
        super().__init__(color_preview)
        self.color_preview = color_preview

    def paint(self, painter, option, index):
        super().paint(painter, option, index)

        colormap_name = index.data(Qt.ItemDataRole.DisplayRole)

        rect = option.rect
        gradient_rect = rect.adjusted(rect.width() - 110, 3, -5, -3)
        colors = self.color_preview.generate_gradient(colormap_name, 10)

        gradient = QLinearGradient(
            QPointF(gradient_rect.left(), gradient_rect.top()),
            QPointF(gradient_rect.right(), gradient_rect.top()),
        )
        for i, color in enumerate(colors):
            gradient.setColorAt(i / (len(colors) - 1), color)

        painter.save()
        painter.fillRect(gradient_rect, gradient)
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), 26))
        return size


class ColorPreviewWidget(QWidget):
    """Widget to display color map preview"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(20)
        self.setMaximumHeight(20)
        self.colors = self.generate_gradient("viridis")

        self.colormaps = [
            "viridis",
            "plasma",
            "magma",
            "inferno",
            "cividis",
            "turbo",
            "jet",
            "coolwarm",
            "RdBu",
            "RdYlBu",
        ]

    def generate_gradient(self, cmap_name: str, n_colors: int = None):
        from ..utils import get_cmap

        cmap = get_cmap(cmap_name)

        count = cmap.N
        if n_colors is not None:
            count = min(n_colors + 1, count)

        ret = []
        for i in range(count):
            pos = int(cmap.N * i / (count - 1))
            ret.append(QColor(*(int(x * 255) for x in cmap(pos))))
        return ret

    def set_colormap(self, cmap_name, reverse=False):
        if reverse:
            cmap_name = f"{cmap_name}_r"
        self.colors = self.generate_gradient(cmap_name)
        self.update()

    def paintEvent(self, event):
        if len(self.colors) <= 0:
            return None

        painter = QPainter(self)
        width = self.width()
        height = self.height()

        color_count = len(self.colors)
        stripe_width = width / len(self.colors)
        for i, color in enumerate(self.colors):
            x_pos = int(i * stripe_width)
            next_x = int((i + 1) * stripe_width) if i < color_count - 1 else width
            rect_width = next_x - x_pos
            painter.fillRect(x_pos, 0, rect_width, height, color)


class ColorButton(QPushButton):
    """Widget to select color"""

    colorChanged = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.update_color((0, 0, 0))
        self.clicked.connect(self.choose_color)

    def update_color(self, color):
        self.current_color = [int(float(c) * 255) for c in color]
        rgb = ",".join([str(x) for x in self.current_color])
        self.setStyleSheet(f"background-color: rgb({rgb})")
        self.colorChanged.emit()

    def choose_color(self):
        color = QColor(*self.current_color)
        color_dialog = QColorDialog.getColor(initial=color, parent=self)
        if color_dialog.isValid():
            color = (
                color_dialog.red() / 255,
                color_dialog.green() / 255,
                color_dialog.blue() / 255,
            )
            self.update_color(color)
        return color

    def get_color(self, uint8: bool = False):
        if uint8:
            return self.current_color
        return [x / 255 for x in self.current_color]
