import os
from sys import platform
from pathlib import Path

from qtpy.QtCore import Qt, QEvent, QObject, QStringListModel
from qtpy.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
    QFrame,
    QFileDialog,
    QCompleter,
)
import qtawesome as qta

from ..stylesheets import Colors


class _TabCompleteFilter(QObject):
    """Accept inline completion on Tab instead of moving focus."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Tab:
            completer = obj.completer()
            if completer and completer.currentCompletion():
                path = completer.currentCompletion()
                if Path(path).is_dir() and not path.endswith("/"):
                    path += "/"
                obj.setText(path)
                obj.setCursorPosition(len(path))
            return True
        return super().eventFilter(obj, event)


def _list_dir_safe(directory: str, dirs_only: bool = False) -> list:
    """List directory entries using os.scandir, skipping iCloud placeholders."""
    entries = []
    try:
        with os.scandir(directory) as it:
            for entry in it:
                if entry.name.startswith("."):
                    continue
                if dirs_only and not entry.is_dir(follow_symlinks=False):
                    continue
                entries.append(entry.path)
    except (PermissionError, OSError):
        pass
    return sorted(entries)


class PathSelector(QWidget):
    """Reusable component for file path selection with browse button"""

    def __init__(
        self,
        label_text="",
        placeholder="Path to file",
        file_mode: bool = True,
        save_mode: bool = False,
        file_filter: str = "",
        parent=None,
    ):
        """
        Initialize the file path selector widget.

        Parameters:
        -----------
        label_text : str
            Text to show as label above the path field
        placeholder : str
            Placeholder text for the input field
        file_mode : bool
            Whether integrated button triggers file or directory selection.
        save_mode : bool
            Whether to use a save dialog instead of an open dialog.
        file_filter : str
            File type filter for the dialog (e.g. "MRC Files (*.mrc)").
        parent : QWidget
            Parent widget
        """
        super().__init__(parent)

        self.file_mode = file_mode
        self.save_mode = save_mode
        self.file_filter = file_filter
        self._dirs_only = not file_mode and not save_mode
        self._cached_dir = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)

        if label_text:
            self.label = QLabel(label_text)
            self.label.setStyleSheet(
                f"""
                QLabel {{
                    font-size: 12px;
                    font-weight: 500;
                    color: {Colors.TEXT_PRIMARY};
                    margin-bottom: 1px;
                }}
            """
            )
            main_layout.addWidget(self.label)

        self.container_frame = QFrame()
        self.container_frame.setObjectName("pathSelectorFrame")
        self.container_frame.setStyleSheet(
            f"""
            #pathSelectorFrame {{
                border: 1px solid {Colors.BORDER_DARK};
                border-radius: 4px;
                background-color: transparent;
            }}
            #pathSelectorFrame:focus-within {{
                border-color: {Colors.PRIMARY};
            }}
        """
        )

        container_layout = QHBoxLayout(self.container_frame)
        container_layout.setContentsMargins(8, 0, 0, 0)
        container_layout.setSpacing(4)

        if save_mode:
            icon_name = "ph.floppy-disk"
        elif file_mode:
            icon_name = "ph.file"
        else:
            icon_name = "ph.folder-open"

        icon_label = QLabel()
        icon_label.setPixmap(
            qta.icon(icon_name, color=Colors.ICON_MUTED).pixmap(14, 14)
        )
        icon_label.setFixedSize(14, 14)
        icon_label.setStyleSheet("border: none;")

        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText(placeholder)

        self._completer_model = QStringListModel(self)
        completer = QCompleter(self._completer_model, self)
        completer.setCompletionMode(QCompleter.CompletionMode.InlineCompletion)
        if platform == "darwin":
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.path_input.setCompleter(completer)
        self.path_input.textChanged.connect(self._update_completions)
        self.path_input.installEventFilter(_TabCompleteFilter(self.path_input))

        self.path_input.setStyleSheet(
            f"""
            QLineEdit {{
                border: none;
                background-color: transparent;
                padding: 4px 6px;
                color: {Colors.TEXT_PRIMARY};
                selection-color: white;
            }}
            QLineEdit::placeholder {{
                color: {Colors.TEXT_MUTED};
            }}
        """
        )

        self.browse_button = QPushButton()
        self.browse_button.setAutoDefault(False)
        self.browse_button.setDefault(False)
        self.browse_button.setIcon(qta.icon("ph.folder-open", color=Colors.ICON))
        self.browse_button.setToolTip("Browse")
        self.browse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-left: 1px solid {Colors.BORDER_DARK};
                padding: 4px 10px;
                min-width: 32px;
            }}
            QPushButton:hover {{
                background-color: {Colors.BG_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {Colors.BG_PRESSED};
            }}
        """
        )
        self.browse_button.clicked.connect(self._browse_clicked)

        container_layout.addWidget(icon_label)
        container_layout.addWidget(self.path_input, 1)
        container_layout.addWidget(self.browse_button)

        self.container_frame.setFixedHeight(Colors.WIDGET_HEIGHT)
        main_layout.addWidget(self.container_frame)

    def _update_completions(self, text):
        parent_dir = str(Path(text).parent) if text else ""
        if not parent_dir or parent_dir == "." or parent_dir == self._cached_dir:
            return
        self._cached_dir = parent_dir
        entries = _list_dir_safe(parent_dir, dirs_only=self._dirs_only)
        self._completer_model.setStringList(entries)

    def _browse_clicked(self):
        dlg = QFileDialog(self)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        if self.save_mode:
            dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
            if self.file_filter:
                dlg.setNameFilter(self.file_filter)
        elif self.file_mode:
            dlg.setFileMode(QFileDialog.FileMode.ExistingFile)
            if self.file_filter:
                dlg.setNameFilter(self.file_filter)
        else:
            dlg.setFileMode(QFileDialog.FileMode.Directory)
            dlg.setOption(QFileDialog.Option.ShowDirsOnly, True)

        dlg.fileSelected.connect(self.set_path)
        dlg.open()

    def get_path(self):
        """Get the currently entered path"""
        return self.path_input.text()

    def set_path(self, path):
        """Set the path in the input field"""
        self.path_input.setText(path)
