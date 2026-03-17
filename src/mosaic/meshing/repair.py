"""
Utilities for repair of triangular meshes.

Hole filling and Leipa triangulation were adapted from
https://github.com/kentechx/hole-filling and are distributed under
MIT license. This origin is indicated as reference for the
respective functions.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import Tuple

import igl
import numpy as np
import scipy.sparse

_epsilon = 1e-16

__all__ = [
    "triangulate_refine_fair",
    "fair_mesh",
    "get_ring_vertices",
    "close_holes",
    "get_mollified_edge_length",
    "harmonic_deformation",
]


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


def _create_weights(size, indices, weight):
    ret = np.full(size, fill_value=0.0)
    ret[indices] = weight
    return scipy.sparse.diags(ret)


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


def harmonic_deformation(vs, fs, vids, k=2):
    vs = vs.astype(np.float32)
    fs = fs.astype(np.int32)

    fixed_vertices = np.setdiff1d(np.arange(len(vs)), vids).astype(np.int32)
    target_positions = vs[fixed_vertices]
    out_vs = igl.harmonic(vs, fs, fixed_vertices, target_positions, k)
    return np.ascontiguousarray(out_vs)


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
    n_ring: int = 1,
    # Legacy parameters — mapped to new interface for backwards compatibility
    alpha=None,
    anchoring=None,
    beta=None,
    gamma=None,
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
        n_ring vertices around vids to consider for fairing. Default 1.
    alpha : float, optional
        Deprecated. Use smoothness instead.
    anchoring : float, optional
        Deprecated. Controlled by smoothness.
    beta : float, optional
        Deprecated. Use curvature_weight instead.
    gamma : float, optional
        Deprecated. Use pressure instead.
    """
    # Legacy parameter mapping
    if alpha is not None:
        smoothness = alpha
    if beta is not None:
        curvature_weight = beta
    if gamma is not None:
        pressure = gamma

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
    vs, fs, mollify_factor=1e-5, weighting_method=None
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

    if weighting_method == "MEAN_CURVATURE":
        M_inv = scipy.sparse.diags(1.0 / M.diagonal())
        Hn = -M_inv @ (L @ vs)

        # Mean curvature magnitude
        W = scipy.sparse.diags(1.0 + np.linalg.norm(Hn, axis=1))
        M = M @ W
    elif weighting_method == "GAUSSIAN_CURVATURE":
        K = igl.gaussian_curvature(vs, fs)
        W = scipy.sparse.diags(1.0 + np.abs(K))
        M = M @ W

    return L, M


def _triangulation_refine_leipa(
    vs: np.ndarray, fs: np.ndarray, fids: np.ndarray, density_factor: float = np.sqrt(2)
):
    """
    Refine triangles using barycentric subdivision and Delaunay triangulation
    using Liepa's hole filling algorithm [1].


    Parameters
    ----------
    vs : ndarray, shape (N, 3)
        Vertex coordinates.
    fs : ndarray, shape (M, 3)
        Face indices.
    fids : ndarray, shape (K,)
        Indices of faces to refine.
    density_factor : float, optional
        Controls subdivision density. Default is sqrt(2).

    Returns
    -------
    out_vs : ndarray, shape (N+P, 3)
        Output vertices, with new vertices appended.
    out_fs : ndarray, shape (M+Q, 3)
        Output faces, with new faces appended.
    FI : ndarray, shape (M,)
        Maps original face indices to refined face indices.
        FI[i] = -1 indicates face i was deleted.

    References
    ----------
    .. [1] Code adapted from https://github.com/kentechx/hole-filling.
    .. [2] Liepa, P. "Filling holes in meshes." (2003)
    """
    out_vs = np.copy(vs)
    out_fs = np.copy(fs)

    if fids is None or len(fids) == 0:
        return out_vs, out_fs, np.arange(len(fs))

    # initialize sigma
    edges = igl.edges(
        np.delete(out_fs, fids, axis=0)
    )  # calculate the edge length without faces to be refined
    edges = np.concatenate([edges, edges[:, [1, 0]]], axis=0)
    edge_lengths = np.linalg.norm(out_vs[edges[:, 0]] - out_vs[edges[:, 1]], axis=-1)
    edge_length_vids = edges[:, 0]
    v_degrees = np.bincount(edge_length_vids, minlength=len(out_vs))
    v_sigma = np.zeros(len(out_vs))
    v_sigma[v_degrees > 0] = (
        np.bincount(edge_length_vids, weights=edge_lengths, minlength=len(out_vs))[
            v_degrees > 0
        ]
        / v_degrees[v_degrees > 0]
    )
    if np.any(v_sigma == 0):
        v_sigma[v_sigma == 0] = np.median(v_sigma[v_sigma != 0])
        # print("Warning: some vertices have no adjacent faces, the refinement may be incorrect.")

    all_sel_fids = np.copy(fids)
    for _ in range(100):
        # calculate sigma of face centers
        vc_sigma = v_sigma[out_fs].mean(axis=1)  # nf

        # check edge length
        s = density_factor * np.linalg.norm(
            out_vs[out_fs[all_sel_fids]].mean(1, keepdims=True)
            - out_vs[out_fs[all_sel_fids]],
            axis=-1,
        )
        cond = np.all(
            np.logical_and(
                s > vc_sigma[all_sel_fids, None], s > v_sigma[out_fs[all_sel_fids]]
            ),
            axis=1,
        )
        sel_fids = all_sel_fids[cond]  # need to subdivide

        if len(sel_fids) == 0:
            break

        # subdivide
        out_vs, added_fs = igl.false_barycentric_subdivision(out_vs, out_fs[sel_fids])

        # update v_sigma after subdivision
        v_sigma = np.concatenate([v_sigma, vc_sigma[sel_fids]], axis=0)
        assert len(v_sigma) == len(out_vs)

        # delete old faces from out_fs and all_sel_fids
        out_fs[sel_fids] = -1
        all_sel_fids = np.setdiff1d(all_sel_fids, sel_fids)

        # add new vertices, faces & update selection
        out_fs = np.concatenate([out_fs, added_fs], axis=0)
        sel_fids = np.arange(len(out_fs) - len(added_fs), len(out_fs))
        all_sel_fids = np.concatenate([all_sel_fids, sel_fids], axis=0)

        # delaunay
        edge_length = get_mollified_edge_length(out_vs, out_fs[all_sel_fids])
        _, add_fs, *_ = igl.intrinsic_delaunay_triangulation(
            edge_length.astype("f8"), out_fs[all_sel_fids]
        )
        out_fs[all_sel_fids] = add_fs

    # update FI, remove deleted faces
    FI = np.arange(len(fs))
    FI[out_fs[: len(fs), 0] < 0] = -1
    idx = np.where(FI >= 0)[0]
    FI[idx] = np.arange(len(idx))
    out_fs = out_fs[out_fs[:, 0] >= 0]
    return out_vs, out_fs, FI


def triangulate_refine_fair(
    vs,
    fs,
    hole_len_thr=-1,
    close_hole_fast=True,
    target_edge_length: float = -1,
    smoothness: float = 1.0,
    curvature_weight: float = 0.0,
    pressure: float = 0.0,
    n_ring: int = 1,
    # Legacy parameters
    alpha=None,
    beta=None,
    gamma=None,
    **kwargs,
):
    """Fill holes, remesh to uniform edge length, and fair inferred vertices.

    Closes holes in the mesh, remeshes to a uniform target edge length,
    identifies vertices in the former hole regions by distance from the
    original mesh, and fairs them.

    Parameters
    ----------
    vs : ndarray, shape (N, 3)
        Vertex coordinates.
    fs : ndarray, shape (M, 3)
        Face indices.
    hole_len_thr : float, optional
        Maximum hole perimeter to fill. Default is -1 (no limit).
    close_hole_fast : bool, optional
        Use fast hole filling. Default is True.
    target_edge_length : float, optional
        Target edge length for isotropic remeshing after hole filling.
        -1 uses the median edge length of the input mesh.
    smoothness : float, optional
        Controls the balance between position anchoring and curvature
        minimization. 0 = vertices stay in place, 1 = full curvature
        minimization. Default 1.0.
    curvature_weight : float, optional
        Weight for triharmonic (higher-order smoothing) energy. Default 0.0.
    pressure : float, optional
        Normal displacement applied to free vertices after fairing.
        Positive values expand outward, negative values contract.
        Units match the input coordinate system. Default 0.0.
    n_ring : int, optional
        Also refine n_ring vertices around inferred vertices. Default 1.

    Returns
    -------
    out_vs : ndarray, shape (P, 3)
        Output vertices after filling, remeshing, and fairing.
    out_fs : ndarray, shape (Q, 3)
        Output faces after filling, remeshing, and fairing.
    """
    import warnings
    from ..utils import find_closest_points
    from .utils import remesh, to_open3d, compute_edge_lengths

    if alpha is not None:
        smoothness = alpha
    if beta is not None:
        curvature_weight = beta
    if gamma is not None:
        pressure = gamma

    vs = np.asarray(vs, dtype=np.float64).copy()
    fs = np.asarray(fs).copy()
    original_vs = vs.copy()

    out_fs = close_holes(vs, fs, hole_len_thr, close_hole_fast)

    if target_edge_length <= 0:
        target_edge_length = float(np.median(compute_edge_lengths(to_open3d(vs, fs))))

    try:
        mesh = remesh(to_open3d(vs, out_fs), target_edge_length)
        vs = np.asarray(mesh.vertices, dtype=np.float64)
        fs = np.asarray(mesh.triangles)
    except (ValueError, RuntimeError):
        warnings.warn(
            "Remeshing failed (non-manifold mesh). Continuing without remeshing."
        )
        fs = out_fs

    distances, _ = find_closest_points(original_vs, vs)
    vids = np.where(distances > target_edge_length * 0.5)[0]

    if len(vids) == 0:
        return vs, fs

    vs = fair_mesh(
        vs,
        fs,
        vids,
        smoothness=smoothness,
        curvature_weight=curvature_weight,
        pressure=pressure,
        n_ring=n_ring,
    )
    return vs, fs
