from qtpy.QtCore import Signal
from qtpy.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QLabel, QFrame
from ..icons import icon_pixmap
from ..stylesheets import Colors


class SearchWidget(QWidget):
    """
    Search widget with icon and clear button. Emits
    searchTextChanged signal when text changes.
    """

    searchTextChanged = Signal(str)

    def __init__(self, placeholder="Search...", parent=None):
        super().__init__(parent)
        self.setup_ui(placeholder)

    def setup_ui(self, placeholder):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        container = QFrame()
        container.setFixedHeight(Colors.WIDGET_HEIGHT)
        container.setStyleSheet(
            f"""
            QFrame {{
                border: 1px solid {Colors.BORDER_DARK};
                border-radius: {Colors.RADIUS}px;
                background-color: transparent;
            }}
            QFrame:hover {{
                border: 1px solid {Colors.BORDER_HOVER};
            }}
            QFrame:hover:!focus {{
                border: 1px solid {Colors.BORDER_HOVER};
            }}
            QFrame:focus-within {{
                border: 1px solid {Colors.PRIMARY};
            }}
        """
        )
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(6, 0, 0, 0)
        container_layout.setSpacing(4)

        icon_label = QLabel()
        icon_label.setPixmap(icon_pixmap("ph.magnifying-glass", 16, role="muted"))
        icon_label.setFixedSize(16, 16)
        icon_label.setStyleSheet("border: none;")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(placeholder)
        self.search_input.setClearButtonEnabled(False)
        self.search_input.textChanged.connect(self.searchTextChanged.emit)
        self.search_input.setStyleSheet(
            """
            QLineEdit {
                border: none;
                padding: 4px 4px;
                background-color: transparent;
            }
        """
        )

        container_layout.addWidget(icon_label)
        container_layout.addWidget(self.search_input)
        layout.addWidget(container)

    def _on_theme_changed(self):
        """Re-apply stylesheet and re-create icon after a theme switch."""
        self.findChild(QFrame).setStyleSheet(
            f"""
            QFrame {{
                border: 1px solid {Colors.BORDER_DARK};
                border-radius: {Colors.RADIUS}px;
                background-color: transparent;
            }}
            QFrame:focus-within {{
                border: 1px solid {Colors.PRIMARY};
            }}
        """
        )
        icon_label = self.findChild(QLabel)
        if icon_label is not None:
            icon_label.setPixmap(icon_pixmap("ph.magnifying-glass", 16, role="muted"))

    def text(self):
        """Get current search text."""
        return self.search_input.text()

    def clear(self):
        """Clear search text."""
        self.search_input.clear()

    def setFocus(self):
        """Set focus to search input."""
        self.search_input.setFocus()
