import os
from sys import platform
from pathlib import Path
from typing import List, Union

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
    """Accept inline completion on Tab and scroll to show completed text."""

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

        if event.type() == QEvent.Type.KeyRelease and obj.hasSelectedText():
            start = obj.selectionStart()
            length = len(obj.selectedText())
            end = start + length
            obj.setCursorPosition(end)
            obj.setSelection(start, length)

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


_ICON_MAP = {
    "file": "ph.file",
    "files": "ph.files",
    "directory": "ph.folder-open",
    "save": "ph.floppy-disk",
}


class PathSelector(QWidget):
    """Reusable component for file path selection with browse button.

    Parameters
    ----------
    label_text : str
        Text to show as label above the path field.
    placeholder : str
        Placeholder text for the input field.
    mode : str
        Selection mode: ``"file"`` (single file), ``"files"`` (multiple
        files), ``"directory"``, or ``"save"``.
    file_filter : str
        File type filter for the dialog (e.g. ``"MRC Files (*.mrc)"``).
    parent : QWidget, optional
        Parent widget.
    """

    def __init__(
        self,
        label_text="",
        placeholder="Path to file",
        mode: str = "file",
        file_filter: str = "",
        parent=None,
    ):
        super().__init__(parent)

        self.mode = mode
        self.file_filter = file_filter
        self._paths: List[str] = []
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

        icon_name = _ICON_MAP.get(mode, "ph.file")

        icon_label = QLabel()
        icon_label.setPixmap(
            qta.icon(icon_name, color=Colors.ICON_MUTED).pixmap(14, 14)
        )
        icon_label.setFixedSize(14, 14)
        icon_label.setStyleSheet("border: none;")

        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText(placeholder)

        self._completer_model = QStringListModel(self)
        self._completer = QCompleter(self._completer_model, self)
        self._completer.setCompletionMode(QCompleter.CompletionMode.InlineCompletion)
        if platform == "darwin":
            self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._tab_filter = _TabCompleteFilter(self.path_input)
        self.path_input.textChanged.connect(self._update_completions)

        if mode != "files":
            self.path_input.setCompleter(self._completer)
            self.path_input.installEventFilter(self._tab_filter)
        else:
            self.path_input.setReadOnly(True)

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

    def set_mode(self, mode: str):
        """Switch the selection mode at runtime."""
        old_mode = self.mode
        self.mode = mode
        if mode == "files":
            self.path_input.setReadOnly(True)
            self.path_input.setCompleter(None)
            self.path_input.removeEventFilter(self._tab_filter)
        elif old_mode == "files":
            self.path_input.setReadOnly(False)
            self.path_input.setCompleter(self._completer)
            self.path_input.installEventFilter(self._tab_filter)

            # Collapse multi-paths to the first one when switching back
            if self._paths:
                self.path_input.setText(self._paths[0])
            self._paths.clear()

    def _update_completions(self, text):
        if self.mode == "files":
            return
        parent_dir = str(Path(text).parent) if text else ""
        if not parent_dir or parent_dir == "." or parent_dir == self._cached_dir:
            return
        self._cached_dir = parent_dir
        entries = _list_dir_safe(parent_dir, dirs_only=(self.mode == "directory"))
        self._completer_model.setStringList(entries)

    def _browse_clicked(self):
        start_dir = ""
        current = self.path_input.text().strip()
        if current:
            p = Path(current)
            if p.is_dir():
                start_dir = current
            elif p.parent.is_dir():
                start_dir = str(p.parent)

        dialog = QFileDialog(self.window() or self)
        dialog.setDirectory(start_dir)

        if self.mode == "files":
            dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
            dialog.setNameFilter(self.file_filter)
        elif self.mode == "save":
            dialog.setFileMode(QFileDialog.FileMode.AnyFile)
            dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
            dialog.setNameFilter(self.file_filter)
        elif self.mode == "directory":
            dialog.setFileMode(QFileDialog.FileMode.Directory)
        else:
            dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
            dialog.setNameFilter(self.file_filter)

        mode = self.mode

        def on_accepted():
            files = dialog.selectedFiles()
            if files:
                self.set_path(files if mode == "files" else files[0])

        dialog.accepted.connect(on_accepted)
        dialog.open()

    def get_path(self) -> Union[str, List[str]]:
        """Return the selected path(s).

        Returns a single string for ``"file"``, ``"directory"``, and
        ``"save"`` modes.  Returns a list of strings for ``"files"`` mode.
        """
        if self.mode == "files":
            return list(self._paths)
        return self.path_input.text()

    def set_path(self, path: Union[str, List[str]]):
        """Set the path(s) in the input field."""
        if self.mode == "files":
            if isinstance(path, str):
                self._paths = [path] if path else []
            else:
                self._paths = list(path)
            n = len(self._paths)
            if n == 0:
                self.path_input.setText("")
            elif n == 1:
                self.path_input.setText(self._paths[0])
            else:
                self.path_input.setText(f"{n} files selected")
        else:
            if isinstance(path, list):
                path = path[0] if path else ""
            self.path_input.setText(path)
