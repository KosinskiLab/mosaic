from types import SimpleNamespace

import numpy as np
import pytest
from qtpy.QtCore import QPoint, Qt
from qtpy.QtTest import QTest

from mosaic.animation.animations import VisibilityAnimation
from mosaic.animation.timeline import TimelineContent
from mosaic.geometry import Geometry


class _Data:
    def __init__(self, geometries):
        self.geometries = geometries

    def format_datalist(self, data_type):
        if data_type != "data":
            return []
        return [(f"obj{i}", g) for i, g in enumerate(self.geometries)]


def _geometry(opacity=1.0, visible=True):
    geometry = Geometry(points=np.random.default_rng(0).random((10, 3)))
    geometry.actor.GetProperty().SetOpacity(opacity)
    geometry.set_visibility(visible)
    return geometry


def _track(cdata, geometries, start=0, duration=10, **params):
    anim = VisibilityAnimation(
        vtk_widget=None, cdata=cdata, volume_viewer=None, global_start_frame=start
    )
    anim.update_parameters(selected_objects=[id(g) for g in geometries], **params)
    anim.set_duration(duration)
    return anim


def _render(tracks, frame):
    for t in tracks:
        t.reset()
    for t in tracks:
        t.update(frame)
    for t in tracks:
        t.commit()


@pytest.fixture(autouse=True)
def _clear_ledger():
    VisibilityAnimation._ledger.clear()
    yield
    VisibilityAnimation._ledger.clear()


def test_hidden_objects_are_switched_off_not_transparent():
    geometry = _geometry(opacity=0.4)
    track = _track(_Data([geometry]), [geometry], start=5, duration=10)

    _render([track], 7)
    assert not geometry.actor.GetVisibility()
    assert geometry.actor.GetProperty().GetOpacity() == pytest.approx(0.4)


def test_track_restores_objects_after_its_end():
    geometry = _geometry(opacity=0.4)
    track = _track(_Data([geometry]), [geometry], start=5, duration=10)

    for frame in (4, 15, 40):
        _render([track], 7)
        _render([track], frame)
        assert geometry.actor.GetVisibility()
        assert geometry.actor.GetProperty().GetOpacity() == pytest.approx(0.4)


def test_fade_scales_each_objects_own_opacity():
    geometry = _geometry(opacity=0.4)
    track = _track(_Data([geometry]), [geometry], duration=20, target_opacity=0.5)

    _render([track], 3)
    assert geometry.actor.GetVisibility()
    assert geometry.actor.GetProperty().GetOpacity() == pytest.approx(0.2)


def test_instant_easing_switches_at_track_edges():
    geometry = _geometry()
    track = _track(_Data([geometry]), [geometry], duration=20)

    _render([track], 0)
    assert not geometry.actor.GetVisibility()
    _render([track], 19)
    assert not geometry.actor.GetVisibility()
    _render([track], 20)
    assert geometry.actor.GetVisibility()


def test_eased_fade_moves_from_start_to_target_across_track():
    geometry = _geometry(opacity=0.8)
    track = _track(
        _Data([geometry]),
        [geometry],
        duration=11,
        start_opacity=0.0,
        target_opacity=1.0,
        easing="linear",
    )
    opacity = geometry.actor.GetProperty().GetOpacity

    _render([track], 0)
    assert not geometry.actor.GetVisibility()
    _render([track], 5)
    assert geometry.actor.GetVisibility()
    assert opacity() == pytest.approx(0.4)
    _render([track], 10)
    assert opacity() == pytest.approx(0.8)


def test_instant_easing_ignores_start_opacity():
    geometry = _geometry()
    track = _track(
        _Data([geometry]),
        [geometry],
        duration=10,
        start_opacity=1.0,
        target_opacity=0.5,
    )

    _render([track], 0)
    assert geometry.actor.GetProperty().GetOpacity() == pytest.approx(0.5)


def test_user_hidden_objects_are_left_alone():
    shown, hidden = _geometry(), _geometry(visible=False)
    track = _track(_Data([shown, hidden]), [shown, hidden], duration=10)

    _render([track], 2)
    _render([track], 20)
    assert shown.actor.GetVisibility()
    assert not hidden.actor.GetVisibility()


def test_later_started_track_overrides_earlier_one():
    geometry = _geometry(opacity=0.8)
    cdata = _Data([geometry])
    hide = _track(cdata, [geometry], start=0, duration=30, target_opacity=0.0)
    reveal = _track(cdata, [geometry], start=10, duration=5, target_opacity=0.5)

    _render([reveal, hide], 12)
    assert geometry.actor.GetVisibility()
    assert geometry.actor.GetProperty().GetOpacity() == pytest.approx(0.4)

    _render([reveal, hide], 20)
    assert not geometry.actor.GetVisibility()

    _render([reveal, hide], 40)
    assert geometry.actor.GetVisibility()
    assert geometry.actor.GetProperty().GetOpacity() == pytest.approx(0.8)


def test_later_track_only_overrides_its_own_objects():
    a, b = _geometry(), _geometry()
    cdata = _Data([a, b])
    hide = _track(cdata, [a, b], start=0, duration=30)
    reveal = _track(cdata, [a], start=10, duration=5, target_opacity=1.0)

    _render([hide, reveal], 12)
    assert a.actor.GetVisibility()
    assert not b.actor.GetVisibility()


def test_same_start_goes_to_later_track():
    geometry = _geometry()
    cdata = _Data([geometry])
    first = _track(cdata, [geometry], start=0, duration=10, target_opacity=0.0)
    second = _track(cdata, [geometry], start=0, duration=10, target_opacity=0.5)

    _render([first, second], 3)
    assert geometry.actor.GetProperty().GetOpacity() == pytest.approx(0.5)


def test_constant_frames_do_not_modify_actor():
    geometry = _geometry()
    track = _track(_Data([geometry]), [geometry], duration=50)

    _render([track], 2)
    mtimes = geometry.actor.GetMTime(), geometry.actor.GetProperty().GetMTime()
    _render([track], 3)
    assert (geometry.actor.GetMTime(), geometry.actor.GetProperty().GetMTime()) == (
        mtimes
    )


def test_deselected_objects_are_restored():
    a, b = _geometry(), _geometry()
    track = _track(_Data([a, b]), [a, b], duration=10)

    _render([track], 2)
    track.update_parameters(selected_objects=[id(a)])
    _render([track], 2)
    assert not a.actor.GetVisibility()
    assert b.actor.GetVisibility()


def test_visibility_duration_ignores_rate():
    track = _track(_Data([]), [], duration=10)
    track.set_duration(37)
    assert track.duration == 37
    assert track.rate == 1.0


@pytest.fixture
def timeline(qapp):
    anim = SimpleNamespace(global_start_frame=10, duration=50, enabled=True, name="t")
    content = TimelineContent()
    content.resize(600, 200)
    content.set_tracks([SimpleNamespace(id="a", animation=anim, color="#888888")])
    content.view_start_frame, content.view_end_frame = 0, 100
    return content


def test_dragging_track_edge_emits_resize(timeline):
    resized, moved = [], []
    timeline.trackResized.connect(lambda tid, d: resized.append((tid, d)))
    timeline.trackMoved.connect(lambda tid, f: moved.append((tid, f)))

    y = timeline.ruler_height + 20
    edge = int(timeline.frame_to_x(60))
    QTest.mousePress(timeline, Qt.MouseButton.LeftButton, pos=QPoint(edge, y))
    QTest.mouseMove(timeline, QPoint(int(timeline.frame_to_x(80)), y))
    QTest.mouseRelease(
        timeline, Qt.MouseButton.LeftButton, pos=QPoint(int(timeline.frame_to_x(80)), y)
    )

    assert resized and resized[-1] == ("a", 70)
    assert not moved


def test_dragging_track_body_still_moves(timeline):
    resized, moved = [], []
    timeline.trackResized.connect(lambda tid, d: resized.append((tid, d)))
    timeline.trackMoved.connect(lambda tid, f: moved.append((tid, f)))

    y = timeline.ruler_height + 20
    QTest.mousePress(
        timeline, Qt.MouseButton.LeftButton, pos=QPoint(int(timeline.frame_to_x(30)), y)
    )
    QTest.mouseMove(timeline, QPoint(int(timeline.frame_to_x(40)), y))

    assert moved and moved[-1] == ("a", 20)
    assert not resized


def test_settings_scroll_instead_of_squeezing_timeline(qapp):
    from mosaic.animation.compose import AnimationComposerDialog

    dialog = AnimationComposerDialog(vtk_widget=None, cdata=_Data([]))
    dialog.resize(300, 500)
    dialog.show()
    qapp.processEvents()

    assert dialog.timeline.height() >= dialog.timeline.minimumHeight() >= 220
    dialog.close()


def test_click_without_moving_does_not_shift_track(timeline):
    moved = []
    timeline.trackMoved.connect(lambda tid, f: moved.append((tid, f)))

    y = timeline.ruler_height + 20
    x = int(timeline.frame_to_x(30))
    QTest.mousePress(timeline, Qt.MouseButton.LeftButton, pos=QPoint(x, y))
    QTest.mouseMove(timeline, QPoint(x + 1, y))
    QTest.mouseRelease(timeline, Qt.MouseButton.LeftButton, pos=QPoint(x + 1, y))

    assert not moved
