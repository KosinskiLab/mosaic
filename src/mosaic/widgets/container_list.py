from uuid import uuid4
from typing import Dict, List
from dataclasses import dataclass, field

from qtpy.QtGui import QColor, QIcon, QPixmap, QPainter
from qtpy.QtCore import Qt, QRect, QByteArray, QItemSelection, QItemSelectionModel
from qtpy.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QApplication,
    QStyledItemDelegate,
    QStyle,
    QAbstractItemView,
)
from qtpy.QtSvg import QSvgRenderer
import qtawesome as qta


@dataclass()
class TreeState:
    """Minimal tree structure tracking."""

    #: {'Group 1': ['uuid1', 'uuid2'], ...}
    groups: Dict[str, List[str]] = field(default_factory=dict)
    #: {'Group 1', 'uuid1', ...}
    root_order: Dict[str, int] = field(default_factory=dict)
    #: ['uuid3', 'uuid4', ...]
    root_items: List[str] = field(default_factory=list)

    def get_all_uuids(self):
        """Get all UUIDs currently in the tree."""
        uuids = set(self.root_items)
        for group_uuids in self.groups.values():
            uuids.update(group_uuids)
        return uuids


class ContainerTreeWidget(QFrame):
    """Drop-in replacement for ContainerListWidget using QTreeWidget for grouping support."""

    def __init__(self, title: str = None, border: bool = True):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title = title
        app = QApplication.instance()
        app.paletteChanged.connect(self.update_style)

        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderHidden(True)
        self.tree_widget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.tree_widget.setIndentation(5)
        self.tree_widget.setAnimated(True)
        self.tree_widget.setRootIsDecorated(False)
        self.tree_widget.setItemsExpandable(True)
        self.tree_widget.setExpandsOnDoubleClick(False)

        self.tree_widget.itemClicked.connect(self._on_item_clicked)

        self.tree_widget.setDragEnabled(False)
        self.tree_widget.setAcceptDrops(True)
        self.tree_widget.setDropIndicatorShown(True)
        self.tree_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

        self.tree_widget.setItemDelegate(MetadataItemDelegate(self.tree_widget))

        self.tree_widget.setStyleSheet(
            """
            QTreeWidget {
                border: none;
                background-color: transparent;
                outline: none;
                padding: 4px 0px;
                font-size: 13px;
            }
            QTreeWidget::item {
                border-radius: 6px;
                border: none;
                padding: 4px 0px;
                margin: 2px 0px;
                outline: none;
            }
            QTreeWidget::item:hover {
                background-color: rgba(0, 0, 0, 0.0);
            }
            QTreeWidget::item:selected {
                background-color: rgba(0, 0, 0, 0.0);
                font-weight: 500;
            }
            QLineEdit {
                background-color: white;
                border: 1px solid #4f46e5;
                border-radius: 6px;
                padding: 0px 3px;
                margin: 0px 8px;
                selection-background-color: rgba(99, 102, 241, 0.6);
                font-size: 13px;
            }
        """
        )

        layout.addWidget(self.tree_widget)
        if border:
            self.update_style()

    def selected_items(self):
        # We specifically omit GroupTreeWidgetItem
        return [
            item
            for item in self.tree_widget.selectedItems()
            if isinstance(item, StyledTreeWidgetItem)
        ]

    def update_style(self):
        return self.setStyleSheet(
            """
            QFrame {
                background-color: transparent;
                border: none;
                border-bottom: 1px solid #6b7280;
            }
        """
        )

    def to_state(self) -> TreeState:
        """Extract current tree structure as TreeState object."""
        state = TreeState()

        for item, parent, _ in self.traverse(reverse=False):

            # GroupTreeWidgetItem structure is evident from parent
            if not isinstance(item, StyledTreeWidgetItem):
                continue

            if (uuid := item.metadata.get("uuid")) is None:
                continue

            group_name = getattr(parent, "group_name", None)

            if parent is None:
                state.root_items.append(uuid)
            elif isinstance(parent, GroupTreeWidgetItem):
                if group_name not in state.groups:
                    state.groups[group_name] = []
                state.groups[group_name].append(uuid)
                uuid = parent.metadata.get("uuid")

            if uuid not in state.root_order:
                state.root_order[uuid] = (len(state.root_order), group_name)

        return state

    def apply_state(self, state: TreeState, uuid_to_items: Dict):
        """Apply tree structure to existing items.

        Parameters
        ----------
        state : :py:class:`TreeState`
            Desired tree structure
        uuid_to_items : dict
            Map of UUID to QTreeWidgetItem
        """
        self.tree_widget.clear()

        order = dict(sorted(state.root_order.items(), key=lambda x: x[1][0]))

        for uuid, (_, group_name) in order.items():
            if group_name is None:
                self.tree_widget.addTopLevelItem(uuid_to_items[uuid])
                continue

            group_item = self.create_group(group_name)
            uuids = [x for x in state.groups.get(group_name, []) if x in uuid_to_items]
            for uuid in uuids:
                group_item.addChild(uuid_to_items[uuid])

    def update(self, uuid_to_items):
        """
        Update tree incrementally based on provided items.

        Parameters
        ----------
        uuid_to_items : dict
            Map from UUID to QTreeWidgetItem to be added/updated
        """
        try:
            self.tree_widget.blockSignals(True)
            existing_uuids = self._process_tree_items(uuid_to_items)
        finally:
            self.tree_widget.blockSignals(False)
        for uuid, item in uuid_to_items.items():
            if uuid in existing_uuids:
                continue
            self.tree_widget.addTopLevelItem(item)

    def _move_items_to_parent(self, items, new_parent):
        """Move items to a new parent (or root if None).

        Parameters
        ----------
        items : list of QTreeWidgetItem
            Items to move
        new_parent : GroupTreeWidgetItem or None
            New parent, or None for root level
        """
        for item in items:
            if old_parent := item.parent():
                old_parent.removeChild(item)
            else:
                index = self.tree_widget.indexOfTopLevelItem(item)
                self.tree_widget.takeTopLevelItem(index)

            if new_parent:
                new_parent.addChild(item)
            else:
                self.tree_widget.addTopLevelItem(item)

    def group_selected(self, group_name: str):
        """Create a new group with currently selected items.

        Parameters
        ----------
        group_name : str
            Name for the new group

        Returns
        -------
        GroupTreeWidgetItem or None
            The created group item, or None if no items selected
        """
        if not (selected_items := self.selected_items()):
            return None

        first_item = selected_items[0]
        insert_index = self.tree_widget.indexOfTopLevelItem(first_item)

        group_item = self.create_group(group_name, insert_index=insert_index)
        try:
            self.tree_widget.blockSignals(True)
            self._move_items_to_parent(selected_items, group_item)
        finally:
            self.tree_widget.blockSignals(False)

        group_item.setExpanded(True)
        self._select_group_children(group_item)
        return group_item

    def ungroup_selected(self) -> int:
        """Move selected items to root level (removing them from their groups).

        Returns
        -------
        int
            Number of items ungrouped
        """
        if not (selected_items := self.selected_items()):
            return 0

        try:
            self.tree_widget.blockSignals(True)
            self._move_items_to_parent(selected_items, None)
        finally:
            self.tree_widget.blockSignals(False)

        self._set_selection(selected_items)
        return len(selected_items)

    def traverse(self, reverse=False):
        """Generator that yields all (item, parent, index) tuples.

        Parameters
        ----------
        reverse : bool
            If True, iterate in reverse order (useful for mutations)
        """
        items = []

        # Collect all items with their metadata
        for i in range(self.tree_widget.topLevelItemCount()):
            item = self.tree_widget.topLevelItem(i)
            items.append((item, None, i))

            if isinstance(item, GroupTreeWidgetItem):
                for j in range(item.childCount()):
                    child = item.child(j)
                    items.append((child, item, j))

        # Yield in requested order
        if reverse:
            yield from reversed(items)
        else:
            yield from items

    def _process_tree_items(self, uuid_to_items):
        """Walk tree, replace existing items, and remove invalid items."""
        existing_uuids = set()

        for item, parent, index in self.traverse(reverse=True):
            if isinstance(item, StyledTreeWidgetItem):
                uuid = item.metadata.get("uuid")
                # Remove non existing items
                if uuid not in uuid_to_items:
                    if parent is not None:
                        parent.removeChild(item)
                    else:
                        self.tree_widget.takeTopLevelItem(index)
                    continue

                # Update visibility status and metadata
                item.update(uuid_to_items[uuid])
                existing_uuids.add(uuid)

            # Remove empty groups
            elif isinstance(item, GroupTreeWidgetItem):
                if item.childCount() == 0:
                    self.tree_widget.takeTopLevelItem(index)
        return existing_uuids

    def __getattr__(self, name):
        """Forward all other attributes to tree_widget for compatibility."""
        return getattr(self.tree_widget, name)

    def addItem(self, item):
        self.tree_widget.addTopLevelItem(item)

    def create_group(self, name: str, insert_index: int = None):
        """Create a new group at the root level.

        Parameters
        ----------
        name : str
            Name for the new group
        insert_index : int, optional
            Index at which to insert the group. If None, appends to end.
        """
        group_item = GroupTreeWidgetItem(name)
        if insert_index is not None and insert_index >= 0:
            self.tree_widget.insertTopLevelItem(insert_index, group_item)
        else:
            self.tree_widget.addTopLevelItem(group_item)
        group_item.setExpanded(True)
        return group_item

    def _on_item_clicked(self, item, column):
        """Handle item clicks - toggle expand/collapse for groups and select children."""
        if not isinstance(item, GroupTreeWidgetItem):
            return

        cursor_pos = self.tree_widget.mapFromGlobal(self.tree_widget.cursor().pos())
        item_rect = self.tree_widget.visualItemRect(item)

        # If clicking on arrow area, toggle expand/collapse
        if (cursor_pos.x() - item_rect.left()) <= 40:
            item.setExpanded(not item.isExpanded())
            item.update_icon(item.isExpanded())
        self._select_group_children(item)

    def _select_group_children(self, group_item):
        """Select all children of a group and the group itself.

        Parameters
        ----------
        group_item : GroupTreeWidgetItem
            The group to select
        """
        if not isinstance(group_item, GroupTreeWidgetItem):
            return None

        items_to_select = [group_item]

        for i in range(group_item.childCount()):
            child = group_item.child(i)
            if isinstance(child, StyledTreeWidgetItem):
                items_to_select.append(child)

        modifiers = QApplication.keyboardModifiers()
        selection_flag = QItemSelectionModel.SelectionFlag.ClearAndSelect
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            selection_flag = QItemSelectionModel.SelectionFlag.Select

        self._set_selection(items_to_select, selection_flag)

    def _set_selection(
        self, items, selection_flag=QItemSelectionModel.SelectionFlag.ClearAndSelect
    ):
        """Set selection to specific items.

        Parameters
        ----------
        items : list of QTreeWidgetItem or single QTreeWidgetItem
            Items to select
        selection_flag : QItemSelectionModel.SelectionFlag
            Selection behavior (ClearAndSelect, Select, Toggle, etc.)
        """
        if not isinstance(items, (list, tuple)):
            items = [items]

        selection = QItemSelection()
        for item in items:
            if item is None:
                continue
            index = self.tree_widget.indexFromItem(item)
            selection.select(index, index)

        self.tree_widget.selectionModel().select(selection, selection_flag)


class GroupTreeWidgetItem(QTreeWidgetItem):
    """Special tree widget item representing a group."""

    def __init__(self, name: str, parent=None):
        super().__init__(parent, [name])
        self.group_name = name
        self.arrow_color = "#6b7280"

        self.update_icon()

        # Groups can be renamed but not dragged
        self.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
            | Qt.ItemFlag.ItemIsEditable
            | Qt.ItemFlag.ItemIsSelectable
        )
        self.metadata = {"uuid": str(uuid4())}

    def update_icon(self, expanded: bool = True):
        """Update the icon based on expanded state."""

        path = "M7,5 L11,9 L7,13"
        if expanded:
            path = "M5,7 L9,11 L13,7"

        svg_template = f"""
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18">
                <rect width="18" height="18" fill="transparent" />
                <path stroke="{self.arrow_color}" stroke-width="2" fill="none" d="{path}" />
            </svg>"""

        svg_bytes = QByteArray(svg_template.encode())
        renderer = QSvgRenderer(svg_bytes)
        pixmap = QPixmap(18, 18)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        icon = QIcon(pixmap)
        self.setIcon(0, icon)

    def setData(self, column, role, value):
        """Update group_name when text is changed."""
        if role == Qt.ItemDataRole.EditRole:
            self.group_name = value
        return super().setData(column, role, value)


class StyledTreeWidgetItem(QTreeWidgetItem):
    """
    Create a styled tree widget item with type-specific icons.

    Parameters
    ----------
    text : str
        The display text for the item
    visible : bool
        Whether the item is visible
    metadata : dict
        Additional metadata for the item
    parent : QWidget or QTreeWidgetItem
        Parent widget or parent tree item
    editable : bool
        Whether the item is editable
    """

    def __init__(self, text, visible=True, metadata=None, parent=None, editable=False):

        super().__init__(parent, [text])

        self.original_color = self.foreground(0)
        self.visible_color = QColor(99, 102, 241)
        self.invisible_color = QColor(128, 128, 128)

        self.metadata = metadata or {}

        _ = self.metadata.pop("metadata_text", None)
        if editable:
            self.setFlags(self.flags() | Qt.ItemFlag.ItemIsEditable)

        # Items can be dragged and selected, but do not accept drops
        # to prevent creating hierarchies of StyledTreeWidgetItem
        self.setFlags(
            self.flags() | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsSelectable
        )
        self.setFlags(self.flags() & ~Qt.ItemFlag.ItemIsDropEnabled)

        self.set_visible(visible)

    def update(self, other: "StyledTreeWidgetItem"):
        if other is None:
            return None

        self.metadata = other.metadata.copy()
        self.setText(0, other.text())

        self.set_visible(other.visible)

    def update_icon(self, visible):
        """Update the item icon based on type and visibility."""
        self.visible = visible

        item_type = self.metadata.get("item_type")
        if item_type == "cluster":
            icon_name = "mdi.scatter-plot"
        elif item_type == "parametric":
            icon_name = "mdi.function"
        elif item_type == "mesh":
            icon_name = "mdi.triangle-outline"
        elif item_type == "trajectory":
            icon_name = "mdi.chart-line-variant"
        else:
            icon_name = "mdi.shape-outline"

        color = self.visible_color if visible else self.invisible_color
        icon = qta.icon(icon_name, color=color, scale_factor=0.85)
        self.setIcon(0, icon)

    def set_visible(self, visible):
        """Update visibility state and icon."""
        self.update_icon(visible)
        self.setForeground(0, self.original_color if visible else self.invisible_color)

    def text(self):
        """Get item text for backward compatibility."""
        return super().text(0)

    def setData(self, *args):
        if len(args) == 2:
            index, (column, value) = 0, args
        elif len(args) == 3:
            index, column, value = args
        else:
            return None
        return super().setData(index, column, value)

    def data(self, *args):
        if len(args) == 1:
            index, column = 0, *args
        elif len(args) == 2:
            index, column = args
        else:
            return None
        return super().data(index, column)


class MetadataItemDelegate(QStyledItemDelegate):
    """Delegate for custom selection/hover painting."""

    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter, option, index):
        tree_widget = self.parent()
        item = tree_widget.itemFromIndex(index)

        # Calculate content rect extending to right edge
        content_rect = QRect(
            option.rect.left() + 6,
            option.rect.top() + 2,
            option.rect.width() - 6,
            option.rect.height() - 4,
        )

        # Draw hover/selection background
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setBrush(QColor(99, 102, 241, int(0.3 * 255)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(content_rect, 6, 6)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.setBrush(QColor(0, 0, 0, int(0.1 * 255)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(content_rect, 6, 6)
        painter.restore()

        # Draw icon
        icon_size = 20
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if icon and not icon.isNull():
            icon_rect = QRect(
                option.rect.left() + 12,
                option.rect.top() + (option.rect.height() - icon_size) // 2,
                icon_size,
                icon_size,
            )
            icon.paint(painter, icon_rect)

        # Draw text
        painter.save()
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if isinstance(item, StyledTreeWidgetItem) and not item.visible:
            painter.setPen(QColor(128, 128, 128))
        else:
            painter.setPen(option.palette.color(option.palette.ColorRole.Text))

        text_rect = QRect(
            option.rect.left() + 12 + icon_size + 4,
            option.rect.top(),
            option.rect.width() - icon_size - 28,
            option.rect.height(),
        )
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter), text)
        painter.restore()


# Backward compatibility aliases
ContainerListWidget = ContainerTreeWidget
StyledListWidgetItem = StyledTreeWidgetItem
