"""Sculpt brush query and per-tool operations.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

import igl
import numpy as np
from scipy.sparse import csr_matrix

from mosaic.meshing.repair import _close_hole, fair_mesh, triangulation_refine_leipa


__all__ = [
    "ActiveSet",
    "brush_query",
    "build_adjacency",
    "compute_boundary_mask",
    "wendland",
    "grab_apply",
    "smooth_stamp",
    "patch_touched_loops",
]


@dataclass(frozen=True)
class ActiveSet:
    """Vertices the brush touches at the current cursor position.

    ``indices`` are vertex ids; ``weights`` are the matching falloff weights in
    ``[0, 1]``. Empty arrays mean the cursor is off the mesh or outside any
    vertex.
    """

    indices: np.ndarray
    weights: np.ndarray
    hit_point: np.ndarray

    @classmethod
    def empty(cls) -> "ActiveSet":
        return cls(
            indices=np.empty(0, dtype=np.int64),
            weights=np.empty(0, dtype=np.float64),
            hit_point=np.zeros(3, dtype=np.float64),
        )


def wendland(t: np.ndarray) -> np.ndarray:
    """Wendland C2 falloff: ``(1-t)^4 * (1 + 4t)`` on [0,1], zero beyond."""
    out = np.zeros_like(t)
    inside = t < 1.0
    ti = t[inside]
    out[inside] = (1.0 - ti) ** 4 * (1.0 + 4.0 * ti)
    return out


def brush_query(
    vs: np.ndarray,
    hit_point: np.ndarray,
    radius: float,
    vertex_normals: Optional[np.ndarray] = None,
    camera_position: Optional[np.ndarray] = None,
) -> ActiveSet:
    """Return the ActiveSet for ``hit_point`` against ``vs``.

    Pure brute-force radius search via numpy. For typical meshes (<= a few
    hundred thousand vertices) this is <1 ms per call.

    Back-face culling is applied when both ``vertex_normals`` and
    ``camera_position`` are provided: vertices whose outward normal points away
    from the camera are dropped.
    """
    diff = vs - hit_point
    d = np.linalg.norm(diff, axis=1)
    mask = d < radius
    if not mask.any():
        return ActiveSet.empty()

    if vertex_normals is not None and camera_position is not None:
        view = camera_position - vs
        view_norm = np.linalg.norm(view, axis=1, keepdims=True)
        view = view / np.maximum(view_norm, 1e-12)
        front = np.einsum("ij,ij->i", vertex_normals, view) > 0.0
        mask &= front
        if not mask.any():
            return ActiveSet.empty()

    indices = np.nonzero(mask)[0].astype(np.int64, copy=False)
    weights = wendland(d[indices] / radius)
    return ActiveSet(
        indices=indices,
        weights=weights,
        hit_point=np.asarray(hit_point, dtype=np.float64).copy(),
    )


def build_adjacency(fs: np.ndarray, n_vertices: int) -> csr_matrix:
    """Symmetric vertex-vertex adjacency as a binary CSR matrix.

    Used by the Smooth tool for its per-stamp Laplacian step.
    """
    if len(fs) == 0:
        return csr_matrix((n_vertices, n_vertices), dtype=np.float32)
    e_a = fs[:, [0, 1, 2]].ravel()
    e_b = fs[:, [1, 2, 0]].ravel()
    rows = np.concatenate([e_a, e_b])
    cols = np.concatenate([e_b, e_a])
    data = np.ones(rows.size, dtype=np.float32)
    adj = csr_matrix((data, (rows, cols)), shape=(n_vertices, n_vertices))
    adj.sum_duplicates()
    adj.data = np.minimum(adj.data, 1.0)
    return adj


def grab_apply(
    vs: np.ndarray,
    locked_indices: np.ndarray,
    locked_weights: np.ndarray,
    rest_positions: np.ndarray,
    world_delta: np.ndarray,
    strength: float = 1.0,
) -> None:
    """Place locked vertices at ``rest + weight * strength * world_delta`` in place.

    Idempotent: invoking with the same ``world_delta`` is a no-op visually.
    Mutates ``vs``.
    """
    if len(locked_indices) == 0:
        return None
    delta = np.asarray(world_delta, dtype=np.float64).reshape(3) * float(strength)
    vs[locked_indices] = rest_positions + locked_weights[:, None] * delta
    return None


def smooth_stamp(
    vs: np.ndarray,
    adjacency: csr_matrix,
    indices: np.ndarray,
    weights: np.ndarray,
    strength: float,
) -> None:
    """One weighted uniform-Laplacian smoothing step on ``indices``. Mutates ``vs``.

    Per-vertex blend: ``v' = (1 - alpha) * v + alpha * mean(neighbours)``,
    with ``alpha = strength * weight``. ``strength`` should be small (<= 0.5)
    because each stamp is one explicit step; multiple stamps accumulate.

    This is the right operator for a *local* brush: the goal is to blend the
    brushed region with what surrounds it, which is exactly what averaging
    against the 1-ring achieves. Taubin's volume-preservation correction is
    a global property and belongs in a separate global-smooth action, not in
    the brush; its inflate step would push brushed vertices back toward the
    unmoved surroundings and partially re-instate the features being flattened.
    """
    if len(indices) == 0 or strength <= 0.0:
        return None
    sub = adjacency[indices]
    neighbour_sum = sub @ vs
    valence = np.asarray(sub.sum(axis=1)).ravel()
    valence = np.maximum(valence, 1.0)
    neighbour_mean = neighbour_sum / valence[:, None]
    alpha = np.clip(weights * float(strength), 0.0, 1.0).reshape(-1, 1)
    vs[indices] = vs[indices] * (1.0 - alpha) + neighbour_mean * alpha
    return None


def compute_boundary_mask(fs: np.ndarray, n_vertices: int) -> np.ndarray:
    """Per-vertex bool mask: True iff the vertex lies on an open boundary edge.

    Vectorised half-edge counting: an edge appears in exactly one triangle iff
    it is on the boundary of an open mesh. O(M) memory, one ``np.unique`` call.
    """
    mask = np.zeros(int(n_vertices), dtype=bool)
    if len(fs) == 0:
        return mask
    e_a = fs[:, [0, 1, 2]].ravel().astype(np.int64, copy=False)
    e_b = fs[:, [1, 2, 0]].ravel().astype(np.int64, copy=False)
    lo = np.minimum(e_a, e_b)
    hi = np.maximum(e_a, e_b)
    key = lo * np.int64(n_vertices) + hi
    _, inverse, counts = np.unique(key, return_inverse=True, return_counts=True)
    boundary = counts[inverse] == 1
    if not boundary.any():
        return mask
    vs_idx = np.unique(np.concatenate([lo[boundary], hi[boundary]]))
    mask[vs_idx] = True
    return mask


def patch_touched_loops(
    vs: np.ndarray,
    fs: np.ndarray,
    touched_boundary_indices: np.ndarray,
    density_factor: float = float(np.sqrt(2)),
    n_ring: int = 2,
    smoothness: float = 1.0,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Close the boundary loop the user painted most heavily.

    When a Patch stroke crosses vertices from several open boundary loops
    (e.g. two adjacent holes), close only the loop with the most painted
    vertices (assuming that is the one the user meant to patch). Returns
    ``(new_vs, new_fs)`` on success, or ``None`` when no painted vertex
    landed on any boundary loop. Designed to run once at the end of a Patch
    stroke, never mid-stroke.
    """
    touched = {
        int(v) for v in np.asarray(touched_boundary_indices, dtype=np.int64).ravel()
    }
    if not touched:
        return None
    best_loop: Optional[List[int]] = None
    best_overlap = 0
    for loop in igl.boundary_loop_all(fs):
        loop_list = [int(v) for v in loop]
        overlap = sum(1 for v in loop_list if v in touched)
        if overlap > best_overlap:
            best_overlap = overlap
            best_loop = loop_list
    if best_loop is None:
        return None

    out_fs = fs.copy()
    n_orig = len(out_fs)
    out_fs = _close_hole(vs, out_fs, np.asarray(best_loop, dtype=np.int64), fast=True)
    if len(out_fs) == n_orig:
        return None

    hole_fids = np.arange(n_orig, len(out_fs))
    new_vs, new_fs, _ = triangulation_refine_leipa(
        vs, out_fs, hole_fids, density_factor
    )
    new_vids = np.arange(len(vs), len(new_vs))
    if len(new_vids) > 0:
        new_vs = fair_mesh(
            new_vs, new_fs, new_vids, smoothness=smoothness, n_ring=n_ring
        )
    return new_vs, new_fs
