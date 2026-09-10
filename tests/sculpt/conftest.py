"""Synthetic mesh fixtures for sculpt unit tests."""

import numpy as np
import pytest


def _grid_mesh(n: int = 5, side: float = 1.0):
    xs, ys = np.meshgrid(np.linspace(0, side, n), np.linspace(0, side, n))
    vs = np.stack([xs.ravel(), ys.ravel(), np.zeros(n * n)], axis=1).astype(np.float64)
    fs = []
    for i in range(n - 1):
        for j in range(n - 1):
            a = i * n + j
            b = i * n + j + 1
            c = (i + 1) * n + j
            d = (i + 1) * n + j + 1
            fs.append([a, b, d])
            fs.append([a, d, c])
    return vs, np.asarray(fs, dtype=np.int64)


@pytest.fixture
def flat_grid_mesh():
    """A 5x5 flat triangulated grid on z=0 in [0,1]^2."""
    return _grid_mesh()


@pytest.fixture
def perturbed_grid_mesh():
    """Flat grid with one interior vertex pulled up along z."""
    vs, fs = _grid_mesh()
    interior_id = 12  # center of a 5x5 grid
    vs = vs.copy()
    vs[interior_id, 2] = 0.4
    return vs, fs, interior_id


@pytest.fixture
def punched_grid_mesh():
    """5x5 grid with the four central faces removed, leaving a square hole."""
    vs, fs = _grid_mesh()
    # Remove the four faces surrounding the center vertex (id 12 on 5x5).
    remove = {12, 13, 18, 19, 20, 21, 26, 27}
    keep = [i for i, tri in enumerate(fs) if not (set(tri.tolist()) & remove)]
    return vs, fs[keep]
