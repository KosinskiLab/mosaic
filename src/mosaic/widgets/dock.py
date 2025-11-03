from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QMessageBox,
    QDockWidget,
    QApplication,
    QMainWindow,
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

    if getattr(instance, dock_attr_name, None) is not None:
        return _exit()

    dock = QDockWidget()
    dock.setFeatures(
        QDockWidget.DockWidgetClosable
        | QDockWidget.DockWidgetFloatable
        | QDockWidget.DockWidgetMovable
    )
    dock.setWidget(dialog_widget)

    # Handle cleanup when dock is closed via X button
    dock.visibilityChanged.connect(lambda visible: _exit() if not visible else None)

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
