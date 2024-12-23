from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtWidgets import (
    QToolBar,
    QWidget,
    QVBoxLayout,
    QLabel,
    QHBoxLayout,
    QToolButton,
    QComboBox,
    QMenu,
    QPushButton,
    QFrame,
    QFormLayout,
)
import qtawesome as qta

from .settings import create_setting_widget, get_layout_widget_value


class SettingsToolButton(QToolButton):
    def __init__(
        self, text, icon_name, settings_config=None, parent=None, callback=None
    ):
        super().__init__(parent)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.setIcon(qta.icon(icon_name, color="#374151"))
        self.setText(text)

        self.callback = callback
        self.main_action = QAction(self.icon(), text, self)
        if self.callback is not None:
            self.main_action.triggered.connect(self._apply)
        self.setDefaultAction(self.main_action)

        if settings_config is not None:
            self.settings_menu = SettingsMenu(settings_config, parent=self)
            self.settings_menu.settings_applied.connect(self._applied_settings)
            self.setMenu(self.settings_menu)

        self.setStyleSheet(
            """
            QToolButton {
                min-width: 60px;
                padding: 6px 4px;
                border-radius: 4px;
                color: #6b7280;
                font-size: 11px;
            }
            QToolButton:hover {
                background: #f3f4f6;
            }
            QToolButton::menu-indicator {
                image: url(none);
                width: 0px;
                subcontrol-position: right bottom;
                subcontrol-origin: padding;
                margin-left: 0px;
            }
            QToolButton::menu-button {
                border: none;
                width: 12px;
                padding: 0px;
            }
            QToolButton::menu-button:hover {
                background: transparent;
            }
        """
        )

    def _apply(self):
        settings = self.settings_menu.get_current_settings()
        return self.callback(**settings) if self.callback else None

    def _applied_settings(self, settings):
        return self.callback(**settings) if self.callback else None


class SettingsMenu(QMenu):
    settings_applied = pyqtSignal(dict)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config.copy()

        self.method_widgets, self.current_method_widgets = {}, []
        if "method_settings" not in self.config:
            self.config["method_settings"] = {}

        self._setup()
        self.setStyleSheet(
            """
            QMenu {
                border: 1px solid #e5e7eb;
                border-radius: 4px;
                padding: 8px;
            }
            QLabel {
                font-weight: 600;
                min-width: 100px;
            }
            QCheckBox {
                color: #374151;
            }
        """
        )

    def get_current_settings(self):
        ret = {}
        if self.method_combo is not None:
            name = self.method_combo.property("parameter")
            ret[name] = self.method_combo.currentText()

        ret.update(get_layout_widget_value(self.general_form))
        if self.method_layout is not None:
            ret.update(get_layout_widget_value(self.method_layout))
        return ret

    def _setup(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(8)
        self.main_layout.setContentsMargins(8, 8, 8, 8)

        title = QLabel(
            f"<span style='font-weight: 600;'>{self.config.get('title', '')}</span>"
        )
        self.main_layout.addWidget(title)

        # Setting shared by multiple methods
        self.general_form = QFormLayout()
        self.general_form.setSpacing(8)
        self.general_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        # Check wheter settings differentiate between different methods
        offset, self.method_combo = 0, None
        base_settings = self.config["settings"][0]
        if "options" in base_settings:
            offset = 1
            self.method_combo = QComboBox()
            self.method_combo.addItems(base_settings["options"])
            self.method_combo.setCurrentText(base_settings["default"])
            self.method_combo.currentTextChanged.connect(self.update_method_settings)
            self.method_combo.setProperty(
                "parameter", base_settings.get("parameter", "method")
            )
            self.general_form.addRow("Method:", self.method_combo)

        for setting in self.config["settings"][offset:]:
            widget = create_setting_widget(setting)
            self.general_form.addRow(f"{setting['label']}:", widget)

        general_container = QWidget()
        general_container.setLayout(self.general_form)
        self.main_layout.addWidget(general_container)

        self.method_layout = None
        if len(self.config.get("method_settings", {})) > 0:
            separator = QFrame()
            separator.setFixedHeight(2)
            separator.setFrameShape(QFrame.Shape.HLine)
            separator.setFrameShadow(QFrame.Shadow.Sunken)
            separator.setStyleSheet("background-color: #e5e7eb;")
            self.main_layout.addWidget(separator)

            self.method_container = QWidget()
            self.method_layout = QFormLayout(self.method_container)
            self.method_layout.setSpacing(8)
            self.method_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

            self.main_layout.addWidget(self.method_container)
            self.main_layout.addStretch()

        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self.apply_settings)
        self.main_layout.addWidget(apply_btn)

        if self.method_combo is not None:
            self.update_method_settings(self.method_combo.currentText())

    def update_method_settings(self, method):
        if self.method_layout is None:
            return None

        while self.method_layout.rowCount() > 0:
            self.method_layout.removeRow(0)

        self.current_method_widgets.clear()
        settings = self.config.get("method_settings", {}).get(method, {})
        for setting in settings:
            widget = create_setting_widget(setting)
            self.method_layout.addRow(f"{setting['label']}:", widget)
            self.current_method_widgets.append(widget)

        self.method_container.updateGeometry()
        # self.adjustSize()

    def apply_settings(self):
        settings = self.get_current_settings()
        self.settings_applied.emit(settings)
        self.close()


class RibbonToolBar(QToolBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIconSize(QSize(20, 20))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setFixedHeight(85)

        self.setStyleSheet(
            """
            QToolBar {
                spacing: 16px;
                border-bottom: 1px solid #6b7280;
                padding: 8px;
            }
            QToolButton {
                min-width: 60px;
                padding: 6px 4px;
                border-radius: 4px;
                color: #6b7280;
                font-size: 11px;
            }
            QToolButton:hover {
                background: #f3f4f6;
            }
        """
        )

    def add_section(self, title, actions):
        if len(self.actions()) > 0:
            separator = QWidget()
            separator.setFixedWidth(1)
            separator.setStyleSheet(
                """
                background-color: #374151;
                margin-top: 4px;
                margin-bottom: 4px;
            """
            )
            self.addWidget(separator)

        section = QWidget()
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(4)

        label = QLabel(title)
        label.setStyleSheet(
            """
            color: #6b7280;
            font-size: 11px;
            margin-bottom: 2px;
        """
        )
        section_layout.addWidget(label)

        actions_widget = QWidget()
        actions_layout = QHBoxLayout(actions_widget)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(2)

        for action in actions:
            actions_layout.addWidget(action)

        section_layout.addWidget(actions_widget)
        self.addWidget(section)


def create_button(
    text, icon_name, parent=None, callback=None, tooltip=None, settings_config=None
):
    if settings_config:
        button = SettingsToolButton(
            text, icon_name, settings_config, parent=parent, callback=callback
        )
    else:
        action = QAction(qta.icon(icon_name, color="#374151"), text, parent)
        button = QToolButton()
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        if callback:
            button.triggered.connect(callback)

    if tooltip:
        button.setToolTip(tooltip)
    return button
