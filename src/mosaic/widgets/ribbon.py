from qtpy.QtGui import QPainter, QPainterPath, QColor, QPen
from qtpy.QtCore import Qt, QSize, Signal, QPoint, QTimer, QRectF
from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QHBoxLayout,
    QPushButton,
    QFrame,
    QGridLayout,
    QSizePolicy,
    QApplication,
)
from .settings import create_setting_widget
from ..stylesheets import Colors, Typography
from ..icons import icon


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

        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setLineWidth(0)

        self._setup_ui()

    def _setup_ui(self):
        # Main container with padding for the custom border
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(0)
        self.main_layout.setContentsMargins(8, 0, 8, 8)

        content = QWidget()
        content.setObjectName("settingsPanelContent")
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(8)
        content_layout.setContentsMargins(12, 10, 12, 10)

        # Grid layout for settings (reliable vertical centering)
        self.settings_grid = QGridLayout()
        self.settings_grid.setSpacing(8)
        self.settings_grid.setContentsMargins(0, 0, 0, 0)
        self.settings_grid.setColumnStretch(1, 1)
        self._grid_row = 0

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
                self._add_form_row("Method:", self.method_combo)

            for setting in self.config["settings"][offset:]:
                widget = create_setting_widget(setting)
                self._add_form_row(f"{setting['label']}:", widget)

        # Track where method-specific rows start
        self.method_row_start = None
        if self.config.get("method_settings"):
            separator = QFrame()
            separator.setFixedHeight(1)
            separator.setFrameShape(QFrame.Shape.HLine)
            separator.setStyleSheet(
                f"background-color: {Colors.BG_PRESSED}; border: none"
            )
            self.settings_grid.addWidget(separator, self._grid_row, 0, 1, 2)
            self._grid_row += 1
            self.method_row_start = self._grid_row

        settings_container = QWidget()
        settings_container.setStyleSheet(
            f"""
            QLabel {{ font-size: {Typography.LABEL}px; }}
            QComboBox {{ font-size: {Typography.LABEL}px; max-height: 26px; }}
            QSpinBox {{ font-size: {Typography.LABEL}px; max-height: 26px; }}
            QDoubleSpinBox {{ font-size: {Typography.LABEL}px; max-height: 26px; }}
            QLineEdit {{ font-size: {Typography.LABEL}px; max-height: 26px; }}
            QCheckBox {{ font-size: {Typography.LABEL}px; }}
        """
        )
        settings_container.setLayout(self.settings_grid)
        content_layout.addWidget(settings_container)

        content_layout.addStretch()

        apply_btn = QPushButton("Apply")
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.setStyleSheet(f"QPushButton {{ font-size: {Typography.LABEL}px; }}")

        apply_btn.clicked.connect(self._apply_settings)
        content_layout.addWidget(apply_btn)

        self.main_layout.addWidget(content)

        if self.method_combo is not None:
            self.update_method_settings(self.method_combo.currentText())

        self.setFocusProxy(apply_btn)

    def _add_form_row(self, label_text, widget):
        label = QLabel(label_text)
        self.settings_grid.addWidget(
            label, self._grid_row, 0, Qt.AlignmentFlag.AlignVCenter
        )
        self.settings_grid.addWidget(
            widget, self._grid_row, 1, Qt.AlignmentFlag.AlignVCenter
        )
        self._grid_row += 1

    def get_current_settings(self):
        ret = {}
        if self.method_combo is not None:
            name = self.method_combo.property("parameter")
            ret[name] = self.method_combo.currentText()

        # Iterate field widgets in column 1 of the grid
        for row in range(self.settings_grid.rowCount()):
            item = self.settings_grid.itemAtPosition(row, 1)
            if not (item and item.widget()):
                continue
            widget = item.widget()
            parameter = widget.property("parameter")
            if parameter is None:
                continue
            from .settings import get_widget_value

            ret[parameter] = get_widget_value(widget)
        return ret

    def update_method_settings(self, method):
        if self.method_row_start is None:
            return

        # Collect widgets to remove first, then remove them
        to_remove = []
        for row in range(self.method_row_start, self._grid_row):
            for col in (0, 1):
                item = self.settings_grid.itemAtPosition(row, col)
                if item and item.widget():
                    to_remove.append(item.widget())

        for widget in to_remove:
            self.settings_grid.removeWidget(widget)
            widget.deleteLater()

        self._grid_row = self.method_row_start

        self.current_method_widgets.clear()
        settings = self.config.get("method_settings", {}).get(method, [])
        for setting in settings:
            widget = create_setting_widget(setting)
            self._add_form_row(f"{setting['label']}:", widget)
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

        btn_rect = button.rect()
        global_pos = button.mapToGlobal(QPoint(0, btn_rect.height()))

        # Offset X by margin (8px) to align panel border with button border
        # Offset Y by -1 to overlap with button's bottom edge
        self.move(global_pos.x() - 8, global_pos.y() - 1)
        self.show()

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

        margin = 8
        rect = QRectF(
            margin + 0.5,
            0.5,
            self.width() - 2 * margin - 1,
            self.height() - margin - 1,
        )
        radius = 6.0

        btn_width = self.parent_button.width() if self.parent_button else 0
        notch_right = min(rect.right(), float(btn_width))

        border_path = QPainterPath()
        border_path.moveTo(rect.left(), rect.top())

        border_path.lineTo(rect.left(), rect.bottom() - radius)
        border_path.arcTo(
            QRectF(rect.left(), rect.bottom() - radius * 2, radius * 2, radius * 2),
            180,
            90,
        )

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

        if notch_right < rect.right() - radius:
            border_path.lineTo(rect.right(), rect.top() + radius)
            border_path.arcTo(
                QRectF(rect.right() - radius * 2, rect.top(), radius * 2, radius * 2),
                0,
                90,
            )
            border_path.lineTo(notch_right + radius + 1.5, rect.top())
        else:
            border_path.lineTo(rect.right(), rect.top())

        fill_path = QPainterPath(border_path)
        fill_path.lineTo(rect.left(), rect.top())

        palette = QApplication.palette()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(palette.window())
        painter.drawPath(fill_path)

        pen = QPen(QColor(Colors.BORDER_DARK))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(border_path)


class RibbonButton(QPushButton):
    """A ribbon push button with an optional attached dropdown settings panel.

    Buttons with settings have two click zones: the main area executes the
    action with current/default settings, while the chevron (▾) on the right
    opens the settings panel.
    """

    CHEVRON_WIDTH = 24

    def __init__(
        self, text, icon_name, settings_config=None, parent=None, callback=None
    ):
        self._has_settings = settings_config is not None
        super().__init__(text, parent)

        self._panel_open = False
        self._icon_name = icon_name
        self._full_text = text
        self._collapsed = False
        self._full_width = None
        self._collapsed_width = None
        self._chevron_clicked = False
        self.callback = callback
        self.settings_panel = None

        self.setFixedHeight(30)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIcon(icon(icon_name, role="active"))
        self.setIconSize(QSize(18, 18))

        if self._has_settings:
            self.settings_panel = SettingsPanel(settings_config, parent_button=self)
            self.settings_panel.settings_applied.connect(self._applied_settings)
            self.clicked.connect(self._handle_click)
        elif callback is not None:
            self.clicked.connect(self._apply)

        self._apply_style()

    def set_collapsed(self, collapsed):
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.setText("" if collapsed else self._full_text)
        self.setToolTip(self._full_text if collapsed else "")

    def _cache_widths(self):
        if self._full_width is not None:
            return
        was = self._collapsed
        self.set_collapsed(False)
        self._full_width = self.sizeHint().width()
        self.set_collapsed(True)
        self._collapsed_width = self.sizeHint().width()
        self.set_collapsed(was)

    def _on_theme_changed(self):
        self.setIcon(icon(self._icon_name, role="active"))
        self._apply_style()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._has_settings:
            return None

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(Colors.TEXT_MUTED))
        pen.setWidthF(1.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        cx = self.width() - 10
        cy = self.height() / 2
        path = QPainterPath()
        path.moveTo(cx - 3, cy - 1.5)
        path.lineTo(cx, cy + 1.5)
        path.lineTo(cx + 3, cy - 1.5)
        p.drawPath(path)
        p.end()

    def mousePressEvent(self, event):
        if self.settings_panel is not None:
            self._chevron_clicked = event.pos().x() >= self.width() - self.CHEVRON_WIDTH
        super().mousePressEvent(event)

    def _handle_click(self):
        """Route click: chevron opens settings, main area executes with defaults."""
        chevron = self._chevron_clicked
        self._chevron_clicked = False
        if chevron:
            self._toggle_panel()
        else:
            self._apply()

    def _apply(self):
        if self.settings_panel:
            settings = self.settings_panel.get_current_settings()
            return self.callback(**settings) if self.callback else None
        return self.callback() if self.callback else None

    def _applied_settings(self, settings):
        return self.callback(**settings) if self.callback else None

    def _toggle_panel(self):
        if self._panel_open:
            self.settings_panel.close()
        else:
            self.settings_panel.showAtButton(self)

    def _set_panel_open(self, is_open):
        self._panel_open = is_open
        self._apply_style()

    def _apply_style(self):
        pad_r = 20 if self._has_settings else 8
        if self._panel_open:
            self.setStyleSheet(
                f"""
                QPushButton {{
                    border: 1px solid {Colors.BORDER_DARK};
                    border-bottom: 1px solid transparent;
                    border-top-left-radius: 6px;
                    border-top-right-radius: 6px;
                    border-bottom-left-radius: 0px;
                    border-bottom-right-radius: 0px;
                    padding: 4px {pad_r}px 4px 8px;
                    font-size: {Typography.LABEL}px;
                    color: {Colors.TEXT_SECONDARY};
                }}
                QPushButton:focus {{ outline: none; }}
            """
            )
        else:
            self.setStyleSheet(
                f"""
                QPushButton {{
                    border: 1px solid transparent;
                    background: transparent;
                    border-radius: 6px;
                    padding: 4px {pad_r}px 4px 8px;
                    font-size: {Typography.LABEL}px;
                    color: {Colors.TEXT_SECONDARY};
                }}
                QPushButton:hover {{
                    background: {Colors.BG_HOVER};
                }}
                QPushButton:pressed {{
                    background: {Colors.BG_PRESSED};
                }}
                QPushButton:focus {{ outline: none; }}
            """
            )


class RibbonToolBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(42)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(8, 2, 8, 6)
        self._layout.setSpacing(4)

        self._sections = []
        self._dividers = []
        self._buttons = []

    def minimumSizeHint(self):
        return QSize(0, 42)

    def clear(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._sections.clear()
        self._dividers.clear()
        self._buttons.clear()

    def _on_theme_changed(self):
        for div in self._dividers:
            div.setStyleSheet(f"background: {Colors.BORDER_DARK}; border: none;")
        for btn in self._buttons:
            if hasattr(btn, "_on_theme_changed"):
                btn._on_theme_changed()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_collapse()

    def _update_collapse(self):
        ribbon_buttons = [
            b for b in reversed(self._buttons) if isinstance(b, RibbonButton)
        ]
        if not ribbon_buttons:
            return

        for btn in ribbon_buttons:
            btn._cache_widths()

        margins = self._layout.contentsMargins()
        available = self.width() - margins.left() - margins.right()
        spacing = self._layout.spacing()
        widget_count = len(self._buttons) + len(self._dividers)
        needed = (
            sum(
                b._full_width if isinstance(b, RibbonButton) else b.sizeHint().width()
                for b in self._buttons
            )
            + sum(d.width() for d in self._dividers)
            + spacing * max(widget_count - 1, 0)
        )

        for btn in ribbon_buttons:
            if needed <= available:
                btn.set_collapsed(False)
            else:
                needed -= btn._full_width - btn._collapsed_width
                btn.set_collapsed(True)

    def add_section(self, title, actions):
        if self._sections:
            div = QFrame()
            div.setFixedWidth(1)
            div.setFixedHeight(28)
            div.setStyleSheet(f"background: {Colors.BORDER_DARK}; border: none;")
            self._layout.addWidget(div)
            self._dividers.append(div)

        for widget in actions:
            self._layout.addWidget(widget)
            self._buttons.append(widget)

        self._sections.append(title)

        # Keep stretch at the end
        self._layout.addStretch()
        # Remove the previous stretch (second-to-last item) if it exists
        if self._layout.count() > len(self._buttons) + len(self._dividers) + 1:
            # Find and remove extra stretches — keep only the last one
            for i in range(self._layout.count() - 2, -1, -1):
                item = self._layout.itemAt(i)
                if item and item.spacerItem() and not item.widget():
                    self._layout.takeAt(i)
                    break


def create_button(
    text, icon_name, parent=None, callback=None, tooltip=None, settings_config=None
):
    button = RibbonButton(
        text, icon_name, settings_config, parent=parent, callback=callback
    )
    if tooltip:
        button.setToolTip(tooltip)
    return button
