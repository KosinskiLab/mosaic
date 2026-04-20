from uuid import uuid4
from typing import Dict, List, Union

from qtpy.QtGui import QColor, QIcon, QPixmap, QPainter
from qtpy.QtCore import (
    Qt,
    QRect,
    QByteArray,
    QItemSelection,
    QItemSelectionModel,
    Signal,
)
from qtpy.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QApplication,
    QStyledItemDelegate,
    QStyle,
    QAbstractItemView,
    QPushButton,
    QFileDialog,
    QMenu,
    QMessageBox,
)
from qtpy.QtSvg import QSvgRenderer
from ..icons import icon as _icon_factory
from ..stylesheets import Colors, Typography, _build_QToolTip_style
from ..tree_state import TreeState, TreeStateData
from ..pipeline._utils import natural_sort_key, strip_filepath


class ContainerTreeWidget(QFrame):
    """Drop-in replacement for ContainerListWidget using QTreeWidget for grouping support."""

    def __init__(self, title: str = None):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title = title
        self.tree_widget = QTreeWidget()
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

        self.tree_widget.setItemDelegate(MetadataItemDelegate(self.tree_widget))

        self.apply_tree_stylesheet(self.tree_widget)

        layout.addWidget(self.tree_widget)

    @staticmethod
    def apply_tree_stylesheet(tree):
        tree.setStyleSheet(
            f"""
            QTreeWidget {{
                border: none;
                background-color: transparent;
                outline: none;
                padding: 4px 0px;
                font-size: {Typography.BODY}px;
            }}
            QTreeWidget::item {{
                border-radius: 6px;
                border: none;
                padding: 4px 0px;
                margin: 2px 0px;
                outline: none;
            }}
            QTreeWidget::item:hover {{
                background-color: rgba(0, 0, 0, 0.0);
            }}
            QTreeWidget::item:selected {{
                background-color: rgba(0, 0, 0, 0.0);
            }}
            QTreeWidget QLineEdit {{
                background-color: palette(base);
                border: 1px solid #4f46e5;
                border-radius: 6px;
                padding: 0px 3px;
                margin: 0px 8px;
                selection-background-color: rgba(99, 102, 241, 0.6);
                font-size: {Typography.BODY}px;
            }}
        """
        )

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

    def apply_state(self, state: Union[TreeStateData, TreeState], uuid_to_items: Dict):
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
        uuids: List[str],
        selection_flag=QItemSelectionModel.SelectionFlag.ClearAndSelect,
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

    def __init__(
        self,
        text=None,
        visible=True,
        metadata=None,
        parent=None,
        editable=False,
        geometry=None,
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
            icon_name = "ph.triangle"
        elif item_type == "trajectory":
            icon_name = "ph.path"
        else:
            icon_name = "mdi.scatter-plot"

        color = self.visible_color if visible else self.invisible_color
        icon = _icon_factory(icon_name, color=color.name(), scale_factor=0.85)
        self.setIcon(0, icon)

    def set_visible(self, visible):
        """Update visibility state and icon."""
        self.update_icon(visible)
        self.setForeground(0, self.original_color if visible else self.invisible_color)

    def text(self, column=0):
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

        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if is_selected:
            accent = QColor(Colors.PRIMARY)
            accent.setAlphaF(0.07 if not Colors.is_dark() else 0.10)
            painter.setBrush(accent)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(content_rect, 6, 6)
        elif is_hovered:
            painter.setBrush(QColor(0, 0, 0, int(0.06 * 255)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(content_rect, 6, 6)
        painter.restore()

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

        painter.save()
        painter.setFont(option.font)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if isinstance(item, StyledTreeWidgetItem) and not item.visible:
            painter.setPen(QColor(Colors.TEXT_MUTED))
        elif is_selected:
            painter.setPen(QColor(Colors.PRIMARY))
        else:
            painter.setPen(QColor(Colors.TEXT_SECONDARY))

        text_rect = QRect(
            option.rect.left() + 12 + icon_size + 4,
            option.rect.top(),
            option.rect.width() - icon_size - 28,
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

    def __init__(self, session_widget, parent=None):
        super().__init__(parent)
        self._session_widget = session_widget

        from ..icons import icon

        h = Colors.WIDGET_HEIGHT

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 4)
        lay.setSpacing(4)

        self._add_btn = QPushButton()
        self._add_btn.setIcon(icon("ph.plus", role="muted"))
        self._add_btn.setFixedHeight(h)
        self._add_btn.setToolTip("Add session files")
        self._add_btn.clicked.connect(session_widget.add_sessions)
        lay.addWidget(self._add_btn, 1)

        self._save_btn = QPushButton()
        self._save_btn.setIcon(icon("ph.floppy-disk", role="muted"))
        self._save_btn.setFixedHeight(h)
        self._save_btn.setToolTip("Save current session")
        self._save_btn.clicked.connect(session_widget.save_current)
        lay.addWidget(self._save_btn, 1)

        self._reload_btn = QPushButton()
        self._reload_btn.setIcon(icon("ph.arrow-counter-clockwise", role="muted"))
        self._reload_btn.setFixedHeight(h)
        self._reload_btn.setToolTip("Reload current session")
        self._reload_btn.clicked.connect(session_widget.reload_current)
        lay.addWidget(self._reload_btn, 1)

        self._auto_save_toggle = QPushButton()
        self._auto_save_toggle.setCheckable(True)
        self._auto_save_toggle.setChecked(True)
        self._auto_save_toggle.setFixedHeight(h)
        self._auto_save_toggle.setToolTip("Auto-save when switching sessions")
        self._auto_save_toggle.toggled.connect(self._on_auto_save_toggled)
        self._update_auto_save_icon()
        lay.addWidget(self._auto_save_toggle, 1)

        self._clear_btn = QPushButton()
        self._clear_btn.setIcon(icon("ph.trash", role="muted"))
        self._clear_btn.setFixedHeight(h)
        self._clear_btn.setToolTip("Clear all sessions")
        self._clear_btn.clicked.connect(
            lambda: session_widget.clear_sessions_with_prompt()
        )
        lay.addWidget(self._clear_btn, 1)

        self._apply_btn_style()

    def _on_auto_save_toggled(self, checked):
        self._session_widget._auto_save = checked
        self._update_auto_save_icon()

    def _update_auto_save_icon(self):
        from ..icons import icon

        role = "primary" if self._auto_save_toggle.isChecked() else "muted"
        self._auto_save_toggle.setIcon(icon("ph.arrows-clockwise", role=role))

    def _apply_btn_style(self):
        qss = (
            self._BTN_QSS.format(
                r=Colors.RADIUS,
                fs=Typography.LABEL,
                color=Colors.TEXT_SECONDARY,
                hover=Colors.BG_HOVER,
                pressed=Colors.BG_PRESSED,
            )
            + _build_QToolTip_style()
        )
        for btn in (
            self._add_btn,
            self._save_btn,
            self._reload_btn,
            self._auto_save_toggle,
            self._clear_btn,
        ):
            btn.setStyleSheet(qss)

    def _on_theme_changed(self):
        self._apply_btn_style()
        self._update_auto_save_icon()
        from ..icons import icon

        self._add_btn.setIcon(icon("ph.plus", role="muted"))
        self._save_btn.setIcon(icon("ph.floppy-disk", role="muted"))
        self._reload_btn.setIcon(icon("ph.arrow-counter-clockwise", role="muted"))
        self._clear_btn.setIcon(icon("ph.trash", role="muted"))


class SessionListWidget(QWidget):
    """Sidebar-integrated session list for batch navigation."""

    load_requested = Signal(str)

    def __init__(self, cdata, parent=None):
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
        self._apply_tree_style()

        font = self._tree.font()
        font.setPixelSize(Typography.BODY)
        self._tree.setFont(font)

        self._layout.addWidget(self._tree, 1)
        self._layout.addWidget(self._header)

    def set_sessions(self, filepaths):
        self.session_files = sorted(filepaths, key=natural_sort_key)
        self.current_index = -1
        self._rebuild_items()

    def add_sessions(self):
        filepaths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Session Files",
            "",
            "Session Files (*.mosaic *.pickle)"
            ";;Mosaic Sessions (*.mosaic)"
            ";;Legacy Pickle (*.pickle)",
        )
        if not filepaths:
            return None

        existing = set(self.session_files)
        for fp in filepaths:
            if fp not in existing:
                self.session_files.append(fp)
                existing.add(fp)
        self.session_files.sort(key=natural_sort_key)
        self._rebuild_items()

    def clear_sessions(self):
        self._save_current()
        self.session_files.clear()
        self.current_index = -1
        self._rebuild_items()

    def set_current(self, filepath):
        try:
            self.current_index = self.session_files.index(filepath)
        except ValueError:
            return None
        self._update_highlight()

    def save_current(self):
        return self._save_current()

    def reload_current(self):
        if self.current_index < 0:
            return None

        reply = QMessageBox.question(
            self,
            "Discard Changes",
            "Reload the current session and discard all unsaved changes?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
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

    def filter_items(self, text):
        lower = text.lower()
        for item in self._items:
            name = strip_filepath(item.data(0, Qt.ItemDataRole.UserRole)).lower()
            item.setHidden(bool(lower) and lower not in name)

    def _mark_modified(self):
        self._session_modified = True

    def _save_current(self):
        if self.current_index < 0 or not self._session_modified:
            return None
        if self._auto_save and self._active:
            filepath = self.session_files[self.current_index]
            self._cdata.to_file(filepath)
            self._session_modified = False

    def _prompt_save_if_needed(self):
        """Prompt to save if there are unsaved changes. Returns True to proceed, False to cancel."""
        if self.current_index < 0 or not self._session_modified:
            return True

        if self._auto_save and self._active:
            filepath = self.session_files[self.current_index]
            self._cdata.to_file(filepath)
            self._session_modified = False
            return True

        reply = QMessageBox.question(
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

        if reply == QMessageBox.StandardButton.Save:
            filepath = self.session_files[self.current_index]
            self._cdata.to_file(filepath)

        self._session_modified = False
        return True

    def remove_session(self, index):
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

        file_icon = _icon("ph.compass", role="muted", scale_factor=0.85)
        for i, filepath in enumerate(self.session_files):
            item = QTreeWidgetItem([strip_filepath(filepath)])
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

    def _on_item_clicked(self, item):
        if (index := self._tree.indexOfTopLevelItem(item)) == self.current_index:
            return None

        self._save_current()
        self.current_index = index
        self._update_highlight()
        filepath = item.data(0, Qt.ItemDataRole.UserRole)
        self.load_requested.emit(filepath)
        self._session_modified = False

    def _on_context_menu(self, pos):
        if (item := self._tree.itemAt(pos)) is None:
            return None

        index = self._tree.indexOfTopLevelItem(item)
        menu = QMenu(self.window())
        menu.setWindowFlags(
            menu.windowFlags()
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        remove_action = menu.addAction("Remove from list")
        action = menu.exec(self._tree.viewport().mapToGlobal(pos))
        if action == remove_action:
            self.remove_session(index)
        self._update_highlight()

    def _apply_tree_style(self):
        ContainerTreeWidget.apply_tree_stylesheet(self._tree)

    def _on_theme_changed(self):
        self._apply_tree_style()
        self._header._on_theme_changed()


# Backward compatibility aliases
ContainerListWidget = ContainerTreeWidget
StyledListWidgetItem = StyledTreeWidgetItem
