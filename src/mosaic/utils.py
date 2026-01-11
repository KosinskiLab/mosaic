"""
Utility functions.

Copyright (c) 2023-2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import List, Optional, Callable

import numpy as np
from qtpy.QtCore import QTimer
from scipy import ndimage
from scipy.spatial import KDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components as sparse_connected_components

__all__ = [
    "points_to_volume",
    "volume_to_points",
    "connected_components",
    "envelope_components",
    "dbscan_clustering",
    "birch_clustering",
    "eigenvalue_outlier_removal",
    "statistical_outlier_removal",
    "find_closest_points",
    "find_closest_points_cutoff",
    "com_cluster_points",
    "compute_normals",
    "compute_bounding_box",
    "cmap_to_vtkctf",
    "get_cmap",
    "normals_to_rot",
    "apply_quat",
    "NORMAL_REFERENCE",
    "skeletonize",
    "Throttle",
]

NORMAL_REFERENCE = (0, 0, 1)


class Throttle:
    """Throttle wrapper for limiting function call frequency.

    Wraps a callable to ensure it executes at most once per interval.
    The first call executes immediately; subsequent calls within the
    interval are ignored. After the interval, the next call executes.

    Parameters
    ----------
    func : Callable
        The function to throttle.
    interval_ms : int, optional
        Minimum interval between calls in milliseconds, by default 100.

    Examples
    --------
    >>> def on_slider_change(value):
    ...     print(f"Value: {value}")
    >>> throttled = Throttle(on_slider_change, interval_ms=100)
    >>> slider.valueChanged.connect(throttled)
    """

    def __init__(self, func: Callable, interval_ms: int = 100):
        self._func = func
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._reset)
        self._can_call = True

    def __call__(self, *args, **kwargs):
        """Execute the function if throttle allows."""
        if self._can_call:
            self._can_call = False
            self._timer.start()
            return self._func(*args, **kwargs)
        return None

    def _reset(self):
        """Reset throttle to allow the next call."""
        self._can_call = True


def points_to_volume(
    points,
    sampling_rate=1,
    shape=None,
    weight=1,
    out=None,
    use_offset: bool = False,
    out_dtype=None,
):
    """
    Convert point cloud to a volumetric representation.

    Parameters
    ----------
    points : ndarray
        Input point cloud coordinates.
    sampling_rate : float, optional
        Spacing between volume voxels, by default 1.
    shape : tuple, optional
        Output volume dimensions. If None, automatically determined from points.
    weight : float, optional
        Weight value for each individual point. Defaults to one.
    out : ndarray, optional
        Array to place result into.
    use_offset: bool
        Move points to origin and return the corresponding offset.
    out_dtype: type
        Dtype of the output array if out is not explicitly passed.

    Returns
    -------
    ndarray
        volume ndarray of point densities
    ndarray
        Array of offsets if use_offset is True.
    """
    positions = np.rint(np.divide(points, sampling_rate)).astype(int)
    if use_offset:
        offset = positions.min(axis=0)
        positions -= offset

    if shape is None:
        shape = positions.max(axis=0) + 1

    valid_mask = np.all((positions >= 0) & (positions < shape), axis=1)
    positions = positions[valid_mask]

    if out is None:
        out_dtype = np.float32 if out_dtype is None else out_dtype
        out = np.zeros(tuple(int(x) for x in shape), dtype=out_dtype)

    out[tuple(positions.T)] = weight
    if use_offset:
        return out, offset
    return out


def volume_to_points(
    volume,
    sampling_rate,
    reverse_order: bool = False,
    max_cluster: Optional[int] = None,
):
    """
    Convert volumetric segmentation to point clouds.

    Parameters
    ----------
    volume : ndarray
        Input volumetric data with cluster labels.
    sampling_rate : float
        Spacing between volume voxels.
    max_cluster : int
        Maximum number of clusters to consider before raising an error. This avoid
        accidentally loading a density volume instead of a segmentation. Default is
        no cutoff.

    Returns
    -------
    list
        List of point clouds, one for each unique cluster label.
    """
    mask = volume != 0

    # Sanity check to avoid wasting time parsing densities instead of segmentations
    if mask.sum() >= 0.7 * volume.size:
        n_points = min(50 * 50 * 50, volume.size)

        rng = np.random.default_rng()
        random_indices = rng.integers(0, volume.size, size=n_points)
        clusters = np.unique(volume.flat[random_indices])
        if max_cluster is not None and clusters.size > max_cluster:
            raise ValueError(
                f"Found {clusters.size} clusters (max: {max_cluster}). \n"
                "Make sure you are opening a segmentation."
            )

    points = np.flatnonzero(mask)
    clusters, cluster_indices = np.unique(volume.flat[points], return_inverse=True)
    if max_cluster is not None and clusters.size > max_cluster:
        raise ValueError(
            f"Found {clusters.size} clusters (max: {max_cluster}). \n"
            "Make sure you are opening a segmentation."
        )

    points = np.array(np.unravel_index(points, volume.shape)).T

    ret = []
    for index in range(len(clusters)):
        cl_points = points[cluster_indices == index]

        if reverse_order:
            indices = np.ravel_multi_index(cl_points[:, ::-1].T, volume.shape[::-1])
            cl_points = cl_points[np.argsort(indices)]

        cl_points = np.multiply(cl_points, sampling_rate)
        ret.append(cl_points)
    return ret


def _get_adjacency_matrix(points, symmetric: bool = False, eps: float = 0.0):
    # Leafsize needs to be tuned depending on the structure of the input data.
    # Points typically originates from voxel membrane segmentation on regular grids.
    # Leaf sizes between 8 - 16 work reasonably well.
    tree = KDTree(
        points,
        leafsize=16,
        compact_nodes=False,
        balanced_tree=False,
        copy_data=False,
    )
    pairs = tree.query_pairs(r=np.sqrt(3), eps=eps, output_type="ndarray")

    n_points = points.shape[0]
    adjacency = coo_matrix(
        (np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])),
        shape=(n_points, n_points),
        dtype=np.int8,
    )
    if symmetric:
        adjacency += adjacency.T
    return adjacency


def connected_components(data, **kwargs):
    """
    Find connected components in point clouds using sparse graph representations.

    Parameters
    ----------
    points : ndarray
        Input data.
    distance : tuple of float, optional
        Distance between points to be considered connected, defaults to 1.

    Returns
    -------
    ndarray
        Cluster labels.
    """
    adjacency = _get_adjacency_matrix(data)
    return sparse_connected_components(adjacency, directed=False, return_labels=True)[1]


def envelope_components(data, **kwargs):
    """
    Find envelope of a point cloud using sparse graph representations.

    Parameters
    ----------
    data : ndarray
        Input data.

    Returns
    -------
    ndarray
        Cluster labels.
    """
    adjacency = _get_adjacency_matrix(data, symmetric=True, eps=0.1)
    n0 = np.asarray(adjacency.sum(axis=0)).reshape(-1)

    # This is a somewhat handwavy approximation of how many neighbors
    # an envelope point should have, but appears stable in practice
    indices = np.where(n0 < (data.shape[1] ** 3 - 4))[0]
    labels = connected_components(data[indices], **kwargs)

    total_labels = np.full(data.shape[0], fill_value=-1)
    for index, label in enumerate(np.unique(labels)):
        selection = indices[labels == label]
        total_labels[selection] = index
    return total_labels


def leiden_clustering(data, resolution_parameter: float = -7.3, **kwargs):
    """
    Find Leiden partition of a point cloud using sparse graph representations.

    Parameters
    ----------
    points : ndarray
        Input data.
    resolution_parameter : float
        Log 10 of resolution parameter. Smaller values yield coarser clusters.

    Returns
    -------
    ndarray
        Cluster labels.
    """
    import leidenalg
    import igraph as ig

    adjacency = _get_adjacency_matrix(data, eps=0.1)

    sources, targets = adjacency.nonzero()
    edges = list(zip(sources, targets))
    g = ig.Graph(n=len(data), edges=edges)
    partitions = leidenalg.find_partition(
        g, leidenalg.CPMVertexPartition, resolution_parameter=10**resolution_parameter
    )
    labels = np.full(data.shape[0], fill_value=-1)
    for index, partition in enumerate(partitions):
        labels[partition] = index
    return labels


def dbscan_clustering(data, distance=100.0, min_points=500):
    """
    Perform DBSCAN clustering on the input points.

    Parameters
    ----------
    data : ndarray
        Input data
    distance : float, optional
        Maximum distance between two samples for one to be considered as in
        the neighborhood of the other, by default 40.
    min_points : int, optional
        Minimum number of samples in a neighborhood for a point to be considered as
        a core point, by default 20.

    Returns
    -------
    ndarray
        Cluster labels.
    """
    from sklearn.cluster import DBSCAN

    return DBSCAN(eps=distance, min_samples=min_points).fit_predict(data)


def birch_clustering(
    data, n_clusters: int = 3, threshold: float = 0.5, branching_factor: int = 50
):
    """
    Perform Birch clustering on the input points using skimage.

    Parameters
    ----------
    data : ndarray
        Input data.
    threshold: float, optional
        The radius of the subcluster obtained by merging a new sample
        and the closest subcluster should be lesser than the threshold.
        Otherwise a new subcluster is started. Setting this value to be
        very low promotes splitting and vice-versa.
    branching_factor: int, optional
        Maximum number of CF subclusters in each node. If a new samples
        enters such that the number of subclusters exceed the branching_factor
        then that node is split into two nodes with the subclusters
        redistributed in each. The parent subcluster of that node is removed
        and two new subclusters are added as parents of the 2 split nodes.

    Returns
    -------
    ndarray
        Cluster labels.
    """
    from sklearn.cluster import Birch

    return Birch(
        n_clusters=n_clusters, threshold=threshold, branching_factor=branching_factor
    ).fit_predict(data)


def kmeans_clustering(data, k=2, **kwargs):
    """Split point cloud into k using K-means.

    Parameters
    ----------
    data : ndarray
        Input data.
    k : int
        Number of clusteres.

    Returns
    -------
    ndarray
        Cluster labels.
    """
    from sklearn.cluster import KMeans

    return KMeans(n_clusters=k, n_init="auto").fit_predict(data)


def eigenvalue_outlier_removal(points, k_neighbors=300, thresh=0.05):
    """
    Remove outliers using covariance-based edge detection.

    Parameters
    ----------
    points : ndarray
        Input point cloud.
    k_neighbors : int, optional
        Number of neighbors to consider, by default 300.
    thresh : float, optional
        Threshold for outlier detection, by default 0.05.

    Returns
    -------
    mask
        Boolean array with non-outlier points.

    References
    ----------
    .. [1]  https://github.com/denabazazian/Edge_Extraction/blob/master/Difference_Eigenvalues.py
    """
    tree = KDTree(points)
    distances, indices = tree.query(points, k=k_neighbors + 1, workers=-1)

    points_centered = points[indices[:, 1:]] - points[:, np.newaxis, :]
    cov_matrices = (
        np.einsum("ijk,ijl->ikl", points_centered, points_centered) / k_neighbors
    )

    eigenvalues = np.linalg.eigvalsh(cov_matrices)
    eigenvalues = np.sort(eigenvalues, axis=1)[:, ::-1]

    sum_eg = np.sum(eigenvalues, axis=1)
    sigma = eigenvalues[:, 0] / sum_eg

    mask = sigma >= thresh
    return mask


def statistical_outlier_removal(points, k_neighbors=100, thresh=0.2):
    """
    Remove statistical outliers from the point cloud.

    Parameters
    ----------
    points : ndarray
        Input point cloud.
    k_neighbors : int, optional
        Number of neighbors to use for mean distance estimation, by default 100.
    thresh : float, optional
        Standard deviation ratio to identify outliers, by default 0.2.

    Returns
    -------
    mask
        Boolean array with non-outlier points.
    """
    import open3d as o3d

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points.astype(np.float64))

    cl, ind = pcd.remove_statistical_outlier(nb_neighbors=k_neighbors, std_ratio=thresh)
    mask = np.zeros(points.shape[0], dtype=bool)
    mask[np.asarray(ind, dtype=int)] = 1
    return mask


def find_closest_points(positions1, positions2, k=1):
    positions1, positions2 = np.asarray(positions1), np.asarray(positions2)

    tree = KDTree(positions1)
    return tree.query(positions2, k=k)


def find_closest_points_cutoff(positions1, positions2, cutoff=1):
    positions1, positions2 = np.asarray(positions1), np.asarray(positions2)

    tree = KDTree(positions1)
    return tree.query_ball_point(positions2, cutoff)


def compute_normals(points: np.ndarray, k: int = 15, return_pcd: bool = False):
    import open3d as o3d

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    pcd.estimate_normals()
    pcd.normalize_normals()
    pcd.orient_normals_consistent_tangent_plane(k=k)
    if return_pcd:
        return pcd
    return np.asarray(pcd.normals)


def com_cluster_points(positions: np.ndarray, cutoff: float) -> np.ndarray:
    if not isinstance(positions, np.ndarray):
        positions = np.array(positions)

    if isinstance(cutoff, np.ndarray):
        cutoff = np.max(cutoff)

    tree = KDTree(positions)
    n_points = len(positions)
    unassigned = np.ones(n_points, dtype=bool)
    clusters = []

    unassigned_indices = np.where(unassigned)[0]
    while np.any(unassigned):
        seed_idx = np.random.choice(unassigned_indices)

        cluster_indices = tree.query_ball_point(positions[seed_idx], cutoff)
        cluster_indices = np.array([idx for idx in cluster_indices if unassigned[idx]])

        if len(cluster_indices) > 0:
            cluster_center = np.mean(positions[cluster_indices], axis=0)
            clusters.append(cluster_center)
            unassigned[cluster_indices] = False
            unassigned_indices = np.where(unassigned)[0]

    return np.array(clusters)


def compute_bounding_box(points: List[np.ndarray]) -> List[float]:
    if len(points) == 0:
        return (0, 0, 0)
    starts = points[0].min(axis=0)
    stops = points[0].max(axis=0)
    for point in points[1:]:
        starts_inner = point.min(axis=0)
        stops_inner = point.max(axis=0)
        starts = np.minimum(starts, starts_inner)
        stops = np.maximum(stops, stops_inner)

    return stops - starts, starts


def get_cmap(*args, **kwargs):
    from matplotlib.pyplot import get_cmap

    return get_cmap(*args, **kwargs)


def cmap_to_vtkctf(
    cmap, max_value, min_value, gamma: float = 1.0, transparent_range: bool = False
):
    """Convert a colormap to a VTK color transfer function or lookup table.

    Parameters
    ----------
    cmap : str
        Name of the colormap.
    max_value : float
        Maximum value for the color range.
    min_value : float
        Minimum value for the color range.
    gamma : float, optional
        Gamma correction factor, by default 1.0.
    transparent_range : bool, optional
        If True, returns a vtkLookupTable with transparent colors for values
        outside the specified range. By default False.

    Returns
    -------
    tuple
        (color_function, (min_value, max_value)) where color_function is either
        a vtkColorTransferFunction or vtkLookupTable depending on transparent_range.
    """
    import vtk

    if np.allclose(min_value, max_value):
        offset = 0.01 * max_value + 1e-6
        max_value += offset
        min_value -= offset

    colormap = get_cmap(cmap)

    if transparent_range:
        lut = vtk.vtkLookupTable()
        lut.SetNumberOfTableValues(256)
        lut.SetRange(min_value, max_value)

        for i in range(256):
            t = i / 255.0
            t = t ** (1 / gamma)
            r, g, b, _ = colormap(t)
            lut.SetTableValue(i, r, g, b, 1.0)

        lut.SetUseBelowRangeColor(True)
        lut.SetBelowRangeColor(0, 0, 0, 0)
        lut.SetUseAboveRangeColor(True)
        lut.SetAboveRangeColor(0, 0, 0, 0)
        lut.Build()

        return lut, (min_value, max_value)

    value_range = max_value - min_value

    # Extend color map beyond data range to avoid wrapping
    offset = value_range / 255.0
    max_value += offset

    color_transfer_function = vtk.vtkColorTransferFunction()
    for i in range(256):
        data_value = min_value + i * offset
        x = (data_value - min_value) / (max_value - min_value)
        x = max(0, min(1, x))
        x = x ** (1 / gamma)

        color_transfer_function.AddRGBPoint(data_value, *colormap(x)[0:3])

    return color_transfer_function, (min_value, max_value)


def normals_to_rot(
    normals: np.ndarray,
    target: np.ndarray = NORMAL_REFERENCE,
    mode: str = "quat",
    degrees: bool = True,
    **kwargs,
) -> np.ndarray:
    """
    Finds the shortest rotation that aligns each normal vector to its
    corresponding target vector.

    Parameters
    ----------
    normals : np.ndarray
        Input normal vectors, shape (N, 3) or (3,).
    target : np.ndarray
        Target direction(s), shape (N, 3) or (3,). If single target provided,
        it will be broadcast to all normals.
    mode : str, optional
        Output format: "quat", "matrix", or "euler". Default is "quat".
    degrees : bool, optional
        If True and mode="euler", return angles in degrees. Default is True.

    Returns
    -------
    np.ndarray
        Rotations in requested format:
        - "quat": shape (N, 4), scalar-first [w, x, y, z]
        - "matrix": shape (N, 3, 3)
        - "euler": shape (N, 3), ZYZ Euler angles
    """
    if mode not in ("quat", "matrix", "euler"):
        raise ValueError(f"Unknown mode '{mode}'. Use 'quat', 'matrix', or 'euler'.")

    normals = np.atleast_2d(normals)
    targets = np.atleast_2d(target)

    # Broadcast target if single value provided
    if targets.shape[0] == 1 and normals.shape[0] > 1:
        targets = np.repeat(targets, normals.shape[0], axis=0)
    elif targets.shape[0] != normals.shape[0]:
        raise ValueError(
            f"Incompatible shapes: normals {normals.shape}, target {targets.shape}. "
            "Provide either a single target or one per normal."
        )

    normals = normals / np.linalg.norm(normals, axis=1, keepdims=True)
    targets = targets / np.linalg.norm(targets, axis=1, keepdims=True)

    ret = _align_vectors_to_quat(targets, normals)
    if mode == "matrix":
        ret = _quat_to_matrix(ret)
    elif mode == "euler":
        ret = _quat_to_euler(ret, degrees=degrees)
    return ret


def _align_vectors_to_quat(vec1: np.ndarray, vec2: np.ndarray) -> np.ndarray:
    """
    Compute quaternions for shortest rotation aligning vec1 to vec2.

    Parameters
    ----------
    vec1, vec2 : np.ndarray
        Normalized vectors, shape (N, 3).

    Returns
    -------
    np.ndarray
        Quaternions [w, x, y, z], shape (N, 4).
    """
    axis = np.cross(vec1, vec2)
    cos_angle = np.sum(vec1 * vec2, axis=1)

    aligned = cos_angle > (1 - 1e-8)
    opposite = cos_angle < (-1 + 1e-8)
    normal = ~(aligned | opposite)

    quaternions = np.empty((vec1.shape[0], 4))
    quaternions[aligned] = [1, 0, 0, 0]

    # Half angle
    if np.any(normal):
        w = np.sqrt((1 + cos_angle[normal]) / 2)
        xyz = axis[normal] / (2 * w[:, np.newaxis])
        quaternions[normal, 0] = w
        quaternions[normal, 1:] = xyz

    # Opposite
    if np.any(opposite):
        for i in np.where(opposite)[0]:
            v = vec1[i]
            perp = np.cross(v, [1, 0, 0]) if abs(v[0]) < 0.9 else np.cross(v, [0, 1, 0])
            perp = perp / np.linalg.norm(perp)
            quaternions[i] = [0, perp[0], perp[1], perp[2]]

    return quaternions


def _quat_to_matrix(q: np.ndarray) -> np.ndarray:
    """
    Convert quaternions to rotation matrices.

    Parameters
    ----------
    q : np.ndarray
        Quaternions [w, x, y, z], shape (N, 4).

    Returns
    -------
    np.ndarray
        Rotation matrices, shape (N, 3, 3).
    """
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]

    matrices = np.empty((q.shape[0], 3, 3))

    matrices[:, 0, 0] = 1 - 2 * (y**2 + z**2)
    matrices[:, 0, 1] = 2 * (x * y - w * z)
    matrices[:, 0, 2] = 2 * (x * z + w * y)

    matrices[:, 1, 0] = 2 * (x * y + w * z)
    matrices[:, 1, 1] = 1 - 2 * (x**2 + z**2)
    matrices[:, 1, 2] = 2 * (y * z - w * x)

    matrices[:, 2, 0] = 2 * (x * z - w * y)
    matrices[:, 2, 1] = 2 * (y * z + w * x)
    matrices[:, 2, 2] = 1 - 2 * (x**2 + y**2)

    return matrices


def _quat_to_euler(q: np.ndarray, degrees: bool = True) -> np.ndarray:
    """
    Convert quaternions to ZYZ Euler angles.

    Parameters
    ----------
    q : np.ndarray
        Quaternions [w, x, y, z], shape (N, 4).
    degrees : bool
        Return in degrees if True, radians if False.

    Returns
    -------
    np.ndarray
        ZYZ Euler angles [alpha, beta, gamma], shape (N, 3).
    """
    R = _quat_to_matrix(q)

    r13 = R[:, 0, 2]
    r23 = R[:, 1, 2]
    r31 = R[:, 2, 0]
    r32 = R[:, 2, 1]
    r33 = R[:, 2, 2]

    beta = np.arccos(np.clip(r33, -1, 1))
    alpha = np.arctan2(r23, r13)
    gamma = np.arctan2(r32, -r31)

    gimbal_lock = np.abs(r33) > (1 - 1e-6)

    # When r33 ≈ 1 (beta ≈ 0)
    gimbal_pos = gimbal_lock & (r33 > 0)
    alpha = np.where(gimbal_pos, np.arctan2(-R[:, 0, 1], R[:, 1, 1]), alpha)
    beta = np.where(gimbal_pos, 0, beta)
    gamma = np.where(gimbal_pos, 0, gamma)

    # When r33 ≈ -1 (beta ≈ π)
    gimbal_neg = gimbal_lock & (r33 <= 0)
    alpha = np.where(gimbal_neg, np.arctan2(R[:, 0, 1], R[:, 1, 1]), alpha)
    beta = np.where(gimbal_neg, np.pi, beta)
    gamma = np.where(gimbal_neg, 0, gamma)

    euler = np.column_stack([alpha, beta, gamma])
    return np.degrees(euler) if degrees else euler


def quat_to_euler(
    q: np.ndarray, degrees: bool = True, inv_quat: bool = False
) -> np.ndarray:
    """
    Convert quaternions to ZYZ Euler angles.

    Equivalent to scipy's
        Rotation.from_quat(q, scalar_first=True).inv().as_euler("ZYZ")
    when inv_quat=True.

    Parameters
    ----------
    q : np.ndarray
        Quaternions [w, x, y, z], shape (N, 4).
    degrees : bool
        Return in degrees if True, radians if False. Default is True.
    inv_quat : bool
        Invert quaternions before conversion. Default is False.

    Returns
    -------
    np.ndarray
        ZYZ Euler angles [alpha, beta, gamma], shape (N, 3).
    """
    if inv_quat:
        q = q.copy()
        q[:, 1:] = -q[:, 1:]

    return _quat_to_euler(q, degrees=degrees)


def apply_quat(quaternions, target=NORMAL_REFERENCE):
    return _quat_to_matrix(quaternions) @ target


def skeletonize(
    mask: np.ndarray,
    sigma: float = 1.0,
    mode: str = "core",
    batch_size: int = 100000,
) -> np.ndarray:
    """
    Skeletonize a membrane segmentation using distance transform and Hessian analysis.

    Parameters
    ----------
    mask : np.ndarray
        Binary mask where non-zero values represent structures of interest.
    sigma : float, optional
        Gaussian smoothing sigma applied to Hessian components. Default is 1.0.
    mode : {'core', 'boundary'}, optional
        Type of skeleton to extract:
        - 'core': Extract centerline/medial axis of the structure (default)
        - 'boundary': Extract skeleton along the boundary
    batch_size : int
        Number of coordinates to process per chunk. Larger values require
        more memory.

    Returns
    -------
    np.ndarray
        Binary skeleton

    References
    ----------
    .. [1]  Martinez-Sanchez, A. et al (2014) JSB,
            https://doi.org/10.1016/j.jsb.2014.02.015
    .. [2]  Lamm, L. et al. (2024) bioRxiv, doi.org/10.1101/2024.01.05.574336.

    Notes
    -----
    The original implementation is from [1]_. [2]_ adapted the code based on which
    we created this implementation, which produces very similar results but optimized
    for CPU runtime, numerical stability, and small memory footprint.
    """
    dist = -ndimage.distance_transform_edt(mask)
    if mode in ("outer", "inner"):
        mode = "boundary"

    if mode == "boundary":
        dist *= -1
    elif mode != "core":
        raise ValueError(f"mode must be 'core' or 'boundary', got '{mode}'")

    batch_size = max(int(batch_size), 1)
    grads = [ndimage.sobel(dist, axis=i) for i in range(3)]

    # Upper tri of hessian
    hessian = np.zeros((6, *dist.shape))
    hessian[0] = ndimage.gaussian_filter(ndimage.sobel(grads[0], axis=0), sigma)
    hessian[1] = ndimage.gaussian_filter(ndimage.sobel(grads[1], axis=1), sigma)
    hessian[2] = ndimage.gaussian_filter(ndimage.sobel(grads[2], axis=2), sigma)
    hessian[3] = ndimage.gaussian_filter(ndimage.sobel(grads[0], axis=1), sigma)
    hessian[4] = ndimage.gaussian_filter(ndimage.sobel(grads[0], axis=2), sigma)
    hessian[5] = ndimage.gaussian_filter(ndimage.sobel(grads[1], axis=2), sigma)

    ndim = dist.ndim
    max_eigval = np.zeros(dist.shape)
    max_eigvec = np.zeros((*dist.shape, ndim))

    coords = np.argwhere(mask)
    n_points = min(batch_size, coords.shape[0])

    H = np.zeros((n_points, ndim, ndim))
    ix = np.arange(H.shape[0], dtype=np.int32)
    for start in range(0, coords.shape[0], batch_size):
        stop = min(start + batch_size, coords.shape[0])

        x, y, z = coords[start:stop].T

        # Crop H for the last iteration otherwise reuse
        if H.shape[0] != x.shape[0]:
            H = H[: x.shape[0]]
            ix = ix[: x.shape[0]]

        H[:, 0, 0] = hessian[0, x, y, z]
        H[:, 0, 1] = hessian[3, x, y, z]
        H[:, 0, 2] = hessian[4, x, y, z]

        H[:, 1, 0] = hessian[3, x, y, z]
        H[:, 1, 1] = hessian[1, x, y, z]
        H[:, 1, 2] = hessian[5, x, y, z]

        H[:, 2, 0] = hessian[4, x, y, z]
        H[:, 2, 1] = hessian[5, x, y, z]
        H[:, 2, 2] = hessian[2, x, y, z]

        eigenvals, eigenvecs = np.linalg.eig(H)
        max_idx = np.argmax(np.abs(eigenvals), axis=-1)
        max_eigval[x, y, z] = eigenvals[ix, max_idx]
        max_eigvec[x, y, z] = eigenvecs[ix, :, max_idx]

    max_eigval = ndimage.gaussian_filter(max_eigval, sigma=1.0)
    return nonmax_suppression_trilinear(
        max_eigval, max_eigvec[..., 0], max_eigvec[..., 1], max_eigvec[..., 2], mask
    )


def nonmax_suppression_trilinear(
    values: np.ndarray,
    vx: np.ndarray,
    vy: np.ndarray,
    vz: np.ndarray,
    mask: np.ndarray,
    interp_factor: float = 0.71,
) -> np.ndarray:
    """
    Perform non-maximum suppression with trilinear interpolation along principal directions.

    Identifies local maxima by comparing each voxel's value to interpolated values along
    the forward and backward directions of its principal eigenvector. Voxels that are
    local maxima are retained in the skeleton.

    Parameters
    ----------
    values : np.ndarray
        3D array of eigenvalues at each voxel.
    vx : np.ndarray
        X-component of the principal eigenvector at each voxel.
    vy : np.ndarray
        Y-component of the principal eigenvector at each voxel.
    vz : np.ndarray
        Z-component of the principal eigenvector at each voxel.
    mask : np.ndarray
        Binary mask indicating regions of interest (1 for foreground, 0 for background).
    interp_factor : float, optional
        Interpolation distance factor along eigenvector direction. Default is 0.71.

    Returns
    -------
    np.ndarray
        Binary 3D array where True indicates skeleton voxels (local maxima).

    Notes
    -----
    A 1-voxel margin is excluded from processing to avoid edge effects. Trilinear
    interpolation is used for sub-voxel precision when comparing along eigenvector
    directions.

    References
    ----------
    .. [1]  Martinez-Sanchez, A. et al (2014) JSB,
            https://doi.org/10.1016/j.jsb.2014.02.015
    .. [2]  Lamm, L. et al. (2024) bioRxiv, doi.org/10.1101/2024.01.05.574336.
    """
    subset = tuple(slice(1, s - 1) for s in values.shape)
    inner_mask = np.zeros_like(mask)
    inner_mask[subset] = mask[subset]

    coords = np.argwhere(inner_mask)

    x, y, z = coords.T
    val = values[x, y, z]
    dx = np.abs(vx[x, y, z] * interp_factor)
    dy = np.abs(vy[x, y, z] * interp_factor)
    dz = np.abs(vz[x, y, z] * interp_factor)

    fx = x + np.sign(vx[x, y, z]).astype(int)
    fy = y + np.sign(vy[x, y, z]).astype(int)
    fz = z + np.sign(vz[x, y, z]).astype(int)

    bx = x - np.sign(vx[x, y, z]).astype(int)
    by = y - np.sign(vy[x, y, z]).astype(int)
    bz = z - np.sign(vz[x, y, z]).astype(int)

    val_forward = (
        values[x, y, z] * (1 - dx) * (1 - dy) * (1 - dz)
        + values[fx, y, z] * dx * (1 - dy) * (1 - dz)
        + values[x, fy, z] * (1 - dx) * dy * (1 - dz)
        + values[x, y, fz] * (1 - dx) * (1 - dy) * dz
        + values[fx, fy, z] * dx * dy * (1 - dz)
        + values[fx, y, fz] * dx * (1 - dy) * dz
        + values[x, fy, fz] * (1 - dx) * dy * dz
        + values[fx, fy, fz] * dx * dy * dz
    )
    val_backward = (
        values[x, y, z] * (1 - dx) * (1 - dy) * (1 - dz)
        + values[bx, y, z] * dx * (1 - dy) * (1 - dz)
        + values[x, by, z] * (1 - dx) * dy * (1 - dz)
        + values[x, y, bz] * (1 - dx) * (1 - dy) * dz
        + values[bx, by, z] * dx * dy * (1 - dz)
        + values[bx, y, bz] * dx * (1 - dy) * dz
        + values[x, by, bz] * (1 - dx) * dy * dz
        + values[bx, by, bz] * dx * dy * dz
    )
    is_max = (val > val_forward) & (val > val_backward)

    result = np.zeros_like(values, dtype=bool)
    result[x[is_max], y[is_max], z[is_max]] = True
    return result
