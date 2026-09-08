"""
Tests for viewport prop picking across lighting modes.

These render offscreen and are skipped where VTK cannot create a
render window. Run with xvfb for CI.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from unittest.mock import Mock

import pytest
import vtk

from mosaic.gui import App
from mosaic.viewport import PropIdBuffer, ViewportInteractor, hardware_picking

pytestmark = [pytest.mark.slow, pytest.mark.gui]

WIDTH, HEIGHT = 300, 300

LIGHTING_PASSES = {
    "simple": None,
    "poster": vtk.vtkSSAOPass,
    "silhouettes": vtk.vtkEDLShading,
}


class _StubWidget:
    """Minimal stand-in exposing a render window to the picking helpers."""

    def __init__(self, render_window):
        self._render_window = render_window

    def GetRenderWindow(self):
        return self._render_window


@pytest.fixture
def scene():
    """Offscreen render window showing a single centered sphere actor."""
    source = vtk.vtkSphereSource()
    source.SetRadius(10)
    source.SetThetaResolution(32)
    source.SetPhiResolution(32)

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(source.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)

    renderer = vtk.vtkRenderer()
    renderer.AddActor(actor)

    render_window = vtk.vtkRenderWindow()
    render_window.SetOffScreenRendering(1)
    render_window.SetSize(WIDTH, HEIGHT)
    render_window.AddRenderer(renderer)

    interactor = vtk.vtkRenderWindowInteractor()
    interactor.SetRenderWindow(render_window)

    renderer.ResetCamera()
    render_window.Render()

    yield renderer, render_window, actor

    renderer.SetPass(None)
    render_window.Finalize()


def _set_lighting_mode(renderer, render_window, mode):
    effect = LIGHTING_PASSES[mode]
    if effect is not None:
        renderer.SetPass(App._screen_effect_pass(effect()))
        render_window.Render()


def _viewport_for(render_window):
    viewport = ViewportInteractor.__new__(ViewportInteractor)
    viewport.vtk_widget = _StubWidget(render_window)
    viewport._prop_ids = None
    return viewport


def _hardware_pick(renderer, x, y):
    """Ground truth: an unassisted prop pick, valid in every lighting mode."""
    picker = vtk.vtkPropPicker()
    with hardware_picking(renderer):
        picker.Pick(x, y, 0, renderer)
    return picker.GetViewProp()


@pytest.mark.parametrize("mode", list(LIGHTING_PASSES))
def test_pick_prop_at_hits_actor(scene, mode):
    renderer, render_window, actor = scene
    _set_lighting_mode(renderer, render_window, mode)

    picked = _viewport_for(render_window)._pick_prop_at((WIDTH // 2, HEIGHT // 2, 0))

    assert picked is actor


@pytest.mark.parametrize("mode", list(LIGHTING_PASSES))
def test_pick_prop_at_misses_background(scene, mode):
    renderer, render_window, _ = scene
    _set_lighting_mode(renderer, render_window, mode)

    assert _viewport_for(render_window)._pick_prop_at((2, 2, 0)) is None


@pytest.mark.parametrize("mode", list(LIGHTING_PASSES))
def test_pick_prop_at_leaves_render_pass_installed(scene, mode):
    renderer, render_window, _ = scene
    _set_lighting_mode(renderer, render_window, mode)
    render_pass = renderer.GetPass()

    _viewport_for(render_window)._pick_prop_at((WIDTH // 2, HEIGHT // 2, 0))

    assert renderer.GetPass() is render_pass


@pytest.mark.parametrize("mode", list(LIGHTING_PASSES))
def test_repeated_picks_keep_hitting_the_actor(scene, mode):
    renderer, render_window, actor = scene
    _set_lighting_mode(renderer, render_window, mode)
    viewport = _viewport_for(render_window)

    for _ in range(5):
        assert viewport._pick_prop_at((WIDTH // 2, HEIGHT // 2, 0)) is actor
        render_window.Render()


def test_hardware_picking_restores_pass_after_exception(scene):
    renderer, render_window, _ = scene
    _set_lighting_mode(renderer, render_window, "poster")
    render_pass = renderer.GetPass()

    with pytest.raises(RuntimeError):
        with hardware_picking(renderer):
            assert renderer.GetPass() is None
            raise RuntimeError("pick failed")

    assert renderer.GetPass() is render_pass


SAMPLE_PIXELS = [
    (WIDTH // 2, HEIGHT // 2),
    (WIDTH // 2 + 40, HEIGHT // 2 + 25),
    (WIDTH // 2 - 55, HEIGHT // 2 - 30),
    (WIDTH // 2 + 90, HEIGHT // 2 - 80),
    (5, 5),
    (WIDTH - 5, HEIGHT - 5),
]


def _reference_props(renderer):
    """Expected prop per sample pixel, resolved before any snapshot exists."""
    return {pixel: _hardware_pick(renderer, *pixel) for pixel in SAMPLE_PIXELS}


@pytest.mark.parametrize("mode", list(LIGHTING_PASSES))
def test_prop_id_buffer_matches_hardware_pick(scene, mode):
    renderer, render_window, _ = scene
    _set_lighting_mode(renderer, render_window, mode)
    expected = _reference_props(renderer)

    buffer = PropIdBuffer(renderer)
    picked = {pixel: buffer.prop_at(*pixel) for pixel in SAMPLE_PIXELS}

    assert picked == expected
    assert any(prop is not None for prop in expected.values())


def test_prop_id_buffer_answers_every_pixel_from_one_capture(scene):
    renderer, render_window, _ = scene
    buffer = PropIdBuffer(renderer)
    buffer.prop_at(*SAMPLE_PIXELS[0])
    captured = buffer._selector

    for pixel in SAMPLE_PIXELS[1:]:
        buffer.prop_at(*pixel)

    assert buffer._selector is captured


@pytest.mark.parametrize("mode", list(LIGHTING_PASSES))
def test_one_capture_serves_a_whole_drag(scene, mode):
    renderer, render_window, _ = scene
    _set_lighting_mode(renderer, render_window, mode)
    buffer = PropIdBuffer(renderer)
    captures = []
    original = PropIdBuffer._capture

    def counted(self):
        captures.append(1)
        return original(self)

    PropIdBuffer._capture = counted
    try:
        # Every sample of a drag recolors the hit prop and re-renders. The
        # poster and silhouettes passes bump the renderer's MTime per frame,
        # which must not be mistaken for a scene change.
        for _ in range(6):
            prop = buffer.prop_at(WIDTH // 2, HEIGHT // 2)
            if prop is not None:
                prop.GetProperty().SetColor(0.9, 0.3, 0.2)
            render_window.Render()
    finally:
        PropIdBuffer._capture = original

    assert len(captures) == 1


def test_prop_id_buffer_survives_recolor_and_rerender(scene):
    renderer, render_window, actor = scene
    expected = _reference_props(renderer)
    buffer = PropIdBuffer(renderer)
    buffer.prop_at(*SAMPLE_PIXELS[0])
    captured = buffer._selector

    # Selecting a geometry recolors it and re-renders, which happens between
    # every two picks of a drag and must not cost a re-capture.
    actor.GetProperty().SetColor(1.0, 0.0, 0.0)
    render_window.Render()

    assert {pixel: buffer.prop_at(*pixel) for pixel in SAMPLE_PIXELS} == expected
    assert buffer._selector is captured


def test_camera_move_forces_a_recapture(scene):
    renderer, render_window, _ = scene
    buffer = PropIdBuffer(renderer)
    buffer.prop_at(WIDTH // 2, HEIGHT // 2)
    captured = buffer._selector

    renderer.GetActiveCamera().Azimuth(35)
    render_window.Render()
    buffer.prop_at(WIDTH // 2, HEIGHT // 2)

    assert buffer._selector is not captured


def test_invalidate_forces_a_recapture(scene):
    renderer, render_window, _ = scene
    buffer = PropIdBuffer(renderer)
    buffer.prop_at(WIDTH // 2, HEIGHT // 2)
    captured = buffer._selector

    buffer.invalidate()
    buffer.prop_at(WIDTH // 2, HEIGHT // 2)

    assert buffer._selector is not captured


@pytest.mark.parametrize("mode", list(LIGHTING_PASSES))
def test_prop_id_buffer_falls_back_when_capture_fails(scene, mode, monkeypatch):
    renderer, render_window, actor = scene
    _set_lighting_mode(renderer, render_window, mode)
    buffer = PropIdBuffer(renderer)

    def failed_capture(self):
        self._selector = None
        self._state = self._state_key()

    monkeypatch.setattr(PropIdBuffer, "_capture", failed_capture)

    assert buffer.prop_at(WIDTH // 2, HEIGHT // 2) is actor
    assert buffer.prop_at(5, 5) is None


def test_failed_capture_is_not_retried_every_event(scene, monkeypatch):
    renderer, render_window, actor = scene
    buffer = PropIdBuffer(renderer)
    attempts = []

    def failed_capture(self):
        attempts.append(1)
        self._selector = None
        self._state = self._state_key()

    monkeypatch.setattr(PropIdBuffer, "_capture", failed_capture)

    for _ in range(5):
        assert buffer.prop_at(WIDTH // 2, HEIGHT // 2) is actor

    assert len(attempts) == 1


OUTSIDE_PIXELS = [
    (-5, HEIGHT // 2),
    (WIDTH // 2, -5),
    (WIDTH + 10, HEIGHT // 2),
    (WIDTH // 2, HEIGHT + 10),
    (-40, -40),
    (WIDTH, HEIGHT),
]


@pytest.mark.parametrize("pixel", OUTSIDE_PIXELS)
def test_prop_id_buffer_ignores_pixels_outside_the_viewport(scene, pixel):
    renderer, render_window, _ = scene
    buffer = PropIdBuffer(renderer)
    buffer.prop_at(WIDTH // 2, HEIGHT // 2)

    assert buffer.prop_at(*pixel) is None


@pytest.mark.parametrize("pixel", OUTSIDE_PIXELS)
def test_pick_prop_at_ignores_pixels_outside_the_viewport(scene, pixel):
    # Dragging past the edge of the viewport keeps delivering move events
    # while the button is held, with coordinates outside the render window.
    renderer, render_window, _ = scene
    viewport = _viewport_for(render_window)

    assert viewport._pick_prop_at((pixel[0], pixel[1], 0)) is None


def test_viewport_render_invalidates_the_prop_id_buffer(qapp, mock_vtk_widget):
    from mosaic.data import MosaicData

    md = MosaicData(mock_vtk_widget)
    md.viewport._prop_ids = Mock()

    md.viewport.render()

    md.viewport._prop_ids.invalidate.assert_called_once()


def test_viewport_render_vtk_keeps_the_prop_id_buffer(qapp, mock_vtk_widget):
    from mosaic.data import MosaicData

    md = MosaicData(mock_vtk_widget)
    md.viewport._prop_ids = Mock()

    md.viewport.render_vtk()

    md.viewport._prop_ids.invalidate.assert_not_called()
