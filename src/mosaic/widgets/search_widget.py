from qtpy.QtCore import Signal
from qtpy.QtWidgets import QWidget, QHBoxLayout, QLineEdit
import qtawesome as qta


class SearchWidget(QWidget):
    """
    Reusable search widget with icon and clear button.

    Emits searchTextChanged signal when text changes.
    """

    searchTextChanged = Signal(str)

    def __init__(self, placeholder="Search...", parent=None):
        super().__init__(parent)
        self.setup_ui(placeholder)

    def setup_ui(self, placeholder):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(placeholder)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.searchTextChanged.emit)

        search_icon = qta.icon("mdi.magnify", color="#6b7280")
        self.search_input.addAction(
            search_icon, QLineEdit.ActionPosition.LeadingPosition
        )
        self.search_input.setStyleSheet(
            """
            QLineEdit {
                border: 1px solid #d1d5db;
                border-radius: 4px;
                padding: 6px 8px 6px 32px;
                background-color: transparent;
            }
            QLineEdit:focus {
                outline: none;
                border: 1px solid #4f46e5;
            }
        """
        )

        layout.addWidget(self.search_input)

    def text(self):
        """Get current search text."""
        return self.search_input.text()

    def clear(self):
        """Clear search text."""
        self.search_input.clear()

    def setFocus(self):
        """Set focus to search input."""
        self.search_input.setFocus()
