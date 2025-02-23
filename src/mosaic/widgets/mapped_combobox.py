from typing import Dict
from qtpy.QtWidgets import QFileDialog, QComboBox
from qtpy.QtCore import Signal


class MappedComboBox(QComboBox):
    customPathSelected = Signal(str)

    def __init__(self, parent=None, choices: Dict = {}):
        super().__init__(parent)

        self.setup_models(choices)
        self.currentTextChanged.connect(self._handle_selection)
        self.setSizePolicy(QComboBox().sizePolicy())

    def setup_models(self, choices):
        self.clear()
        self.predefined_models = choices | {"Browse...": None}
        self.addItems(self.predefined_models.keys())

    def _handle_selection(self, text):
        if text == "Browse...":
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Model Checkpoint",
                "",
                "Checkpoint Files (*.ckpt *.pth);;All Files (*.*)",
            )

            if file_path:
                display_name = file_path
                self.predefined_models[display_name] = file_path

                self.blockSignals(True)
                self.insertItem(self.count() - 1, display_name)
                self.setCurrentText(display_name)
                self.blockSignals(False)

                self.customPathSelected.emit(file_path)
            else:
                self.blockSignals(True)
                self.setCurrentIndex(0)
                self.blockSignals(False)

    def get_selected_path(self):
        return self.predefine
