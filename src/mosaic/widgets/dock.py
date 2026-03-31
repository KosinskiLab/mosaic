from qtpy.QtCore import Qt, QSize
from qtpy.QtWidgets import (
    QMessageBox,
    QDockWidget,
    QApplication,
    QMainWindow,
    QScrollArea,
    QFrame,
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
    instance, dock_attr_name, dialog_widget, dock_area=Qt.RightDockWidgetArea
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

    from ..stylesheets import QScrollArea_style

    scroll_area = VerticalScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QFrame.Shape.NoFrame)
    scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll_area.setStyleSheet(QScrollArea_style)
    scroll_area.setWidget(dialog_widget)
    dock.setWidget(scroll_area)

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
        QMessageBox.warning(
            instance, "Warning", "Could not determine application main window."
        )
        return dialog_widget.show()

    main_window.addDockWidget(dock_area, dock)
    setattr(instance, dock_attr_name, dock)
    dock.show()
    dock.raise_()
