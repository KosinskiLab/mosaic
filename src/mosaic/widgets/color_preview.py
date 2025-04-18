""" ColorPreviewWidget widget for visualization of color maps.

    Copyright (c) 2025 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtWidgets import QWidget
from qtpy.QtGui import QColor, QPainter


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
