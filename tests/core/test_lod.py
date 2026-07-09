"""Unit tests for the pure LOD index helpers in mosaic.lod."""

import numpy as np

from mosaic import lod


def test_merge_lod_indices_offsets_each_input():
    merged = lod.merge_lod_indices(
        [np.array([0, 2]), np.array([1, 3])],
        counts=[5, 6],
        budget=100,
    )
    # Second input's indices are shifted by the first input's point count (5).
    assert merged.tolist() == [0, 2, 6, 8]


def test_merge_lod_indices_returns_none_when_any_input_lacks_lod():
    merged = lod.merge_lod_indices(
        [np.array([0, 1]), None],
        counts=[4, 4],
        budget=100,
    )
    assert merged is None


def test_merge_lod_indices_trims_to_budget_and_sorts():
    merged = lod.merge_lod_indices(
        [np.arange(10), np.arange(10)],
        counts=[10, 10],
        budget=5,
    )
    assert len(merged) == 5
    assert np.all(np.diff(merged) > 0)  # sorted, unique
    assert int(merged.max()) < 20  # all indices valid in merged space
