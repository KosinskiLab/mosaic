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
        updated = False
        for b in igl.all_boundary_loop(out_fs):
            hole_edge_len = np.linalg.norm(vs[np.roll(b, -1)] - vs[b], axis=1).sum()
            if len(b) >= 3 and (hole_edge_len <= hole_len_thr or hole_len_thr < 0):
                out_fs = _close_hole(vs, out_fs, b, fast)
                updated = True
        if not updated:
            break

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


def fair_mesh(
    vs: np.ndarray,
    fs: np.ndarray,
    vids: np.ndarray,
    alpha=1,
    beta=0.0,
    gamma=0.0,
    n_ring=0,
):
    """
    Minimizes vertex displacement and polyharmonic energy of a mesh at vids.

    Parameters
    ----------
    vs : ndarray, shape (N, 3)
        Vertex coordinates.
    fs : ndarray, shape (M, 3)
        Face indices.
    vids: ndarray (k)
        Vertices to optimize
    alpha : float, optional
        k2 polyharmonic weighting factor.
    beta : float, optional
        k3 polyharmonic weighting factor.
    gamma : float, optional
        Internal mesh pressure.
    n_ring : int, optional
        n_ring vertices around vids to consider for fairing.
    """
    vids = np.asarray(vids)
    if n_ring > 0:
        vids = np.asarray(list(get_ring_vertices(vs, fs, vids, n=n_ring)))

    L, M = _robust_laplacian(vs, fs)
    Q2 = igl.harmonic_integrated_from_laplacian_and_mass(L, M, 2)
    Q4 = igl.harmonic_integrated_from_laplacian_and_mass(L, M, 3)

    a = _create_weights(len(vs), vids, alpha)
    b = _create_weights(len(vs), vids, beta)

    # Alpha is coupled to displacement to avoid mesh shrinkage
    displacement = M - a * M
    Q = a * Q2 + b * Q4 + displacement
    B = displacement @ vs
    out_vs = np.ascontiguousarray(igl.spsolve(Q, B))

    if np.any(np.isnan(out_vs)):
        return vs

    if gamma == 0:
        return out_vs

    L, M = _robust_laplacian(out_vs, fs)
    Q2 = igl.harmonic_integrated_from_laplacian_and_mass(L, M, 2)
    Q4 = igl.harmonic_integrated_from_laplacian_and_mass(L, M, 3)

    normals = igl.per_vertex_normals(vs, fs)

    displacement = M - a * M
    B = displacement @ vs + gamma * normals
    Q = a * Q2 + b * Q4 + displacement

    return np.ascontiguousarray(igl.spsolve(Q, B))


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
    lin, fin = igl.intrinsic_delaunay_triangulation(lin, fs)
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
        l = get_mollified_edge_length(out_vs, out_fs[all_sel_fids])
        _, add_fs = igl.intrinsic_delaunay_triangulation(
            l.astype("f8"), out_fs[all_sel_fids]
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
    density_factor=np.sqrt(2),
    alpha=0.05,
    beta=0.0,
    gamma=0,
    n_ring: int = 0,
):
    """
    Fill and fair holes in triangular meshes.

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
    density_factor : float, optional
        Controls subdivision density. Default is sqrt(2).
    alpha : float, optional
        Weight for membrane energy. Default is 0.05.
    beta : float, optional
        Weight for curvature energy. Default is 0.
    gamma : float, optional
        Volume pressure. Default is 0.
    n_ring : int, optional
        Also refine n_ring vertices for filled in vertices. Default is 0.

    Returns
    -------
    out_vs : ndarray, shape (N+P, 3)
        Output vertices after filling and fairing.
    out_fs : ndarray, shape (M+Q, 3)
        Output faces after filling and fairing.
    """
    vs = np.asarray(vs).copy()
    fs = np.asarray(fs).copy()
    out_fs = close_holes(vs, fs, hole_len_thr, close_hole_fast)
    add_fids = np.arange(len(fs), len(out_fs))

    nv = len(vs)
    vs, fs, FI = _triangulation_refine_leipa(vs, out_fs, add_fids, density_factor)
    vids = np.arange(nv, len(vs))

    # Fair selected parts of the mesh
    vs = fair_mesh(vs, fs, vids, alpha=alpha, beta=beta, gamma=gamma, n_ring=n_ring)
    return vs, fs
