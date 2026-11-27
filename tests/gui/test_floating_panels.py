import pytest
from qtpy.QtCore import QPoint
from qtpy.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from mosaic.widgets.ribbon import RibbonButton
from mosaic.widgets.status_indicator import StatusIndicator


@pytest.fixture
def main_window(qapp):
    mw = QMainWindow()
    mw.statusBar()
    mw.resize(800, 600)
    mw.move(100, 100)
    mw.show()
    QApplication.processEvents()
    yield mw
    mw.close()


def _offset_after_move(window, panel):
    offset = panel.pos() - window.pos()
    window.move(window.pos() + QPoint(150, 80))
    QApplication.processEvents()
    return offset, panel.pos() - window.pos()


def test_task_monitor_follows_window(main_window):
    indicator = StatusIndicator(main_window)
    indicator._show_task_monitor()
    before, after = _offset_after_move(main_window, indicator.task_monitor)
    assert after == before


def test_ribbon_settings_panel_follows_window(main_window):
    central = QWidget()
    button = RibbonButton("Fit", "ph.cube", settings_config={"settings": []})
    QVBoxLayout(central).addWidget(button)
    main_window.setCentralWidget(central)
    QApplication.processEvents()
    button._toggle_panel()
    before, after = _offset_after_move(main_window, button.settings_panel)
    assert after == before
    button.settings_panel.close()


def test_task_monitor_stays_on_status_bar_after_resize(main_window):
    indicator = StatusIndicator(main_window)
    indicator._show_task_monitor()
    bar = main_window.statusBar()
    before = indicator.task_monitor.pos() - bar.mapToGlobal(bar.rect().topRight())
    main_window.resize(1100, 700)
    QApplication.processEvents()
    after = indicator.task_monitor.pos() - bar.mapToGlobal(bar.rect().topRight())
    assert after == before
