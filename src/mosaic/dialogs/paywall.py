from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
)
import qtawesome as qta


class PaywallDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Premium Features")
        self.setFixedWidth(400)

        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(24, 24, 24, 24)

        icon_label = QLabel()
        icon = qta.icon("fa5b.paypal", color="#009cde", scale_factor=2)
        icon_label.setPixmap(icon.pixmap(48, 48))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        message = QLabel(
            "<h3>Unlock Premium Features</h3>"
            "<p>Create high-resolution meshes with more than 50 vertices "
            "and unlock all premium features of ColabSeg.</p>"
            "<p><b>Only $10.99/month</b></p>"
        )
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message.setStyleSheet(
            """
            QLabel {
                font-size: 13px;
                line-height: 1.5;
            }
        """
        )
        layout.addWidget(message)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)

        subscribe_btn = QPushButton("Subscribe Now")
        subscribe_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #009cde;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #008abd;
            }
        """
        )
        subscribe_btn.clicked.connect(self.handle_subscribe)

        cancel_btn = QPushButton("Maybe Later")
        cancel_btn.setStyleSheet(
            """
            QPushButton {
                background-color: transparent;
                color: #6b7280;
                border: 1px solid #d1d5db;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #f3f4f6;
            }
        """
        )
        cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(subscribe_btn)
        layout.addLayout(button_layout)

    def handle_subscribe(self):
        import webbrowser

        webbrowser.open("https://www.youtube.com/shorts/SXHMnicI6Pg")
        self.accept()

    @staticmethod
    def show_dialog(parent=None):
        dialog = PaywallDialog()
        return dialog.exec()
