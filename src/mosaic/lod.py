"""
Level-of-detail support for large point clouds.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
from vtkmodules.util import numpy_support

LOD_DISABLED = 0


def get_point_budget() -> int:
    """Read the current LOD point budget from application settings.

    Returns :data:`LOD_DISABLED` (0) when interaction-LOD is off
    (ultra preset).  Any positive value is the actual point limit.
    """
    from .settings import Settings

    return int(Settings.vtk.point_budget)


def surface_shell_indices(points: np.ndarray, sampling_rate, budget: int) -> np.ndarray:
    """Return indices of points on the surface shell of a cloud.

    Uses a 6-connected occupancy grid to classify each point as
    surface (at least one empty face-neighbor) or interior (fully
    surrounded).  Falls back to random subsampling when the grid
    cannot be built or would not help.

    Parameters
    ----------
    points : np.ndarray
        Point coordinates, shape ``(n, 3)``.
    sampling_rate : float or array-like
        Voxel spacing.  When array-like the maximum is used.
    budget : int
        Maximum number of indices to return.
    """
    n = len(points)
    sr = float(np.max(sampling_rate))

    if sr <= 0:
        rng = np.random.default_rng(42)
        return np.sort(rng.choice(n, size=min(budget, n), replace=False))

    min_pt = points.min(axis=0)
    extent = points.max(axis=0) - min_pt

    MAX_VOXELS = 50_000_000
    grid_dims = extent / sr + 1
    total_voxels = float(np.prod(grid_dims))
    voxel_size = sr * max(1.0, (total_voxels / MAX_VOXELS) ** (1.0 / 3.0))

    vc = ((points - min_pt) / voxel_size).astype(np.int32) + 1
    shape = tuple(vc.max(axis=0) + 2)

    grid = np.zeros(shape, dtype=bool)
    grid[vc[:, 0], vc[:, 1], vc[:, 2]] = True

    interior_grid = (
        grid[:-2, 1:-1, 1:-1]
        & grid[2:, 1:-1, 1:-1]
        & grid[1:-1, :-2, 1:-1]
        & grid[1:-1, 2:, 1:-1]
        & grid[1:-1, 1:-1, :-2]
        & grid[1:-1, 1:-1, 2:]
    )
    surface_idx = np.flatnonzero(
        ~interior_grid[vc[:, 0] - 1, vc[:, 1] - 1, vc[:, 2] - 1]
    )

    if len(surface_idx) > budget:
        rng = np.random.default_rng(42)
        surface_idx = rng.choice(surface_idx, size=budget, replace=False)
        surface_idx.sort()

    return surface_idx


def build_lod_actor(points: np.ndarray, indices: np.ndarray):
    """Build a complete LOD actor from pre-computed point indices.

    Parameters
    ----------
    points : np.ndarray
        Full point array of the parent geometry.
    indices : np.ndarray
        Indices into *points* that form the LOD subset.

    Returns
    -------
    tuple
        ``(actor, polydata, indices)`` ready to attach to a Geometry,
        or ``(None, None, None)`` when *indices* covers all points
        or is empty.
    """
    import vtk

    n = len(points)
    if len(indices) >= n or len(indices) == 0:
        return None, None, None

    subset = points[indices].astype(np.float32)
    lod = vtkPolyData()
    vtk_pts = vtkPoints()
    vtk_pts.SetData(numpy_support.numpy_to_vtk(subset, deep=True))
    lod.SetPoints(vtk_pts)

    n_lod = len(indices)
    cell_arr = np.empty(n_lod + 1, dtype=np.int64)
    cell_arr[0] = n_lod
    cell_arr[1:] = np.arange(n_lod, dtype=np.int64)
    cells = vtkCellArray()
    cells.SetCells(1, numpy_support.numpy_to_vtkIdTypeArray(cell_arr))
    lod.SetVerts(cells)

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(lod)
    mapper.SetScalarModeToDefault()
    mapper.SetVBOShiftScaleMethod(1)

    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.SetVisibility(False)

    return actor, lod, indices


def remap_lod_indices(parent_indices, subset_idx, n_child, budget):
    """Remap a parent's LOD indices into a child subset's index space.

    Parameters
    ----------
    parent_indices : np.ndarray
        LOD indices from the parent geometry.
    subset_idx : np.ndarray
        Indices used to create the child from the parent.
    n_child : int
        Number of points in the child geometry.
    budget : int
        Maximum number of LOD indices for the child.
    """
    if (
        len(subset_idx) == n_child
        and len(parent_indices) > 0
        and int(np.max(parent_indices)) < n_child
    ):
        if len(parent_indices) <= budget:
            return parent_indices

        rng = np.random.default_rng(42)
        trimmed = rng.choice(parent_indices, size=budget, replace=False)
        trimmed.sort()
        return trimmed

    n_parent = int(np.max(subset_idx)) + 1
    kept = np.zeros(n_parent, dtype=bool)
    kept[subset_idx] = True

    valid = parent_indices < n_parent
    surviving = parent_indices[valid]
    surviving = surviving[kept[surviving]]

    new_map = np.cumsum(kept) - 1
    new_indices = new_map[surviving]

    if len(new_indices) > budget:
        rng = np.random.default_rng(42)
        new_indices = rng.choice(new_indices, size=budget, replace=False)
        new_indices.sort()

    return new_indices


def compute_scene_lod(geometries, budget):
    """Determine per-geometry LOD budgets for a scene.

    Parameters
    ----------
    geometries : list of Geometry
        All geometries in the scene.
    budget : int
        Total point budget for the scene.

    Returns
    -------
    dict
        Maps ``geometry.uuid`` → individual budget.  Geometries that
        don't need LOD (point count ≤ their share) are omitted.

    Notes
    -----
    Distributes the total *budget* proportionally across geometries
    based on their point counts.  Only geometries whose point count
    exceeds their proportional share are included in the result.
    """
    if budget == LOD_DISABLED:
        return {}

    counts = []
    for g in geometries:
        n = g.get_number_of_points()
        rep = getattr(g, "_representation", "pointcloud")
        if rep not in ("pointcloud", "gaussian_density"):
            n = 0
        counts.append(n)

    total = sum(counts)
    if total <= budget:
        return {}

    result = {}
    for g, n in zip(geometries, counts):
        if n == 0:
            continue
        share = max(1, int(budget * n / total))
        if n > share:
            result[g.uuid] = share
    return result
