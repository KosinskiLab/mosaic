from qtpy.QtGui import QAction, QPainter, QPainterPath, QColor, QPen
from qtpy.QtCore import Qt, QSize, Signal, QPoint, QTimer, QRectF
from qtpy.QtWidgets import (
    QToolBar,
    QWidget,
    QVBoxLayout,
    QLabel,
    QHBoxLayout,
    QToolButton,
    QMenu,
    QPushButton,
    QFrame,
    QFormLayout,
    QSizePolicy,
    QApplication,
)
import qtawesome as qta

from .settings import create_setting_widget, get_layout_widget_value
from ..stylesheets import QPushButton_style, QToolButton_style, Colors


class SettingsPanel(QFrame):
    """A dropdown panel that appears as a visual extension of its parent button."""

    settings_applied = Signal(dict)

    def __init__(self, config, parent_button=None):
        super().__init__(parent=None)
        self.config = config.copy()
        self.parent_button = parent_button

        if "method_settings" not in self.config:
            self.config["method_settings"] = {}

        self.method_widgets, self.current_method_widgets = {}, []

        # Frameless popup window
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Disable QFrame's default border drawing
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setLineWidth(0)

        self._setup_ui()

    def _setup_ui(self):
        # Main container with padding for the custom border
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(0)
        self.main_layout.setContentsMargins(8, 0, 8, 8)

        # Content container
        content = QWidget()
        content.setObjectName("settingsPanelContent")
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(10)
        content_layout.setContentsMargins(12, 12, 12, 12)

        # Title
        title_text = self.config.get("title", "")
        if title_text:
            title = QLabel(title_text)
            title.setStyleSheet(
                f"font-weight: 500; font-size: 12px; color: {Colors.TEXT_SECONDARY}; "
                "letter-spacing: 0.5px; text-transform: uppercase; "
            )
            content_layout.addWidget(title)

        # General settings form
        self.general_form = QFormLayout()
        self.general_form.setSpacing(8)
        self.general_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.general_form.setFormAlignment(Qt.AlignmentFlag.AlignLeft)
        self.general_form.setContentsMargins(0, 0, 0, 0)

        # Check for method selector
        offset, self.method_combo = 0, None
        if self.config.get("settings"):
            base_settings = self.config["settings"][0]
            if "options" in base_settings:
                offset = 1
                self.method_combo = create_setting_widget(base_settings)
                self.method_combo.currentTextChanged.connect(
                    self.update_method_settings
                )
                self.method_combo.setProperty(
                    "parameter", base_settings.get("parameter", "method")
                )
                self.general_form.addRow(
                    self._create_label("Method"), self.method_combo
                )

            for setting in self.config["settings"][offset:]:
                widget = create_setting_widget(setting)
                self.general_form.addRow(self._create_label(setting["label"]), widget)

        general_container = QWidget()
        general_container.setLayout(self.general_form)
        content_layout.addWidget(general_container)

        # Method-specific settings
        self.method_layout = None
        if self.config.get("method_settings"):
            separator = QFrame()
            separator.setFrameShape(QFrame.Shape.HLine)
            separator.setFixedHeight(1)
            separator.setStyleSheet(
                "background-color: rgba(0, 0, 0, 0.12); margin: 4px 0px;"
            )
            content_layout.addWidget(separator)

            self.method_container = QWidget()
            self.method_layout = QFormLayout(self.method_container)
            self.method_layout.setSpacing(8)
            self.method_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
            self.method_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft)
            self.method_layout.setContentsMargins(0, 0, 0, 0)
            content_layout.addWidget(self.method_container)

        content_layout.addStretch()

        # Apply button - uses platform palette colors
        apply_btn = QPushButton("Apply")
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.setStyleSheet(QPushButton_style)

        apply_btn.clicked.connect(self._apply_settings)
        content_layout.addWidget(apply_btn)

        self.main_layout.addWidget(content)

        if self.method_combo is not None:
            self.update_method_settings(self.method_combo.currentText())

        self.setFocusProxy(apply_btn)

    def _create_label(self, text):
        label = QLabel(text)
        label.setStyleSheet("font-size: 12px; min-width: 70px;")
        return label

    def get_current_settings(self):
        ret = {}
        if self.method_combo is not None:
            name = self.method_combo.property("parameter")
            ret[name] = self.method_combo.currentText()

        ret.update(get_layout_widget_value(self.general_form))
        if self.method_layout is not None:
            ret.update(get_layout_widget_value(self.method_layout))
        return ret

    def update_method_settings(self, method):
        if self.method_layout is None:
            return

        while self.method_layout.rowCount() > 0:
            self.method_layout.removeRow(0)

        self.current_method_widgets.clear()
        settings = self.config.get("method_settings", {}).get(method, [])
        for setting in settings:
            widget = create_setting_widget(setting)
            self.method_layout.addRow(self._create_label(setting["label"]), widget)
            self.current_method_widgets.append(widget)

        QTimer.singleShot(0, self.adjustSize)

    def _apply_settings(self):
        settings = self.get_current_settings()
        self.settings_applied.emit(settings)
        self.close()

    def showAtButton(self, button):
        """Position and show the panel below the button."""
        self.parent_button = button
        self.adjustSize()

        # Position below button, left-aligned with button's left edge
        # The panel has 8px left margin, so offset by that amount
        btn_rect = button.rect()
        global_pos = button.mapToGlobal(QPoint(0, btn_rect.height()))

        # Offset X by margin (8px) to align panel border with button border
        # Offset Y by -1 to overlap with button's bottom edge
        self.move(global_pos.x() - 8, global_pos.y() - 1)
        self.show()

        # Notify button we're open
        if hasattr(button, "_set_panel_open"):
            button._set_panel_open(True)

    def closeEvent(self, event):
        if self.parent_button and hasattr(self.parent_button, "_set_panel_open"):
            self.parent_button._set_panel_open(False)
        super().closeEvent(event)

    def paintEvent(self, event):
        """Custom paint to draw connected border with button."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Use 0.5 pixel insets for crisp 1px border rendering with antialiasing
        margin = 8
        rect = QRectF(
            margin + 0.5,
            0.5,
            self.width() - 2 * margin - 1,
            self.height() - margin - 1,
        )
        radius = 6.0

        # Determine button overlap region (where top border is omitted)
        btn_width = self.parent_button.width() if self.parent_button else 0
        notch_right = min(rect.right(), float(btn_width))

        # Build border path: open at top where button connects
        # Start at top-left, go down left side, around bottom, up right side
        border_path = QPainterPath()
        border_path.moveTo(rect.left(), rect.top())

        # Left side down to bottom-left corner
        border_path.lineTo(rect.left(), rect.bottom() - radius)
        border_path.arcTo(
            QRectF(rect.left(), rect.bottom() - radius * 2, radius * 2, radius * 2),
            180,
            90,
        )

        # Bottom edge to bottom-right corner
        border_path.lineTo(rect.right() - radius, rect.bottom())
        border_path.arcTo(
            QRectF(
                rect.right() - radius * 2,
                rect.bottom() - radius * 2,
                radius * 2,
                radius * 2,
            ),
            270,
            90,
        )

        # Right side: either with top-right corner or straight up
        if notch_right < rect.right() - radius:
            # Panel is wider than button - draw top-right corner
            border_path.lineTo(rect.right(), rect.top() + radius)
            border_path.arcTo(
                QRectF(rect.right() - radius * 2, rect.top(), radius * 2, radius * 2),
                0,
                90,
            )
            border_path.lineTo(notch_right + radius + 1.5, rect.top())
        else:
            # Button covers full width - no corner needed
            border_path.lineTo(rect.right(), rect.top())

        # Close the border path to create a fill shape
        # The top edge under the button gets filled but not stroked
        fill_path = QPainterPath(border_path)
        fill_path.lineTo(rect.left(), rect.top())

        # Fill with platform window background color
        palette = QApplication.palette()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(palette.window())
        painter.drawPath(fill_path)

        # Draw border (stroke only, path is not closed at top)
        pen = QPen(QColor(Colors.BORDER_DARK))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(border_path)


class SettingsToolButton(QToolButton):
    """A tool button with an attached dropdown settings panel."""

    def __init__(
        self, text, icon_name, settings_config=None, parent=None, callback=None
    ):
        super().__init__(parent)
        self._panel_open = False
        self.callback = callback
        self.settings_panel = None

        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.setIcon(qta.icon(icon_name, color=Colors.ICON))
        self.setText(text)

        self.main_action = QAction(self.icon(), text, self)
        if self.callback is not None:
            self.main_action.triggered.connect(self._apply)
        self.setDefaultAction(self.main_action)

        if settings_config is not None:
            self.settings_panel = SettingsPanel(settings_config, parent_button=self)
            self.settings_panel.settings_applied.connect(self._applied_settings)
            # Create a dummy menu to enable the menu button, but we'll intercept clicks
            self._dummy_menu = QMenu(self)
            self.setMenu(self._dummy_menu)

        self._update_style()

    def _apply(self):
        if self.settings_panel:
            settings = self.settings_panel.get_current_settings()
            return self.callback(**settings) if self.callback else None
        return self.callback() if self.callback else None

    def _applied_settings(self, settings):
        return self.callback(**settings) if self.callback else None

    def _set_panel_open(self, is_open):
        self._panel_open = is_open
        self._update_style()

    def _update_style(self):
        """Update button style based on panel state."""
        if self._panel_open:
            self.setStyleSheet(
                f"""
                QToolButton {{
                    min-width: 52px;
                    padding: 4px 6px;
                    border-top-left-radius: 6px;
                    border-top-right-radius: 6px;
                    border-bottom-left-radius: 0px;
                    border-bottom-right-radius: 0px;
                    font-size: 11px;
                    border: 1px solid {Colors.BORDER_DARK};
                    border-bottom: none;
                }}
                QToolButton::menu-indicator {{
                    image: url(none);
                    width: 0px;
                }}
                QToolButton::menu-button {{
                    border: none;
                    border-left: none;
                    border-bottom: none;
                    width: 14px;
                    padding: 0px;
                    margin: 0px;
                    subcontrol-origin: padding;
                    subcontrol-position: right center;
                }}
                """
            )
        else:
            self.setStyleSheet(QToolButton_style)

    def mousePressEvent(self, event):
        """Intercept menu button clicks to show our panel instead."""
        if self.settings_panel:
            # Check if click is in the menu button region
            opt_btn_width = 16
            if event.pos().x() > self.width() - opt_btn_width:
                if self._panel_open:
                    self.settings_panel.close()
                else:
                    self.settings_panel.showAtButton(self)
                return
        super().mousePressEvent(event)


# Keep SettingsMenu as alias for backward compatibility
SettingsMenu = SettingsPanel


class RibbonToolBar(QToolBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIconSize(QSize(20, 20))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(
            """
            QToolBar {
                spacing: 16px;
                padding: 12px 12px 12px 12px;
                border-bottom: 1px solid rgba(0, 0, 0, 0.10);
            }
            QToolButton {
                min-width: 52px;
                padding: 4px 6px;
                border-radius: 6px;
                font-size: 11px;
                background: transparent;
                border: 1px solid transparent;
            }
            QToolButton:hover {
                background: rgba(0, 0, 0, 0.06);
                border: 1px solid rgba(0, 0, 0, 0.08);
            }
            QToolButton:pressed {
                background: rgba(0, 0, 0, 0.10);
                border: 1px solid rgba(0, 0, 0, 0.12);
            }
        """
        )
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def add_section(self, title, actions):
        if len(self.actions()) > 0:
            separator = QFrame()
            separator.setFrameShape(QFrame.Shape.VLine)
            separator.setFixedWidth(2)
            separator.setStyleSheet(
                """
                QFrame {
                    background: rgba(0, 0, 0, 0.10);
                    border: none;
                    border-radius: 1px;
                    margin-top: 4px;
                    margin-bottom: 4px;
                }
            """
            )
            self.addWidget(separator)

        section = QWidget()
        section_layout = QHBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(4)

        for action in actions:
            section_layout.addWidget(action)

        self.addWidget(section)


def create_button(
    text, icon_name, parent=None, callback=None, tooltip=None, settings_config=None
):
    if settings_config:
        button = SettingsToolButton(
            text, icon_name, settings_config, parent=parent, callback=callback
        )
    else:
        action = QAction(qta.icon(icon_name, color=Colors.ICON), text, parent)
        button = QToolButton()
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        if callback:
            button.triggered.connect(callback)

    button.setStyleSheet(QToolButton_style)
    button.setIconSize(QSize(20, 20))
    if tooltip:
        button.setToolTip(tooltip)
    return button
