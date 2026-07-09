"""
REPL apply() places through the shared chokepoint and records on the stack.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np

from mosaic.commands.session import Session
from mosaic.undo import STACK


def _session_with_cloud(n=20):
    s = Session(quiet=True)
    pts = np.random.default_rng(0).uniform(0, 1, size=(n, 3)).astype(np.float64)
    s._data.add(pts)
    return s, list(s._data.data)[0]


def test_apply_persists_results_and_tracks_last():
    """Persisted apply adds to a container, records on the undo stack, and is reversible."""
    STACK.clear()
    s, cloud = _session_with_cloud()
    created = s.apply("compute_normals", [cloud], method="remove", workers=1)

    assert created
    assert s.resolve("@last") == created
    assert any(g is created[0] for g in list(s._data.data) + list(s._models.data))

    result_uuid = created[0].uuid
    STACK.undo()
    assert s._data.get(result_uuid) is None
    STACK.clear()


def test_apply_transient_does_not_persist():
    """Transient apply keeps results only in _last_results, not containers."""
    STACK.clear()
    s, cloud = _session_with_cloud()
    created = s.apply(
        "compute_normals", [cloud], method="remove", persist=False, workers=1
    )

    assert created
    assert s.resolve("@last") == created
    assert all(g is not created[0] for g in list(s._data.data) + list(s._models.data))
    STACK.clear()
