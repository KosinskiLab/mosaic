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

from qtpy.QtGui import QIcon, QFont, QFontDatabase
from qtpy.QtWidgets import QApplication

from mosaic import __version__
from mosaic.stylesheets import (
    build_global_stylesheet,
    build_qt_palette,
    install_macos_titlebar_filter,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version=f"{__version__}")
    parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("Mosaic")
    app.setApplicationDisplayName("Mosaic")
    icon = QIcon(str(files("mosaic.data").joinpath("data/mosaic.icns")))
    app.setWindowIcon(icon)

    # Fixes alignment issue in default style
    # https://forum.qt.io/topic/105191/why-isn-t-a-qcombobox-positioned-correctly-in-a-layout/11
    app.setStyle("Fusion")
    app.setPalette(build_qt_palette())
    app.setStyleSheet(build_global_stylesheet())

    font = QFont("Helvetica Neue")
    if "Helvetica Neue" not in QFontDatabase.families():
        font = app.font()
    font.setPointSize(13)
    app.setFont(font)

    install_macos_titlebar_filter()

    signal.signal(signal.SIGINT, lambda *args: app.quit())

    from mosaic.gui import App

    window = App()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
