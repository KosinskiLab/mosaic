from unittest.mock import Mock

import pytest

from mosaic.animation.animations import TrajectoryAnimation


class _Trajectory:
    uuid = "traj"
    frames = 10

    def __init__(self):
        self.current_frame = None
        self.shown = []

    def display_frame(self, idx):
        self.shown.append(idx)
        self.current_frame = idx
        return True


def _track(trajectory, start=0, selected=()):
    models = Mock()
    models._get_selected_uuids.return_value = list(selected)
    cdata = Mock(models=models)
    cdata.format_datalist.return_value = []

    anim = TrajectoryAnimation(
        vtk_widget=None, cdata=cdata, volume_viewer=None, global_start_frame=start
    )
    anim._trajectory = trajectory
    anim.update_parameters(data_start=0, data_stop=10)
    return anim, models


def _render(tracks, frame):
    for t in tracks:
        t.reset()
    for t in tracks:
        t.update(frame)
    for t in tracks:
        t.commit()


@pytest.fixture(autouse=True)
def _clear_claims():
    TrajectoryAnimation._claims.clear()
    yield
    TrajectoryAnimation._claims.clear()


def test_before_start_shows_first_frame():
    trajectory = _Trajectory()
    track, _ = _track(trajectory, start=5)

    _render([track], 8)
    _render([track], 0)
    assert trajectory.current_frame == 0


def test_after_end_holds_last_frame():
    trajectory = _Trajectory()
    track, _ = _track(trajectory, start=0)

    _render([track], 2)
    _render([track], 50)
    assert trajectory.current_frame == 9


def test_latest_started_track_drives_trajectory():
    trajectory = _Trajectory()
    first, _ = _track(trajectory, start=0)
    second, _ = _track(trajectory, start=20)

    _render([second, first], 3)
    assert trajectory.current_frame == 3
    _render([second, first], 22)
    assert trajectory.current_frame == 2


def test_earliest_track_fills_before_any_start():
    trajectory = _Trajectory()
    late, _ = _track(trajectory, start=20)
    early, _ = _track(trajectory, start=10)
    early.update_parameters(data_start=4, data_stop=10)

    _render([late, early], 0)
    assert trajectory.current_frame == 4


def test_unchanged_frame_is_not_redisplayed():
    trajectory = _Trajectory()
    track, _ = _track(trajectory, start=0)

    _render([track], 50)
    _render([track], 60)
    assert trajectory.shown == [9]


@pytest.mark.parametrize("selected", [["other"], ["traj", "other"]])
def test_update_never_renders_through_interactor(selected):
    track, models = _track(_Trajectory(), selected=selected)
    _render([track], 3)
    models.set_selection_by_uuid.assert_not_called()
    models.render_vtk.assert_not_called()


def test_highlight_restored_only_when_trajectory_selected():
    track, models = _track(_Trajectory(), selected=["other"])
    _render([track], 3)
    models.container.highlight.assert_not_called()

    TrajectoryAnimation._claims.clear()
    track, models = _track(_Trajectory(), selected=["traj", "other"])
    _render([track], 3)
    models.container.highlight.assert_called_once_with(["traj", "other"])
