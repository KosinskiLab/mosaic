"""
Processing of Geometry objects.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import List, Optional

import numpy as np
from .utils import (
    statistical_outlier_removal,
    eigenvalue_outlier_removal,
    com_cluster_points,
    find_closest_points,
    connected_components,
    envelope_components,
    leiden_clustering,
    dbscan_clustering,
    birch_clustering,
    kmeans_clustering,
)

__all__ = ["GeometryOperations"]


def decimate(geometry, method: str = "core", **kwargs):
    """
    Reduces the number of points in a point cloud by keeping only representative
    points based on the selected method.

    Parameters
    ----------
    geometry : :py:class:`mosaic.geometry.Geometry`
        Input data.
    method : str, optional
        Method to use. Options are:
        - 'outer' : Keep outer hull points using convex hull
        - 'core' : Keep core points using clustering
        - 'inner' : Keep inner points using spherical ray-casting
        Default is 'core'.
    **kwargs
        Additional arguments passed to the chosen method.

    Returns
    -------
    :py:class:`mosaic.geometry.Geometry`
        Decimated geometry.

    Raises
    ------
    ValueError
        If unsupported method is specified.
    """
    from .geometry import Geometry
    from .parametrization import ConvexHull

    points = geometry.points

    if method == "core":
        cutoff = kwargs.get("cutoff", None)
        if cutoff is None:
            cutoff = 4 * np.max(geometry._sampling_rate)

        points = com_cluster_points(points, cutoff)
    elif method == "outer":
        hull = ConvexHull.fit(
            points,
            elastic_weight=0,
            curvature_weight=0,
            volume_weight=0,
            voxel_size=geometry._sampling_rate,
        )
        hull_points = hull.sample(int(0.5 * points.shape[0]))
        _, indices = find_closest_points(points, hull_points)
        points = points[np.unique(indices)]
    elif method == "inner":
        # Budget ray-casting using spherical coordinates
        centroid = np.mean(points, axis=0)
        centered_points = points - centroid

        r = np.linalg.norm(centered_points, axis=1)
        theta = np.arccos(centered_points[:, 2] / r)
        phi = np.arctan2(centered_points[:, 1], centered_points[:, 0])

        n_phi_bins = 360
        theta_idx = np.digitize(theta, np.linspace(0, np.pi, n_phi_bins // 2))
        phi_idx = np.digitize(phi, np.linspace(-np.pi, np.pi, n_phi_bins))
        bin_id = theta_idx * n_phi_bins + phi_idx

        inner_indices = []
        for b in np.unique(bin_id):
            mask = np.where(bin_id == b)[0]
            inner_indices.append(mask[np.argmin(r[mask])])

        points = points[inner_indices]
    else:
        raise ValueError("Supported methods are 'inner', 'core' and 'outer'.")

    return Geometry(points, sampling_rate=geometry._sampling_rate)


def downsample(geometry, method: str = "radius", **kwargs):
    """
    Reduces point density by removing points based on spatial or random criteria.

    Parameters
    ----------
    geometry : :py:class:`mosaic.geometry.Geometry`
        Input data.
    method : str, optional
        Method to use. Options are:
        - 'radius' : Remove points that fall within radius of each other using voxel downsampling
        - 'number' : Randomly subsample points to target number
        Default is 'radius'.
    **kwargs
        Additional arguments passed to the chosen method:
        - For 'radius': voxel_size parameter for open3d.voxel_down_sample
        - For 'number': size parameter specifying target number of points

    Returns
    -------
    :py:class:`mosaic.geometry.Geometry`
        Downsampled geometry.
    """
    from .geometry import Geometry

    points, normals = geometry.points, geometry.normals

    if method.lower() == "radius":
        import open3d as o3d

        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        pcd.normals = o3d.utility.Vector3dVector(normals)
        pcd = pcd.voxel_down_sample(**kwargs)
        points = np.asarray(pcd.points)
        normals = np.asarray(pcd.normals)
    elif method.lower() == "number":
        size = kwargs.get("size", 1000)
        size = min(size, points.shape[0])
        keep = np.random.choice(range(points.shape[0]), replace=False, size=size)
        points, normals = points[keep], normals[keep]
    else:
        raise ValueError("Supported methods are 'radius' and 'number'.")

    return Geometry(points, normals=normals, sampling_rate=geometry._sampling_rate)


def crop(geometry, distance: float, query: np.ndarray, keep_smaller: bool = True):
    """
    Filters points based on their distance to a set of query points.

    Parameters
    ----------
    geometry : :py:class:`mosaic.geometry.Geometry`
        Input data.
    distance : float
        Distance threshold for cropping.
    query : np.ndarray
        Points to compute distances to.
    keep_smaller : bool, optional
        If True, keep points closer than distance threshold.
        If False, keep points farther than distance threshold.
        Default is True.

    Returns
    -------
    :py:class:`mosaic.geometry.Geometry`
        Cropped geometry.
    """
    dist = geometry.compute_distance(query_points=query, cutoff=distance)
    if keep_smaller:
        mask = dist < distance
    else:
        mask = dist >= distance

    return geometry[mask]


def sample(
    geometry, sampling: float, method: str, normal_offset: float = 0.0, **kwargs
):
    """
    Generates new points by sampling from a fitted parametric model.

    Parameters
    ----------
    geometry : :py:class:`mosaic.geometry.Geometry`
        Input data.
    sampling : float
        Sampling rate or number of points to generate.
    method : str
        Sampling method to use. If not "N points", sampling is interpreted
        as a rate and converted to number of points.
    normal_offset : float, optional
        Point offset along normal vector, defaults to 0.0.

    Returns
    -------
    :py:class:`mosaic.geometry.Geometry`
        Sampled geometry.

    Raises
    ------
    ValueError
        If geometry has no fitted model.
    """
    from .geometry import Geometry

    fit = geometry._meta.get("fit", None)
    if fit is None:
        return None

    n_samples, extra_kwargs = sampling, {}
    if method != "Points":
        n_samples = fit.points_per_sampling(sampling)
        extra_kwargs["mesh_init_factor"] = 5

    # We handle normal offset in sample to ensure equidistant spacing for meshes
    extra_kwargs["normal_offset"] = normal_offset
    points = fit.sample(int(n_samples), **extra_kwargs, **kwargs)
    normals = fit.compute_normal(points)

    return Geometry(points, normals=normals, sampling_rate=geometry._sampling_rate)


def trim(geometry, min_value: float, max_value: float, axis: str = "z"):
    """
    Filters points that fall within specified bounds along a coordinate axis.

    Parameters
    ----------
    geometry : :py:class:`mosaic.geometry.Geometry`
        Input data.
    min_value : float
        Minimum bound value (inclusive).
    max_value : float
        Maximum bound value (inclusive).
    axis : str, optional
        Axis along which to trim ('x', 'y', or 'z').
        Default is 'z'.

    Returns
    -------
    :py:class:`mosaic.geometry.Geometry`
        Trimmed geometry.

    Raises
    ------
    ValueError
        If an invalid axis is provided.
    """
    _axis_map = {"x": 0, "y": 1, "z": 2}

    trim_column = _axis_map.get(axis.lower())
    if trim_column is None:
        raise ValueError(f"Axis must be one of {list(_axis_map.keys())}, got '{axis}'.")

    points = geometry.points
    coordinate_column = points[:, trim_column]
    mask = np.logical_and(
        coordinate_column >= min_value,
        coordinate_column <= max_value,
    )

    return geometry[mask]


def cluster(
    geometry,
    method: str,
    drop_noise: bool = False,
    use_points: bool = True,
    use_normals: bool = False,
    downsampling_radius: float = -1.0,
    **kwargs,
) -> List:
    """
    Partitions points into clusters using the specified clustering algorithm.

    Parameters
    ----------
    geometry : :py:class:`mosaic.geometry.Geometry`
        Input data.
    method : str
        Clustering method to use. Options are:
        - 'DBSCAN' : Density-based clustering
        - 'Birch' : Balanced iterative reducing clustering hierarchy
        - 'K-Means' : K-means clustering
        - 'Connected Components' : Connected component analysis
        - 'Envelope' : Envelope-based clustering
        - 'Leiden' : Leiden community detection
    drop_noise : bool, optional
        If True, drop noise points (label -1) from results.
        Default is False.
    use_points : bool, optional
        If True, use point coordinates for clustering.
        Default is True.
    use_normals : bool, optional
        If True, include normal vectors in clustering features.
        Default is False.
    downsampling_radius : float, optional
        Downsample point cloud based on radius and perform clustering. Subsequently
        all points are assigned to the nearest cluster in the downsampled set.
    **kwargs
        Additional arguments passed to the chosen clustering method.

    Returns
    -------
    List[:py:class:`mosaic.geometry.Geometry`]
        List of geometries, one per cluster.

    Raises
    ------
    ValueError
        If unsupported clustering method is specified or too many clusters found.
    """
    _mapping = {
        "DBSCAN": dbscan_clustering,
        "Birch": birch_clustering,
        "K-Means": kmeans_clustering,
        "Connected Components": connected_components,
        "Envelope": envelope_components,
        "Leiden": leiden_clustering,
    }
    func = _mapping.get(method)
    if func is None:
        raise ValueError(
            f"Method must be one of {list(_mapping.keys())}, got '{method}'."
        )

    points = geometry.points.copy()

    downsample = downsampling_radius > 0
    if downsample:
        downsampled_geometry = downsample(
            geometry, method="radius", voxel_size=downsampling_radius
        )
        points = downsampled_geometry.points

    distance = geometry.sampling_rate
    if method in ("Connected Components", "Envelope", "Leiden"):
        distance = kwargs.pop("distance", -1)
        if np.any(np.array(distance) < 0):
            distance = geometry.sampling_rate
        kwargs["distance"] = distance

    distance = np.maximum(distance, downsampling_radius)
    points = np.divide(points, distance)

    # Prepare feature data for clustering
    data = points
    if use_points and use_normals:
        data = np.concatenate((points, geometry.normals), axis=1)
    elif not use_points and use_normals:
        data = geometry.normals

    labels = func(data, **kwargs)
    unique_labels = np.unique(labels)
    if len(unique_labels) > 10000:
        raise ValueError("Found more than 10k clusters. Try coarser clustering.")

    if downsample:
        _, indices = find_closest_points(downsampled_geometry.points, geometry.points)
        labels = labels[indices]

    # Create geometry objects for each cluster
    result_geometries = []
    for label in unique_labels:
        if label == -1 and drop_noise:
            continue
        cluster_geometry = geometry[labels == label]
        result_geometries.append(cluster_geometry)

    return result_geometries


def remove_outliers(geometry, method: str = "statistical", **kwargs):
    """
    Filters out points that are statistical outliers based on local neighborhoods.

    Parameters
    ----------
    geometry : :py:class:`mosaic.geometry.Geometry`
        Input data.
    method : str, optional
        Outlier detection method. Options are:
        - 'statistical' : Statistical outlier removal based on neighbor distances
        - 'eigenvalue' : Eigenvalue-based outlier removal
        Default is 'statistical'.
    **kwargs
        Additional parameters for outlier removal method.

    Returns
    -------
    :py:class:`mosaic.geometry.Geometry` or None
        Filtered point cloud geometry with outliers removed.
        Returns None if no points remain after filtering.
    """
    func = statistical_outlier_removal
    if method == "eigenvalue":
        func = eigenvalue_outlier_removal
    else:
        if method != "statistical":
            raise ValueError(
                f"Unsupported method '{method}'. Use 'statistical' or 'eigenvalue'."
            )

    mask = func(geometry.points, **kwargs)
    if mask.sum() == 0:
        return None

    return geometry[mask]


def compute_normals(
    geometry, method: str = "Compute", k: int = 15, **kwargs
) -> Optional:
    """
    Calculates normals for points or flips existing normals.

    Parameters
    ----------
    geometry : :py:class:`mosaic.geometry.Geometry`
        Input data. This geometry object is modified in-place.
    method : str, optional
        Normal computation method. Options are:
        - 'Compute' : Calculate new normals from point neighborhoods
        - 'Flip' : Flip existing normals (multiply by -1)
        Default is 'Compute'.
    k : int, optional
        Number of neighbors to consider for normal computation.
        Only used when method='Compute'. Default is 15.
    **kwargs
        Additional parameters for normal computation.
    """
    from .utils import compute_normals

    if method == "Flip":
        geometry.normals *= -1
        return None
    elif method == "Compute":
        geometry.normals = compute_normals(geometry.points, k=k, **kwargs)
        return None
    else:
        raise ValueError(f"Unsupported method '{method}'. Use 'Compute' or 'Flip'.")


def duplicate(geometry, **kwargs):
    """
    Duplicate a geometry.

    Parameters
    ----------
    geometry : :py:class:`mosaic.geometry.Geometry`
        Geometry to duplicate.

    Returns
    -------
    :py:class:`mosaic.geometry.Geometry`
        Duplicated geometry.
    """
    return geometry[...]


def visibility(geometry, visible: bool = True, **kwargs):
    """
    Change the visibility of a geometry object

    Parameters
    ----------
    geometry : :py:class:`mosaic.geometry.Geometry`
        Geometry to duplicate.
    visible: bool, optional
        Whether the Geometry instance should be visible or not.
    """
    geometry.set_visibility(visible)


class GeometryOperations:
    """Registry for geometry operation functions."""

    @classmethod
    def register(cls, operation_name: str, func):
        """Register an operation function."""
        setattr(cls, operation_name, staticmethod(func))


for operation_name, operation_func in [
    ("decimate", decimate),
    ("downsample", downsample),
    ("crop", crop),
    ("sample", sample),
    ("trim", trim),
    ("cluster", cluster),
    ("remove_outliers", remove_outliers),
    ("compute_normals", compute_normals),
    ("duplicate", duplicate),
    ("visibility", visibility),
]:
    GeometryOperations.register(operation_name, operation_func)
