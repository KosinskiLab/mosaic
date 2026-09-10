"""Sculpt records carry both endpoints so STACK can both undo and redo."""

import numpy as np
import pytest

from mosaic.sculpt.session import (
    PositionRecord,
    SculptSession,
    SculptTarget,
    SnapshotRecord,
)


def _flat_grid():
    n = 4
    xs, ys = np.meshgrid(np.linspace(0, 1, n), np.linspace(0, 1, n))
    vs = np.stack([xs.ravel(), ys.ravel(), np.zeros(n * n)], axis=1).astype(np.float64)
    fs = []
    for j in range(n - 1):
        for i in range(n - 1):
            a = j * n + i
            b = a + 1
            c = a + n
            d = c + 1
            fs.append([a, b, d])
            fs.append([a, d, c])
    return vs, np.asarray(fs, dtype=np.int64)


def test_commit_stroke_returns_record_with_both_endpoints():
    vs, fs = _flat_grid()
    session = SculptSession(SculptTarget(vs.copy(), fs))
    session.begin_stroke()
    session.target.vs[0, 2] = 1.0
    record = session.commit_stroke()
    assert isinstance(record, PositionRecord)
    assert record.indices.tolist() == [0]
    np.testing.assert_allclose(record.before_positions[0], vs[0])
    np.testing.assert_allclose(record.after_positions[0, 2], 1.0)


def test_apply_topology_change_returns_record_with_both_endpoints():
    vs, fs = _flat_grid()
    session = SculptSession(SculptTarget(vs.copy(), fs))
    new_vs = vs.copy()
    new_vs[0, 2] = 2.0
    new_fs = fs.copy()
    record = session.apply_topology_change(new_vs, new_fs)
    assert isinstance(record, SnapshotRecord)
    np.testing.assert_allclose(record.before_vs[0, 2], 0.0)
    np.testing.assert_allclose(record.after_vs[0, 2], 2.0)
