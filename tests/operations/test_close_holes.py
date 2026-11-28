import numpy as np

from mosaic.meshing.repair import close_holes


def _grid_with_holes(n, holes):
    xs, ys = np.meshgrid(np.arange(n), np.arange(n))
    vs = np.stack([xs.ravel(), ys.ravel(), np.zeros(n * n)], axis=1).astype(float)
    fs = []
    for i in range(n - 1):
        for j in range(n - 1):
            if (i, j) in holes:
                continue
            a, b, c, d = i * n + j, i * n + j + 1, (i + 1) * n + j, (i + 1) * n + j + 1
            fs += [[a, b, d], [a, d, c]]
    return vs, np.array(fs)


def _open_edges(fs):
    edges = np.sort(
        np.concatenate([fs[:, [0, 1]], fs[:, [1, 2]], fs[:, [2, 0]]]), axis=1
    )
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return int((counts == 1).sum())


def test_fills_holes_touching_at_a_vertex():
    vs, fs = _grid_with_holes(6, {(1, 1), (2, 2)})
    filled = close_holes(vs, fs, 10)
    assert _open_edges(filled) == 4 * 5


def test_fills_hole_next_to_flipped_face():
    vs, fs = _grid_with_holes(6, {(2, 2)})
    touching = np.flatnonzero(np.isin(fs, [14, 15]).sum(axis=1) == 2)[0]
    fs[touching] = fs[touching][::-1]
    filled = close_holes(vs, fs, 10)
    assert _open_edges(filled) == 4 * 5


def test_keeps_majority_orientation():
    vs, fs = _grid_with_holes(6, {(2, 2)})
    fs[0] = fs[0][::-1]
    filled = close_holes(vs, fs, 10)
    np.testing.assert_array_equal(filled[1 : len(fs)], fs[1:])


def _mobius(n, w):
    t, s = np.meshgrid(
        np.linspace(0, 2 * np.pi, n, endpoint=False), np.linspace(-1, 1, w + 1)
    )
    r = 3 + s.T * np.cos(t.T / 2)
    vs = np.stack([r * np.cos(t.T), r * np.sin(t.T), s.T * np.sin(t.T / 2)], -1)
    fs = []
    for i in range(n):
        for j in range(w):
            a, b = i * (w + 1) + j, i * (w + 1) + j + 1
            if i == n - 1:
                c, d = w - j, w - j - 1
            else:
                c, d = a + w + 1, b + w + 1
            fs += [[a, c, b], [b, c, d]]
    return vs.reshape(-1, 3), np.array(fs)


def _orientation_conflicts(fs):
    directed = np.concatenate([fs[:, [0, 1]], fs[:, [1, 2]], fs[:, [2, 0]]])
    return len(directed) - len(np.unique(directed, axis=0))


def test_does_not_add_orientation_conflicts_to_non_orientable_surface():
    vs, fs = _mobius(60, 4)
    filled = close_holes(vs, fs, 1)
    assert _orientation_conflicts(filled) <= _orientation_conflicts(fs)


def test_accepts_mesh_without_faces():
    filled = close_holes(np.zeros((3, 3)), np.zeros((0, 3), dtype=int), 10)
    assert len(filled) == 0


def test_fill_does_not_reuse_existing_edges():
    vs, fs = _grid_with_holes(6, {(1, 2), (2, 1)})
    filled = close_holes(vs, fs, 10)
    edges = np.sort(
        np.concatenate([filled[:, [0, 1]], filled[:, [1, 2]], filled[:, [2, 0]]]),
        axis=1,
    )
    _, counts = np.unique(edges, axis=0, return_counts=True)
    assert counts.max() <= 2
