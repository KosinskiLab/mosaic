from qtpy.QtCore import Qt, QSize, QRectF
from qtpy.QtGui import QPainter, QColor
from qtpy.QtWidgets import (
    QDockWidget,
    QApplication,
    QMainWindow,
    QScrollArea,
    QFrame,
    QWidget,
    QHBoxLayout,
    QLabel,
    QToolButton,
)


def toggle_dock(dock, show):
    """Show or hide a QDockWidget.

    Parameters
    ----------
    dock : QDockWidget
        The dock widget to toggle.
    show : bool
        *True* to show, *False* to hide.
    """
    dock.setVisible(show)


class _DockTitleBar(QWidget):
    def __init__(self, dock):
        super().__init__(dock)
        self._dock = dock
        self._setup_ui()
        dock.topLevelChanged.connect(self._on_floating_changed)

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(2)

        self._title_label = QLabel()
        layout.addWidget(self._title_label)
        layout.addStretch()

        self._float_btn = QToolButton()
        self._float_btn.setAutoRaise(True)
        self._float_btn.setFixedSize(24, 24)
        self._float_btn.setIconSize(QSize(14, 14))
        self._float_btn.clicked.connect(
            lambda: self._dock.setFloating(not self._dock.isFloating())
        )
        layout.addWidget(self._float_btn)

        self._close_btn = QToolButton()
        self._close_btn.setAutoRaise(True)
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.setIconSize(QSize(14, 14))
        self._close_btn.clicked.connect(self._dock.close)
        layout.addWidget(self._close_btn)

        self.setFixedHeight(24)
        self._on_theme_changed()

    def _on_floating_changed(self, floating):
        from ..icons import icon

        if floating:
            self._float_btn.setIcon(icon("ph.arrow-square-in", role="muted"))
            self._float_btn.setToolTip("Re-dock")
        else:
            self._float_btn.setIcon(icon("ph.arrow-square-out", role="muted"))
            self._float_btn.setToolTip("Detach")

    def _on_theme_changed(self):
        from ..icons import icon

        self._close_btn.setIcon(icon("ph.x", role="muted"))
        self._close_btn.setToolTip("Close")
        self._on_floating_changed(self._dock.isFloating())


class VerticalScrollArea(QScrollArea):
    def sizeHint(self):
        """Return size hint based on contained widget, with reasonable defaults."""
        if self.widget():
            child_hint = self.widget().sizeHint()
            if child_hint.isValid():
                width = child_hint.width() + 20
                return QSize(width, min(child_hint.height(), 600))
        return QSize(400, 350)

    def resizeEvent(self, event):
        if self.widget():
            self.widget().setFixedWidth(self.viewport().width())
        super().resizeEvent(event)

    def __getattr__(self, name):
        widget = self.widget()
        if widget is not None and hasattr(widget, name):
            return getattr(widget, name)
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )


def create_or_toggle_dock(
    instance,
    dock_attr_name,
    dialog_widget,
    dock_area=Qt.RightDockWidgetArea,
    scroll=True,
):
    """
    Helper method to create or toggle a docked dialog.

    Parameters
    ----------
    dock_attr_name : str
        The attribute name to store the dock widget (e.g., 'histogram_dock')
    dialog_widget : QWidget
        The dialog widget to display in the dock
    dock_area : Qt.DockWidgetArea, optional
        Where to dock the widget, default is RightDockWidgetArea
    scroll : bool, optional
        Whether to wrap the widget in a VerticalScrollArea, default is True.
    """

    def _exit():
        dock = getattr(instance, dock_attr_name, None)
        if dock:
            if widget := dock.widget():
                widget.close()
            dock.close()
            dock.deleteLater()
        setattr(instance, dock_attr_name, None)
        try:
            dialog_widget.close()
        except Exception:
            pass

    if getattr(instance, dock_attr_name, None) is not None:
        return _exit()

    if dialog_widget is None:
        return None

    class ClosableDockWidget(QDockWidget):
        def closeEvent(self, event):
            _exit()
            super().closeEvent(event)

    dock = ClosableDockWidget()
    dock.setFeatures(
        QDockWidget.DockWidgetClosable
        | QDockWidget.DockWidgetFloatable
        | QDockWidget.DockWidgetMovable
    )
    dock.setTitleBarWidget(_DockTitleBar(dock))

    if scroll:
        scroll_area = VerticalScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setWidget(dialog_widget)
        dock.setWidget(scroll_area)
    else:
        dock.setWidget(dialog_widget)

    if hasattr(dialog_widget, "accepted"):
        dialog_widget.accepted.connect(_exit)
    if hasattr(dialog_widget, "rejected"):
        dialog_widget.rejected.connect(_exit)

    main_window = None
    for widget in QApplication.instance().topLevelWidgets():
        if isinstance(widget, QMainWindow):
            main_window = widget
            break

    if main_window is None:
        return dialog_widget.show()

    main_window.addDockWidget(dock_area, dock)
    setattr(instance, dock_attr_name, dock)
    dock.show()
    dock.raise_()
