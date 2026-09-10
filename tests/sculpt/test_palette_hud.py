"""Tests for the sculpt palette HUD widget."""

import pytest

from mosaic.widgets.sculpt_palette_hud import SculptPaletteHUD


@pytest.fixture
def palette(qtbot):
    widget = SculptPaletteHUD(parent=None)
    qtbot.addWidget(widget)
    return widget


def test_palette_constructs(palette):
    assert palette is not None
    assert not palette.isVisible()
    for tool in ("view", "grab", "smooth", "patch"):
        assert tool in palette._tool_buttons
        text = palette._tool_buttons[tool].text()
        assert tool.title() in text  # natural label
        assert text.lstrip()[0].isdigit()  # hotkey prefix


def test_tool_buttons_are_exclusive(palette):
    palette._tool_buttons["smooth"].click()
    assert palette._tool_buttons["smooth"].isChecked()
    assert not palette._tool_buttons["grab"].isChecked()
    assert not palette._tool_buttons["patch"].isChecked()

    palette._tool_buttons["patch"].click()
    assert palette._tool_buttons["patch"].isChecked()
    assert not palette._tool_buttons["smooth"].isChecked()
    assert not palette._tool_buttons["grab"].isChecked()


def test_tool_button_click_emits_signal(palette, qtbot):
    with qtbot.waitSignal(palette.toolChanged, timeout=1000) as blocker:
        palette._tool_buttons["smooth"].click()
    assert blocker.args == ["smooth"]


def test_set_tool_does_not_emit(palette, qtbot):
    received = []
    palette.toolChanged.connect(received.append)
    palette.set_tool("smooth")
    qtbot.wait(20)
    assert received == []
    assert palette._tool_buttons["smooth"].isChecked()


def test_radius_slider_emits(palette, qtbot):
    with qtbot.waitSignal(palette.radiusChanged, timeout=1000) as blocker:
        palette._radius_row.slider.setValue(palette._radius_row.slider.value() + 5)
    assert isinstance(blocker.args[0], float)


def test_set_radius_does_not_emit(palette, qtbot):
    received = []
    palette.radiusChanged.connect(received.append)
    palette.set_radius(50.0)
    qtbot.wait(20)
    assert received == []
    # Slider quantises to 100 steps across its full range, so the read-back
    # can land roughly one step away from the exact set value.
    step = (palette._radius_row.max_val - palette._radius_row.min_val) / 100.0
    assert palette._radius_row.value() == pytest.approx(50.0, abs=step)


def test_strength_slider_emits(palette, qtbot):
    with qtbot.waitSignal(palette.strengthChanged, timeout=1000) as blocker:
        palette._strength_row.slider.setValue(palette._strength_row.slider.value() + 5)
    assert isinstance(blocker.args[0], float)


def test_set_strength_does_not_emit(palette, qtbot):
    received = []
    palette.strengthChanged.connect(received.append)
    palette.set_strength(0.5)
    qtbot.wait(20)
    assert received == []
    assert palette.current_strength() == pytest.approx(0.5, abs=0.01)


def test_palette_defaults_to_view_tool(palette):
    assert palette.current_tool() == "view"
    assert palette._tool_buttons["view"].isChecked()


def test_set_radius_range_rescales_without_emitting(palette, qtbot):
    received = []
    palette.radiusChanged.connect(received.append)
    palette.set_radius_range(1.0, 1000.0)
    qtbot.wait(20)
    assert received == []
    assert palette._radius_row.min_val == pytest.approx(1.0)
    assert palette._radius_row.max_val == pytest.approx(1000.0)


def test_set_radius_range_clamps_current_value(palette):
    palette.set_radius(50.0)
    palette.set_radius_range(0.5, 20.0)
    assert palette._radius_row.value() == pytest.approx(20.0, abs=0.5)


def test_set_radius_range_ignores_invalid(palette):
    before_min = palette._radius_row.min_val
    palette.set_radius_range(10.0, 5.0)
    assert palette._radius_row.min_val == before_min
