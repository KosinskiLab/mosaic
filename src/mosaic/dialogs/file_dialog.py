"""
Cross-platform file dialog wrappers.

The native file dialog on macOS omits the window title text, which can be
confusing for users. These wrappers ensure consistent behavior across platforms.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from sys import platform
from qtpy.QtWidgets import QFileDialog

from ..stylesheets import QPushButton_style


__all__ = [
    "getExistingDirectory",
    "getOpenFileName",
    "getOpenFileNames",
    "getSaveFileName",
]


def _configure_dialog(dialog, use_native: bool = True):
    """Apply platform-specific configuration to file dialog."""
    if platform.lower() == "darwin" and use_native:
        dialog.setOptions(
            QFileDialog.DontUseCustomDirectoryIcons | QFileDialog.DontUseNativeDialog
        )
    dialog.setStyleSheet(QPushButton_style)


def getExistingDirectory(
    parent=None, caption="", directory="", use_native: bool = True
):
    """
    Open a dialog to select an existing directory.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget.
    caption : str, optional
        Dialog window title.
    directory : str, optional
        Starting directory.
    use_native : bool, optional
        Whether to use the native dialog on macOS. Default is True.

    Returns
    -------
    str
        Selected directory path, or empty string if cancelled.
    """
    dialog = QFileDialog(parent)
    dialog.setWindowTitle(caption)
    dialog.setFileMode(QFileDialog.FileMode.Directory)
    dialog.setDirectory(directory)
    _configure_dialog(dialog, use_native=use_native)

    if dialog.exec():
        selected = dialog.selectedFiles()
        return selected[0] if selected else ""
    return ""


def getOpenFileName(
    parent=None,
    caption="",
    directory="",
    filter="All Files (*)",
    use_native: bool = True,
):
    """
    Open a dialog to select an existing file.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget.
    caption : str, optional
        Dialog window title.
    directory : str, optional
        Starting directory.
    filter : str, optional
        File type filter (e.g., "Images (*.png *.jpg);;All Files (*)").
    use_native : bool, optional
        Whether to use the native dialog on macOS. Default is True.

    Returns
    -------
    tuple
        (selected_file, selected_filter) or ("", "") if cancelled.
    """
    dialog = QFileDialog(parent)
    dialog.setWindowTitle(caption)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    dialog.setDirectory(directory)
    dialog.setNameFilter(filter)
    _configure_dialog(dialog, use_native=use_native)

    if dialog.exec():
        selected = dialog.selectedFiles()
        return (selected[0] if selected else "", dialog.selectedNameFilter())
    return ("", "")


def getOpenFileNames(
    parent=None,
    caption="",
    directory="",
    filter="All Files (*)",
    use_native: bool = True,
):
    """
    Open a dialog to select multiple existing files.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget.
    caption : str, optional
        Dialog window title.
    directory : str, optional
        Starting directory.
    filter : str, optional
        File type filter (e.g., "Images (*.png *.jpg);;All Files (*)").
    use_native : bool, optional
        Whether to use the native dialog on macOS. Default is True.

    Returns
    -------
    tuple
        (selected_files, selected_filter) or ([], "") if cancelled.
    """
    dialog = QFileDialog(parent)
    dialog.setWindowTitle(caption)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
    dialog.setDirectory(directory)
    dialog.setNameFilter(filter)
    _configure_dialog(dialog, use_native=use_native)

    if dialog.exec():
        return (dialog.selectedFiles(), dialog.selectedNameFilter())
    return ([], "")


def getSaveFileName(
    parent=None,
    caption="",
    directory="",
    filter="All Files (*)",
    use_native: bool = False,
):
    """
    Open a dialog to specify a file to save.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget.
    caption : str, optional
        Dialog window title.
    directory : str, optional
        Starting directory or default filename.
    filter : str, optional
        File type filter (e.g., "Images (*.png *.jpg);;All Files (*)").
    use_native : bool, optional
        Whether to use the native dialog on macOS. Default is True.

    Returns
    -------
    tuple
        (selected_file, selected_filter) or ("", "") if cancelled.
    """
    dialog = QFileDialog(parent)
    dialog.setWindowTitle(caption)
    dialog.setFileMode(QFileDialog.FileMode.AnyFile)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    dialog.setDirectory(directory)
    dialog.setNameFilter(filter)
    _configure_dialog(dialog, use_native=use_native)

    if dialog.exec():
        selected = dialog.selectedFiles()
        return (selected[0] if selected else "", dialog.selectedNameFilter())
    return ("", "")
