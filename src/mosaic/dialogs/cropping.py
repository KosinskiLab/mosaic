from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
    QVBoxLayout,
    QDialog,
    QLabel,
    QDoubleSpinBox,
    QHBoxLayout,
    QPushButton,
    QListWidget,
    QRadioButton,
    QButtonGroup,
    QGroupBox,
    QWidget,
    QFrame,
    QMessageBox,
)

from ..widgets import DialogFooter, ContainerListWidget, StyledListWidgetItem
from ..stylesheets import (
    QGroupBox_style,
    QPushButton_style,
    QScrollArea_style,
    HelpLabel_style,
    QListWidget_style,
)


class DistanceCropDialog(QDialog):
    cropApplied = Signal(dict)

    def __init__(self, clusters, fits=[], parent=None):
        super().__init__(parent)
        self.clusters = clusters
        self.fits = fits

        self.setWindowTitle("Distance Crop")
        self.resize(800, 550)
        self.setup_ui()
        self.setStyleSheet(
            QGroupBox_style
            + QPushButton_style
            + QScrollArea_style
            + QListWidget_style
            + """
            QRadioButton {
                spacing: 5px;
            }
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
            }
            """
        )

    def setup_ui(self):
        from ..icons import (
            dialog_selectall_icon,
            dialog_selectnone_icon,
        )

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        selection_widget = QWidget()
        selection_layout = QHBoxLayout(selection_widget)
        selection_layout.setContentsMargins(0, 0, 0, 0)
        selection_layout.setSpacing(15)

        source_panel = QGroupBox("Source Clusters")
        source_layout = QVBoxLayout(source_panel)
        source_layout.setSpacing(10)

        source_description = QLabel("Select clusters to crop based on distance")
        source_description.setStyleSheet(HelpLabel_style)
        source_layout.addWidget(source_description)

        # Quick select buttons
        quick_select_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.setIcon(dialog_selectall_icon)
        select_all_btn.clicked.connect(lambda: self.source_list.selectAll())
        select_none_btn = QPushButton("Clear")
        select_none_btn.setIcon(dialog_selectnone_icon)
        select_none_btn.clicked.connect(lambda: self.source_list.clearSelection())

        quick_select_layout.addWidget(select_all_btn)
        quick_select_layout.addWidget(select_none_btn)
        source_layout.addLayout(quick_select_layout)

        self.source_list = ContainerListWidget(border=False)
        self.source_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        source_layout.addWidget(self.source_list)

        selection_layout.addWidget(source_panel)

        target_panel = QGroupBox("Target Reference")
        target_layout = QVBoxLayout(target_panel)
        target_layout.setSpacing(10)

        target_description = QLabel("Select reference objects to compute distances to")
        target_description.setStyleSheet(HelpLabel_style)
        target_layout.addWidget(target_description)

        target_select_layout = QHBoxLayout()
        target_all_btn = QPushButton("Select All")
        target_all_btn.setIcon(dialog_selectall_icon)
        target_all_btn.clicked.connect(lambda: self.target_list.selectAll())
        target_none_btn = QPushButton("Clear")
        target_none_btn.setIcon(dialog_selectnone_icon)
        target_none_btn.clicked.connect(lambda: self.target_list.clearSelection())
        target_select_layout.addWidget(target_all_btn)
        target_select_layout.addWidget(target_none_btn)
        target_layout.addLayout(target_select_layout)

        self.target_list = ContainerListWidget(border=False)
        self.target_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        target_layout.addWidget(self.target_list)

        selection_layout.addWidget(target_panel)
        main_layout.addWidget(selection_widget)

        settings_group = QGroupBox("Distance Settings")
        settings_layout = QHBoxLayout(settings_group)

        distance_layout = QHBoxLayout()
        distance_label = QLabel("Maximum Distance:")
        distance_label.setMinimumWidth(150)

        self.distance_input = QDoubleSpinBox()
        self.distance_input.setValue(40.0)
        self.distance_input.setRange(0.01, 9999.99)
        self.distance_input.setMaximum(float("inf"))
        self.distance_input.setDecimals(2)
        self.distance_input.setSingleStep(1.0)
        self.distance_input.setMinimumWidth(100)
        distance_layout.addWidget(distance_label)
        distance_layout.addWidget(self.distance_input)
        distance_layout.addStretch()
        settings_layout.addLayout(distance_layout)

        direction_layout = QHBoxLayout()
        direction_label = QLabel("Keep Points:")
        direction_label.setMinimumWidth(150)
        direction_layout.addWidget(direction_label)

        self.comparison_group = QButtonGroup()

        radio_container = QFrame()
        radio_layout = QHBoxLayout(radio_container)
        radio_layout.setContentsMargins(0, 0, 0, 0)
        radio_layout.setSpacing(15)

        self.smaller_radio = QRadioButton("Within Distance")
        self.smaller_radio.setChecked(True)
        self.larger_radio = QRadioButton("Outside Distance")
        self.comparison_group.addButton(self.smaller_radio)
        self.comparison_group.addButton(self.larger_radio)

        radio_layout.addWidget(self.smaller_radio)
        radio_layout.addWidget(self.larger_radio)
        radio_layout.addStretch()

        direction_layout.addWidget(radio_container)
        settings_layout.addLayout(direction_layout)
        main_layout.addWidget(settings_group)

        footer = DialogFooter(
            info_text="Points will be filtered based on their distance to the target references.",
            dialog=self,
            margin=(0, 15, 0, 0),
        )
        main_layout.addWidget(footer)

        self.populate_lists()

    def populate_lists(self):
        for name, data in self.clusters:
            item = StyledListWidgetItem(name, data.visible, data._meta.get("info"))
            item.setData(Qt.ItemDataRole.UserRole, data)
            self.source_list.addItem(item)

        for name, data in self.clusters:
            item = StyledListWidgetItem(name, data.visible, data._meta.get("info"))
            item.setData(Qt.ItemDataRole.UserRole, data)
            self.target_list.addItem(item)

        for name, data in self.fits:
            item = StyledListWidgetItem(name, data.visible, data._meta.get("info"))
            item.setData(Qt.ItemDataRole.UserRole, data)
            self.target_list.addItem(item)

    def get_results(self):
        if self.exec() == QDialog.DialogCode.Accepted:
            return self.sources, self.targets, self.distance, self.keep_smaller
        return None, None, None, None

    def accept(self):
        self.sources = [
            x.data(Qt.ItemDataRole.UserRole) for x in self.source_list.selectedItems()
        ]
        self.targets = [
            x.data(Qt.ItemDataRole.UserRole) for x in self.target_list.selectedItems()
        ]

        if not self.sources:
            return QMessageBox.warning(
                self,
                "Selection Required",
                "Please select at least one source cluster to crop.",
            )

        if not self.targets:
            return QMessageBox.warning(
                self,
                "Selection Required",
                "Please select at least one target reference.",
            )

        self.distance = self.distance_input.value()
        self.keep_smaller = self.smaller_radio.isChecked()

        crop_data = {
            "sources": self.sources,
            "targets": self.targets,
            "distance": self.distance,
            "keep_smaller": self.keep_smaller,
        }
        self.cropApplied.emit(crop_data)
        return super().accept()
