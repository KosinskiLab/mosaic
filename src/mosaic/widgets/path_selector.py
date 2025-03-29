from qtpy.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
    QFrame,
    QFileDialog,
)


class PathSelector(QWidget):
    """Reusable component for file path selection with browse button"""

    def __init__(
        self,
        label_text="",
        placeholder="Path to file",
        file_mode: bool = True,
        parent=None,
    ):
        """
        Initialize the file path selector widget.

        Parameters:
        -----------
        label_text : str
            Text to show as label above the path field
        placeholder : str
            Placeholder text for the input field
        file_mode : str
            Whether integrated button triggers file or directory selection.
        parent : QWidget
            Parent widget
        """
        super().__init__(parent)

        self.file_mode = file_mode
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)

        if label_text:
            self.label = QLabel(label_text)
            self.label.setStyleSheet(
                """
                QLabel {
                    font-size: 12px;
                    font-weight: 500;
                    margin-bottom: 1px;
                }
            """
            )
            main_layout.addWidget(self.label)

        self.container_frame = QFrame()
        self.container_frame.setObjectName("container_frame")
        self.container_frame.setStyleSheet(
            """
            #container_frame {
                border: 1px solid #d1d5db;
                border-radius: 4px;
            }
            #container_frame:focus-within {
                border-color: #6366f1;
            }
        """
        )

        container_layout = QHBoxLayout(self.container_frame)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText(placeholder)
        self.path_input.setStyleSheet(
            """
            QLineEdit {
                border: none;
                background-color: transparent;
                padding: 6px 8px;
            }
        """
        )

        self.browse_button = QPushButton("Browse")
        self.browse_button.setStyleSheet(
            """
            QPushButton {
                background-color: #f3f4f6;
                border: none;
                border-left: 1px solid #d1d5db;
                padding: 6px 12px;
                min-width: 70px;
                color: #374151;
            }
            QPushButton:hover {
                background-color: #e5e7eb;
            }
            QPushButton:pressed {
                background-color: #d1d5db;
            }
        """
        )
        self.browse_button.clicked.connect(self._browse_clicked)

        container_layout.addWidget(self.path_input, 1)
        container_layout.addWidget(self.browse_button)

        main_layout.addWidget(self.container_frame)

    def _browse_clicked(self):
        if self.file_mode:
            path, _ = QFileDialog.getOpenFileName(self, "Select File")
        else:
            path = QFileDialog.getExistingDirectory(self, "Select Directory")

        if path:
            return self.set_path(path)

    def get_path(self):
        """Get the currently entered path"""
        return self.path_input.text()

    def set_path(self, path):
        """Set the path in the input field"""
        self.path_input.setText(path)
