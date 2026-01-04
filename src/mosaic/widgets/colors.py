"""
Widgets for visualization of color maps.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import Dict, List, Optional

from qtpy.QtCore import Qt, Signal, QPointF, QRect
from qtpy.QtGui import QColor, QPainter, QLinearGradient, QPen
from qtpy.QtWidgets import (
    QWidget,
    QPushButton,
    QColorDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QWidgetAction,
)
import qtawesome as qta

from ..stylesheets import Colors, QPushButton_style

__all__ = [
    "ColorMapSelector",
    "ColorSwatch",
    "ColorPickerRow",
    "generate_gradient_colors",
]

# Default colormap categories
DEFAULT_COLORMAP_CATEGORIES: Dict[str, List[str]] = {
    "Sequential": [
        "viridis",
        "plasma",
        "magma",
        "inferno",
        "cividis",
        "turbo",
        "jet",
    ],
    "Diverging": [
        "coolwarm",
        "RdBu",
        "RdYlBu",
        "seismic",
        "bwr",
    ],
    "Cyclic": [
        "twilight",
        "hsv",
    ],
    "Categorical": [
        "Dark2",
        "Set1",
        "Set2",
        "Set3",
        "tab10",
        "Paired",
        "Accent",
    ],
}


def generate_gradient_colors(cmap_name: str, n_colors: int = 10) -> List[QColor]:
    """Generate a list of QColors from a matplotlib colormap."""
    from ..utils import get_cmap

    cmap = get_cmap(cmap_name)
    count = min(n_colors + 1, cmap.N)

    colors = []
    for i in range(count):
        pos = int(cmap.N * i / (count - 1))
        colors.append(QColor(*(int(x * 255) for x in cmap(pos))))
    return colors


class ColormapMenuItem(QWidget):
    """A menu item widget showing colormap name and gradient preview."""

    clicked = Signal(str)

    def __init__(self, cmap_name: str, parent=None):
        super().__init__(parent)
        self.cmap_name = cmap_name
        self.setFixedHeight(26)
        self.setMinimumWidth(180)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def mousePressEvent(self, event):
        self.clicked.emit(self.cmap_name)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        from qtpy.QtGui import QBrush, QPainterPath

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()

        # Draw hover background matching QMenu::item:selected
        # Use underMouse() for reliable hover detection with QWidgetAction
        if self.underMouse():
            path = QPainterPath()
            path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(), 4, 4)

            hover_color = QColor(0, 0, 0, 15)
            painter.fillPath(path, QBrush(hover_color))

            # Add border matching QMenu::item:selected
            pen = QPen(QColor(0, 0, 0, 20))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawPath(path)

        painter.setPen(self.palette().text().color())

        # Draw colormap name with padding matching QMenu::item (padding: 4px 12px)
        text_rect = QRect(12, 0, rect.width() - 120, rect.height())
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.cmap_name,
        )

        # Draw gradient preview
        gradient_rect = QRect(rect.width() - 108, 5, 100, rect.height() - 10)
        colors = generate_gradient_colors(self.cmap_name, 10)

        gradient = QLinearGradient(
            QPointF(gradient_rect.left(), gradient_rect.top()),
            QPointF(gradient_rect.right(), gradient_rect.top()),
        )
        for i, color in enumerate(colors):
            gradient.setColorAt(i / (len(colors) - 1), color)

        painter.fillRect(gradient_rect, gradient)

        pen = QPen(self.palette().mid().color())
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRect(gradient_rect)

        painter.end()


class ColorMapSelector(QPushButton):
    """A button that opens a hierarchical menu for selecting colormaps."""

    colormapChanged = Signal(str)

    def __init__(
        self,
        categories: Optional[Dict[str, List[str]]] = None,
        default: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)

        self._categories = categories or DEFAULT_COLORMAP_CATEGORIES
        self._current_cmap = default or "viridis"

        self._setup_ui()
        self._build_menu()

    def _setup_ui(self):
        self.setStyleSheet(
            QPushButton_style
            + """
            QPushButton:focus {
                outline: none;
            }
            QPushButton::menu-indicator {
                image: none;
                width: 0;
            }
        """
        )
        self._update_text()

    def _update_text(self):
        """Trigger repaint when colormap changes."""
        self.update()

    def _build_menu(self):
        """Build the hierarchical menu with category submenus."""
        menu = QMenu(self)

        for category, colormaps in self._categories.items():
            submenu = QMenu(category, menu)

            for cmap_name in colormaps:
                action = QWidgetAction(submenu)
                item = ColormapMenuItem(cmap_name)
                item.clicked.connect(self._on_colormap_selected)
                item.clicked.connect(menu.close)
                action.setDefaultWidget(item)
                submenu.addAction(action)

            menu.addMenu(submenu)

        self.setMenu(menu)

    def _on_colormap_selected(self, cmap_name: str):
        """Handle colormap selection."""
        self._current_cmap = cmap_name
        self._update_text()
        self.colormapChanged.emit(cmap_name)

    def currentText(self) -> str:
        """Get the currently selected colormap name."""
        return self._current_cmap

    def setCurrentText(self, cmap_name: str):
        """Set the current colormap by name."""
        self._current_cmap = cmap_name
        self._update_text()

    def paintEvent(self, event):
        """Draw default button, then add text and gradient preview overlay."""
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        padding = 8
        spacing = 12

        # Measure text width to allocate appropriate space
        font_metrics = painter.fontMetrics()
        text_width = font_metrics.horizontalAdvance(self._current_cmap)
        text_area_width = text_width + padding

        # Draw colormap name with proper left padding
        text_rect = QRect(padding, 0, text_area_width, rect.height())
        painter.setPen(self.palette().text().color())
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._current_cmap,
        )

        # Draw gradient preview filling the remaining space
        gradient_left = text_area_width + spacing
        gradient_width = rect.width() - gradient_left - padding
        gradient_rect = QRect(
            gradient_left, 5, max(gradient_width, 40), rect.height() - 10
        )
        colors = generate_gradient_colors(self._current_cmap, 10)

        gradient = QLinearGradient(
            QPointF(gradient_rect.left(), gradient_rect.top()),
            QPointF(gradient_rect.right(), gradient_rect.top()),
        )
        for i, color in enumerate(colors):
            gradient.setColorAt(i / (len(colors) - 1), color)

        painter.fillRect(gradient_rect, gradient)
        painter.end()


class ColorSwatch(QWidget):
    """A clickable color swatch."""

    clicked = Signal()

    def __init__(self, color: tuple, size: int = 28, parent=None):
        super().__init__(parent)
        self.color = color
        self.selected = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_selected(self, selected: bool):
        """Set the selected state."""
        self.selected = selected
        self.update()

    def set_color(self, color: tuple):
        """Set the swatch color."""
        self.color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw color fill
        r, g, b = [int(c * 255) for c in self.color]
        painter.setBrush(QColor(r, g, b))

        if self.selected:
            pen = QPen(QColor(Colors.TEXT_PRIMARY))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRoundedRect(2, 2, self.width() - 4, self.height() - 4, 4, 4)
        else:
            pen = QPen(QColor(Colors.BORDER_DARK))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 4, 4)

    def mousePressEvent(self, event):
        self.clicked.emit()


class ColorPickerRow(QWidget):
    """A row with color swatches and custom color picker."""

    colorChanged = Signal(tuple)

    # Curated preset colors - muted tones plus common defaults
    DEFAULT_PRESETS = [
        (0.70, 0.70, 0.70),  # Neutral gray
        (0.80, 0.20, 0.20),  # Default red
        (0.20, 0.40, 0.80),  # Model highlight blue
        (0.45, 0.62, 0.45),  # Sage green
        (0.80, 0.70, 0.45),  # Sand/wheat
        (0.58, 0.45, 0.62),  # Dusty lavender
    ]

    def __init__(
        self,
        label: str,
        default_color: tuple = (0.7, 0.7, 0.7),
        preset_colors: list = None,
        parent=None,
    ):
        super().__init__(parent)
        self.current_color = default_color
        self.preset_colors = (
            preset_colors if preset_colors is not None else self.DEFAULT_PRESETS
        )
        self.swatches = []
        self._setup_ui(label)
        self._update_selection()

    def _setup_ui(self, label: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Label
        label_widget = QLabel(label)
        label_widget.setStyleSheet(
            f"""
            QLabel {{
                font-size: 13px;
                color: {Colors.TEXT_PRIMARY};
            }}
        """
        )
        layout.addWidget(label_widget)

        # Swatches row
        swatches_layout = QHBoxLayout()
        swatches_layout.setContentsMargins(0, 0, 0, 0)
        swatches_layout.setSpacing(6)

        for color in self.preset_colors:
            swatch = ColorSwatch(color)
            swatch.clicked.connect(lambda c=color: self._select_color(c))
            self.swatches.append(swatch)
            swatches_layout.addWidget(swatch)

        swatches_layout.addStretch()

        # Custom color button
        self.custom_btn = QPushButton("Custom")
        self.custom_btn.setIcon(qta.icon("ph.eyedropper", color=Colors.ICON))
        self.custom_btn.setStyleSheet(QPushButton_style)
        self.custom_btn.setFixedHeight(28)
        self.custom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.custom_btn.clicked.connect(self._open_color_dialog)
        swatches_layout.addWidget(self.custom_btn)

        layout.addLayout(swatches_layout)

    def _select_color(self, color: tuple):
        """Select a preset color."""
        self.current_color = color
        self._update_selection()
        self.colorChanged.emit(color)

    def _update_selection(self):
        """Update swatch selection states."""
        for swatch in self.swatches:
            # Check if colors are close enough (floating point comparison)
            is_match = all(
                abs(a - b) < 0.01 for a, b in zip(swatch.color, self.current_color)
            )
            swatch.set_selected(is_match)

    def _open_color_dialog(self):
        """Open the custom color picker dialog."""
        r, g, b = [int(c * 255) for c in self.current_color]
        color = QColorDialog.getColor(QColor(r, g, b), self)
        if color.isValid():
            new_color = (color.red() / 255, color.green() / 255, color.blue() / 255)
            self.current_color = new_color
            self._update_selection()
            self.colorChanged.emit(new_color)

    def get_color(self) -> tuple:
        """Get the current color as (r, g, b) floats."""
        return self.current_color

    def set_color(self, color: tuple):
        """Set the current color."""
        self.current_color = color
        self._update_selection()
