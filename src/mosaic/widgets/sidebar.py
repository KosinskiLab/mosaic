from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QToolButton,
    QLabel,
    QFrame,
    QSizePolicy,
    QScrollArea,
)
import qtawesome as qta


class ChevronButton(QToolButton):
    def __init__(self, direction="right", parent=None):
        """Initialize a chevron button with specified direction."""
        super().__init__(parent)
        self.direction = direction
        self.setFixedSize(24, 24)
        self.setStyleSheet(
            """
            QToolButton {
                border: none;
                background-color: transparent;
            }
            QToolButton:hover {
                background-color: rgba(0, 0, 0, 0.05);
                border-radius: 12px;
            }
        """
        )
        self._update_icon()

    def set_direction(self, direction):
        """Change the direction of the chevron."""
        self.direction = direction
        self._update_icon()

    def _update_icon(self):
        self.setIcon(qta.icon("fa5s.chevron-right", color="#696c6f"))
        if self.direction == "left":
            self.setIcon(qta.icon("fa5s.chevron-left", color="#696c6f"))
        elif self.direction == "up":
            self.setIcon(qta.icon("fa5s.chevron-up", color="#696c6f"))
        elif self.direction == "down":
            self.setIcon(qta.icon("fa5s.chevron-down", color="#696c6f"))
        return None


class ObjectBrowserSidebarSection(QWidget):
    """A simple section with a header that can contain any widget."""

    def __init__(self, title: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.title = title

        # Main layout with no spacing or margins
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create compact header
        header_frame = QFrame()
        header_frame.setObjectName("sectionHeader")
        header_frame.setFixedHeight(26)  # Compact fixed height

        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(8, 0, 8, 0)  # Horizontal padding only

        # Simple title label
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")

        header_layout.addWidget(title_label)
        header_layout.addStretch()

        # Content widget container
        self.content_widget = QWidget()
        self.content_widget.setObjectName("sectionContent")

        # Content layout with no margins
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

        # Add components to main layout
        layout.addWidget(header_frame)
        layout.addWidget(self.content_widget, 1)  # Give content stretch priority

    def addWidget(self, widget):
        """Add a widget to the content layout."""
        self.content_layout.addWidget(widget)


class ObjectBrowserSidebar(QWidget):
    """
    Simplified sidebar component for Mosaic.
    Provides direct widget support for maximum flexibility.
    """

    visibility_changed = pyqtSignal(bool)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.visible = True
        self.collapsed = False
        self.sections = {}

        # Setup UI
        self._setup_ui()
        self._setup_styling()

        # Setup animation
        self.animation = QPropertyAnimation(self, b"maximumWidth")
        self.animation.setDuration(200)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.animation.valueChanged.connect(self._update_width)

    def _update_width(self, width):
        """Update the sidebar width during animation."""
        show_content = width > 50
        if hasattr(self, "title_label"):
            self.title_label.setVisible(show_content)

        if hasattr(self, "scroll_area"):
            self.scroll_area.setVisible(show_content)

    def _setup_ui(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header section
        self.header = QWidget()
        self.header.setObjectName("sidebarHeader")
        self.header.setFixedHeight(40)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(10, 8, 10, 8)

        self.title_label = QLabel()
        self.title_label.setObjectName("panelTitle")
        self.collapse_btn = ChevronButton("left")
        self.collapse_btn.clicked.connect(self.toggle_collapse)

        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.collapse_btn)
        main_layout.addWidget(self.header)

        # Content scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setObjectName("scrollArea")

        # Content widget
        self.content_widget = QWidget()
        self.content_widget.setMinimumWidth(100)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(6, 6, 6, 6)
        self.content_layout.setSpacing(10)

        self.scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll_area, 1)
        main_layout.setStretchFactor(self.scroll_area, 1)
        main_layout.addStretch(0)

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

    def _setup_styling(self):
        """Set up the widget styling."""
        self.setStyleSheet(
            """
            QLabel {
                background-color: transparent;
            }

            /* Header styling with border-bottom */
            #sidebarHeader {
                background-color: transparent;
                border-bottom: 1px solid #6b7280;
            }

            #panelTitle {
                font-weight: 600;
                font-size: 13px;
            }

            /* Section styling */
            #sectionHeader {
                background-color: #1a000000;
                border-radius: 4px;
            }

            #sectionContent {
                background-color: transparent;
            }

            #sectionTitle {
                font-weight: 500;
                font-size: 13px;
            }

            /* Item styling */
            #selectedItem {
                background-color: #eef2ff;
                border-radius: 4px;
            }

            #normalItem {
                background-color: transparent;
                border-radius: 4px;
            }

            #normalItem:hover {
                background-color: #f5f5f5;
            }

            #visibilityDot[status="visible"] {
                background-color: #34d399;
                border-radius: 5px;
            }

            #visibilityDot[status="hidden"] {
                background-color: #9ca3af;
                border-radius: 5px;
            }

            #metadataLabel {
                color: #6b7280;
                font-size: 10px;
            }

            /* Content area */
            #scrollArea {
                background-color: transparent;
                border: none;
            }

            #contentWidget {
                background-color: transparent;
            }

            QScrollArea {
                border: none;
            }

            QScrollBar:vertical {
                border: none;
                background: #f1f1f1;
                width: 6px;
                margin: 0px;
            }

            QScrollBar::handle:vertical {
                background: #c1c1c1;
                min-height: 20px;
                border-radius: 3px;
            }

            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }

            QScrollBar:horizontal {
                height: 0px;
                background: transparent;
            }
        """
        )

    def add_widget(self, section_id: str, title: str, widget: QWidget) -> QWidget:
        """Add a widget wrapped in a section with header to the sidebar."""
        section = ObjectBrowserSidebarSection(title)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        section.addWidget(widget)

        for i in range(self.content_layout.count()):
            item = self.content_layout.itemAt(i)
            if item and item.spacerItem():
                self.content_layout.removeItem(item)

        self.content_layout.addWidget(section, 1)
        self.content_layout.addStretch(0)

        self.sections[section_id] = section

        return widget

    def clear_sections(self):
        """Remove all sections."""
        for section_id in list(self.sections.keys()):
            self.remove_section(section_id)

    def toggle_collapse(self):
        """Toggle between collapsed and expanded states with animation."""
        container = self.content_widget
        if not self.collapsed:
            self.previous_width = container.width()

        start, stop, direction = container.width(), 40, "right"
        if self.collapsed:
            start, stop, direction = 40, self.previous_width, "left"

        self.collapsed = not self.collapsed
        self.animation.setStartValue(start)
        self.animation.setEndValue(stop)

        self.animation.start()
        self.collapse_btn.set_direction(direction)
        self.visibility_changed.emit(self.collapsed)

    def set_title(self, title: str):
        """Set the sidebar title."""
        self.title_label.setText(title)
