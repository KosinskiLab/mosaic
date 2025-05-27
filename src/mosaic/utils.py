""" Utility functions.

    Copyright (c) 2023-2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import warnings
from typing import List
from functools import lru_cache

import vtk
import numpy as np
import open3d as o3d

from scipy import spatial
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

__all__ = [
    "points_to_volume",
    "volume_to_points",
    "connected_components",
    "dbscan_clustering",
    "birch_clustering",
    "eigenvalue_outlier_removal",
    "statistical_outlier_removal",
    "find_closest_points",
    "find_closest_points_cutoff",
    "com_cluster_points",
    "compute_bounding_box",
    "cmap_to_vtkctf",
    "get_cmap",
    "normals_to_rot",
    "apply_quat",
    "NORMAL_REFERENCE",
]

NORMAL_REFERENCE = (0, 0, 1)


def points_to_volume(points, sampling_rate=1, shape=None, weight=1, out=None):
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

    Returns
    -------
    ndarray
        volume ndarray of point densities
    """
    positions = np.rint(np.divide(points, sampling_rate)).astype(int)

    if shape is None:
        shape = positions.max(axis=0) + 1

    valid_positions = np.sum(np.logical_and(positions < shape, positions >= 0), axis=1)
    positions = positions[valid_positions == positions.shape[1], :]

    if out is None:
        out = np.zeros(tuple(int(x) for x in shape), dtype=np.float32)

    out[tuple(positions.T)] = weight
    return out


def volume_to_points(volume, sampling_rate, reverse_order: bool = False):
    """
    Convert volumetric representation back to point clouds.

    Parameters
    ----------
    volume : ndarray
        Input volumetric data with cluster labels.
    sampling_rate : float
        Spacing between volume voxels.

    Returns
    -------
    list
        List of point clouds, one for each unique cluster label.
        Returns None if more than 10k clusters are found.
    """

    points = np.where(volume > 0)
    points_cluster = volume[points]

    points = np.array(points, dtype=int).T
    unique_clusters = np.unique(points_cluster)
    if unique_clusters.size > 1e6:
        warnings.warn(
            "Found more than 10k cluster. Make sure you are loading a segmentation."
        )
        return None

    ret = []
    for cluster in unique_clusters:
        indices = np.where(points_cluster == cluster)
        cluster_points = points[indices]

        if reverse_order:
            indices = np.ravel_multi_index(
                cluster_points[:, ::-1].T, volume.shape[::-1]
            )
            cluster_points = cluster_points[np.argsort(indices)]

        cluster_points = np.multiply(cluster_points, sampling_rate)
        ret.append(cluster_points)

    return ret


def binary_opening(points, sampling_rate=1, iterations=1, structure=None, **kwargs):
    """
    Uses binary erosion to break thin connections between structures,
    then applies connected components to identify separate clusters.

    Parameters
    ----------
    points : ndarray
        Input point cloud coordinates.
    sampling_rate : float, optional
        Spacing between volume voxels, by default 1.
    structure : ndarray, optional
        Structuring element. If None, uses 3x3x3 cube, by default None.
    **kwargs
        Additional arguments passed to skimage.measure.label.

    Returns
    -------
    list
        List of point clouds, one for each separated component.
    """
    import numpy as np
    from scipy import ndimage as ndi

    offset = points.min(axis=0)
    volume = points_to_volume(points - offset, sampling_rate=sampling_rate)

    if structure is None:
        structure = np.ones((3, 3, 3), dtype=bool)

    ndi_volume = ndi.binary_opening(
        volume.astype(bool), structure=structure, iterations=iterations
    )
    labels = volume * ndi_volume
    return [x + offset for x in volume_to_points(labels, sampling_rate)]


def connected_components(points, sampling_rate=1, **kwargs):
    """
    Find connected components in point cloud using volumetric analysis.

    Parameters
    ----------
    points : ndarray
        Input point cloud coordinates.
    sampling_rate : float, optional
        Spacing between volume voxels, by default 1.
    **kwargs
        Additional arguments passed to skimage.measure.label.

    Returns
    -------
    list
        List of point clouds, one for each connected component.
    """
    from skimage.measure import label

    offset = points.min(axis=0)
    volume = points_to_volume(points - offset, sampling_rate=sampling_rate)
    labels = label(volume.astype(np.int32), background=0, **kwargs)
    return [x + offset for x in volume_to_points(labels, sampling_rate)]


def dbscan_clustering(points, distance=100.0, min_points=500):
    """
    Perform DBSCAN clustering on the input points.

    Parameters
    ----------
    points : ndarray
        Input point cloud.
    distance : float, optional
        Maximum distance between two samples for one to be considered as in
        the neighborhood of the other, by default 40.
    min_points : int, optional
        Minimum number of samples in a neighborhood for a point to be considered as
        a core point, by default 20.

    Returns
    -------
    list
        List of clusters, where each cluster is an array of points.
    """
    from sklearn.cluster import DBSCAN

    labels = DBSCAN(eps=distance, min_samples=min_points).fit_predict(points)
    return [points[labels == x] for x in np.unique(labels) if x != -1]


def birch_clustering(
    points, n_clusters: int = 3, threshold: float = 0.5, branching_factor: int = 50
):
    """
    Perform Birch clustering on the input points using skimage.

    Parameters
    ----------
    points : ndarray
        Input point cloud.
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
    list
        List of clusters, where each cluster is an array of points.
    """
    from sklearn.cluster import Birch

    labels = Birch(
        n_clusters=n_clusters, threshold=threshold, branching_factor=branching_factor
    ).fit_predict(points)
    return [points[labels == x] for x in np.unique(labels) if x != -1]


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
    ndarray
        Filtered point cloud with outliers removed.

    References
    ----------
    .. [1]  https://github.com/denabazazian/Edge_Extraction/blob/master/Difference_Eigenvalues.py
    """
    tree = spatial.cKDTree(points)
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
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points.astype(np.float64))

    cl, ind = pcd.remove_statistical_outlier(nb_neighbors=k_neighbors, std_ratio=thresh)
    mask = np.zeros(points.shape[0], dtype=bool)
    mask[np.asarray(ind, dtype=int)] = 1
    return mask


def find_closest_points(positions1, positions2, k=1):
    positions1, positions2 = np.asarray(positions1), np.asarray(positions2)

    tree = cKDTree(positions1)
    return tree.query(positions2, k=k)


def find_closest_points_cutoff(positions1, positions2, cutoff=1):
    positions1, positions2 = np.asarray(positions1), np.asarray(positions2)

    tree = cKDTree(positions1)
    return tree.query_ball_point(positions2, cutoff)


def com_cluster_points(positions: np.ndarray, cutoff: float) -> np.ndarray:
    if not isinstance(positions, np.ndarray):
        positions = np.array(positions)

    if isinstance(cutoff, np.ndarray):
        cutoff = np.max(cutoff)

    tree = cKDTree(positions)
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


def cmap_to_vtkctf(cmap, max_value, min_value, gamma: float = 1.0):
    if np.allclose(min_value, max_value):
        offset = 0.01 * max_value + 1e-6
        max_value += offset
        min_value -= offset

    colormap = get_cmap(cmap)
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


@lru_cache(maxsize=128)
def _align_vectors(target, base) -> Rotation:
    try:
        return Rotation.align_vectors(target, base)[0]
    except ValueError:
        return Rotation.from_quat((1, 0, 0, 0), scalar_first=True)


def normals_to_rot(normals, target=NORMAL_REFERENCE, mode: str = "quat", **kwargs):
    normals = np.atleast_2d(normals)
    targets = np.atleast_2d(target)

    if targets.shape[0] != normals.shape[0]:
        targets = np.repeat(targets, normals.shape[0] // targets.shape[0], axis=0)

    if targets.shape != normals.shape:
        raise ValueError(
            "Incorrect input. Either specifiy a single target or one per normal."
        )

    rotations = Rotation.concatenate(
        [_align_vectors(tuple(t), tuple(b)) for b, t in zip(normals, targets)]
    ).inv()
    func = rotations.as_matrix
    if mode == "quat":
        func = rotations.as_quat
    elif mode == "euler":
        func = rotations.as_euler
    return func(**kwargs)


def apply_quat(quaternions, target=NORMAL_REFERENCE):
    return Rotation.from_quat(quaternions, scalar_first=True).apply(target)
