from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton,
    QListWidget, QCheckBox, QComboBox, QHBoxLayout
)

class LocalizationDialog(QDialog):
    def __init__(self, clusters, fits=[], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Localization")
        self.setMinimumWidth(300)

        layout = QVBoxLayout()

        layout.addWidget(QLabel("Select Objects:"))
        self.object_list = QListWidget(self)
        self.object_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)

        for name, _ in clusters:
            self.object_list.addItem(name)

        layout.addWidget(self.object_list)

        layout.addWidget(QLabel("Color Based On:"))
        self.color_criteria_combo = QComboBox(self)
        self.color_criteria_combo.addItems(["Identity", "Camera Distance", "Cluster Distance", "Fit Distance"])
        layout.addWidget(self.color_criteria_combo)

        layout.addWidget(QLabel("Color Mapping:"))
        self.color_map_combo = QComboBox(self)
        self.color_map_combo.addItems(["Viridis", "Plasma", "Jet"])
        layout.addWidget(self.color_map_combo)

        self.reverse_checkbox = QCheckBox("Reverse Color", self)
        layout.addWidget(self.reverse_checkbox)

        self.apply_button = QPushButton("Apply", self)
        layout.addWidget(self.apply_button)

        self.setLayout(layout)

if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    object_list = [("Object1", 1), ("Object2", 2), ("MembraneA", 3), ("MembraneB", 4)]
    dialog = LocalizationDialog(object_list)
    dialog.exec()
