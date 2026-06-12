"""
Update checker

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from sys import executable, argv

from qtpy.QtCore import Qt, QThread, QUrl, Signal
from qtpy.QtGui import QDesktopServices
from qtpy.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from ..stylesheets import Colors, Typography
from ..widgets import MosaicMessageBox
from ..__version__ import __version__


_GITHUB_RELEASE_URL = "https://github.com/KosinskiLab/mosaic/releases/tag/v{version}"
_GITHUB_LATEST_API = "https://api.github.com/repos/KosinskiLab/mosaic/releases/latest"


class UpdateChecker(QThread):
    """Background thread to check GitHub for the latest release."""

    update_available = Signal(str, str)

    def __init__(self, current_version: str = __version__, parent=None):
        super().__init__(parent)
        self.current_version = str(current_version)
        self.api_url = _GITHUB_LATEST_API

    def run(self):
        import json
        import urllib.request
        from packaging import version

        try:
            req = urllib.request.Request(self.api_url)
            req.add_header("User-Agent", "Mosaic-Update-Checker")

            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())

            latest = str(data.get("tag_name", "")).lstrip("v")
            if not latest:
                return None

            latest_v = version.parse(latest)
            if latest_v.is_prerelease:
                return None
            if latest_v <= version.parse(self.current_version):
                return None

            notes = data.get("body") or ""
            self.update_available.emit(latest, notes)
        except Exception:
            pass  # Dont bother handling network issues


class UpdateDialog(QDialog):
    """Lightweight update dialog with rendered release notes."""

    def __init__(
        self,
        current_version: str,
        latest_version: str,
        release_notes: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Update available")
        self.setModal(True)
        self.setMinimumSize(520, 400)
        self.resize(650, 550)

        self._current = current_version
        self._latest = latest_version
        self._notes = (release_notes or "").strip()
        self._release_url = _GITHUB_RELEASE_URL.format(version=latest_version)
        self.update_result = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(6)

        header = QLabel(
            f"<span style='font-weight:600;color:{Colors.TEXT_PRIMARY};'>"
            f"Mosaic {latest_version} available</span> "
            f"<span style='color:{Colors.TEXT_SECONDARY};'>"
            f"(you have {current_version})</span>"
        )
        header.setTextFormat(Qt.TextFormat.RichText)
        header.setStyleSheet(f"font-size: {Typography.BODY}px;")
        root.addWidget(header)

        if self._notes:
            root.addSpacing(14)
            root.addWidget(self._build_notes_view(), 1)
        else:
            root.addStretch(1)

        root.addSpacing(16)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        notes_btn = QPushButton("Open on GitHub")
        notes_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        notes_btn.clicked.connect(self._open_release_notes)
        notes_btn.setStyleSheet(self._link_btn_style())
        btn_row.addWidget(notes_btn)
        btn_row.addStretch()

        skip_btn = QPushButton("Skip")
        skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        skip_btn.clicked.connect(self._on_skip_clicked)
        skip_btn.setStyleSheet(self._secondary_btn_style())
        btn_row.addWidget(skip_btn)

        update_btn = QPushButton("Update Now")
        update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        update_btn.setDefault(True)
        update_btn.clicked.connect(self._on_update_clicked)
        update_btn.setStyleSheet(self._primary_btn_style())
        btn_row.addWidget(update_btn)

        root.addLayout(btn_row)
        self.setStyleSheet(f"QDialog {{ background: {Colors.SURFACE}; }}")

    def _build_notes_view(self) -> QTextBrowser:
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        view.setLineWrapMode(QTextBrowser.LineWrapMode.WidgetWidth)
        view.setMarkdown(self._notes)
        view.setMinimumHeight(280)
        view.setStyleSheet(
            f"""
            QTextBrowser {{
                background: palette(base);
                border: 1px solid {Colors.BORDER_DARK};
                border-radius: 6px;
                padding: 10px 12px;
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.BODY}px;
            }}
            """
        )
        return view

    def _on_skip_clicked(self):
        from ..settings import Settings

        Settings.ui.skipped_version = self._latest
        self.reject()

    def _open_release_notes(self):
        QDesktopServices.openUrl(QUrl(self._release_url))

    def _on_update_clicked(self):
        self.accept()
        self._run_update()

    def _run_update(self):
        from subprocess import run

        try:
            result = run(
                [executable, "-m", "pip", "install", "-U", "mosaic-gui"],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                MosaicMessageBox.information(
                    self.parent(),
                    "Update Successful",
                    "Mosaic has been updated successfully!\n\n"
                    "The application will now restart to use the new version.",
                )
                self.update_result = "success"
                self._restart_application()
            else:
                MosaicMessageBox.warning(
                    self.parent(),
                    "Update Failed",
                    f"The update failed. Please run manually in your terminal:\n\n"
                    f"{executable} -m pip install -U mosaic-gui\n\n"
                    f"Error: {result.stderr}",
                )
        except Exception as e:
            MosaicMessageBox.warning(
                self.parent(),
                "Update Failed",
                f"Could not run update command.\n\n"
                f"Please run manually in your terminal:\n"
                f"{executable} -m pip install -U mosaic-gui\n\n"
                f"Error: {str(e)}",
            )

    def _restart_application(self):
        from subprocess import Popen

        app = QApplication.instance()
        Popen([executable] + argv)
        app.quit()

    def _primary_btn_style(self) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                color: {Colors.PRIMARY};
                border: 1px solid {Colors.BORDER_DARK};
                border-radius: 6px;
                padding: 7px 18px;
                font-size: {Typography.BODY}px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                border-color: {Colors.PRIMARY};
                background: {Colors.alpha("PRIMARY", 0.08)};
            }}
            QPushButton:pressed {{ background: {Colors.alpha("PRIMARY", 0.14)}; }}
            QPushButton:focus {{ outline: none; }}
        """

    def _secondary_btn_style(self) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_DARK};
                border-radius: 6px;
                padding: 7px 18px;
                font-size: {Typography.BODY}px;
            }}
            QPushButton:hover {{
                border-color: {Colors.BORDER_HOVER};
                color: {Colors.TEXT_PRIMARY};
            }}
            QPushButton:focus {{ outline: none; }}
        """

    def _link_btn_style(self) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {Colors.TEXT_SECONDARY};
                padding: 6px 4px;
                font-size: {Typography.BODY}px;
            }}
            QPushButton:hover {{ color: {Colors.PRIMARY}; }}
            QPushButton:focus {{ outline: none; }}
        """
