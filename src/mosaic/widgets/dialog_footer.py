from typing import Tuple

from qtpy.QtWidgets import (
    QLabel,
    QHBoxLayout,
    QPushButton,
    QFrame,
    QDialog,
)
from ..stylesheets import HelpLabel_style, QPushButton_style


class DialogFooter(QFrame):
    def __init__(
        self, info_text: str = None, dialog: QDialog = None, margin: Tuple[int] = None
    ):
        super().__init__()

        from mosaic.icons import dialog_reject_icon, dialog_accept_icon, info_icon

        # left, top, right, bottom
        layout = QHBoxLayout(self)
        if margin is not None:
            layout.setContentsMargins(*margin)

        if info_text is not None:
            info = QLabel()
            info.setPixmap(info_icon)
            info.setStyleSheet(HelpLabel_style)
            info_label = QLabel(info_text)
            info_label.setStyleSheet(HelpLabel_style)

            layout.addWidget(info)
            layout.addWidget(info_label)
            layout.addStretch()

        self.reject_button = QPushButton("Cancel")
        self.reject_button.setIcon(dialog_reject_icon)

        self.accept_button = QPushButton("Done")
        self.accept_button.setIcon(dialog_accept_icon)

        if isinstance(dialog, QDialog):
            self.reject_button.clicked.connect(dialog.reject)
            self.accept_button.clicked.connect(dialog.accept)

        layout.addWidget(self.reject_button)
        layout.addWidget(self.accept_button)
        self.setStyleSheet(QPushButton_style)
