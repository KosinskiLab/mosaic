from PyQt6.QtWidgets import (
    QVBoxLayout,
    QDialog,
    QLabel,
    QDoubleSpinBox,
    QHBoxLayout,
    QPushButton,
    QListWidget,
    QRadioButton,
    QButtonGroup,
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
        main_layout = QVBoxLayout()
        lists_layout = QHBoxLayout()

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

        for name, *_ in self.cluster_data:
            self.source_list.addItem(name)
            self.target_list.addItem(name)

        lists_layout.addLayout(source_layout)
        lists_layout.addLayout(target_layout)

        bottom_layout = QVBoxLayout()

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

        direction_layout = QHBoxLayout()
        label = QLabel("Direction:")
        tooltip = format_tooltip(
            "Direction",
            "Select whether to keep points with distances greater than or less than equal to the specified value",
            None,
        )
        label.setToolTip(tooltip)
        direction_layout.addWidget(label)

        comparison_layout = QHBoxLayout()
        self.comparison_group = QButtonGroup()

        self.larger_radio = QRadioButton(">")
        tooltip = format_tooltip(
            "Greater than",
            "Keep points with distances larger than the specified value",
            None,
        )
        self.larger_radio.setToolTip(tooltip)
        self.larger_radio.setChecked(True)

        self.smaller_radio = QRadioButton("≤")
        tooltip = format_tooltip(
            "Less than or equal",
            "Keep points with distances less than or equal to the specified value",
            None,
        )
        self.smaller_radio.setToolTip(tooltip)

        self.comparison_group.addButton(self.larger_radio)
        self.comparison_group.addButton(self.smaller_radio)

        comparison_layout.addWidget(self.larger_radio)
        comparison_layout.addWidget(self.smaller_radio)
        comparison_layout.setSpacing(10)

        direction_layout.addLayout(comparison_layout)
        direction_layout.addStretch()

        dist_layout.addSpacing(20)
        dist_layout.addLayout(direction_layout)
        dist_layout.addStretch()

        apply_btn = QPushButton("Apply Crop")
        apply_btn.clicked.connect(self.apply_crop)

        bottom_layout.addLayout(dist_layout)
        bottom_layout.addWidget(apply_btn)

        main_layout.addLayout(lists_layout)
        main_layout.addLayout(bottom_layout)
        self.setLayout(main_layout)

    def get_results(self):
        if self.exec() == QDialog.DialogCode.Accepted:
            return self.sources, self.targets, self.distance, self.keep_smaller
        return None, None, None, None

    def apply_crop(self):
        self.sources = [
            self.source_list.row(x) for x in self.source_list.selectedItems()
        ]
        self.targets = [
            self.target_list.row(x) for x in self.target_list.selectedItems()
        ]
        self.distance = self.distance_input.value()
        self.keep_smaller = self.smaller_radio.isChecked()
        self.accept()
