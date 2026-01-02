from typing import Optional

from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QSizePolicy,
    QScrollArea,
)

from .search_widget import SearchWidget
from ..stylesheets import Colors


class ObjectBrowserSidebarSection(QWidget):
    """A simple section with a header that can contain any widget."""

    def __init__(self, title: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.title = title

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header_frame = QFrame()
        header_frame.setObjectName("sectionHeader")
        header_frame.setFixedHeight(26)

        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(8, 0, 8, 0)

        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")

        header_layout.addWidget(title_label)
        header_layout.addStretch()

        self.content_widget = QWidget()
        self.content_widget.setObjectName("sectionContent")

        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

        layout.addWidget(header_frame)
        layout.addWidget(self.content_widget, 1)

    def addWidget(self, widget):
        """Add a widget to the content layout."""
        self.content_layout.addWidget(widget)


class ObjectBrowserSidebar(QWidget):
    """
    Simplified sidebar component for Mosaic.
    Provides direct widget support for maximum flexibility.
    """

    visibility_changed = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.sections = {}

        self._setup_ui()
        self._setup_styling()

    def _setup_ui(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header section with title and search
        self.header = QWidget()
        self.header.setObjectName("sidebarHeader")
        header_layout = QVBoxLayout(self.header)
        header_layout.setContentsMargins(10, 10, 10, 10)
        header_layout.setSpacing(8)

        self.title_label = QLabel()
        self.title_label.setObjectName("panelTitle")

        self.search_widget = SearchWidget(placeholder="Search objects...")
        self.search_widget.searchTextChanged.connect(self._filter_objects)

        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.search_widget)
        header_layout.addStretch()
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
            f"""
            QLabel {{
                background-color: transparent;
            }}

            /* Header styling with border-bottom */
            #sidebarHeader {{
                background-color: transparent;
                border-bottom: 1px solid {Colors.BORDER_DARK};
            }}

            #panelTitle {{
                font-weight: 500;
                font-size: 13px;
            }}

            /* Section styling - minimal */
            #sectionHeader {{
                background-color: transparent;
            }}

            #sectionContent {{
                background-color: transparent;
            }}

            #sectionTitle {{
                font-weight: 500;
                font-size: 12px;
            }}

            /* Item styling */
            #selectedItem {{
                background-color: rgba(79, 70, 229, 0.08);
                border-radius: 4px;
            }}

            #normalItem {{
                background-color: transparent;
                border-radius: 4px;
            }}

            #normalItem:hover {{
                background-color: {Colors.BG_HOVER};
            }}

            #visibilityDot[status="visible"] {{
                background-color: {Colors.SUCCESS};
                border-radius: 5px;
            }}

            #visibilityDot[status="hidden"] {{
                background-color: {Colors.ICON_MUTED};
                border-radius: 5px;
            }}

            #metadataLabel {{
                color: {Colors.TEXT_MUTED};
                font-size: 10px;
            }}

            /* Content area */
            #scrollArea {{
                background-color: transparent;
                border: none;
            }}

            #contentWidget {{
                background-color: transparent;
            }}

            QScrollArea {{
                border: none;
            }}

            QScrollBar:vertical {{
                border: none;
                background: {Colors.BG_TERTIARY};
                width: 6px;
                margin: 0px;
            }}

            QScrollBar::handle:vertical {{
                background: {Colors.ICON_MUTED};
                min-height: 20px;
                border-radius: 3px;
            }}

            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}

            QScrollBar:horizontal {{
                height: 0px;
                background: transparent;
            }}
        """
        )

    def add_widget(self, section_id: str, title: str, widget: QWidget) -> QWidget:
        """Add a widget wrapped in a section with header to the sidebar."""
        # Add separator line if this is not the first section
        if len(self.sections) > 0:
            separator = QFrame()
            separator.setFrameShape(QFrame.Shape.HLine)
            separator.setFixedHeight(2)
            separator.setStyleSheet(
                """
                QFrame {
                    background: rgba(0, 0, 0, 0.10);
                    border: none;
                    border-radius: 1px;
                    margin-left: 4px;
                    margin-right: 4px;
                }
            """
            )
            self.content_layout.addWidget(separator)

        section = ObjectBrowserSidebarSection(title)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Remove any border styling from the container widget
        widget.setStyleSheet("QFrame { border: none; border-bottom: none; }")

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

    def _filter_objects(self, search_text: str):
        """Filter both cluster and model lists by name."""
        search_lower = search_text.lower()

        for section_id, section in self.sections.items():
            content = section.content_widget
            if not content or not content.layout():
                continue

            # Find the ContainerListWidget inside the content
            for i in range(content.layout().count()):
                item = content.layout().itemAt(i)
                if item is None:
                    continue
                widget = item.widget()
                if widget is not None and hasattr(widget, "tree_widget"):
                    tree = widget.tree_widget
                    self._filter_tree(tree, search_lower)

    def _filter_tree(self, tree, search_text: str):
        """Filter all items in a tree widget."""
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            self._filter_item(item, search_text)

    def _filter_item(self, item, search_text: str):
        """Recursively filter tree items."""
        # If search is empty, show all
        if not search_text:
            item.setHidden(False)
            for i in range(item.childCount()):
                self._filter_item(item.child(i), search_text)
            return

        # Get item name - handle both StyledTreeWidgetItem and GroupTreeWidgetItem
        # StyledTreeWidgetItem.text() takes no args, GroupTreeWidgetItem uses text(0)
        try:
            name = item.text().lower()
        except TypeError:
            name = item.text(0).lower()

        matches = search_text in name

        # For groups, also check children
        child_matches = False
        for i in range(item.childCount()):
            child = item.child(i)
            self._filter_item(child, search_text)
            if not child.isHidden():
                child_matches = True

        # Show if this matches or any child matches
        item.setHidden(not (matches or child_matches))

    def set_title(self, title: str):
        """Set the sidebar title."""
        self.title_label.setText(title)
