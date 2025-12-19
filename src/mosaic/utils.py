"""
Utility functions.

Copyright (c) 2023-2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from functools import lru_cache
from typing import List, Optional


import numpy as np

from scipy import ndimage
from scipy.spatial import KDTree
from scipy.sparse import coo_matrix
from scipy.spatial.transform import Rotation
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
]

NORMAL_REFERENCE = (0, 0, 1)


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


def cmap_to_vtkctf(cmap, max_value, min_value, gamma: float = 1.0):
    import vtk

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

    # I am not sure why, but having a large number of Rotation objects in scope
    # while within a concurrent.futures worker seems to lock itself, hence we
    # use the intermediate quaternion representation
    rotations = [
        _align_vectors(tuple(b), tuple(t)).as_quat(scalar_first=True)
        for b, t in zip(normals, targets)
    ]
    rotations = Rotation.from_quat(rotations, scalar_first=True)

    func = rotations.as_matrix
    if mode == "quat":
        func = rotations.as_quat
    elif mode == "euler":
        func = rotations.as_euler
    return func(**kwargs)


def apply_quat(quaternions, target=NORMAL_REFERENCE):
    return Rotation.from_quat(quaternions, scalar_first=True).apply(target)


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
