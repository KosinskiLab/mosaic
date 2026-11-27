"""
Cross-platform styled message box.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtWidgets import QMessageBox, QWidget

from ..stylesheets import _build_QMessageBox_style


class MosaicMessageBox(QMessageBox):
    """QMessageBox that always applies the application stylesheet.

    On some Linux desktop environments the global stylesheet is not
    inherited by dialogs created via the static convenience methods
    (warning/information/critical/question), producing unreadable
    dark-on-dark text.  This subclass applies the stylesheet at
    construction time so every dialog is styled consistently.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStyleSheet(_build_QMessageBox_style())

    @staticmethod
    def _show(
        parent: QWidget | None,
        icon: QMessageBox.Icon,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton,
        default_button: QMessageBox.StandardButton,
    ):
        box = MosaicMessageBox(parent)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(buttons)
        if default_button != QMessageBox.StandardButton.NoButton:
            box.setDefaultButton(default_button)
        return box.exec()

    @staticmethod
    def warning(
        parent: QWidget | None,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        defaultButton: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
    ):
        return MosaicMessageBox._show(
            parent, QMessageBox.Icon.Warning, title, text, buttons, defaultButton
        )

    @staticmethod
    def information(
        parent: QWidget | None,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        defaultButton: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
    ):
        return MosaicMessageBox._show(
            parent, QMessageBox.Icon.Information, title, text, buttons, defaultButton
        )

    @staticmethod
    def critical(
        parent: QWidget | None,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        defaultButton: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
    ):
        return MosaicMessageBox._show(
            parent, QMessageBox.Icon.Critical, title, text, buttons, defaultButton
        )

    @staticmethod
    def question(
        parent: QWidget | None,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Yes
        | QMessageBox.StandardButton.No,
        defaultButton: QMessageBox.StandardButton = QMessageBox.StandardButton.No,
    ):
        return MosaicMessageBox._show(
            parent, QMessageBox.Icon.Question, title, text, buttons, defaultButton
        )
