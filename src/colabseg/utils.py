import numpy as np
import open3d as o3d
from scipy import spatial


def dbscan_clustering(points, eps=0.02, min_points=10):
    """
    Perform DBSCAN clustering on the input points.

    Parameters
    ----------
    points : ndarray
        Input point cloud.
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
    pcd.points = o3d.utility.Vector3dVector(points.astype(np.float64))
    pcd = pcd.cluster_dbscan(eps=eps, min_points=min_points)
    dbscan_labels = np.asarray(pcd.points)

    new_cluster = []
    for label in np.unique(dbscan_labels):
        positions_to_write = np.asarray(pcd.points)[dbscan_labels == label]
        if label == -1:
            continue
        new_cluster.append(positions_to_write)

    return np.squeeze(np.array(new_cluster))


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
    ndarray
        Filtered point cloud with outliers removed.
    """
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points.astype(np.float64))

    cl, ind = pcd.remove_statistical_outlier(nb_neighbors=k_neighbors, std_ratio=thresh)
    return np.asarray(cl.points)
