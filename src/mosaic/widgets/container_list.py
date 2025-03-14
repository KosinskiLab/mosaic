from qtpy.QtCore import Qt
from qtpy.QtGui import QColor, QIcon, QPixmap, QPainter

from qtpy.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QLabel,
    QListWidget,
    QSizePolicy,
    QApplication,
    QListWidgetItem,
)


class ContainerListWidget(QFrame):
    def __init__(self, title: str = None):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title = title
        app = QApplication.instance()
        app.paletteChanged.connect(self.updateStyleSheet)
        if self.title is not None:
            self.setSizePolicy(
                QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Expanding
            )

            title_label = QLabel(self.title)
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

        if self.title is not None:
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
                    font-size: 13px;
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
        else:
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
                    margin: 2px 8px;
                    font-size: 14px;
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
        if self.title is not None:
            return self.setStyleSheet(
                """
                QFrame {
                    background-color: transparent;
                    border: none;
                    border-bottom: 1px solid #6b7280;
                }
            """
            )
        return None

    def __getattr__(self, name):
        return getattr(self.list_widget, name)


class StyledListWidgetItem(QListWidgetItem):
    def __init__(self, text, visible=True, metadata=None, parent=None):
        super().__init__(text, parent)

        self.visible = visible
        self.metadata = metadata or {}

        self.invisible_color = QColor(128, 128, 128)
        self.setFlags(self.flags() | Qt.ItemFlag.ItemIsEditable)
        self._update_visibility_icon(visible)

    def _update_visibility_icon(self, visible):
        """Create a small colored dot icon to indicate visibility."""
        self.visible = visible

        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = self.invisible_color
        if visible:
            color = QColor(99, 102, 241, int(0.3 * 255))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(4, 4, 8, 8)
        painter.end()

        self.setIcon(QIcon(pixmap))

    def set_visible(self, visible):
        if visible != self.visible:
            self._update_visibility_icon(visible)

        if not visible:
            self.setForeground(self.invisible_color)

    def set_metadata(self, metadata):
        """Update the metadata and tooltip."""
        self.metadata = metadata
        self._update_tooltip()
