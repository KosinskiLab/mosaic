import numpy as np
import open3d as o3d
from scipy import spatial
from skimage import measure


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


def volume_to_points(volume, sampling_rate):
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

    points = np.multiply(np.array(points).T, sampling_rate)
    unique_clusters = np.unique(points_cluster)
    if unique_clusters.size > 10000:
        warnings.warn(
            "Found more than 10k cluster. Make sure you are loading a segmentation."
        )
        return None

    ret = []
    for cluster in unique_clusters:
        indices = np.where(points_cluster == cluster)
        ret.append(points[indices])

    return ret


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
    volume, origin = points_to_volume(points, sampling_rate=sampling_rate)
    labels = measure.label(volume.astype(np.int32), background=0, **kwargs)
    return volume_to_points(labels, sampling_rate)


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
    dbscan_labels = np.asarray(pcd.cluster_dbscan(eps=eps, min_points=min_points))

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
