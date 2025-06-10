#!python3
"""
GUI entrypoint.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""
import sys
import argparse
from platform import system
from os import environ as os_environ
from importlib_resources import files

if system() == "Darwin":
    os_environ["OMP_NUM_THREADS"] = "1"

from qtpy.QtGui import QIcon
from qtpy.QtWidgets import QApplication

from mosaic import __version__
from mosaic.stylesheets import (
    QMessageBox_style,
    QLineEdit_style,
    QSpinBox_style,
    QDoubleSpinBox_style,
    QComboBox_style,
    QCheckBox_style,
    QSlider_style,
    QGroupBox_style,
    QListWidget_style,
    QToolButton_style,
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
    app.setStyleSheet(
        QMessageBox_style
        + QLineEdit_style
        + QSpinBox_style
        + QDoubleSpinBox_style
        + QComboBox_style
        + QCheckBox_style
        + QSlider_style
        + QGroupBox_style
        + QListWidget_style
        + QToolButton_style
    )

    from mosaic.gui import App

    window = App()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
