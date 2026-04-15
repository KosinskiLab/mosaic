"""
Object browser sidebar.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtCore import Qt
from qtpy.QtGui import QColor, QPalette
from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QSizePolicy,
    QSplitter,
)

from ..stylesheets import Colors
from .search_widget import SearchWidget


class ObjectBrowserSidebar(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._widgets = {}
        self._labels = {}

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(8, 8, 8, 0)
        self._lay.setSpacing(8)

        self.search_widget = SearchWidget(placeholder="Search objects...")
        self.search_widget.searchTextChanged.connect(self._filter_objects)
        self._lay.addWidget(self.search_widget)

        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.setHandleWidth(0)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setStyleSheet("background: transparent; border: none;")
        self._lay.addWidget(self._splitter, 1)

        self.setMinimumWidth(190)
        self.setMaximumWidth(260)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._apply_styling()

    def add_widget(self, title, widget):
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        box_lay = QVBoxLayout(box)
        box_lay.setContentsMargins(0, 0, 0, 0)
        box_lay.setSpacing(2)

        label = QLabel(title)
        self._style_label(label)
        box_lay.addWidget(label)
        box_lay.addWidget(widget, 1)

        self._splitter.addWidget(box)
        self._labels[title] = label
        self._widgets[title] = widget

    def _style_label(self, label):
        label.setStyleSheet(
            f"""
            font-size: 12px; font-weight: 600;
            color: {Colors.TEXT_MUTED};
            padding: 8px 0px 4px 0px;
            border-right: 1px solid {Colors.BORDER_DARK};
            background: transparent;
        """
        )

    def _apply_styling(self):
        self.setStyleSheet(
            f"ObjectBrowserSidebar {{ background-color: {Colors.BG_SECONDARY}; }}"
        )

    def _on_theme_changed(self):
        self._apply_styling()
        self.update()
        for label in self._labels.values():
            self._style_label(label)

    def _filter_objects(self, text):
        lower = text.lower()
        for widget in self._widgets.values():
            if hasattr(widget, "tree_widget"):
                tree = widget.tree_widget
                for i in range(tree.topLevelItemCount()):
                    self._filter_item(tree.topLevelItem(i), lower)

    def _filter_item(self, item, text):
        if not text:
            item.setHidden(False)
            for i in range(item.childCount()):
                self._filter_item(item.child(i), text)
            return
        try:
            name = item.text().lower()
        except TypeError:
            name = item.text(0).lower()
        matches = text in name
        visible_child = False
        for i in range(item.childCount()):
            child = item.child(i)
            self._filter_item(child, text)
            if not child.isHidden():
                visible_child = True
        item.setHidden(not matches and not visible_child)
