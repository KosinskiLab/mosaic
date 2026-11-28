"""
Find mesh defects that automatic repair cannot remove.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from dataclasses import dataclass

import numpy as np

__all__ = ["MeshDefect", "check_mesh"]


@dataclass(frozen=True, eq=False)
class MeshDefect:
    """A defect on a triangle mesh.

    Parameters
    ----------
    kind : str
        ``"hole"``, ``"twisted"`` or ``"nonmanifold"``.
    vertices : np.ndarray
        Indices of the vertices the defect concerns.
    perimeter : float, optional
        Length around a hole in the mesh's units, 0 for other kinds.
    """

    kind: str
    vertices: np.ndarray
    perimeter: float = 0.0


def check_mesh(
    vertices: np.ndarray, faces: np.ndarray, max_hole_fraction: float = 0.15
) -> list[MeshDefect]:
    """Find holes, twisted spots and non-manifold edges.

    Parameters
    ----------
    vertices : np.ndarray
        Vertex coordinates, shape (N, 3).
    faces : np.ndarray
        Triangle vertex indices, shape (M, 3).
    max_hole_fraction : float, optional
        A hole counts as a defect when its area is below this fraction of
        the area of the connected piece it borders. Larger openings are
        taken as intended.

    Returns
    -------
    list of MeshDefect
        One entry per hole, one for all twisted or self-touching spots and
        one for all non-manifold edges.
    """
    import igl
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    faces = np.asarray(faces, dtype=np.int64)
    if len(faces) == 0:
        return []
    vertices = np.asarray(vertices, dtype=np.float64)
    n = len(vertices)

    directed = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    undirected = np.sort(directed, axis=1)
    _, inverse, counts = np.unique(
        undirected[:, 0] * n + undirected[:, 1], return_inverse=True, return_counts=True
    )
    uses = counts[inverse]

    defects = []
    boundary = directed[uses == 1]
    if len(boundary):
        adjacency = coo_matrix(
            (np.ones(len(directed)), (directed[:, 0], directed[:, 1])), shape=(n, n)
        )
        _, piece = connected_components(adjacency, directed=False)
        tri = vertices[faces]
        face_area = 0.5 * np.linalg.norm(
            np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1
        )
        piece_area = np.bincount(piece[faces[:, 0]], weights=face_area)

        loops = coo_matrix(
            (np.ones(len(boundary)), (boundary[:, 0], boundary[:, 1])), shape=(n, n)
        )
        _, loop = connected_components(loops, directed=False)
        edge_loop = loop[boundary[:, 0]]
        cross = np.cross(vertices[boundary[:, 0]], vertices[boundary[:, 1]])
        length = np.linalg.norm(
            vertices[boundary[:, 1]] - vertices[boundary[:, 0]], axis=1
        )
        for label in np.unique(edge_loop):
            mask = edge_loop == label
            area = 0.5 * np.linalg.norm(cross[mask].sum(axis=0))
            edges = boundary[mask]
            if area < max_hole_fraction * piece_area[piece[edges[0, 0]]]:
                defects.append(
                    MeshDefect("hole", np.unique(edges), float(length[mask].sum()))
                )

    pairs = directed[uses == 2]
    keys, dcounts = np.unique(pairs[:, 0] * n + pairs[:, 1], return_counts=True)
    repeated = keys[dcounts > 1]
    used = np.zeros(n, dtype=bool)
    used[faces.ravel()] = True
    manifold = np.ones(n, dtype=bool)
    result = np.asarray(igl.is_vertex_manifold(faces), dtype=bool)
    manifold[: len(result)] = result
    twisted = np.union1d(
        np.concatenate([repeated // n, repeated % n]), np.flatnonzero(~manifold & used)
    )
    if len(twisted):
        defects.append(MeshDefect("twisted", twisted.astype(np.int64)))

    shared = np.unique(undirected[uses > 2])
    if len(shared):
        defects.append(MeshDefect("nonmanifold", shared.astype(np.int64)))
    return defects
