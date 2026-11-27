import pytest
from qtpy.QtWidgets import QMainWindow

from mosaic.stylesheets import Colors
from mosaic.widgets.status_indicator import StatusIndicator


@pytest.fixture
def indicator(qapp):
    mw = QMainWindow()
    mw.statusBar()
    yield StatusIndicator(mw)
    mw.close()


def test_transient_message_times_out(indicator):
    indicator.show_task("Loaded ", path="/d/TS_012_rec.mrc")
    assert "TS_012_rec.mrc" in indicator.task_label.text()
    assert indicator.task_label.toolTip() == "Loaded /d/TS_012_rec.mrc"
    assert indicator._task_timer.isActive()


def test_missing_warning_persists_until_cleared(indicator):
    indicator.show_task(
        "Tomogram missing: ", path="/d/TS_031_rec.mrc", warning=True, persist=True
    )
    assert not indicator._task_timer.isActive()
    assert Colors.WARNING_TEXT in indicator.task_label.styleSheet()
    indicator.show_task("Saved as ", path="/d/TS_031.mosaic")
    indicator._task_timer.timeout.emit()
    assert "TS_031_rec.mrc" in indicator.task_label.text()
    indicator.clear_persistent_task()
    assert indicator.task_label.text() == ""


def test_label_is_wider(indicator):
    assert indicator.task_label.width() == 260


def test_warning_survives_theme_refresh(indicator):
    indicator.show_task(
        "Tomogram missing: ", path="/d/a.mrc", warning=True, persist=True
    )
    indicator._setup_status_bar_style()
    assert Colors.WARNING_TEXT in indicator.task_label.styleSheet()


def test_transient_over_warning_stays_secondary_on_refresh(indicator):
    indicator.show_task(
        "Tomogram missing: ", path="/d/a.mrc", warning=True, persist=True
    )
    indicator.show_task("Saved as ", path="/d/a.mosaic")
    indicator._setup_status_bar_style()
    assert Colors.WARNING_TEXT not in indicator.task_label.styleSheet()
