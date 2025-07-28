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

    def populate_lists(self):
        """Same logic as PropertyAnalysisDialog.populate_lists()"""
        from ..widgets import StyledListWidgetItem

        self.objects_list.clear()

        clusters = self.cdata.format_datalist("data")
        for name, obj in clusters:
            item = StyledListWidgetItem(name, obj.visible, obj._meta.get("info"))
            item.setData(Qt.ItemDataRole.UserRole, obj)
            item.setData(Qt.ItemDataRole.UserRole + 1, "cluster")
            item.setData(Qt.ItemDataRole.UserRole + 2, id(obj))
            self.objects_list.addItem(item)

        models = self.cdata.format_datalist("models")
        for name, obj in models:
            item = StyledListWidgetItem(name, obj.visible, obj._meta.get("info"))
            item.setData(Qt.ItemDataRole.UserRole, obj)
            item.setData(Qt.ItemDataRole.UserRole + 1, "model")
            item.setData(Qt.ItemDataRole.UserRole + 2, id(obj))
            self.objects_list.addItem(item)

    def selectedItems(self):
        return self.objects_list.selectedItems()

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
