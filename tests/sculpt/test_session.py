"""SculptSession and SculptTarget lifecycle tests."""

import numpy as np
import pytest

from mosaic.sculpt.session import (
    PositionRecord,
    SculptSession,
    SculptTarget,
    SnapshotRecord,
)
from mosaic.sculpt.tools import smooth_stamp
from mosaic.undo import STACK


@pytest.fixture(autouse=True)
def _reset_stack():
    STACK.clear()
    yield
    STACK.clear()


def _new_session(vs, fs):
    target = SculptTarget(vs=vs, fs=fs)
    return target, SculptSession(target)


def test_target_exposes_adjacency_and_normals(flat_grid_mesh):
    vs, fs = flat_grid_mesh
    target = SculptTarget(vs=vs, fs=fs)
    adj = target.adjacency
    assert adj.shape == (len(vs), len(vs))
    normals = target.normals
    assert normals.shape == vs.shape


def test_commit_stroke_records_position_changes(flat_grid_mesh):
    vs, fs = flat_grid_mesh
    target, session = _new_session(vs, fs)
    session.set_tool("smooth")
    session.begin_stroke()
    smooth_stamp(
        target.vs,
        target.adjacency,
        indices=np.array([12], dtype=np.int64),
        weights=np.array([1.0]),
        strength=0.5,
    )
    target.vs[12, 2] += 0.1  # ensure a recordable change
    record = session.commit_stroke()
    assert isinstance(record, PositionRecord)
    assert record.indices.size > 0
    assert hasattr(record, "after_positions")


def test_commit_stroke_no_change_records_nothing(flat_grid_mesh):
    vs, fs = flat_grid_mesh
    _, session = _new_session(vs, fs)
    session.set_tool("smooth")
    session.begin_stroke()
    record = session.commit_stroke()
    assert record is None


def test_cancel_stroke_restores_vs(flat_grid_mesh):
    vs, fs = flat_grid_mesh
    target, session = _new_session(vs, fs)
    before = target.vs.copy()
    session.begin_stroke()
    target.vs[5] += 0.5
    session.cancel_stroke()
    assert np.array_equal(target.vs, before)
    assert not session.in_stroke


def test_grab_state_round_trip(flat_grid_mesh):
    vs, fs = flat_grid_mesh
    target, session = _new_session(vs, fs)
    locked = np.array([12], dtype=np.int64)
    weights = np.array([1.0])
    session.set_tool("grab")
    session.begin_stroke(
        anchor_world=np.array([0.5, 0.5, 0.0]),
        locked_indices=locked,
        locked_weights=weights,
    )
    state = session.grab_state()
    assert state is not None
    idx, w, rest, anchor = state
    assert np.array_equal(idx, locked)
    assert np.array_equal(w, weights)
    assert np.allclose(rest, target.vs[locked])
    assert np.allclose(anchor, [0.5, 0.5, 0.0])


def test_apply_topology_change_records_snapshot(punched_grid_mesh):
    vs, fs = punched_grid_mesh
    target, session = _new_session(vs, fs)
    n_v_before, n_f_before = target.n, len(target.fs)

    extra_vs = np.vstack([target.vs, target.vs.mean(axis=0)[None]])
    extra_fs = np.vstack([target.fs, np.array([[0, 1, n_v_before]], dtype=np.int64)])
    record = session.apply_topology_change(extra_vs, extra_fs)
    assert isinstance(record, SnapshotRecord)
    assert target.n == n_v_before + 1
    assert len(target.fs) == n_f_before + 1
    assert hasattr(record, "after_vs")


def test_in_progress_stroke_cancels_on_topology_change(flat_grid_mesh):
    vs, fs = flat_grid_mesh
    target, session = _new_session(vs, fs)
    before = target.vs.copy()
    session.begin_stroke()
    target.vs[3] += 0.4
    # Topology op should cancel the stroke before applying
    grown_vs = np.vstack([target.vs, np.array([[2.0, 2.0, 0.0]])])
    grown_fs = np.vstack([target.fs, np.array([[0, 1, target.n]], dtype=np.int64)])
    session.apply_topology_change(grown_vs, grown_fs)
    assert not session.in_stroke
    assert target.n == len(before) + 1


def test_stroke_topology_change_raises():
    vs = np.zeros((4, 3), dtype=np.float64)
    fs = np.array([[0, 1, 2]], dtype=np.int64)
    target, session = _new_session(vs, fs)
    session.set_tool("smooth")
    session.begin_stroke()
    target.vs = np.vstack([target.vs, [1.0, 1.0, 1.0]])
    try:
        session.commit_stroke()
    except RuntimeError:
        pass
    else:
        raise AssertionError("strokes must not change topology")
