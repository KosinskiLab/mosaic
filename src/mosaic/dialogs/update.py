"""
Update checker

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from sys import executable, argv

from qtpy.QtCore import QThread, Signal
from qtpy.QtWidgets import QMessageBox, QCheckBox, QApplication

from ..__version__ import __version__


class UpdateChecker(QThread):
    """Background thread to check for updates without blocking UI."""

    update_available = Signal(str, str)  # latest_version, release_notes

    def __init__(self, current_version: str = __version__):
        super().__init__()
        self.current_version = str(current_version)
        self.repo_url = (
            "https://api.github.com/repos/KosinskiLab/mosaic/releases/latest"
        )

    def run(self):
        """Check GitHub for latest release."""
        import json
        import urllib.request
        from packaging import version

        try:
            req = urllib.request.Request(self.repo_url)
            req.add_header("User-Agent", "Mosaic-Update-Checker")

            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                latest = data["tag_name"].lstrip("v")
                notes = data.get("body", "No release notes available.")

                if version.parse(latest) > version.parse(self.current_version):
                    self.update_available.emit(latest, notes)
        except Exception:
            pass  # Dont bother handling network issues


class UpdateDialog(QMessageBox):
    """Dialog to show update information using QMessageBox."""

    def __init__(self, current_version, latest_version, release_notes, parent=None):
        super().__init__(parent)

        self.setIcon(QMessageBox.Icon.Information)
        self.setWindowTitle("Update")

        self.setText(
            f"Mosaic {latest_version} available\n\n"
            f"Current version: {current_version}\n"
        )

        self.setInformativeText(release_notes)

        self.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Ignore
        )
        self.setDefaultButton(QMessageBox.StandardButton.Ok)

        self.button(QMessageBox.StandardButton.Ok).setText("Update Now")
        self.button(QMessageBox.StandardButton.Ignore).setText("Skip")

        self._checkbox = QCheckBox("Don't show this update again", self)
        self.setCheckBox(self._checkbox)

        self.latest_version = latest_version
        self.update_result = None

    def exec(self):
        """Execute dialog and handle result."""
        result = super().exec()

        if self.checkBox().isChecked():
            from .settings import Settings

            Settings.ui.skipped_version = self.latest_version

        if result == QMessageBox.StandardButton.Ok:
            self._run_update()

        return result

    def _run_update(self):
        """Run update command."""
        from subprocess import run

        try:
            result = run(
                [executable, "-m", "pip", "install", "-U", "mosaic-gui"],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                msg_box = QMessageBox(self.parent())
                msg_box.setIcon(QMessageBox.Icon.Information)
                msg_box.setWindowTitle("Update Successful")
                msg_box.setText("Mosaic has been updated successfully!")
                msg_box.setInformativeText(
                    "The application will now restart to use the new version."
                )
                msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
                msg_box.exec()

                self.update_result = "success"
                self._restart_application()
            else:
                QMessageBox.warning(
                    self.parent(),
                    "Update Failed",
                    f"The update failed. Please run manually in your terminal:\n\n"
                    f"{executable} -m pip install -U mosaic-gui\n\n"
                    f"Error: {result.stderr}",
                )
        except Exception as e:
            QMessageBox.warning(
                self.parent(),
                "Update Failed",
                f"Could not run update command.\n\n"
                f"Please run manually in your terminal:\n"
                f"{executable} -m pip install -U mosaic-gui\n\n"
                f"Error: {str(e)}",
            )

    def _restart_application(self):
        """Restart the application."""
        from subprocess import Popen

        app = QApplication.instance()
        Popen([executable] + argv)
        app.quit()
