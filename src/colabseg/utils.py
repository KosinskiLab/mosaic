import numpy as np
import open3d as o3d
from scipy import spatial


def find_neighbors(points, other_points, distance):
    """
    Find neighboring points within a specified distance.

    Parameters
    ----------
    points : ndarray
        Array of points to search from.
    other_points : ndarray
        Array of query points.
    distance : float
        Maximum distance to consider for neighbors.

    Returns
    -------
    ndarray
        Array of unique neighboring points.
    """
    tree = spatial.cKDTree(points)
    indices = tree.query_ball_point(other_points, distance)

    unique_indices = np.unique(np.concatenate(indices)).astype(int)
    return points[unique_indices]


def dbscan_clustering(points, minimal_dbscsan_size=1000, eps=40, min_points=20):
    """
    Perform DBSCAN clustering on the input points.

    Parameters
    ----------
    points : ndarray
        Input point cloud.
    minimal_dbscsan_size : int, optional
        Minimum cluster size to keep, by default 1000.
    eps : float, optional
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
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    dbscan_labels = np.asarray(pcd.cluster_dbscan(eps=eps, min_points=min_points))

    new_cluster = []
    for label in np.unique(dbscan_labels):
        positions_to_write = np.asarray(pcd.points)[dbscan_labels == label]
        if label == -1:
            continue
        if len(positions_to_write) < minimal_dbscsan_size:
            continue
        new_cluster.append(positions_to_write)

    return np.concatenate(new_cluster)


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
    return points[mask]


def statistical_outlier_removal(points, k_neighbors=100, std_ratio=0.2):
    """
    Remove statistical outliers from the point cloud.

    Parameters
    ----------
    points : ndarray
        Input point cloud.
    k_neighbors : int, optional
        Number of neighbors to use for mean distance estimation, by default 100.
    std_ratio : float, optional
        Standard deviation ratio to identify outliers, by default 0.2.

    Returns
    -------
    ndarray
        Filtered point cloud with outliers removed.
    """
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)

    cl, ind = pcd.remove_statistical_outlier(
        nb_neighbors=k_neighbors, std_ratio=std_ratio
    )

    return np.asarray(cl.points)


def trim(points, trim_min=0, trim_max=0, trim_axis="z"):
    """
    Trim cluster edges along the specified axis.

    Parameters
    ----------
    points : ndarray
        Input point cloud.
    trim_min : float, optional
        Minimum value to trim from the lower bound, by default 0.
    trim_max : float, optional
        Maximum value to trim from the upper bound, by default 0.
    trim_axis : str, optional
        Axis along which to trim ('x', 'y', or 'z'), by default 'z'.

    Returns
    -------
    ndarray
        Trimmed point cloud.

    Raises
    ------
    ValueError
        If an invalid trim_axis is provided.
    """
    axis_map = {"x": 0, "y": 1, "z": 2}

    trim_column = axis_map.get(trim_axis)
    if trim_column is None:
        raise ValueError(f"Value for trim axis must be in {axis_map.keys()}.")

    coordinate_colum = points[:, trim_column]
    mask = np.logical_and(
        coordinate_colum > np.min(coordinate_colum) + trim_min,
        coordinate_colum < np.max(coordinate_colum) - trim_max,
    )

    return points[mask]
