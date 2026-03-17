"""
Utilities for repair of triangular meshes.

Hole filling were adapted from https://github.com/kentechx/hole-filling
and are distributed under MIT license. This origin is indicated as
reference for the respective functions.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import Tuple

import igl
import numpy as np
import scipy.sparse

_epsilon = 1e-16

__all__ = ["fair_mesh", "get_ring_vertices", "close_holes"]


def _close_hole(vs: np.ndarray, fs: np.ndarray, hole_vids, fast=True) -> np.ndarray:
    """Close mesh holes with perimeter length below threshold.

    Parameters
    ----------
    vs : ndarray, shape (N, 3)
        Vertex coordinates.
    fs : ndarray, shape (M, 3)
        Face indices.
    hole_vids : ndarray, shape (K, 3)
        Boundary vertex indices.
    fast : bool, optional
        Whether to use fast hole filling. Default is True.

    Returns
    -------
    ndarray, shape (K, 3)
        Face indices of mesh with holes closed.

    References
    ----------
    .. [1] Code adapted from https://github.com/kentechx/hole-filling
    """

    def hash_func(edges):
        # edges: (n, 2)
        edges = np.core.defchararray.chararray.encode(edges.astype("str"))
        edges = np.concatenate(
            [edges[:, 0:1], np.full_like(edges[:, 0:1], "_", dtype=str), edges[:, 1:2]],
            axis=1,
        )
        edges_hash = np.core.defchararray.add(
            np.core.defchararray.add(edges[:, 0], edges[:, 1]), edges[:, 2]
        )
        return edges_hash

    # create edge hash
    if not fast:
        edges = igl.edges(fs)
        edges_hash = hash_func(edges)

    hole_vids = np.array(hole_vids)
    if len(hole_vids) < 3:
        return fs.copy()

    if len(hole_vids) == 3:
        # fill one triangle
        out_fs = np.concatenate([fs, hole_vids[::-1][None]], axis=0)
        return out_fs

    # heuristically divide the hole
    queue = [hole_vids[::-1]]
    out_fs = []
    while len(queue) > 0:
        cur_vids = queue.pop(0)
        if len(cur_vids) == 3:
            out_fs.append(cur_vids)
            continue

        # current hole
        hole_edge_len = np.linalg.norm(vs[np.roll(cur_vids, -1)] - vs[cur_vids], axis=1)
        hole_len = np.sum(hole_edge_len)
        min_concave_degree = np.inf
        tar_i, tar_j = -1, -1
        for i in range(len(cur_vids)):
            eu_dists = np.linalg.norm(vs[cur_vids[i]] - vs[cur_vids], axis=1)
            if not fast:
                # check if the edge exists
                _edges = np.sort(
                    np.stack([np.tile(cur_vids[i], len(cur_vids)), cur_vids], axis=1),
                    axis=1,
                )
                _edges_hash = hash_func(_edges)
                eu_dists[np.isin(_edges_hash, edges_hash, assume_unique=True)] = np.inf

            geo_dists = np.roll(np.roll(hole_edge_len, -i).cumsum(), i)
            geo_dists = np.roll(np.minimum(geo_dists, hole_len - geo_dists), 1)
            concave_degree = eu_dists / (geo_dists**2 + _epsilon)
            concave_degree[i] = -np.inf  # there may exist two duplicate vertices

            _idx = 1
            j = np.argsort(concave_degree)[_idx]
            while (
                min(
                    (j + len(cur_vids) - i) % len(cur_vids),
                    (i + len(cur_vids) - j) % len(cur_vids),
                )
                <= 1
            ):
                _idx += 1
                j = np.argsort(concave_degree)[_idx]

            if concave_degree[j] < min_concave_degree:
                min_concave_degree = concave_degree[j]
                tar_i, tar_j = min(i, j), max(i, j)

        queue.append(cur_vids[tar_i : tar_j + 1])
        queue.append(np.concatenate([cur_vids[tar_j:], cur_vids[: tar_i + 1]]))

    out_fs = np.concatenate([fs, np.array(out_fs)], axis=0)
    return out_fs


def close_holes(
    vs: np.ndarray, fs: np.ndarray, hole_len_thr: float = 10000.0, fast=True
) -> np.ndarray:
    """Close mesh holes with perimeter length below threshold.

    Parameters
    ----------
    vs : ndarray, shape (N, 3)
        Vertex coordinates.
    fs : ndarray, shape (M, 3)
        Face indices.
    hole_len_thr : float, optional
        Maximum perimeter length of holes to close. Default is 10000.0.
    fast : bool, optional
        Whether to use fast hole filling. Default is True.

    Returns
    -------
    ndarray, shape (K, 3)
        Face indices of mesh with holes closed.

    References
    ----------
    .. [1] Code adapted from https://github.com/kentechx/hole-filling
    """
    out_fs = fs.copy()
    while True:
        b = igl.boundary_loop(out_fs)
        if len(b) < 3:
            break
        hole_edge_len = np.linalg.norm(vs[np.roll(b, -1)] - vs[b], axis=1).sum()
        if hole_len_thr >= 0 and hole_edge_len > hole_len_thr:
            break
        out_fs = _close_hole(vs, out_fs, b, fast)

    return out_fs


def get_mollified_edge_length(
    vs: np.ndarray, fs: np.ndarray, mollify_factor=1e-5
) -> np.ndarray:
    """Calculate mollified edge lengths of mesh faces.

    Parameters
    ----------
    vs : ndarray, shape (N, 3)
        Vertex coordinates.
    fs : ndarray, shape (M, 3)
        Face indices.
    mollify_factor : float, optional
        Factor controlling edge length smoothing. Default is 1e-5.

    Returns
    -------
    ndarray, shape (M, 3)
        Mollified edge lengths for each face triangle.

    References
    ----------
    .. [1] Code adapted from https://github.com/kentechx/hole-filling
    """
    lin = igl.edge_lengths(vs, fs)
    if mollify_factor == 0:
        return lin
    delta = mollify_factor * np.mean(lin)
    eps = np.maximum(0, delta - lin[:, 0] - lin[:, 1] + lin[:, 2])
    eps = np.maximum(eps, delta - lin[:, 0] - lin[:, 2] + lin[:, 1])
    eps = np.maximum(eps, delta - lin[:, 1] - lin[:, 2] + lin[:, 0])
    eps = eps.max()
    lin += eps
    return lin


def get_ring_vertices(V, F, query_vertices, n=1):
    """
    Find n-ring vertices for given vertices in a mesh.
    Args:
        V: #V by 3 vertices array
        F: #F by 3 faces array
        query_vertices: list/array of vertex indices
        n: integer specifying the number of rings (default=1)
    Returns:
        ring_vertices: set of vertex indices up to n rings away
    """
    vertex_set = set(query_vertices)
    if n < 1:
        return vertex_set

    A = igl.adjacency_matrix(F)
    current_ring = set(query_vertices)
    for i in range(n):
        next_ring = set()
        for v in current_ring:
            next_ring.update(A.getrow(v).indices)
        vertex_set.update(next_ring)
        current_ring = next_ring

    return vertex_set


def _fair_mesh(
    vs: np.ndarray,
    fs: np.ndarray,
    vids: np.ndarray,
    smoothness: float = 1.0,
    curvature_weight: float = 0.0,
):
    """
    Minimizes polyharmonic energy of a mesh at vids.

    Smoothness controls the biharmonic term (k=2, ``Q2 = L^T M^{-1} L``),
    which minimizes total mean curvature squared ``∫(2H)² dA`` and
    produces C1-continuous surfaces.

    Curvature weight adds the triharmonic term (k=3,
    ``Q3 = L^T M^{-1} Q2``), which minimizes the gradient of mean
    curvature ``∫|∇H|² dA``. This propagates curvature from the
    boundary into the free region, producing C2-continuous surfaces.

    Parameters
    ----------
    vs : ndarray, shape (N, 3)
        Vertex coordinates.
    fs : ndarray, shape (M, 3)
        Face indices.
    vids : ndarray (k)
        Vertices to optimize.
    smoothness : float, optional
        Weight for the biharmonic energy (k=2). Controls the balance
        between position anchoring and curvature minimization.
        0 = vertices stay in place, 1 = full smoothing. Default 1.0.
    curvature_weight : float, optional
        Weight for the triharmonic energy (k=3). Propagates curvature
        from the boundary into the free region. Acts independently
        of smoothness. Default 0.0.
    """
    L, M = _robust_laplacian(vs, fs)
    m_diag = M.diagonal()
    m_diag = np.where(m_diag > _epsilon, m_diag, _epsilon)
    M_inv = scipy.sparse.diags(1.0 / m_diag)
    Q2 = L.T @ M_inv @ L

    n = len(vs)
    smoothness = np.clip(smoothness, _epsilon, 1.0 - _epsilon)

    free = np.zeros(n)
    free[vids] = 1.0

    W_smooth = scipy.sparse.diags(free * smoothness)
    W_anchor = scipy.sparse.diags(free * (1.0 - smoothness) + 1.0 - free)
    Q = W_smooth @ Q2 + W_anchor @ M + _epsilon * scipy.sparse.eye(n)

    if curvature_weight != 0:
        Q3 = L.T @ M_inv @ Q2
        W_curv = scipy.sparse.diags(free * curvature_weight)
        Q = Q + W_curv @ Q3

    out_vs = np.zeros_like(vs)
    B = (W_anchor @ M + _epsilon * scipy.sparse.eye(n)) @ vs
    for axis in range(3):
        out_vs[:, axis] = scipy.sparse.linalg.spsolve(Q, B[:, axis])
    return out_vs


def fair_mesh(
    vs: np.ndarray,
    fs: np.ndarray,
    vids: np.ndarray,
    smoothness: float = 1.0,
    curvature_weight: float = 0.0,
    pressure: float = 0.0,
    n_ring: int = 0,
    **kwargs
):
    """
    Minimizes vertex displacement and polyharmonic energy of a mesh at vids.

    Parameters
    ----------
    vs : ndarray, shape (N, 3)
        Vertex coordinates.
    fs : ndarray, shape (M, 3)
        Face indices.
    vids : ndarray (k)
        Vertices to optimize.
    smoothness : float, optional
        Controls the balance between position anchoring and curvature
        minimization. 0 = vertices stay in place, 1 = full curvature
        minimization. Default 1.0.
    curvature_weight : float, optional
        Weight for triharmonic (higher-order smoothing) energy. Acts
        independently of smoothness. Default 0.0.
    pressure : float, optional
        Normal displacement applied to free vertices before fairing.
        Positive values expand outward, negative values contract.
        Units match the input coordinate system. Default 0.0.
    n_ring : int, optional
        n_ring vertices around vids to consider for fairing. Default 0.
    """
    if smoothness == 0 and curvature_weight == 0 and pressure == 0:
        return vs

    vs = np.asarray(vs, dtype=np.float64).copy()
    vids = np.asarray(vids)
    if n_ring > 0:
        vids = np.asarray(list(get_ring_vertices(vs, fs, vids, n=n_ring)))

    vs_center = np.mean(vs, axis=0)
    vs = vs - vs_center

    vs_scale = np.std(vs)
    vs_scale = np.where(np.abs(vs_scale) <= 1e-6, 1, vs_scale)
    vs = vs / vs_scale

    fair_kwargs = {"smoothness": smoothness, "curvature_weight": curvature_weight}
    out_vs = _fair_mesh(vs, fs, vids, **fair_kwargs)

    # Two step to avoid degenerate normal vectors of inferred vertices
    if pressure != 0:
        out_vs_world = out_vs * vs_scale + vs_center
        normals = igl.per_vertex_normals(out_vs_world, fs)
        out_vs[vids] += (pressure / vs_scale) * normals[vids]
        out_vs = _fair_mesh(out_vs, fs, vids, **fair_kwargs)

    return out_vs * vs_scale + vs_center


def _robust_laplacian(
    vs, fs, mollify_factor=1e-5
) -> Tuple[scipy.sparse.csc_matrix, scipy.sparse.csc_matrix]:
    """
    Get a laplacian with intrinsic Delaunay triangulation and intrinsic mollification.

    Parameters
    ----------
    vs : ndarray, shape (N, 3)
        Vertex coordinates.
    fs : ndarray, shape (M, 3)
        Face indices.
    mollify_factor : float, optional
        Factor controlling edge length smoothing. Default is 1e-5.

    Returns
    -------
    ndarray, shape (M, 3)
        Mollified edge lengths for each face triangle.

    References
    ----------
    .. [1] Code copied from https://github.com/kentechx/hole-filling
    .. [2] https://www.cs.cmu.edu/~kmcrane/Projects/NonmanifoldLaplace/NonmanifoldLaplace.pdf
    """
    lin = get_mollified_edge_length(vs, fs, mollify_factor).astype(np.float64)
    lin, fin, *_ = igl.intrinsic_delaunay_triangulation(lin, fs)
    L = igl.cotmatrix_intrinsic(lin, fin)
    M = igl.massmatrix_intrinsic(lin, fin, igl.MASSMATRIX_TYPE_VORONOI)
    return L, M
