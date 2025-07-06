"""
ColorPreviewWidget widget for visualization of color maps.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtCore import Signal
from qtpy.QtGui import QColor, QPainter
from qtpy.QtWidgets import QWidget, QPushButton, QColorDialog


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
