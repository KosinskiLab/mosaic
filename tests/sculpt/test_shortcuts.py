"""SculptShortcutFilter dispatch tests."""

from unittest.mock import MagicMock

import pytest
from qtpy.QtCore import QEvent, Qt
from qtpy.QtGui import QKeyEvent, QWheelEvent
from qtpy.QtCore import QPointF, QPoint

from mosaic.sculpt.controller import Brush, SculptController
from mosaic.sculpt.shortcuts import SculptShortcutFilter


def _key(key, mods=Qt.KeyboardModifier.NoModifier):
    return QKeyEvent(QEvent.Type.KeyPress, int(key), mods)


def _wheel(delta_y, mods=Qt.KeyboardModifier.NoModifier):
    return QWheelEvent(
        QPointF(0, 0),
        QPointF(0, 0),
        QPoint(0, 0),
        QPoint(0, delta_y),
        Qt.MouseButton.NoButton,
        mods,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


@pytest.fixture
def hud_stub():
    hud = MagicMock()
    hud.current_tool.return_value = "grab"
    return hud


@pytest.fixture
def controller(perturbed_grid_mesh):
    vs, _fs, _ = perturbed_grid_mesh
    c = SculptController(Brush(radius=10.0))
    target = MagicMock()
    target.n = len(vs)
    c.session = MagicMock()
    c.session.tool = "grab"
    return c


def test_number_keys_dispatch_to_tools(hud_stub, controller):
    f = SculptShortcutFilter(controller, sculpt_hud=hud_stub)
    for key, expected in (
        (Qt.Key.Key_1, "view"),
        (Qt.Key.Key_2, "grab"),
        (Qt.Key.Key_3, "smooth"),
        (Qt.Key.Key_4, "patch"),
    ):
        consumed = f.eventFilter(None, _key(key))
        assert consumed is True
        hud_stub.set_tool.assert_called_with(expected)


def test_bracket_keys_adjust_radius(hud_stub, controller):
    f = SculptShortcutFilter(controller, sculpt_hud=hud_stub)
    r0 = controller.brush.radius
    f.eventFilter(None, _key(Qt.Key.Key_BracketRight))
    assert controller.brush.radius > r0
    hud_stub.set_radius.assert_called()


def test_ctrl_z_consumed_by_filter(controller):
    # Ctrl+Z is no longer intercepted here; the filter swallows all non-Escape
    # keys so the event is consumed (True) but the controller is not called.
    f = SculptShortcutFilter(controller)
    consumed = f.eventFilter(
        None, _key(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    )
    assert consumed is True


def test_other_keys_consumed_but_not_acted_on(controller):
    f = SculptShortcutFilter(controller)
    consumed = f.eventFilter(None, _key(Qt.Key.Key_3))
    assert consumed is True
    consumed = f.eventFilter(None, _key(Qt.Key.Key_W))
    assert consumed is True  # swallowed so VTK can't wireframe-toggle


def test_shift_wheel_changes_radius(controller):
    f = SculptShortcutFilter(controller)
    r0 = controller.brush.radius
    f.eventFilter(None, _wheel(120, Qt.KeyboardModifier.ShiftModifier))
    assert controller.brush.radius > r0
    f.eventFilter(None, _wheel(-120, Qt.KeyboardModifier.ShiftModifier))
    assert controller.brush.radius < r0 * 1.1


def test_unmodified_wheel_passes_through(controller):
    f = SculptShortcutFilter(controller)
    r0 = controller.brush.radius
    consumed = f.eventFilter(None, _wheel(120))
    assert consumed is False
    assert controller.brush.radius == r0


def test_escape_bubbles_out(controller):
    """Filter returns False for Escape so gui-level QShortcut handles it."""
    f = SculptShortcutFilter(controller)
    consumed = f.eventFilter(None, _key(Qt.Key.Key_Escape))
    assert consumed is False


def test_tool_change_delegates_to_mode(controller):
    mode = MagicMock()
    f = SculptShortcutFilter(controller, mode=mode)
    f.eventFilter(None, _key(Qt.Key.Key_1))
    mode.set_tool.assert_called_with("view")
    f.eventFilter(None, _key(Qt.Key.Key_2))
    mode.set_tool.assert_called_with("grab")
