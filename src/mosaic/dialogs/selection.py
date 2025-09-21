from typing import List

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QWidget,
    QListWidget,
    QGroupBox,
)

from ..widgets import DialogFooter
from ..stylesheets import QPushButton_style, QScrollArea_style


class ObjectSelectionWidget(QWidget):
    """Reusable widget for selecting objects (clusters and models)"""

    def __init__(self, cdata, parent=None):
        super().__init__(parent)
        self.cdata = cdata
        self._setup_ui()
        self.populate_lists()

        self.setStyleSheet(QPushButton_style + QScrollArea_style)

    def _setup_ui(self):
        from ..widgets import ContainerListWidget
        from ..icons import dialog_selectall_icon, dialog_selectnone_icon

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Quick select buttons
        objects_panel = QGroupBox("Objects")

        objects_layout = QVBoxLayout()

        quick_select_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.setIcon(dialog_selectall_icon)
        select_all_btn.clicked.connect(lambda: self.objects_list.selectAll())

        clear_btn = QPushButton("Clear")
        clear_btn.setIcon(dialog_selectnone_icon)
        clear_btn.clicked.connect(lambda: self.objects_list.clearSelection())

        quick_select_layout.addWidget(select_all_btn)
        quick_select_layout.addWidget(clear_btn)
        objects_layout.addLayout(quick_select_layout)

        self.objects_list = ContainerListWidget(border=False)
        self.objects_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        objects_layout.addWidget(self.objects_list)
        objects_panel.setLayout(objects_layout)

        layout.addWidget(objects_panel)

    def _make_items(self, data, data_type: str, ids: List[int]):
        from ..widgets import StyledListWidgetItem

        all_ids, new_items = [], []
        for name, obj in data:
            object_id = id(obj)

            all_ids.append(object_id)

            item = self.get_item_by_id(object_id)

            is_new = item is None
            if is_new:
                item = StyledListWidgetItem(name, obj.visible, obj._meta.get("info"))

            # Sync properties of new and existing items
            item.setText(name)
            item.set_visible(obj.visible)
            item.setData(Qt.ItemDataRole.UserRole, obj)
            item.setData(Qt.ItemDataRole.UserRole + 1, data_type)
            item.setData(Qt.ItemDataRole.UserRole + 2, id(obj))

            if is_new:
                new_items.append(item)
        return all_ids, new_items

    def populate_lists(self):
        ids = [item.data(Qt.ItemDataRole.UserRole + 2) for item in self.allItems()]

        selected = [
            item.data(Qt.ItemDataRole.UserRole + 2) for item in self.selectedItems()
        ]

        data = self.cdata.format_datalist("data")
        all_ids, new_items = self._make_items(data, "cluster", ids)

        data = self.cdata.format_datalist("models")
        _all_ids, _new_items = self._make_items(data, "models", ids)

        all_ids.extend(_all_ids)
        new_items.extend(_new_items)

        # Remove objects that have been deleted, add new items and keep selection
        deleted_ids = set(ids) - set(all_ids)
        for i in reversed(range(self.objects_list.count())):
            item = self.objects_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole + 2) in deleted_ids:
                _ = self.objects_list.takeItem(i)

        for item in new_items:
            self.objects_list.addItem(item)
        return self.set_selection(set(selected) & set(all_ids))

    def get_item_by_id(self, obj_id: int):
        for i in range(self.objects_list.count()):
            item = self.objects_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole + 2) == obj_id:
                return item
        return None

    def selectedItems(self):
        return self.objects_list.selectedItems()

    def allItems(self):
        return [self.objects_list.item(i) for i in range(self.objects_list.count())]

    def get_selected_objects(self):
        """Get names of selected objects"""
        return [item.text() for item in self.objects_list.selectedItems()]

    def set_selection(self, object_ids):
        """Set which objects are selected by their IDs"""
        for i in range(self.objects_list.count()):
            item = self.objects_list.item(i)
            object_id = item.data(Qt.ItemDataRole.UserRole + 2)
            item.setSelected(object_id in object_ids)


class ActorSelectionDialog(QDialog):
    """Simple dialog for selecting actors for visibility animation"""

    def __init__(self, cdata, current_selection=None, parent=None):
        super().__init__()
        self.cdata = cdata
        self.current_selection = current_selection or []

        self.setWindowTitle("Select Objects for Animation")
        self.resize(400, 450)
        self.setModal(True)

        self._setup_ui()
        self.setStyleSheet(QPushButton_style + QScrollArea_style)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.selection_widget = ObjectSelectionWidget(self.cdata, self)
        layout.addWidget(self.selection_widget)

        if self.current_selection:
            self.selection_widget.set_selection(self.current_selection)

        footer = DialogFooter(
            dialog=self,
            margin=(0, 15, 0, 0),
        )
        layout.addWidget(footer)

    def get_selected_objects(self):
        """Get names of selected objects"""
        return [
            item.data(Qt.ItemDataRole.UserRole + 2)
            for item in self.selection_widget.selectedItems()
        ]
