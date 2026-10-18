from unittest.mock import Mock

import pytest
import vtk

from mosaic.animation.animations import VolumeAnimation


class _Viewer:
    def __init__(self):
        self.slice = vtk.vtkActor()
        self.is_visible = True
        self.orientation_selector = Mock()
        self.orientation_selector.currentText.return_value = "Z"
        self.project_selector = Mock()
        self._rendering_suspended = False
        self.slices = []

    def get_dimensions(self):
        return (10, 10, 10)

    def get_orientation(self):
        return "Z"

    def get_projection(self):
        return "Off"

    def set_slice(self, n):
        self.slices.append(n)


def _track(viewer, start, **params):
    anim = VolumeAnimation(
        vtk_widget=None,
        cdata=None,
        volume_viewer=Mock(primary=viewer),
        global_start_frame=start,
    )
    anim.update_parameters(**params)
    return anim


def _render(tracks, frame):
    for t in tracks:
        t.reset()
    for t in tracks:
        t.update(frame)
    for t in tracks:
        t.commit()


@pytest.fixture(autouse=True)
def _clear_state():
    VolumeAnimation._claims.clear()
    VolumeAnimation._original_visibility.clear()
    yield
    VolumeAnimation._claims.clear()
    VolumeAnimation._original_visibility.clear()


def test_finished_track_does_not_fight_later_track():
    viewer = _Viewer()
    first = _track(viewer, start=0)
    second = _track(viewer, start=30, direction="backward")

    _render([first, second], 35)
    assert viewer.slices == [5]


def test_latest_start_wins_regardless_of_track_order():
    viewer = _Viewer()
    later = _track(viewer, start=30)
    earlier = _track(viewer, start=0)

    _render([later, earlier], 32)
    assert viewer.slices == [2]


def test_hide_restores_visibility_when_scrubbing_back():
    viewer = _Viewer()
    track = _track(viewer, start=10, hide="True")

    _render([track], 12)
    assert not viewer.slice.GetVisibility()
    _render([track], 0)
    assert viewer.slice.GetVisibility()


def test_hidden_volume_is_not_recorded_as_original():
    viewer = _Viewer()
    hider = _track(viewer, start=0, hide="True")
    shower = _track(viewer, start=20)

    _render([hider, shower], 5)
    _render([hider, shower], 25)
    assert viewer.slice.GetVisibility()
