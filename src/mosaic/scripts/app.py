#!python3
"""
GUI entrypoint.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""
import sys
import signal
import argparse
from importlib_resources import files

from qtpy.QtCore import Qt, QLocale
from qtpy.QtWidgets import QApplication
from qtpy.QtGui import QIcon, QFont, QFontDatabase, QFontInfo

from mosaic import __version__
from mosaic.stylesheets import (
    Colors,
    Typography,
    build_global_stylesheet,
    build_qt_palette,
    install_macos_titlebar_filter,
    build_appstyle,
)

try:
    from mosaic.onboarding.chapters import all_chapters
    from mosaic.onboarding import launch_onboarding

    HAS_ONBOARDING = True
except Exception:
    HAS_ONBOARDING = False


def _prompt_first_launch(window):
    from qtpy.QtWidgets import QMessageBox
    from mosaic.widgets import MosaicMessageBox
    from mosaic.settings import Settings
    from mosaic.onboarding import launch_onboarding

    box = MosaicMessageBox(window)
    box.setWindowTitle("Welcome to Mosaic")
    box.setIcon(QMessageBox.Icon.Question)
    box.setText("Hey, looks like it's your first time here!\n\nWant a quick tour?")
    yes_btn = box.addButton("Sure, let's go", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Maybe later", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(yes_btn)
    box.exec()

    Settings.ui.onboarding_done = True

    if box.clickedButton() is yes_btn:
        launch_onboarding(window, "basics")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version=f"{__version__}")
    if HAS_ONBOARDING:
        parser.add_argument(
            "--onboard",
            nargs="?",
            const="__list__",
            metavar="CHAPTER",
            help="Launch onboarding walkthrough. Run without argument to list chapters.",
        )
    args = parser.parse_args()

    if HAS_ONBOARDING and args.onboard == "__list__":
        print("\nAvailable onboarding chapters:\n")
        for ch in all_chapters():
            print(f"  {ch.id:<20} {ch.description}")
        print("\nUsage: mosaic --onboard <chapter>\n")
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
    QLocale.setDefault(QLocale.c())
    app.setApplicationName("Mosaic")
    app.setApplicationDisplayName("Mosaic")
    icon = QIcon(str(files("mosaic.data").joinpath("data/mosaic.icns")))
    app.setWindowIcon(icon)

    # Restore the previously selected theme before any palette/stylesheet is
    # built so the very first frame is painted with the correct colors.
    from mosaic.settings import Settings

    if Settings.ui.theme_mode == "dark":
        Colors.apply_palette(Colors.DARK)
    else:
        Colors.apply_palette(Colors.LIGHT)

    app.setStyle(build_appstyle())
    if sys.platform == "darwin":
        font = QFont("Helvetica Neue")
        if "Helvetica Neue" not in QFontDatabase.families():
            font = app.font()
        font.setPointSize(13)
        app.setFont(font)

    Typography.set_base(QFontInfo(app.font()).pixelSize())

    app.setPalette(build_qt_palette())
    app.setStyleSheet(build_global_stylesheet())

    install_macos_titlebar_filter()

    signal.signal(signal.SIGINT, lambda *args: app.quit())

    from mosaic.gui import App

    window = App()
    window.show()

    if HAS_ONBOARDING:
        from qtpy.QtCore import QTimer

        if args.onboard:
            QTimer.singleShot(200, lambda: launch_onboarding(window, args.onboard))
        elif not Settings.ui.onboarding_done:
            QTimer.singleShot(500, lambda: _prompt_first_launch(window))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
