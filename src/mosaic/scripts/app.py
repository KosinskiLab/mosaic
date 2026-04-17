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

from qtpy.QtGui import QIcon, QFont, QFontDatabase, QFontInfo
from qtpy.QtWidgets import QApplication


from mosaic import __version__
from mosaic.stylesheets import (
    Colors,
    Typography,
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

    # Restore the previously selected theme before any palette/stylesheet is
    # built so the very first frame is painted with the correct colors.
    from mosaic.settings import Settings

    if Settings.ui.theme_mode == "dark":
        Colors.apply_palette(Colors.DARK)
    else:
        Colors.apply_palette(Colors.LIGHT)

    # Fixes alignment issue in default style
    # https://forum.qt.io/topic/105191/why-isn-t-a-qcombobox-positioned-correctly-in-a-layout/11
    app.setStyle("Fusion")

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
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
