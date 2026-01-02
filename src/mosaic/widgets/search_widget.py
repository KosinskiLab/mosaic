from qtpy.QtCore import Signal
from qtpy.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QLabel, QFrame
import qtawesome as qta

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
        container.setStyleSheet(
            """
            QFrame {
                border: 1px solid #d1d5db;
                border-radius: 4px;
                background-color: transparent;
            }
            QFrame:focus-within {
                border: 1px solid #4f46e5;
            }
        """
        )
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(6, 0, 0, 0)
        container_layout.setSpacing(4)

        icon_label = QLabel()
        icon_label.setPixmap(
            qta.icon("ph.magnifying-glass", color=Colors.ICON).pixmap(16, 16)
        )
        icon_label.setFixedSize(16, 16)
        icon_label.setStyleSheet("border: none;")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(placeholder)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.searchTextChanged.emit)
        self.search_input.setStyleSheet(
            """
            QLineEdit {
                border: none;
                padding: 6px 4px;
                background-color: transparent;
            }
        """
        )

        container_layout.addWidget(icon_label)
        container_layout.addWidget(self.search_input)
        layout.addWidget(container)

    def text(self):
        """Get current search text."""
        return self.search_input.text()

    def clear(self):
        """Clear search text."""
        self.search_input.clear()

    def setFocus(self):
        """Set focus to search input."""
        self.search_input.setFocus()
