from PyQt6.QtWidgets import (
    QVBoxLayout,
    QDialog,
    QLabel,
    QDoubleSpinBox,
    QHBoxLayout,
    QPushButton,
    QListWidget,
)
from ..widgets.settings import format_tooltip


class DistanceCropDialog(QDialog):
    def __init__(self, cluster_data, parent=None):
        super().__init__(parent)
        self.cluster_data = cluster_data
        self.setWindowTitle("Distance Crop")
        self.resize(500, 250)
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout()

        source_layout = QVBoxLayout()
        label = QLabel("Source Clusters")
        tooltip = format_tooltip("Source Clusters", "Clusters to crop.", None)
        label.setToolTip(tooltip)
        source_layout.addWidget(label)
        self.source_list = QListWidget()
        self.source_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        source_layout.addWidget(self.source_list)

        target_layout = QVBoxLayout()
        label = QLabel("Target Clusters")
        tooltip = format_tooltip(
            "Target Clusters", "Reference to compute source distances to.", None
        )
        label.setToolTip(tooltip)
        target_layout.addWidget(label)
        self.target_list = QListWidget()
        self.target_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        target_layout.addWidget(self.target_list)

        for name, _ in self.cluster_data:
            self.source_list.addItem(name)
            self.target_list.addItem(name)

        param_layout = QVBoxLayout()
        dist_layout = QHBoxLayout()
        label = QLabel("Distance:")
        tooltip = format_tooltip(
            "Distance", "Maximum distance between source and target.", 40
        )
        label.setToolTip(tooltip)
        dist_layout.addWidget(label)
        self.distance_input = QDoubleSpinBox()
        self.distance_input.setValue(40.0)
        self.distance_input.setMaximum(float("inf"))
        self.distance_input.setMinimumWidth(100)
        self.distance_input.setDecimals(2)
        dist_layout.addWidget(self.distance_input)

        apply_btn = QPushButton("Apply Crop")
        apply_btn.clicked.connect(self.apply_crop)

        param_layout.addLayout(dist_layout)
        param_layout.addWidget(apply_btn)
        param_layout.addStretch()

        layout.addLayout(source_layout)
        layout.addLayout(target_layout)
        layout.addLayout(param_layout)
        self.setLayout(layout)

    def get_results(self):
        if self.exec() == QDialog.DialogCode.Accepted:
            return self.sources, self.targets, self.distance
        return None, None, None

    def apply_crop(self):
        self.sources = [
            self.source_list.row(x) for x in self.source_list.selectedItems()
        ]
        self.targets = [
            self.target_list.row(x) for x in self.target_list.selectedItems()
        ]
        self.distance = self.distance_input.value()
        self.accept()
