"""
Processing of Geometry objects.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import List, Optional
from functools import wraps

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


def use_point_data(operation):
    """
    Decorator to ensure operations work on underlying point cloud data.

    When a geometry is in mesh representation, operations should work on the
    original point cloud data (stored in _point_data), not the mesh vertices.
    This decorator handles that conversion.
    """

    @wraps(operation)
    def wrapper(geometry, *args, **kwargs):
        from .geometry import Geometry

        temp_geometry = geometry
        has_mesh_model = hasattr(geometry.model, "vertices")
        is_mesh_representation = geometry.is_mesh_representation()

        # In this case, geometry.points, normals and quaternions contains the
        # information from the mesh representation. Not the underlying point
        # cloud the object should represent. If we are dealing with an actual
        # model however, its fine to use the geometry attributes directly
        if is_mesh_representation and not has_mesh_model:
            points, normals, quaternions = geometry.get_point_data()
            temp_geometry = Geometry(
                points=points,
                normals=normals,
                quaternions=quaternions,
                sampling_rate=geometry.sampling_rate,
            )

        results = operation(temp_geometry, *args, **kwargs)

        # We do not care about the representation in this case. However when
        # we explicitly start with a surface representation for rendering purposes
        # we make sure this is propagated.
        if not is_mesh_representation or has_mesh_model:
            return results

        if isinstance(results, Geometry):
            results.change_representation("surface")
        elif isinstance(results, (tuple, list)):
            [x.change_representation("surface") for x in results]
        return results

    return wrapper


@use_point_data
def skeletonize(geometry, method: str = "core", sigma: float = 1.0, **kwargs):
    """
    Extract structural skeleton from point cloud.

    Parameters
    ----------
    geometry : :py:class:`mosaic.geometry.Geometry`
        Input data.
    method : {'outer', 'core', 'boundary'}, optional
        Structural feature to extract:
        - 'outer': Outer boundaries
        - 'core': Medial axis/centerline
        - 'boundary': Inner/outer boundaries
        - 'outer_hull': Outer boundaries using a convex hull
    sigma : float, optional
        Gaussian smoothing for Hessian computation.
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
    from .utils import skeletonize as _skeletonize
    from .utils import points_to_volume, volume_to_points

    methods = ("core", "outer", "boundary", "outer_hull")
    if method not in methods:
        supported = ",".join([f"'{x}'" for x in methods])
        raise ValueError(f"method must be {supported} got '{method}'.")

    skeleton_method = method
    if method == "outer":
        skeleton_method = "boundary"

    points = geometry.points
    if method in ("core", "boundary", "outer"):
        vol, offset = points_to_volume(
            geometry.points, geometry.sampling_rate, use_offset=True
        )
        skeleton = _skeletonize(vol, mode=skeleton_method, sigma=sigma)
        points = volume_to_points(skeleton, geometry.sampling_rate)[0]
        points = np.add(points, offset * geometry.sampling_rate)

    if method in ("outer", "outer_hull"):
        hull = ConvexHull.fit(
            points,
            elastic_weight=0,
            curvature_weight=0,
            volume_weight=0,
            voxel_size=geometry.sampling_rate,
        )
        sample_frac = kwargs.get("sample_fraction", 0.5)
        hull_points = hull.sample(int(sample_frac * points.shape[0]))
        _, indices = find_closest_points(points, hull_points)
        points = points[np.unique(indices)]

    return Geometry(points, sampling_rate=geometry.sampling_rate)


@use_point_data
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
        - 'core' : Replace points that fall within radius of each other by theor centroid.
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
    elif method.lower() == "center of mass":
        cutoff = kwargs.get("radius", None)
        if cutoff is None:
            cutoff = 4 * np.max(geometry.sampling_rate)
        normals = None
        points = com_cluster_points(points, cutoff)
    else:
        raise ValueError("Supported are 'radius', 'center of mass', and 'number'.")

    return Geometry(points, normals=normals, sampling_rate=geometry._sampling_rate)


@use_point_data
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


@use_point_data
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

    if (fit := geometry.model) is None:
        return None

    n_samples, extra_kwargs = sampling, {}
    if method != "Points":
        n_samples = fit.points_per_sampling(sampling, normal_offset)
        extra_kwargs["mesh_init_factor"] = 5

    # We handle normal offset in sample to ensure equidistant spacing for meshes
    extra_kwargs["normal_offset"] = normal_offset
    points = fit.sample(int(n_samples), **extra_kwargs, **kwargs)
    normals = fit.compute_normal(points)

    return Geometry(points, normals=normals, sampling_rate=geometry._sampling_rate)


@use_point_data
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

    if downsampling_radius > 0:
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

    if downsampling_radius > 0:
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


@use_point_data
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


@use_point_data
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
        geometry.normals = geometry.normals * -1
    elif method == "Compute":
        geometry.normals = compute_normals(geometry.points, k=k, **kwargs)
    else:
        raise ValueError(f"Unsupported method '{method}'. Use 'Compute' or 'Flip'.")
    return duplicate(geometry)


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
    def register(cls, operation_name: str, func, decorator=None):
        """Register an operation function."""
        if decorator is not None:
            func = decorator(func)
        setattr(cls, operation_name, staticmethod(func))


for operation_name, operation_func in [
    ("skeletonize", skeletonize),
    ("downsample", downsample),
    ("crop", crop),
    ("sample", sample),
    ("cluster", cluster),
    ("remove_outliers", remove_outliers),
    ("compute_normals", compute_normals),
    ("duplicate", duplicate),
    ("visibility", visibility),
]:
    GeometryOperations.register(operation_name, operation_func)
