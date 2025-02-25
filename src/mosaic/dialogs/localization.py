from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QGroupBox,
    QCompleter,
    QListWidgetItem,
)

__all__ = ["LocalizationDialog"]

_colormaps = sorted(
    [
        "viridis",
        "plasma",
        "inferno",
        "magma",
        "cividis",
        "cool",
        "turbo",
        "jet",
    ]
)


class LocalizationDialog(QDialog):
    previewRequested = Signal(dict)

    def __init__(self, clusters, fits=[], parent=None):
        super().__init__(parent)
        self.clusters = clusters
        self.fits = fits

        self.setWindowTitle("Localization")
        self.setMinimumWidth(400)
        self.setup_ui()

        self.update_target_selection()

    def setup_ui(self):
        layout = QVBoxLayout()

        preset_group = QGroupBox("Quick Presets")
        preset_layout = QHBoxLayout()

        identity_btn = QPushButton("Color by Identity")
        identity_btn.clicked.connect(self.preset_identity)
        camera_btn = QPushButton("Color by Camera")
        camera_btn.clicked.connect(self.preset_camera)

        preset_layout.addWidget(identity_btn)
        preset_layout.addWidget(camera_btn)
        preset_group.setLayout(preset_layout)
        layout.addWidget(preset_group)

        object_group = QGroupBox("Select Objects")
        object_layout = QVBoxLayout()
        self.object_list = QListWidget()
        self.object_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        for name, data in self.clusters:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, data)
            self.object_list.addItem(item)
        for name, data in self.fits:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, data)
            self.object_list.addItem(item)

        object_layout.addWidget(self.object_list)
        object_group.setLayout(object_layout)
        layout.addWidget(object_group)

        color_group = QGroupBox("Color Options")
        color_layout = QVBoxLayout()

        criteria_layout = QVBoxLayout()
        criteria_label = QLabel("Color Based On:")
        self.color_criteria_combo = QComboBox()
        self.color_criteria_combo.addItems(
            [
                "Identity",
                "Camera Distance",
                "Cluster Distance",
                "Fit Distance",
                "Volume",
                "Segments",
            ]
        )
        self.color_criteria_combo.currentTextChanged.connect(
            self.update_target_selection
        )
        criteria_layout.addWidget(criteria_label)
        criteria_layout.addWidget(self.color_criteria_combo)
        color_layout.addLayout(criteria_layout)

        self.target_layout = QVBoxLayout()
        self.target_label = QLabel("Select Target:")
        self.target_combo = QComboBox()
        self.target_combo.setEditable(True)
        self.target_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        completer = QCompleter()
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.target_combo.setCompleter(completer)
        self.target_layout.addWidget(self.target_label)
        self.target_layout.addWidget(self.target_combo)
        color_layout.addLayout(self.target_layout)

        map_layout = QVBoxLayout()
        map_label = QLabel("Color Mapping:")
        self.color_map_combo = QComboBox()
        self.color_map_combo.addItems(_colormaps)
        self.color_map_combo.setCurrentText("viridis")
        map_layout.addWidget(map_label)
        map_layout.addWidget(self.color_map_combo)
        color_layout.addLayout(map_layout)

        # Create horizontal layout for checkboxes
        checkbox_layout = QHBoxLayout()
        self.reverse_checkbox = QCheckBox("Reverse Color")
        self.normalize_checkbox = QCheckBox("Normalize per Object")
        checkbox_layout.addWidget(self.reverse_checkbox)
        checkbox_layout.addWidget(self.normalize_checkbox)
        color_layout.addLayout(checkbox_layout)

        color_group.setLayout(color_layout)
        layout.addWidget(color_group)

        button_layout = QHBoxLayout()
        preview_button = QPushButton("Preview")
        preview_button.clicked.connect(self.handle_preview)
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        button_layout.addWidget(preview_button)
        button_layout.addStretch()

        button_layout.addWidget(cancel_button)
        button_layout.addWidget(self.apply_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)
        self.update_target_selection()

    def update_target_selection(self):
        self.target_combo.clear()
        criteria = self.color_criteria_combo.currentText()

        self.target_label.setVisible(True)
        self.target_combo.setVisible(True)
        self.normalize_checkbox.setEnabled(criteria != "Identity")

        if criteria == "Cluster Distance":
            self.target_combo.addItems([name for name, _ in self.clusters])
        elif criteria == "Fit Distance":
            self.target_combo.addItems([name for name, _ in self.fits])
        else:
            self.target_label.setVisible(False)
            self.target_combo.setVisible(False)

        completer = self.target_combo.completer()
        completer.setModel(self.target_combo.model())

    def preset_identity(self):
        self.color_criteria_combo.setCurrentText("Identity")
        self.color_map_combo.setCurrentText("viridis")
        self.reverse_checkbox.setChecked(False)
        self.normalize_checkbox.setChecked(False)
        self.object_list.selectAll()

    def preset_camera(self):
        self.color_criteria_combo.setCurrentText("Camera Distance")
        self.color_map_combo.setCurrentText("jet")
        self.reverse_checkbox.setChecked(True)
        self.normalize_checkbox.setChecked(False)
        if self.target_combo.count() > 0:
            self.target_combo.setCurrentIndex(0)
        self.object_list.selectAll()

    def handle_preview(self):
        self.previewRequested.emit(self.get_settings())

    def get_settings(self):
        target = None
        if self.target_combo.isVisible():
            index = self.target_combo.currentIndex()
            target = self.fits[index][1]

        return {
            "objects": [
                item.data(Qt.ItemDataRole.UserRole)
                for item in self.object_list.selectedItems()
            ],
            "color_by": self.color_criteria_combo.currentText(),
            "color_map": self.color_map_combo.currentText(),
            "reverse": self.reverse_checkbox.isChecked(),
            "normalize_per_object": self.normalize_checkbox.isChecked(),
            "target": target,
        }
