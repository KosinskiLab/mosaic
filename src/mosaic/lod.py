"""
Level-of-detail support for large point clouds.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np
from vtkmodules.util import numpy_support
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData

LOD_DISABLED = 0

# Rendering cost is negligible below this point count
LOD_SMALL_CLOUD_POINTS = 10_000


def get_point_budget() -> int:
    """Read the current LOD point budget from application settings.

    Returns :data:`LOD_DISABLED` (0) when interaction-LOD is off
    (ultra preset).  Any positive value is the actual point limit.
    """
    from .settings import Settings

    return int(Settings.vtk.point_budget)


def _subsample(indices, budget):
    """Pick *budget* entries from a sorted index array, preserving order.

    Stratified sampling (one random pick per equal-width bin) stays ascending
    without a post-sort and spreads picks evenly, which is what an LOD wants.
    Assumes ``len(indices) > budget``.

    Parameters
    ----------
    indices : np.ndarray
        Sorted index array to thin.
    budget : int
        Number of indices to keep.
    """
    rng = np.random.default_rng(42)
    edges = np.linspace(0, len(indices), budget + 1).astype(np.int64)
    pos = edges[:-1] + (rng.random(budget) * (edges[1:] - edges[:-1])).astype(np.int64)
    return indices[pos]


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
        surface_idx = _subsample(surface_idx, budget)
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
        return _subsample(parent_indices, budget)

    n_parent = int(np.max(subset_idx)) + 1
    kept = np.zeros(n_parent, dtype=bool)
    kept[subset_idx] = True

    valid = parent_indices < n_parent
    surviving = parent_indices[valid]
    surviving = surviving[kept[surviving]]

    new_map = np.cumsum(kept) - 1
    new_indices = new_map[surviving]

    if len(new_indices) > budget:
        new_indices = _subsample(new_indices, budget)

    return new_indices


def merge_lod_indices(lod_indices, counts, budget):
    """Combine per-geometry LOD indices into a merged index space.

    Parameters
    ----------
    lod_indices : list of np.ndarray or None
        Each input geometry's LOD indices, in merge order.  A ``None`` entry
        means that input has no LOD.
    counts : list of int
        Each input geometry's point count, in the same order.
    budget : int
        Maximum number of LOD indices for the merged result.

    Returns
    -------
    np.ndarray or None
        Merged LOD indices, trimmed to *budget* if needed.  ``None`` when any
        entry of *lod_indices* is ``None`` (the merge is then not a
        resynthesizable subset/merge and the caller should recompute).
    """
    if any(idx is None for idx in lod_indices):
        return None

    offsets = np.cumsum([0, *counts[:-1]])
    merged = np.concatenate(
        [np.asarray(idx) + off for idx, off in zip(lod_indices, offsets)]
    )

    if len(merged) > budget:
        merged = _subsample(merged, budget)

    return merged


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

        # Ignore other representations or really small point clouds
        if rep not in ("pointcloud", "gaussian_density") or n < LOD_SMALL_CLOUD_POINTS:
            n = LOD_DISABLED
        counts.append(n)

    total = sum(counts)
    if total <= budget:
        return {}

    result = {}
    for g, n in zip(geometries, counts):
        if n == LOD_DISABLED:
            continue
        share = max(1, int(budget * n / total))
        if n > share:
            result[g.uuid] = share
    return result


class InteractionLOD:
    """Runtime interaction level-of-detail for one geometry.

    Owns the LOD actor and its point-index subset and swaps it in for the
    owner's full-resolution actor during camera interaction.  Purely a
    rendering concern: never pickled, rebuilt on demand from the owner.

    Parameters
    ----------
    owner : Geometry
        Geometry supplying points, sampling rate, the main actor and data.
    """

    def __init__(self, owner):
        self._owner = owner
        self.actor = None
        self.data = None
        self.indices = None
        self.active = False
        self._sync_mtime = -1

    @property
    def count(self):
        """Number of points in the owning geometry."""
        return self._owner.get_number_of_points()

    def setup(self, budget=None):
        """Build the LOD actor from a fresh surface-shell extraction.

        Parameters
        ----------
        budget : int, optional
            Maximum LOD points.  Defaults to the global point budget.
        """
        self.actor = self.data = self.indices = None
        self.active = False
        self._sync_mtime = -1

        if budget is None:
            budget = get_point_budget()
        if budget == LOD_DISABLED or self.count <= budget:
            return None

        owner = self._owner
        self.apply(surface_shell_indices(owner.points, owner.sampling_rate, budget))
        return None

    def inherit(self, parent, subset_idx, budget=None):
        """Remap a parent's LOD into the owner's index space.

        Parameters
        ----------
        parent : InteractionLOD
            LOD of the geometry this one was subset from.  A no-op when the
            parent carries no LOD.
        subset_idx : np.ndarray
            Indices used to create the owner from the parent.
        budget : int, optional
            Maximum LOD points.  Defaults to the global point budget.
        """
        if parent.indices is None:
            return None
        if budget is None:
            budget = get_point_budget()
        self.apply(remap_lod_indices(parent.indices, subset_idx, self.count, budget))
        return None

    def merge(self, inputs, budget=None):
        """Rebuild the LOD from the LODs of merged geometries.

        Each input's indices are offset by the running point count, mirroring
        the point concatenation in :meth:`Geometry.merge`.  A no-op when the
        merged result is small enough not to need a LOD or any input lacks one.

        Parameters
        ----------
        inputs : list of InteractionLOD
            LODs of the merged geometries, in merge order.
        budget : int, optional
            Maximum LOD points.  Defaults to the global point budget.
        """
        budget = get_point_budget() if budget is None else budget
        if budget == LOD_DISABLED or self.count <= budget:
            return None

        merged = merge_lod_indices(
            [inp.indices for inp in inputs], [inp.count for inp in inputs], budget
        )
        if merged is not None:
            self.apply(merged)
        return None

    def apply(self, indices):
        """Build and attach the LOD actor for the given point *indices*."""
        actor, data, indices = build_lod_actor(self._owner.points, indices)
        if actor is not None:
            self.actor, self.data, self.indices = actor, data, indices
            self._sync_mtime = -1
        return None

    def begin(self):
        """Hide the main actor and show the LOD actor for fast interaction."""
        owner = self._owner
        if self.actor is None or self.active or not owner._intent_visible:
            return None
        self._sync_arrays()
        self._sync_mapper()
        self.active = True
        owner._actor.SetVisibility(False)
        self.actor.SetVisibility(True)
        return None

    def end(self):
        """Restore the main actor and hide the LOD actor."""
        if not self.active:
            return None

        owner = self._owner
        self.active = False
        owner._actor.SetVisibility(owner._intent_visible)
        self.actor.SetVisibility(False)
        return None

    def _sync_mapper(self):
        owner = self._owner
        self.actor.GetProperty().DeepCopy(owner._actor.GetProperty())
        transform = owner._actor.GetUserTransform()
        if transform is not None:
            self.actor.SetUserTransform(transform)

        src, dst = owner._actor.GetMapper(), self.actor.GetMapper()
        dst.SetScalarVisibility(src.GetScalarVisibility())
        dst.SetScalarMode(src.GetScalarMode())
        dst.SetColorMode(src.GetColorMode())
        dst.SetScalarRange(src.GetScalarRange())
        lut = src.GetLookupTable()
        if lut is not None:
            dst.SetLookupTable(lut)
        return None

    def _sync_arrays(self):
        owner = self._owner
        mtime = owner._data.GetPointData().GetMTime()
        if mtime == self._sync_mtime:
            return None

        idx = self.indices
        pd, lod_pd = owner._data.GetPointData(), self.data.GetPointData()
        scalars = pd.GetScalars()
        if scalars is not None:
            src = numpy_support.vtk_to_numpy(scalars)
            lod_pd.SetScalars(numpy_support.numpy_to_vtk(src[idx], deep=True))
        else:
            lod_pd.SetScalars(None)
        normals = pd.GetNormals()
        if normals is not None:
            src = numpy_support.vtk_to_numpy(normals)
            vtk_n = numpy_support.numpy_to_vtk(src[idx], deep=True)
            vtk_n.SetName("Normals")
            lod_pd.SetNormals(vtk_n)
        else:
            lod_pd.SetNormals(None)
        self._sync_mtime = mtime
        return None
