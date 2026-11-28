import os
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from qtpy.QtCore import (
    QEvent,
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    QObject,
    QPoint,
    QRect,
    Qt,
    Signal,
)
from qtpy.QtGui import QColor, QDropEvent, QPainter
from qtpy.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..formats.session import prefer_mosaic_sessions, session_save_path
from ..icons import icon as _icon_factory
from ..pipeline._utils import natural_sort_key, strip_filepath
from ..settings import Settings
from ..stylesheets import Colors, Typography
from ..tree_state import TreeState, TreeStateData
from .dock import CheckableMenu, menu_pos_above, style_popup
from .message_box import MosaicMessageBox

if TYPE_CHECKING:
    from ..data import MosaicData
    from ..geometry import Geometry
    from ..meshing.check import MeshDefect
    from ..parametrization import TriangularMesh


class SelectionIndicator(QWidget):
    """Overlay labels that appear when selected items are scrolled off-screen."""

    def __init__(self, tree_widget: QTreeWidget):
        super().__init__(tree_widget.viewport())
        self._tree = tree_widget
        self._above = []
        self._below = []

        self._top_label = QLabel(self)
        self._bottom_label = QLabel(self)
        for label in (self._top_label, self._bottom_label):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setCursor(Qt.CursorShape.PointingHandCursor)
            label.setFixedHeight(16)
            label.hide()

        self._top_label.mousePressEvent = lambda _: self._scroll_to(self._above)
        self._bottom_label.mousePressEvent = lambda _: self._scroll_to(self._below)

        tree_widget.selectionModel().selectionChanged.connect(self._recompute)
        tree_widget.verticalScrollBar().valueChanged.connect(self._recompute)
        tree_widget.viewport().installEventFilter(self)

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._top_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, False
        )
        self._bottom_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, False
        )
        self.setVisible(True)
        self._on_theme_changed()

    def eventFilter(self, obj: QObject, event: QEvent):
        if obj is self._tree.viewport() and event.type() == QEvent.Type.Resize:
            self._reposition()
            self._recompute()
        return False

    def _recompute(self):
        viewport_h = self._tree.viewport().height()
        selected = [
            item
            for item in self._tree.selectedItems()
            if isinstance(item, StyledTreeWidgetItem)
        ]

        above, below = [], []
        for item in selected:
            rect = self._tree.visualItemRect(item)
            if rect.bottom() < 0:
                above.append((rect.bottom(), item))
            elif rect.top() >= viewport_h:
                below.append((rect.top(), item))

        above.sort(key=lambda x: -x[0])
        below.sort(key=lambda x: x[0])

        self._above = [item for _, item in above]
        self._below = [item for _, item in below]

        self._update_label(self._top_label, self._above, "\u2191")
        self._update_label(self._bottom_label, self._below, "\u2193")
        self._reposition()

    def _update_label(
        self, label: QLabel, items: Sequence[QTreeWidgetItem], arrow: str
    ):
        if not items:
            label.hide()
            return
        name = items[0].text(0)
        max_len = 20
        if len(name) > max_len:
            name = name[: max_len - 1] + "\u2026"
        if len(items) > 1:
            text = f"{arrow}  {name} + {len(items) - 1} more"
        else:
            text = f"{arrow}  {name}"
        label.setText(text)
        label.show()

    def _reposition(self):
        w = self._tree.viewport().width()
        h = self._tree.viewport().height()
        self.setGeometry(0, 0, w, h)
        self._top_label.setGeometry(4, 0, w - 8, 16)
        self._bottom_label.setGeometry(4, h - 16, w - 8, 16)

    def _scroll_to(self, items: Sequence[QTreeWidgetItem]):
        if not items:
            return
        target = items[0]
        if (parent := target.parent()) is not None and not parent.isExpanded():
            parent.setExpanded(True)
            if isinstance(parent, GroupTreeWidgetItem):
                parent.update_icon(True)
        self._tree.scrollToItem(target, QAbstractItemView.ScrollHint.PositionAtCenter)

    def _on_theme_changed(self):
        for label in (self._top_label, self._bottom_label):
            label.setStyleSheet(
                f"""
                QLabel {{
                    background: {Colors.BG_TERTIARY};
                    color: {Colors.TEXT_SECONDARY};
                    font-size: {Typography.LABEL}px;
                    border-radius: 4px;
                    padding: 0px 8px;
                }}
            """
            )


class _DropAwareTreeWidget(QTreeWidget):
    """QTreeWidget that emits ``dropped`` once the user finishes a drag-drop."""

    dropped = Signal()

    def dropEvent(self, event: QDropEvent):
        super().dropEvent(event)
        self.dropped.emit()


class ContainerTreeWidget(QFrame):
    """Drop-in replacement for ContainerListWidget using QTreeWidget for grouping support."""

    structure_changed = Signal()
    defect_requested = Signal(object, object)
    defect_hidden = Signal()

    def __init__(self, title: str | None = None, compact: bool = False):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title = title
        self.tree_widget = _DropAwareTreeWidget()
        self.tree_widget.setHeaderHidden(True)
        self.tree_widget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.tree_widget.setIndentation(0)
        self.tree_widget.setAnimated(True)
        self.tree_widget.setRootIsDecorated(False)
        self.tree_widget.setItemsExpandable(True)
        self.tree_widget.setExpandsOnDoubleClick(False)

        self.tree_widget.itemClicked.connect(self._on_item_clicked)

        self.tree_widget.setDragEnabled(False)
        self.tree_widget.setAcceptDrops(True)
        self.tree_widget.setDropIndicatorShown(True)
        self.tree_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

        self.tree_widget.dropped.connect(self.structure_changed)

        self.tree_widget.setItemDelegate(
            MetadataItemDelegate(self.tree_widget, compact=compact)
        )
        self._selection_indicator = SelectionIndicator(self.tree_widget)
        self._defect_menu = None
        self.tree_widget.active_defect_geometry = None
        self.tree_widget.viewport().installEventFilter(_DefectIconClicks(self))
        _defect_notifier().checked.connect(self.tree_widget.viewport().update)

        layout.addWidget(self.tree_widget)

        self.setStyleSheet(
            f"""
            QListWidget QLineEdit, QTreeWidget QLineEdit {{
                background-color: palette(base);
                border: 1px solid {Colors.PRIMARY};
                border-radius: {Colors.RADIUS}px;
                padding: 0px 1px;
                selection-background-color: {Colors.alpha("PRIMARY", 0.6)};
                font-size: {Typography.BODY}px;
            }}
            """
        )

    def set_active_defect(self, geometry: "Geometry | None") -> None:
        """Draw the attention icon of ``geometry``'s row filled, or none.

        Parameters
        ----------
        geometry : Geometry or None
            Geometry whose defect is highlighted in the viewport.
        """
        self.tree_widget.active_defect_geometry = geometry
        self.tree_widget.viewport().update()
        return None

    def _open_defect_menu(self, geometry: "Geometry", defects: list, rect: QRect):
        menu = style_popup(QMenu(self.window()))
        if self.tree_widget.active_defect_geometry is geometry:
            menu.addAction("Hide").triggered.connect(self.defect_hidden.emit)
            menu.addSeparator()
        for defect in defects:
            action = menu.addAction(_defect_label(defect))
            action.triggered.connect(
                lambda _=False, d=defect: self.defect_requested.emit(geometry, d)
            )
        viewport = self.tree_widget.viewport()
        menu.popup(viewport.mapToGlobal(rect.bottomLeft() + QPoint(0, 4)))
        self._defect_menu = menu
        return None

    def selected_items(self):
        # We specifically omit GroupTreeWidgetItem
        return [
            item
            for item in self.tree_widget.selectedItems()
            if isinstance(item, StyledTreeWidgetItem)
        ]

    def to_state(self) -> TreeStateData:
        """Extract current tree structure as TreeStateData object."""
        state = TreeStateData()

        for item, parent, _ in self.traverse(reverse=False):
            if not isinstance(item, StyledTreeWidgetItem):
                continue

            if (uuid := item.metadata.get("uuid")) is None:
                continue

            group_name = getattr(parent, "group_name", None)
            if parent is None:
                state.root_items.append(uuid)
            elif isinstance(parent, GroupTreeWidgetItem):
                if (group_uuid := parent.metadata.get("uuid")) is None:
                    continue

                if group_uuid not in state.groups:
                    state.groups[group_uuid] = []
                    state.root_items.append(group_uuid)
                    state.group_names[group_uuid] = group_name
                state.groups[group_uuid].append(uuid)
        return state

    def apply_state(self, state: TreeStateData | TreeState, uuid_to_items: dict):
        """Apply tree structure to existing items.

        Parameters
        ----------
        state : :py:class:`TreeStateData` or py:class:`TreeState`
            Desired tree structure
        uuid_to_items : dict
            Map of UUID to QTreeWidgetItem
        """
        self.tree_widget.clear()

        # Convert legacy format
        if isinstance(state, TreeState):
            state = state.to_tree_state_data()

        for uuid in state.root_items:
            if (group_name := state.group_names.get(uuid)) is None:
                self.tree_widget.addTopLevelItem(uuid_to_items[uuid])
                continue

            group_item = self.create_group(group_name)
            uuids = [x for x in state.groups.get(uuid, []) if x in uuid_to_items]
            for uuid in uuids:
                group_item.addChild(uuid_to_items[uuid])

    def update(self, uuid_to_items: "Mapping[str, StyledTreeWidgetItem]"):
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

    def _move_items_to_parent(
        self, items: Sequence[QTreeWidgetItem], new_parent: QTreeWidgetItem
    ):
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
        self.structure_changed.emit()
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
        self.structure_changed.emit()
        return len(selected_items)

    def traverse(self, reverse: bool = False):
        """Generator that yields all (item, parent, index) tuples.

        Parameters
        ----------
        reverse : bool
            If True, iterate in reverse order (useful for mutations)
        """
        items = []

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

    def _process_tree_items(self, uuid_to_items: "Mapping[str, StyledTreeWidgetItem]"):
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

    def __getattr__(self, name: str):
        """Forward all other attributes to tree_widget for compatibility."""
        return getattr(self.tree_widget, name)

    def addItem(self, item: QTreeWidgetItem):
        self.tree_widget.addTopLevelItem(item)

    def create_group(self, name: str, insert_index: int | None = None):
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

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
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

    def _select_group_children(self, group_item: QTreeWidgetItem):
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
        self,
        items: Sequence[QTreeWidgetItem],
        selection_flag: QItemSelectionModel.SelectionFlag = QItemSelectionModel.SelectionFlag.ClearAndSelect,
    ):
        """
        Set selection to specific items.

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

    def set_selection(
        self,
        uuids: list[str],
        selection_flag: QItemSelectionModel.SelectionFlag = QItemSelectionModel.SelectionFlag.ClearAndSelect,
    ):
        """
        Set selection to specific items.

        Parameters
        ----------
        uuids : list of str
            List of UUIDs that correspond to Geometry objects in tree.
        selection_flag : QItemSelectionModel.SelectionFlag
            Selection behavior (ClearAndSelect, Select, Toggle, etc.)
        """
        if not isinstance(uuids, (list, tuple)):
            uuids = [uuids]

        items = []
        for item, parent, _ in self.traverse(reverse=False):
            if item.metadata.get("uuid") in uuids:
                items.append(item)

        self._set_selection(items)


class GroupTreeWidgetItem(QTreeWidgetItem):
    """Special tree widget item representing a group."""

    def __init__(self, name: str, parent: QTreeWidget | QTreeWidgetItem | None = None):
        super().__init__(parent, [name])
        self.group_name = name

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
        name = "ph.caret-down" if expanded else "ph.caret-right"
        self.setIcon(0, _icon_factory(name, role="muted"))

    def setData(self, column: int, role: int, value: Any):
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

    def __init__(
        self,
        text: str | None = None,
        visible: bool = True,
        metadata: dict | None = None,
        parent: QTreeWidget | QTreeWidgetItem | None = None,
        editable: bool = False,
        geometry: "Geometry | None" = None,
    ):

        self._geometry = geometry
        if geometry is not None:
            if text is None:
                text = geometry._meta.get("name", "")
            if metadata is None:
                metadata = {
                    "item_type": geometry.geometry_type,
                    "name": text,
                    "uuid": geometry.uuid,
                }

        super().__init__(parent, [text or ""])

        if geometry is not None:
            super().setData(0, Qt.ItemDataRole.UserRole, geometry)

        self.original_color = self.foreground(0)

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

        self._geometry = other._geometry
        self.metadata = other.metadata.copy()
        self.setText(0, other.text())

        self.set_visible(other.visible)

    def update_icon(self, visible: bool):
        """Update the item icon based on type and visibility."""
        self.visible = visible

        item_type = self.metadata.get("item_type")
        if item_type == "cluster":
            icon_name = "mdi.scatter-plot"
        elif item_type == "parametric":
            icon_name = "mdi.function"
        elif item_type == "mesh":
            icon_name = "ph.triangle"
        elif item_type == "trajectory":
            icon_name = "ph.path"
        else:
            icon_name = "mdi.scatter-plot"

        color = Colors.PRIMARY if visible else Colors.TEXT_MUTED
        icon = _icon_factory(icon_name, color=color, scale_factor=0.85)
        self.setIcon(0, icon)

    def set_visible(self, visible: bool):
        """Update visibility state and icon."""
        self.update_icon(visible)
        foreground = self.original_color if visible else QColor(Colors.TEXT_MUTED)
        self.setForeground(0, foreground)

    def text(self, column: int = 0):
        return super().text(column)

    def setData(self, *args):
        if len(args) == 2:
            index, (column, value) = 0, args
        elif len(args) == 3:
            index, column, value = args
        else:
            return None
        if (
            index == 0
            and column in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole)
            and self._geometry is not None
        ):
            self._geometry._meta["name"] = value
        return super().setData(index, column, value)

    def data(self, *args):
        if len(args) == 1:
            index, column = 0, *args
        elif len(args) == 2:
            index, column = args
        else:
            return None
        if (
            index == 0
            and column == Qt.ItemDataRole.DisplayRole
            and self._geometry is not None
        ):
            return self._geometry._meta.get("name", "")
        return super().data(index, column)


class SessionTreeItem(QTreeWidgetItem):
    """Row of the session list."""


class _DefectNotifier(QObject):
    checked = Signal()


_pending_checks: set[int] = set()
_notifier: _DefectNotifier | None = None


def _defect_notifier() -> _DefectNotifier:
    global _notifier
    if _notifier is None:
        _notifier = _DefectNotifier()
    return _notifier


def _check_in_background(model: "TriangularMesh") -> None:
    from qtpy.QtCore import QThreadPool

    if id(model) in _pending_checks:
        return None
    _pending_checks.add(id(model))
    notifier = _defect_notifier()

    def run():
        _ = model.defects
        _pending_checks.discard(id(model))
        notifier.checked.emit()

    QThreadPool.globalInstance().start(run)
    return None


def shown_defects(model: object) -> list["MeshDefect"]:
    """Return the defects of ``model`` whose kind is shown.

    Parameters
    ----------
    model : object
        A geometry's model; anything but a triangle mesh has no defects.

    Returns
    -------
    list of MeshDefect
        Defects whose kind is ticked under Preferences > Mesh Check.
    """
    from ..parametrization import TriangularMesh

    if not isinstance(model, TriangularMesh):
        return []
    # Checking a mesh this large would stall painting the list.
    if model._defects is None and len(model.triangles) > 200_000:
        _check_in_background(model)
        return []
    shown = {
        "hole": Settings.ui.mesh_check_holes,
        "twisted": Settings.ui.mesh_check_twisted,
        "nonmanifold": Settings.ui.mesh_check_nonmanifold,
    }
    return [defect for defect in model.defects if shown[defect.kind]]


def _defect_label(defect: "MeshDefect") -> str:
    if defect.kind == "hole":
        return f"Hole, {defect.perimeter:,.0f} Å around"
    if defect.kind == "twisted":
        return "Twisted spot"
    return "Non-manifold edge"


class _DefectIconClicks(QObject):
    """Opens the defect menu when the attention icon of a row is pressed."""

    def __init__(self, container: "ContainerTreeWidget"):
        super().__init__(container)
        self.container = container

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.MouseButtonPress:
            return False
        tree = self.container.tree_widget
        pos = event.position().toPoint()
        item = tree.itemAt(pos)
        geometry = getattr(item, "_geometry", None)
        if geometry is None:
            return False
        defects = shown_defects(geometry.model)
        rect = tree.itemDelegate().icon_rect(
            tree.visualItemRect(item), tree.indexFromItem(item)
        )
        if not defects or not rect.adjusted(-4, -4, 4, 4).contains(pos):
            return False
        self.container._open_defect_menu(geometry, defects, rect)
        return True


class MetadataItemDelegate(QStyledItemDelegate):
    """Delegate for custom selection/hover painting."""

    def __init__(self, parent: QObject | None = None, compact: bool = False):
        super().__init__(parent)
        # Compact mode strips the left padding for embedded uses (e.g. option
        # blocks in dialogs); the default keeps a small breathing room.
        self._pad = 0 if compact else 6
        self._child_indent = 4 if compact else 6
        # Header-style items (group carets, picker categories) render with a
        # smaller icon than element rows so the chevron does not dominate.
        self._header_icon_size = 14
        self._item_icon_size = 20

    def _icon_size_for(self, item: QTreeWidgetItem) -> int:
        return (
            self._item_icon_size
            if isinstance(item, (StyledTreeWidgetItem, SessionTreeItem))
            else self._header_icon_size
        )

    def _indent_for(self, index: QModelIndex):
        return self._child_indent if index.parent().isValid() else 0

    def icon_rect(self, rect: QRect, index: QModelIndex) -> QRect:
        """Rectangle of the leading icon within a row."""
        size = self._icon_size_for(self.parent().itemFromIndex(index))
        return QRect(
            rect.left() + self._pad + self._indent_for(index),
            rect.top() + (rect.height() - size) // 2,
            size,
            size,
        )

    def updateEditorGeometry(
        self, editor: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ):
        tree_widget = self.parent()
        item = tree_widget.itemFromIndex(index)
        icon_size = self._icon_size_for(item)
        indent = self._indent_for(index)
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        has_icon = icon is not None and not icon.isNull()
        text_left = self._pad + icon_size + 4 if has_icon else self._pad
        editor.setGeometry(option.rect.adjusted(text_left + indent - 4, 2, 0, -2))

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ):
        tree_widget = self.parent()
        item = tree_widget.itemFromIndex(index)

        indent = self._indent_for(index)
        pad = self._pad

        # Calculate content rect extending to right edge
        content_rect = QRect(
            option.rect.left() + max(pad - 6, 0) + indent,
            option.rect.top() + 2,
            option.rect.width() - max(pad - 6, 0) - indent,
            option.rect.height() - 4,
        )

        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if is_selected:
            accent = QColor(Colors.PRIMARY)
            accent.setAlphaF(0.07)
            painter.setBrush(accent)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(content_rect, 6, 6)
        elif is_hovered:
            hover = QColor(Colors.TEXT_PRIMARY)
            hover.setAlphaF(0.06)
            painter.setBrush(hover)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(content_rect, 6, 6)
        painter.restore()

        icon_size = self._icon_size_for(item)
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        geometry = getattr(item, "_geometry", None)
        if geometry is not None and shown_defects(geometry.model):
            name = "ph.warning-circle"
            if getattr(tree_widget, "active_defect_geometry", None) is geometry:
                name = "ph.warning-circle-fill"
            icon = _icon_factory(name, color=Colors.WARNING)
        has_icon = icon and not icon.isNull()
        if has_icon:
            icon.paint(painter, self.icon_rect(option.rect, index))

        painter.save()
        painter.setFont(option.font)
        text = index.data(Qt.ItemDataRole.DisplayRole)

        if isinstance(item, StyledTreeWidgetItem) and not item.visible:
            painter.setPen(QColor(Colors.TEXT_MUTED))
        elif is_selected:
            painter.setPen(QColor(Colors.PRIMARY))
        else:
            painter.setPen(QColor(Colors.TEXT_SECONDARY))

        text_left = pad + icon_size + 4 if has_icon else pad
        text_rect = QRect(
            option.rect.left() + text_left + indent,
            option.rect.top(),
            option.rect.width() - text_left - pad,
            option.rect.height(),
        )
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter), text)
        painter.restore()


class _SessionHeader(QWidget):
    """Icon action bar for session management, sits below the session list."""

    _BTN_QSS = """
        QPushButton {{
            border: 1px solid transparent;
            background: transparent;
            border-radius: {r}px;
            padding: 4px 8px;
            font-size: {fs}px;
            color: {color};
        }}
        QPushButton:hover {{
            background: {hover};
        }}
        QPushButton:pressed {{
            background: {pressed};
        }}
        QPushButton:focus {{ outline: none; }}
    """

    def __init__(
        self, session_widget: "SessionListWidget", parent: QWidget | None = None
    ):
        super().__init__(parent)
        self._session_widget = session_widget

        from ..icons import icon

        h = Colors.WIDGET_HEIGHT

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 4)
        lay.setSpacing(4)

        self._add_btn = QPushButton()
        self._add_btn.setIcon(icon("ph.plus", role="muted"))
        self._add_btn.setFixedSize(h, h)
        self._add_btn.setToolTip("Add session files")
        self._add_btn.clicked.connect(session_widget.add_sessions)
        lay.addWidget(self._add_btn)

        self._reload_btn = QPushButton()
        self._reload_btn.setIcon(icon("ph.arrow-counter-clockwise", role="muted"))
        self._reload_btn.setFixedSize(h, h)
        self._reload_btn.setToolTip("Reload current session")
        self._reload_btn.clicked.connect(session_widget.reload_current)
        lay.addWidget(self._reload_btn)
        lay.addStretch(1)

        self._menu_btn = QPushButton()
        self._menu_btn.setIcon(icon("ph.gear", role="muted"))
        self._menu_btn.setFixedSize(h, h)
        self._menu_btn.setToolTip("Session options")
        self._menu_btn.clicked.connect(self._show_menu)
        lay.addWidget(self._menu_btn)

        self._menu = self._build_menu()
        self._apply_btn_style()

    def _build_menu(self):
        menu = style_popup(CheckableMenu())

        link = menu.addAction("Link tomograms…")
        link.triggered.connect(self._session_widget.link_tomograms_requested)
        menu.addSeparator()

        auto_save = menu.addAction("Auto-save on switch")
        auto_save.setCheckable(True)
        auto_save.setChecked(self._session_widget._auto_save)
        auto_save.toggled.connect(self._on_auto_save_toggled)

        load_tomogram = menu.addAction("Load tomogram on switch")
        load_tomogram.setCheckable(True)
        load_tomogram.setChecked(Settings.ui.load_linked_tomogram)
        load_tomogram.toggled.connect(self._on_load_tomogram_toggled)
        menu.addSeparator()

        clear = menu.addAction(
            _icon_factory("ph.trash", role="muted"), "Clear all sessions"
        )
        clear.triggered.connect(
            lambda: self._session_widget.clear_sessions_with_prompt()
        )
        return menu

    def _action(self, text: str):
        return next(a for a in self._menu.actions() if a.text() == text)

    def _show_menu(self):
        top_left = self._menu_btn.mapToGlobal(QPoint(0, 0))
        button_rect = QRect(top_left, self._menu_btn.size())
        self._menu.exec(menu_pos_above(button_rect, self._menu.sizeHint()))

    def _on_auto_save_toggled(self, checked: bool):
        self._session_widget._auto_save = checked

    def _on_load_tomogram_toggled(self, checked: bool):
        Settings.ui.load_linked_tomogram = checked

    def _apply_btn_style(self):
        qss = self._BTN_QSS.format(
            r=Colors.RADIUS,
            fs=Typography.LABEL,
            color=Colors.TEXT_SECONDARY,
            hover=Colors.BG_HOVER,
            pressed=Colors.BG_PRESSED,
        )
        for btn in (self._add_btn, self._reload_btn, self._menu_btn):
            btn.setStyleSheet(qss)

    def _on_theme_changed(self):
        self._apply_btn_style()
        from ..icons import icon

        self._reload_btn.setIcon(icon("ph.arrow-counter-clockwise", role="muted"))
        self._menu_btn.setIcon(icon("ph.gear", role="muted"))
        self._add_btn.setIcon(icon("ph.plus", role="muted"))
        self._action("Clear all sessions").setIcon(icon("ph.trash", role="muted"))


def confirm_session_overwrite(parent: QWidget, source: str) -> bool:
    """Ask before a legacy ``.pickle`` save replaces an existing ``.mosaic``.

    Parameters
    ----------
    parent : QWidget
        Parent of the dialog.
    source : str
        Path the caller wants to save to.

    Returns
    -------
    bool
        True if the save may proceed.
    """
    if not source.lower().endswith(".pickle"):
        return True

    target = session_save_path(source)
    if not os.path.exists(target):
        return True

    reply = MosaicMessageBox.question(
        parent,
        "Overwrite Session",
        f"Overwrite {os.path.basename(target)}?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return reply == QMessageBox.StandardButton.Yes


class SessionListWidget(QWidget):
    """Sidebar-integrated session list for batch navigation."""

    load_requested = Signal(str)
    session_path_changed = Signal(str, str)
    link_tomograms_requested = Signal()

    def __init__(self, cdata: "MosaicData", parent: QWidget | None = None):
        super().__init__(parent)
        self._cdata = cdata
        self.session_files = []
        self.current_index = -1
        self._items = []
        self._session_modified = False
        self._active = False
        self._auto_save = True
        self._header = _SessionHeader(self)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(0)
        self._tree.setRootIsDecorated(False)
        self._tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tree.setFrameShape(QFrame.Shape.NoFrame)
        self._tree.setDragEnabled(False)
        self._tree.setItemDelegate(MetadataItemDelegate(self._tree))
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.itemClicked.connect(self._on_item_clicked)

        font = self._tree.font()
        font.setPixelSize(Typography.BODY)
        self._tree.setFont(font)

        self._layout.addWidget(self._tree, 1)
        self._layout.addWidget(self._header)

    def set_sessions(self, filepaths: Sequence[str]):
        self.session_files = prefer_mosaic_sessions(
            sorted(filepaths, key=natural_sort_key)
        )
        self.current_index = -1
        self._rebuild_items()

    def add_sessions(self):
        filepaths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Session Files",
            "",
            "Session Files (*.mosaic *.pickle)",
        )
        if not filepaths:
            return None

        existing = set(self.session_files)
        for fp in filepaths:
            if fp not in existing:
                self.session_files.append(fp)
                existing.add(fp)
        self.session_files = prefer_mosaic_sessions(
            sorted(self.session_files, key=natural_sort_key)
        )
        self._rebuild_items()

    def clear_sessions(self):
        if self._auto_save and self._session_modified and not self.save_current():
            return None

        self.session_files.clear()
        self.current_index = -1
        self._rebuild_items()

    def set_current(self, filepath: str):
        try:
            self.current_index = self.session_files.index(filepath)
        except ValueError:
            return None
        self._update_highlight()

    def save_current(self):
        if self.current_index < 0 or self.current_index >= len(self.session_files):
            return True
        if not self._save_to(self.session_files[self.current_index]):
            return False

        self._session_modified = False
        return True

    def replace_paths(self, mapping: Mapping[str, str]):
        """Swap list entries using an old to new mapping."""
        current = None
        if 0 <= self.current_index < len(self.session_files):
            current = self.session_files[self.current_index]

        mapped = [mapping.get(x, x) for x in self.session_files]
        self.session_files = list(dict.fromkeys(mapped))
        if current is not None:
            self.current_index = self.session_files.index(mapping.get(current, current))
        self._rebuild_items()

        for old, new in mapping.items():
            if old != new:
                self.session_path_changed.emit(old, new)
        return None

    def mark_saved(self, filepath: str):
        """Clear the modified flag if ``filepath`` is the current session."""
        if (
            0 <= self.current_index < len(self.session_files)
            and self.session_files[self.current_index] == filepath
        ):
            self._session_modified = False
        return None

    def _save_to(self, filepath: str):
        if not confirm_session_overwrite(self, filepath):
            return False

        written = self._cdata.to_file(filepath)
        if written != filepath:
            self.replace_paths({filepath: written})
        return True

    def reload_current(self):
        if self.current_index < 0:
            return None

        reply = MosaicMessageBox.question(
            self,
            "Discard Changes",
            "Reload the current session and discard all unsaved changes?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            filepath = self.session_files[self.current_index]
            self.load_requested.emit(filepath)

    def activate(self):
        if self._active:
            return None

        self._active = True
        self._cdata.data.data_changed.connect(self._mark_modified)
        self._cdata.models.data_changed.connect(self._mark_modified)

    def deactivate(self):
        if not self._active:
            return None

        self._active = False
        try:
            self._cdata.data.data_changed.disconnect(self._mark_modified)
            self._cdata.models.data_changed.disconnect(self._mark_modified)
        except (TypeError, RuntimeError):
            pass

    def filter_items(self, text: str):
        lower = text.lower()
        for item in self._items:
            name = strip_filepath(item.data(0, Qt.ItemDataRole.UserRole)).lower()
            item.setHidden(bool(lower) and lower not in name)

    def _mark_modified(self):
        self._session_modified = True

    def _prompt_save_if_needed(self):
        """Prompt to save if there are unsaved changes. Returns True to proceed, False to cancel."""
        if self.current_index < 0 or not self._session_modified:
            return True

        if self._auto_save and self._active:
            if not self.save_current():
                return False
            return True

        reply = MosaicMessageBox.question(
            self,
            "Unsaved Changes",
            "The current session has unsaved changes.",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if reply == QMessageBox.StandardButton.Cancel:
            return False
        if reply == QMessageBox.StandardButton.Save and not self.save_current():
            return False

        self._session_modified = False
        return True

    def remove_session(self, index: int):
        """Remove a single session by index. Prompts to save if removing the active session."""
        if index < 0 or index >= len(self.session_files):
            return None

        is_active = index == self.current_index
        if is_active and not self._prompt_save_if_needed():
            return None

        self.session_files.pop(index)
        if is_active:
            if not self.session_files:
                self.current_index = -1
            else:
                self.current_index = min(index, len(self.session_files) - 1)
        elif index < self.current_index:
            self.current_index -= 1

        self._rebuild_items()
        if is_active and self.session_files:
            filepath = self.session_files[self.current_index]
            self.load_requested.emit(filepath)
            self._session_modified = False

    def clear_sessions_with_prompt(self):
        """Clear all sessions, prompting to save if needed."""
        if not self.session_files:
            return None
        if not self._prompt_save_if_needed():
            return None

        self.session_files.clear()
        self.current_index = -1
        self._session_modified = False
        self._rebuild_items()

    def _rebuild_items(self):
        self._tree.clear()
        self._items.clear()

        from ..icons import icon as _icon

        file_icon = _icon("ph.file", role="muted", scale_factor=0.85)
        for i, filepath in enumerate(self.session_files):
            item = SessionTreeItem([strip_filepath(filepath)])
            item.setData(0, Qt.ItemDataRole.UserRole, filepath)
            item.setIcon(0, file_icon)
            self._tree.addTopLevelItem(item)
            self._items.append(item)

        self._update_highlight()

    def _update_highlight(self):
        self._tree.blockSignals(True)
        self._tree.clearSelection()
        if 0 <= self.current_index < len(self._items):
            self._items[self.current_index].setSelected(True)
        self._tree.blockSignals(False)

    def _on_item_clicked(self, item: SessionTreeItem):
        if (index := self._tree.indexOfTopLevelItem(item)) == self.current_index:
            return None

        if self._auto_save and self._session_modified and not self.save_current():
            return None

        self.current_index = index
        self._update_highlight()
        filepath = self.session_files[index]
        self.load_requested.emit(filepath)
        self._session_modified = False

    def _on_context_menu(self, pos: QPoint):
        if (item := self._tree.itemAt(pos)) is None:
            return None

        index = self._tree.indexOfTopLevelItem(item)
        menu = style_popup(QMenu(self.window()))
        remove_action = menu.addAction("Remove from list")
        action = menu.exec(self._tree.viewport().mapToGlobal(pos))
        if action == remove_action:
            self.remove_session(index)
        self._update_highlight()


# Backward compatibility aliases
ContainerListWidget = ContainerTreeWidget
StyledListWidgetItem = StyledTreeWidgetItem
