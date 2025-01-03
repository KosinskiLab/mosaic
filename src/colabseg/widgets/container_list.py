from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QLabel,
    QListWidget,
    QSizePolicy,
    QApplication,
)


class ContainerListWidget(QFrame):
    def __init__(self, title):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Expanding
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        app = QApplication.instance()
        app.paletteChanged.connect(self.updateStyleSheet)
        title_label = QLabel(title)
        title_label.setStyleSheet(
            """
            QLabel {
                font-weight: 600;
                font-size: 14px;
                padding-left: 8px;
                padding-top: 8px;
                border: 0px solid transparent;
            }
        """
        )
        layout.addWidget(title_label)

        self.list_widget = QListWidget()
        self.list_widget.setFrameStyle(QFrame.Shape.NoFrame)
        self.list_widget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.list_widget.setStyleSheet(
            """
            QListWidget {
                border: none;
                background-color: transparent;
                outline: none;
                padding: 4px 0px;
            }
            QListWidget::item {
                border-radius: 6px;
                padding: 0px 12px;
                margin: 2px 8px;
                font-size: 11px;
            }
            QListWidget::item:hover {
                background-color: rgba(0, 0, 0, 0.10);
            }
            QListWidget::item:selected {
                background-color: rgba(99, 102, 241, 0.3);
                font-weight: 500;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 8px;
                margin: 4px 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(209, 213, 219, 0.5);
                border-radius: 4px;
                min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(209, 213, 219, 0.8);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """
        )

        layout.addWidget(self.list_widget)
        self.updateStyleSheet()

    def updateStyleSheet(self):
        return self.setStyleSheet(
            """
            QFrame {
                background-color: transparent;
                border: none;
                border-bottom: 1px solid #6b7280;
            }
        """
        )

    def __getattr__(self, name):
        return getattr(self.list_widget, name)
