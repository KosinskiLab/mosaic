"""
Update checker

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from sys import argv, executable

from qtpy.QtCore import Qt, QThread, QUrl, Signal
from qtpy.QtGui import QDesktopServices
from qtpy.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..__version__ import __version__
from ..stylesheets import Colors, Typography

__all__ = ["UpdateChecker", "UpdateDialog", "newer_version", "release_exists"]

PACKAGE_NAME = "mosaic-gui"

_PYPI_API = f"https://pypi.org/pypi/{PACKAGE_NAME}/json"
_GITHUB_RELEASE_API = (
    "https://api.github.com/repos/KosinskiLab/mosaic/releases/tags/v{version}"
)
_GITHUB_RELEASE_URL = "https://github.com/KosinskiLab/mosaic/releases/tag/v{version}"


def _fetch_json(url: str, timeout: float = 5.0) -> dict | None:
    """Return the decoded JSON body of *url*, or None if it cannot be read.

    Parameters
    ----------
    url : str
        Endpoint to request.
    timeout : float, optional
        Socket timeout in seconds.

    Returns
    -------
    dict or None
        Decoded payload, or None on any network or decoding failure.
    """
    import json
    import urllib.request

    try:
        request = urllib.request.Request(url)
        request.add_header("User-Agent", "Mosaic-Update-Checker")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except Exception:
        return None


def _installable_versions(payload: dict) -> list[str]:
    """Version strings from a PyPI payload that still have usable files."""
    releases = payload.get("releases")
    if not releases:
        version = (payload.get("info") or {}).get("version")
        return [version] if version else []

    versions = []
    for version, files in releases.items():
        if not files:
            continue
        if all(file.get("yanked") for file in files):
            continue
        versions.append(version)
    return versions


def newer_version(payload: dict, current: str) -> str | None:
    """Highest stable release in *payload* that supersedes *current*.

    Parameters
    ----------
    payload : dict
        Decoded response of the PyPI JSON API.
    current : str
        Version currently installed.

    Returns
    -------
    str or None
        The version string to offer, or None when already up to date.
    """
    from packaging.version import InvalidVersion, Version

    try:
        installed = Version(str(current))
    except InvalidVersion:
        return None

    best = None
    for raw in _installable_versions(payload):
        try:
            candidate = Version(raw)
        except InvalidVersion:
            continue
        if candidate.is_prerelease or candidate.is_devrelease:
            continue
        if candidate <= installed:
            continue
        if best is None or candidate > best[0]:
            best = (candidate, raw)
    return None if best is None else best[1]


def release_exists(version: str) -> bool:
    """Whether GitHub carries a tagged release, and thus notes, for *version*."""
    return _fetch_json(_GITHUB_RELEASE_API.format(version=version)) is not None


class UpdateChecker(QThread):
    """Background check of PyPI for a newer release.

    Parameters
    ----------
    current_version : str, optional
        Version to compare against, defaults to the running one.
    parent : QObject, optional
        Parent object.
    """

    update_available = Signal(str, bool)

    def __init__(self, current_version: str = __version__, parent=None):
        super().__init__(parent)
        self.current_version = str(current_version)

    def run(self):
        payload = _fetch_json(_PYPI_API)
        if payload is None:
            return

        latest = newer_version(payload, self.current_version)
        if latest is None:
            return

        self.update_available.emit(latest, release_exists(latest))


class _InstallWorker(QThread):
    """Runs ``pip install -U`` out of the GUI thread."""

    completed = Signal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process = None

    def run(self):
        from subprocess import PIPE, Popen

        try:
            self._process = Popen(
                [executable, "-m", "pip", "install", "-U", PACKAGE_NAME],
                stdout=PIPE,
                stderr=PIPE,
                text=True,
            )
            _, stderr = self._process.communicate()
            self.completed.emit(self._process.returncode == 0, stderr or "")
        except Exception as error:
            self.completed.emit(False, str(error))

    def cancel(self):
        """Ask pip to stop; the run emits its failure through ``completed``."""
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()


class UpdateDialog(QDialog):
    """Small update window in the shape of a system software updater.

    Parameters
    ----------
    current_version : str
        Version currently installed.
    latest_version : str
        Version offered by PyPI.
    has_changelog : bool, optional
        Whether a GitHub release exists for *latest_version*.
    parent : QWidget, optional
        Parent widget.
    """

    WIDTH = 400

    #: ``role -> (attribute, label, handler, kind)`` for every action button.
    _BUTTONS = {
        "changelog": ("changelog_button", "Changelog", "_open_changelog", "quiet"),
        "cancel": ("cancel_button", "Cancel", "reject", "flat"),
        "install": ("install_button", "Install", "_on_install_clicked", "default"),
        "stop": ("cancel_button", "Cancel", "_on_cancel_install", "flat"),
        "later": ("cancel_button", "Later", "accept", "flat"),
        "restart": ("restart_button", "Restart now", "_restart_application", "default"),
        "copy": ("copy_button", "Copy command", "_copy_command", "quiet"),
        "close": ("cancel_button", "Close", "reject", "flat"),
    }

    #: ``state -> (window title, body text, leading roles, trailing roles)``.
    _STATES = {
        "idle": (
            "Update available",
            "A newer release is available on PyPI.",
            ("changelog",),
            ("cancel", "install"),
        ),
        "installing": (
            "Installing update",
            "Fetching {package} {version} from PyPI.",
            ("progress",),
            ("stop",),
        ),
        "success": (
            "Update installed",
            "Restart Mosaic to use the new version.",
            (),
            ("later", "restart"),
        ),
        "failed": (
            "Update failed",
            "Run the command below in a terminal instead.",
            ("copy",),
            ("close",),
        ),
    }

    def __init__(
        self,
        current_version: str,
        latest_version: str,
        has_changelog: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setModal(True)

        self._current = str(current_version)
        self._latest = str(latest_version)
        self._has_changelog = bool(has_changelog)
        self._worker = None

        self.state = "idle"

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(0)

        self.subline = self._label("")
        self.subline.setWordWrap(True)
        root.addWidget(self.subline)
        root.addSpacing(18)

        self.installed_label = self._version_value(self._current, emphasis=False)
        self.available_label = self._version_value(self._latest, emphasis=True)
        root.addWidget(self._version_table())
        root.addSpacing(26)

        self.command_box = self._command_box()
        self.command_box.setVisible(False)
        root.addWidget(self.command_box)

        self._root = root
        self._action_row = QHBoxLayout()
        self._action_row.setContentsMargins(0, 0, 0, 0)
        self._action_row.setSpacing(8)
        root.addLayout(self._action_row)

        self.setFixedWidth(self.WIDTH)
        self.setStyleSheet(f"QDialog {{ background: {Colors.SURFACE}; }}")
        self._apply_state("idle")

    def _label(
        self, text: str, role: str = "secondary", size: int | None = None
    ) -> QLabel:
        color = {
            "primary": Colors.TEXT_PRIMARY,
            "secondary": Colors.TEXT_SECONDARY,
            "muted": Colors.TEXT_MUTED,
            "error": Colors.ERROR,
        }[role]
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {color}; background: transparent;"
            f"font-size: {Typography.BODY if size is None else size}px;"
        )
        return label

    def _version_value(self, text: str, emphasis: bool) -> QLabel:
        label = QLabel(text)
        weight = 600 if emphasis else 400
        color = Colors.TEXT_PRIMARY if emphasis else Colors.TEXT_SECONDARY
        label.setStyleSheet(
            f"color: {color}; background: transparent;"
            f"font-family: {Typography.MONO}; font-size: {Typography.BODY}px;"
            f"font-weight: {weight};"
        )
        return label

    def _version_table(self) -> QWidget:
        table = QWidget()
        table.setStyleSheet("background: transparent;")
        rows = QVBoxLayout(table)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(6)

        for caption, value in (
            ("Installed", self.installed_label),
            ("Available", self.available_label),
        ):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(0)
            key = self._label(caption, role="muted", size=Typography.LABEL)
            key.setFixedWidth(84)
            row.addWidget(key)
            row.addWidget(value)
            row.addStretch(1)
            rows.addLayout(row)
        return table

    def _flat_style(self, quiet: bool = False) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                color: {Colors.TEXT_SECONDARY};
                border: none;
                border-radius: {Colors.RADIUS}px;
                padding: 4px {8 if quiet else 14}px;
                font-size: {Typography.BODY}px;
            }}
            QPushButton:hover {{
                background: {Colors.BG_HOVER};
                color: {Colors.TEXT_PRIMARY};
            }}
            QPushButton:pressed {{ background: {Colors.BG_PRESSED}; }}
            QPushButton:disabled {{
                background: transparent;
                color: {Colors.BORDER_HOVER};
            }}
            QPushButton:focus {{ outline: none; }}
        """

    def _command_box(self) -> QWidget:
        """Container for the manual pip command, revealed when pip fails."""
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 14)
        layout.setSpacing(0)

        self.command_label = QLabel(f"{executable} -m pip install -U {PACKAGE_NAME}")
        self.command_label.setWordWrap(True)
        self.command_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.command_label.setStyleSheet(
            f"""
            QLabel {{
                background: {Colors.BG_TERTIARY};
                color: {Colors.TEXT_SECONDARY};
                border-radius: {Colors.RADIUS}px;
                padding: 8px 10px;
                font-family: {Typography.MONO};
                font-size: {Typography.SMALL}px;
            }}
            """
        )
        layout.addWidget(self.command_label)
        return box

    def _progress_bar(self) -> QProgressBar:
        bar = QProgressBar()
        bar.setRange(0, 0)
        bar.setTextVisible(False)
        bar.setFixedHeight(3)
        bar.setFixedWidth(160)
        return bar

    def _clear_actions(self):
        for attr, *_ in self._BUTTONS.values():
            setattr(self, attr, None)

        while self._action_row.count():
            item = self._action_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _make_widget(self, role: str) -> QWidget:
        """Build one action-row entry from its entry in ``_BUTTONS``."""
        if role == "progress":
            return self._progress_bar()

        attr, label, handler, kind = self._BUTTONS[role]
        button = QPushButton(label)
        button.setFixedHeight(28)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(getattr(self, handler))

        if kind == "default":
            button.setDefault(True)
        else:
            button.setStyleSheet(self._flat_style(quiet=kind == "quiet"))

        if role == "changelog" and not self._has_changelog:
            button.setEnabled(False)
            button.setToolTip("This release has no GitHub release notes")
            button.setCursor(Qt.CursorShape.ArrowCursor)

        setattr(self, attr, button)
        return button

    def _apply_state(self, state: str, detail: str = ""):
        title, text, leading, trailing = self._STATES[state]

        self.state = state
        self._clear_actions()
        self.setWindowTitle(title)
        self.subline.setText(
            detail or text.format(package=PACKAGE_NAME, version=self._latest)
        )
        self.command_box.setVisible(state == "failed")

        for role in leading:
            self._action_row.addWidget(self._make_widget(role))
        self._action_row.addStretch(1)
        for role in trailing:
            self._action_row.addWidget(self._make_widget(role))

        self._root.activate()
        self.setFixedSize(self.WIDTH, self._root.sizeHint().height())

    def _open_changelog(self):
        QDesktopServices.openUrl(QUrl(_GITHUB_RELEASE_URL.format(version=self._latest)))

    def _copy_command(self):
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.command_label.text())

    def _on_install_clicked(self):
        self._apply_state("installing")
        self._start_install()

    def _start_install(self):
        self._worker = _InstallWorker(self)
        self._worker.completed.connect(self._on_install_finished)
        self._worker.start()
        return None

    def _on_cancel_install(self):
        if self._worker is not None:
            self._worker.cancel()

    def _on_install_finished(self, succeeded: bool, message: str):
        if succeeded:
            return self._apply_state("success")

        detail = (message or "").strip().splitlines()
        return self._apply_state("failed", detail[-1] if detail else "")

    def _restart_application(self):
        from subprocess import Popen

        self.accept()
        Popen([executable] + argv)
        QApplication.instance().quit()

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        super().closeEvent(event)
