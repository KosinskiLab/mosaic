from qtpy.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QDialog,
    QLabel,
    QComboBox,
    QPushButton,
    QWidget,
    QDoubleSpinBox,
    QScrollArea,
    QGroupBox,
    QFrame,
    QLineEdit,
    QMessageBox,
    QCheckBox,
)
import qtawesome as qta

from ..widgets import DialogFooter
from ..stylesheets import QPushButton_style


class MeshMappingRow(QWidget):
    def __init__(self, clusters, is_first=False, parent=None, dialog=None):
        super().__init__(parent)
        self.clusters = clusters
        self.dialog = dialog
        self.setup_ui()
        self.update_button_state(is_first)

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Protein Name")

        self.cluster_combo, names = QComboBox(), []
        for name, data in self.clusters:
            names.append(name)
            self.cluster_combo.addItem(name, data)

        self.name_edit.setText(self.cluster_combo.currentText())
        self.cluster_combo.currentTextChanged.connect(self.name_edit.setText)

        self.toggle_btn = QPushButton()
        self.toggle_btn.setFixedWidth(20)

        layout.addWidget(self.name_edit, 1)
        layout.addWidget(self.cluster_combo, 2)
        layout.addWidget(self.toggle_btn)

    def update_button_state(self, state):
        if state:
            self.toggle_btn.setIcon(qta.icon("fa5s.plus", color="#696c6f"))
            self.toggle_btn.clicked.connect(self.add_requested)
            return None

        self.toggle_btn.setIcon(qta.icon("fa5s.trash", color="#696c6f"))
        self.toggle_btn.clicked.connect(self.deleteLater)

    def add_requested(self):
        if self.dialog and hasattr(self.dialog, "add_mapping_row"):
            self.dialog.add_mapping_row()

    def get_parameters(self):
        return {
            "name": self.name_edit.text().strip(),
            "data": self.cluster_combo.currentData(),
        }

    def is_valid(self):
        return bool(self.name_edit.text().strip() and self.cluster_combo.currentText())


class MeshMappingDialog(QDialog):
    def __init__(self, fits, clusters, parent=None):
        super().__init__(parent)
        self.fits = fits
        self.clusters = clusters

        self.setWindowTitle("Backmapping")
        self.resize(500, 540)
        self.setup_ui()
        self.setStyleSheet(QPushButton_style)

    def setup_ui(self):
        from ..icons import dialog_margin, footer_margin

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(*dialog_margin)

        config_group = QGroupBox("Mesh")
        config_layout = QVBoxLayout()
        config_layout.setSpacing(10)

        fit_layout = QHBoxLayout()
        fit_label = QLabel("Surface:")
        self.fit_combo = QComboBox()
        for name, data in self.fits:
            self.fit_combo.addItem(name, data)
        fit_layout.addWidget(fit_label)
        fit_layout.addWidget(self.fit_combo)
        config_layout.addLayout(fit_layout)

        edge_layout = QHBoxLayout()
        edge_label = QLabel("Output Edge Length:")
        self.edge_length = QDoubleSpinBox()
        self.edge_length.setValue(40.0)
        self.edge_length.setRange(0, 1e32)
        self.edge_length.setSingleStep(0.1)
        edge_layout.addWidget(edge_label)
        edge_layout.addWidget(self.edge_length)
        config_layout.addLayout(edge_layout)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        projection_group = QGroupBox("Projection")
        projection_layout = QVBoxLayout(projection_group)
        projection_layout.setSpacing(10)
        self.cast_rays = QCheckBox("Use raycasting to project proteins onto mesh.")
        self.cast_rays.toggled.connect(
            lambda: self.flip_normals.setEnabled(self.cast_rays.isChecked())
        )

        self.flip_normals = QCheckBox("Flip normal direction (needs to point inward).")
        self.cast_rays.setChecked(False)
        self.flip_normals.setChecked(False)
        self.flip_normals.setEnabled(False)
        projection_layout.addWidget(self.cast_rays)
        projection_layout.addWidget(self.flip_normals)
        layout.addWidget(projection_group)

        mapping_group = QGroupBox("Inclusions")
        mapping_layout = QVBoxLayout()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.mapping_container = QWidget()
        self.mapping_layout = QVBoxLayout(self.mapping_container)
        self.mapping_layout.setContentsMargins(0, 0, 0, 0)
        self.mapping_layout.setSpacing(5)
        self.mapping_layout.addStretch()

        scroll.setWidget(self.mapping_container)
        mapping_layout.addWidget(scroll)
        mapping_group.setLayout(mapping_layout)
        layout.addWidget(mapping_group)

        footer = DialogFooter(dialog=self, margin=footer_margin)
        layout.addWidget(footer)

        first_row = MeshMappingRow(
            self.clusters, is_first=True, parent=self.mapping_container, dialog=self
        )
        self.mapping_layout.insertWidget(self.mapping_layout.count() - 1, first_row)

    def accept(self):
        """Validate the dialog inputs before accepting"""
        if not self.fit_combo.currentText():
            QMessageBox.warning(
                self, "Validation Error", "Please select a surface fit."
            )
            return

        valid_mappings = False
        for i in range(self.mapping_layout.count() - 1):
            widget = self.mapping_layout.itemAt(i).widget()
            if isinstance(widget, MeshMappingRow) and widget.is_valid():
                valid_mappings = True
                break

        if not valid_mappings:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Please add at least one valid cluster mapping.",
            )
            return

        return super().accept()

    def add_mapping_row(self):
        new_row = MeshMappingRow(
            self.clusters, is_first=False, parent=self.mapping_container, dialog=self
        )
        self.mapping_layout.insertWidget(self.mapping_layout.count() - 1, new_row)

    def get_parameters(self):
        selected_fit = self.fit_combo.currentData()
        edge_length = self.edge_length.value()

        mappings = []
        for i in range(self.mapping_layout.count() - 1):
            widget = self.mapping_layout.itemAt(i).widget()
            if isinstance(widget, MeshMappingRow):
                mappings.append(widget.get_parameters())

        return (
            selected_fit,
            edge_length,
            mappings,
            self.cast_rays.isChecked(),
            self.flip_normals.isChecked(),
        )
