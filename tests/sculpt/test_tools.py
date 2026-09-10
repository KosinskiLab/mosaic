"""Tests for the pure brush-query and tool ops in :mod:`mosaic.sculpt.tools`."""

import numpy as np

from mosaic.sculpt.tools import (
    ActiveSet,
    brush_query,
    build_adjacency,
    compute_boundary_mask,
    grab_apply,
    patch_touched_loops,
    smooth_stamp,
    wendland,
)


def test_wendland_zero_at_origin_one_at_boundary():
    t = np.linspace(0.0, 1.0, 11)
    w = wendland(t)
    assert w[0] == 1.0
    assert w[-1] == 0.0
    assert np.all(w >= 0.0)
    assert np.all(np.diff(w) <= 1e-9), "wendland must be monotonically decreasing"


def test_wendland_zero_beyond_one():
    t = np.array([1.2, 2.0, 10.0])
    assert np.all(wendland(t) == 0.0)


def test_brush_query_hits_only_within_radius(flat_grid_mesh):
    vs, _ = flat_grid_mesh
    hit = np.array([0.5, 0.5, 0.0], dtype=np.float64)
    active = brush_query(vs, hit_point=hit, radius=0.3)
    assert active.indices.size > 0
    d = np.linalg.norm(vs[active.indices] - hit, axis=1)
    assert np.all(d < 0.3)


def test_brush_query_empty_when_outside(flat_grid_mesh):
    vs, _ = flat_grid_mesh
    active = brush_query(vs, hit_point=np.array([10.0, 10.0, 10.0]), radius=0.5)
    assert active.indices.size == 0
    assert active.weights.size == 0


def test_brush_query_back_face_culling_drops_far_side(flat_grid_mesh):
    vs, _ = flat_grid_mesh
    normals = np.tile([0.0, 0.0, -1.0], (len(vs), 1))
    cam = np.array([0.5, 0.5, 5.0])
    hit = np.array([0.5, 0.5, 0.0], dtype=np.float64)
    active = brush_query(
        vs,
        hit_point=hit,
        radius=0.5,
        vertex_normals=normals,
        camera_position=cam,
    )
    assert active.indices.size == 0


def test_grab_apply_displaces_locked_only(flat_grid_mesh):
    vs, _ = flat_grid_mesh
    vs = vs.copy()
    locked = np.array([0, 5, 10], dtype=np.int64)
    weights = np.array([1.0, 0.5, 0.25])
    rest = vs[locked].copy()
    grab_apply(vs, locked, weights, rest, np.array([0.0, 0.0, 1.0]), strength=1.0)
    assert np.allclose(vs[locked, 2], [1.0, 0.5, 0.25])
    mask = np.ones(len(vs), dtype=bool)
    mask[locked] = False
    assert np.all(vs[mask, 2] == 0.0)


def test_grab_apply_idempotent(flat_grid_mesh):
    vs, _ = flat_grid_mesh
    vs = vs.copy()
    locked = np.array([12], dtype=np.int64)
    weights = np.array([1.0])
    rest = vs[locked].copy()
    grab_apply(vs, locked, weights, rest, np.array([0.0, 0.0, 0.7]))
    snapshot = vs.copy()
    grab_apply(vs, locked, weights, rest, np.array([0.0, 0.0, 0.7]))
    assert np.allclose(vs, snapshot)


def test_smooth_stamp_pulls_perturbed_vertex_toward_neighbour_mean(perturbed_grid_mesh):
    vs, fs, interior = perturbed_grid_mesh
    vs = vs.copy()
    z_before = vs[interior, 2]
    adj = build_adjacency(fs, len(vs))
    smooth_stamp(
        vs,
        adj,
        indices=np.array([interior], dtype=np.int64),
        weights=np.array([1.0]),
        strength=0.5,
    )
    z_after = vs[interior, 2]
    assert 0 < z_after < z_before


def test_smooth_stamp_zero_strength_is_noop(perturbed_grid_mesh):
    vs, fs, _ = perturbed_grid_mesh
    snapshot = vs.copy()
    adj = build_adjacency(fs, len(vs))
    smooth_stamp(
        vs,
        adj,
        indices=np.arange(len(vs)),
        weights=np.ones(len(vs)),
        strength=0.0,
    )
    assert np.array_equal(vs, snapshot)


def test_smooth_stamp_empty_active_is_noop(flat_grid_mesh):
    vs, fs = flat_grid_mesh
    snapshot = vs.copy()
    adj = build_adjacency(fs, len(vs))
    smooth_stamp(
        vs,
        adj,
        indices=np.empty(0, dtype=np.int64),
        weights=np.empty(0),
        strength=0.5,
    )
    assert np.array_equal(vs, snapshot)


def test_compute_boundary_mask_flat_grid_outer_ring(flat_grid_mesh):
    vs, fs = flat_grid_mesh
    mask = compute_boundary_mask(fs, len(vs))
    # 5x5 grid: 4 corners + 4 edges of 3 inner vertices each = 16 boundary verts.
    assert mask.sum() == 16
    # Centre vertex is interior.
    assert not mask[12]


def test_compute_boundary_mask_closed_mesh_has_no_boundary():
    vs = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    fs = np.array([[0, 1, 2], [0, 2, 3], [0, 3, 1], [1, 3, 2]], dtype=np.int64)
    mask = compute_boundary_mask(fs, len(vs))
    assert not mask.any()


def test_compute_boundary_mask_punched_grid_has_inner_loop(punched_grid_mesh):
    vs, fs = punched_grid_mesh
    mask = compute_boundary_mask(fs, len(vs))
    # Punched grid has the original 16 outer boundary + new hole boundary verts.
    assert mask.sum() > 16


def test_patch_touched_loops_closes_inner_hole(punched_grid_mesh):
    vs, fs = punched_grid_mesh
    mask = compute_boundary_mask(fs, len(vs))
    # Only painting the inner hole boundary, not the outer rim.
    interior_boundary = np.where(mask)[0]
    # Pick a vertex near the centre that is on a boundary (must be the hole).
    centres = vs[interior_boundary]
    dist = np.linalg.norm(centres - np.array([0.5, 0.5, 0.0]), axis=1)
    near_hole = interior_boundary[dist < 0.4]
    assert len(near_hole) > 0
    result = patch_touched_loops(vs, fs, near_hole)
    assert result is not None
    _, new_fs = result
    assert len(new_fs) > len(fs)


def test_patch_touched_loops_returns_none_for_empty_input(flat_grid_mesh):
    vs, fs = flat_grid_mesh
    assert patch_touched_loops(vs, fs, np.empty(0, dtype=np.int64)) is None


def test_patch_touched_loops_returns_none_if_no_loop_touched(punched_grid_mesh):
    vs, fs = punched_grid_mesh
    # Pick an interior vertex (not on any boundary).
    mask = compute_boundary_mask(fs, len(vs))
    interior = np.where(~mask)[0]
    assert len(interior) > 0
    # patch_touched_loops should reject because none of these are on a boundary.
    assert patch_touched_loops(vs, fs, interior[:1]) is None


def _grid_with_two_holes():
    """9x9 flat grid with two 2x2-cell interior holes, well separated."""
    n = 9
    xs, ys = np.meshgrid(np.linspace(0, 1, n), np.linspace(0, 1, n))
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
    fs = np.asarray(fs, dtype=np.int64)

    def cell_face_ids(i: int, j: int) -> tuple:
        base = 2 * (i * (n - 1) + j)
        return base, base + 1

    hole_a_cells = [(i, j) for i in (2, 3) for j in (2, 3)]
    hole_b_cells = [(i, j) for i in (5, 6) for j in (5, 6)]
    remove_face_ids = set()
    for i, j in hole_a_cells + hole_b_cells:
        remove_face_ids.update(cell_face_ids(i, j))
    keep = [k for k in range(len(fs)) if k not in remove_face_ids]
    return vs, fs[keep]


def test_patch_touched_loops_closes_only_most_painted_loop():
    """When a stroke touches two boundary loops, close only the one with
    the most painted vertices, not both."""
    import igl

    vs, fs = _grid_with_two_holes()
    n_loops_before = len(igl.boundary_loop_all(fs))
    assert n_loops_before == 3  # outer rim + 2 interior holes

    mask = compute_boundary_mask(fs, len(vs))
    boundary_ids = np.where(mask)[0]
    near_a = boundary_ids[
        np.linalg.norm(vs[boundary_ids] - [3 / 8, 3 / 8, 0], axis=1) < 0.2
    ]
    near_b = boundary_ids[
        np.linalg.norm(vs[boundary_ids] - [5 / 8, 5 / 8, 0], axis=1) < 0.2
    ]
    assert len(near_a) >= 3 and len(near_b) >= 3
    # Paint the entire rim of hole A, but only one vertex of hole B.
    painted = np.concatenate([near_a, near_b[:1]])

    result = patch_touched_loops(vs, fs, painted)
    assert result is not None
    _, new_fs = result
    n_loops_after = len(igl.boundary_loop_all(new_fs))
    assert n_loops_after == n_loops_before - 1, (
        "exactly one hole should close (the heavily painted one), "
        f"got loops before={n_loops_before} after={n_loops_after}"
    )


def test_active_set_empty():
    empty = ActiveSet.empty()
    assert empty.indices.size == 0
    assert empty.weights.size == 0
