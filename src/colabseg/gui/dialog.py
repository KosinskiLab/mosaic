from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QDialog,
    QLabel,
    QPushButton,
)


class KeybindsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keybinds")
        # self.setFixedSize(400, 450)

        layout = QVBoxLayout()

        keybinds = [
            ("z", "Set camera view along Z-axis"),
            ("x", "Set camera view along X-axis"),
            ("c", "Set camera view along Y-axis"),
            ("d", "Toggle renderer background color"),
            ("Delete", "Remove selected cluster or points"),
            ("R", "Bring up point selector"),
            ("Right Mouse", "Deselect cluster or points"),
            ("Left Mouse Drag", "Rotate scene"),
            ("Shift Left Mouse Drag", "Translate scene"),
            ("Ctrl+O", "Open file"),
            ("Ctrl+S", "Save file"),
            ("Ctrl+H", "Show this keybinds popup"),
        ]

        for key, description in keybinds:
            key_label = QLabel(f"<b>{key}</b>: {description}")
            layout.addWidget(key_label)

        close_button = QPushButton("Close")
        close_button.setFixedSize(100, 30)
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setLayout(layout)

    def show_keybinds(parent):
        dialog = KeybindsDialog(parent)
        dialog.setStyleSheet(
            """
            QDialog {
                background-color: #f0f0f0;
            }
            QLabel {
                color: #333333;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 5px 10px;
                text-align: center;
                text-decoration: none;
                font-size: 14px;
                margin: 4px 2px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """
        )
        dialog.exec()
