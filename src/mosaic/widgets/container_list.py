from qtpy.QtCore import Qt, QRect
from qtpy.QtGui import QColor, QFont, QFontMetrics
from qtpy.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QLabel,
    QListWidget,
    QSizePolicy,
    QApplication,
    QListWidgetItem,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)
import qtawesome as qta


class ContainerListWidget(QFrame):
    def __init__(self, title: str = None, border: bool = True):
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

        self.list_widget.setItemDelegate(MetadataItemDelegate(self.list_widget))
        self.list_widget.setStyleSheet(
            """
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
            QLineEdit {
                background-color: rgba(99, 102, 241, 1.0);
                border: none;
                padding: 4px 0px;
            }
        """
        )

        layout.addWidget(self.list_widget)
        if border:
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


class StyledListWidgetItem(QListWidgetItem):
    def __init__(self, text, visible=True, metadata=None, parent=None, editable=False):
        """
        Create a styled list widget item with type-specific icons.

        Parameters
        ----------
        text : str
            The display text for the item
        visible : bool
            Whether the item is visible
        metadata : dict
            Additional metadata for the item
        parent : QWidget
            Parent widget

        """
        super().__init__(text, parent)

        self.visible = visible
        self.metadata = metadata or {}

        # Deactivate metadata label rendering
        _ = self.metadata.pop("metadata_text", None)

        self.visible_color = QColor(99, 102, 241)
        self.invisible_color = QColor(128, 128, 128)

        if editable:
            self.setFlags(self.flags() | Qt.ItemFlag.ItemIsEditable)

        self._update_icon(visible)

    def _update_icon(self, visible):
        """Update the item icon based on type and visibility."""
        self.visible = visible

        item_type = self.metadata.get("item_type")
        if item_type == "cluster":
            icon_name = "mdi.scatter-plot"
        elif item_type == "parametric":
            icon_name = "mdi.function"
        elif item_type == "mesh":
            icon_name = "mdi.triangle-outline"
        elif item_type == "trajectory":
            icon_name = "mdi.chart-line-variant"
        else:
            icon_name = "mdi.shape-outline"

        color = self.visible_color if visible else self.invisible_color
        icon = qta.icon(icon_name, color=color, scale_factor=0.7)
        self.setIcon(icon)

    def set_visible(self, visible):
        if visible != self.visible:
            self._update_visibility_icon(visible)

        if not visible:
            self.setForeground(self.invisible_color)


class MetadataItemDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter, option, index):
        original_rect = QRect(option.rect)

        list_widget = self.parent()
        item = list_widget.item(index.row())

        if not isinstance(item, StyledListWidgetItem):
            return super().paint(painter, option, index)

        metadata_text = item.metadata.get("metadata_text", "")

        metadata_font = QFont(painter.font())
        metadata_font.setPointSize(8)
        fm = QFontMetrics(metadata_font)
        metadata_width = min(fm.horizontalAdvance(metadata_text), 55)

        modified_option = QStyleOptionViewItem(option)
        modified_option.rect.setWidth(option.rect.width() - metadata_width)

        super().paint(painter, modified_option, index)
        painter.save()

        metadata_font = QFont(painter.font())
        metadata_font.setPointSize(8)
        painter.setFont(metadata_font)
        painter.setPen(QColor(107, 114, 128))

        metadata_rect = QRect(
            original_rect.right() - metadata_width,
            original_rect.top(),
            metadata_width,
            original_rect.height(),
        )
        painter.drawText(
            metadata_rect,
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            metadata_text,
        )
        painter.restore()
