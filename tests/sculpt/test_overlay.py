"""Tests for the sculpt overlay actors."""

from mosaic.sculpt.overlay import SculptOverlay


def test_overlay_constructs():
    overlay = SculptOverlay()
    assert overlay.cursor_ring is not None
    assert overlay.drag_vector is not None


def test_overlay_set_tool_color_does_not_crash():
    overlay = SculptOverlay()
    overlay.set_tool_color((1.0, 0.7, 0.2))


def test_overlay_update_cursor_screen_position():
    overlay = SculptOverlay()
    overlay.set_cursor_screen_position(120, 240, on_mesh=True)
    overlay.set_cursor_screen_position(120, 240, on_mesh=False)


def test_overlay_drag_vector_visibility():
    import numpy as np

    overlay = SculptOverlay()
    overlay.set_drag_vector(np.zeros(3), np.array([1.0, 0.0, 0.0]))
    assert overlay.drag_vector.GetVisibility() == 1
    overlay.clear_drag_vector()
    assert overlay.drag_vector.GetVisibility() == 0
