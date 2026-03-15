"""
Processing of Geometry objects.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import List, Optional

import numpy as np

from .registry import MethodRegistry

from . import meshing
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


def _get_meta(geometry):
    name = geometry._meta.get("name", None)
    if name is None:
        return {}
    return {"name": name}


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

    method = MethodRegistry.resolve_method("skeletonize", method).lower()
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

    return Geometry(
        points, sampling_rate=geometry.sampling_rate, meta=_get_meta(geometry)
    )


def downsample(geometry, method: str = "radius", **kwargs):
    """
    Downsample point cloud.

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

    method = MethodRegistry.resolve_method("downsample", method).lower()
    points, normals = geometry.points, geometry.normals
    if method == "radius":
        import open3d as o3d

        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        pcd.normals = o3d.utility.Vector3dVector(normals)

        pcd = pcd.voxel_down_sample(**kwargs)
        points = np.asarray(pcd.points)
        normals = np.asarray(pcd.normals)
    elif method == "number":
        size = kwargs.get("size", 1000)
        size = min(size, points.shape[0])
        keep = np.random.choice(range(points.shape[0]), replace=False, size=size)
        points, normals = points[keep], normals[keep]
    elif method in ("center_of_mass", "center of mass"):
        cutoff = kwargs.get("radius", None)
        if cutoff is None:
            cutoff = 4 * np.max(geometry.sampling_rate)
        normals = None
        points = com_cluster_points(points, cutoff)
    else:
        raise ValueError("Supported are 'radius', 'center of mass', and 'number'.")

    return Geometry(
        points,
        normals=normals,
        sampling_rate=geometry.sampling_rate,
        meta=_get_meta(geometry),
    )


def sample(
    geometry,
    sampling: float,
    method: str,
    normal_offset: float = 0.0,
    bidirectional: bool = False,
    **kwargs,
):
    """
    Sample points from a fitted model.

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
    bidirectional : bool, optional
        Draw inward and outward facing points at the same time. This doubles the
        total number of points. Default is False.

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

    method = method.lower()
    n_samples, extra_kwargs = sampling, {}
    if method != "points":
        n_samples = fit.points_per_sampling(sampling, normal_offset)
        extra_kwargs["mesh_init_factor"] = 5

    # We handle normal offset in sample to ensure equidistant spacing for meshes
    extra_kwargs["normal_offset"] = normal_offset
    points = fit.sample(int(n_samples), **extra_kwargs, **kwargs)
    normals = fit.compute_normal(points)

    if bidirectional:
        extra_kwargs["normal_offset"] = -normal_offset
        new_points = fit.sample(int(n_samples), **extra_kwargs, **kwargs)
        new_normals = -1 * fit.compute_normal(points)
        points = np.concatenate([points, new_points])
        normals = np.concatenate([normals, new_normals])
    return Geometry(
        points,
        normals=normals,
        sampling_rate=geometry.sampling_rate,
        meta=_get_meta(geometry),
    )


def cluster(
    geometry,
    method: str,
    drop_noise: bool = False,
    use_points: bool = True,
    use_normals: bool = False,
    **kwargs,
) -> List:
    """
    Partition points into clusters.

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
    _func_mapping = {
        "connected_components": connected_components,
        "envelope": envelope_components,
        "leiden": leiden_clustering,
        "dbscan": dbscan_clustering,
        "kmeans": kmeans_clustering,
        "birch": birch_clustering,
    }
    method = MethodRegistry.resolve_method("cluster", method)
    func = _func_mapping.get(method)
    if func is None:
        raise ValueError(
            f"Method must be one of {list(_func_mapping.keys())}, got '{method}'."
        )

    distance = geometry.sampling_rate
    if method in ("connected_components", "envelope", "leiden"):
        distance = kwargs.pop("distance", -1)
        if np.any(np.array(distance) < 0):
            distance = geometry.sampling_rate
        kwargs["distance"] = distance

    points = np.divide(geometry.points, distance)

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

    # Create geometry objects for each cluster
    ret = []
    for label in unique_labels:
        if label == -1 and drop_noise:
            continue
        cluster_geom = geometry[labels == label]
        cluster_geom._meta.pop("name", None)
        ret.append(cluster_geom)
    return ret


def remove_outliers(geometry, method: str = "statistical", **kwargs):
    """
    Remove statistical outliers from point cloud.

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
    method = MethodRegistry.resolve_method("remove_outliers", method).lower()
    func = statistical_outlier_removal
    if method == "eigenvalue":
        func = eigenvalue_outlier_removal
    elif method != "statistical":
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
    Compute or flip point normals.

    Parameters
    ----------
    geometry : :py:class:`mosaic.geometry.Geometry`
        Input data.
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

    Returns
    -------
    Geometry
        A duplicate of the input geometry with updated normals.
    """
    from .utils import compute_normals

    method = MethodRegistry.resolve_method("compute_normals", method).lower()
    if method == "flip":
        geometry.normals = geometry.normals * -1
    elif method == "compute":
        geometry.normals = compute_normals(geometry.points, k=k, **kwargs)
    else:
        raise ValueError(f"Unsupported method '{method}'. Use 'compute' or 'flip'.")
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
    Change geometry visibility.

    Parameters
    ----------
    geometry : :py:class:`mosaic.geometry.Geometry`
        Target geometry.
    visible : bool, optional
        Whether the geometry should be visible. Default is True.
    """
    geometry.set_visibility(visible)


def remesh(geometry, method: str, **kwargs):
    """
    Remesh by edge length, vertex count, or subdivision.

    Parameters
    ----------
    geometry : :py:class:`mosaic.geometry.Geometry`
        Input geometry with a TriangularMesh model.
    method : str
        Remeshing strategy. Options are:
        - 'Edge Length' : Isotropic remeshing to target edge length
        - 'Vertex Clustering' : Simplify by merging nearby vertices
        - 'Subdivide' : Increase resolution via midpoint or Loop subdivision
        - 'Decimation' : Reduce triangle count via quadric or fast decimation
    target_edge_length : float, optional
        Target edge length for 'Edge Length' method.
    voxel_size : float, optional
        Voxel size for 'Vertex Clustering' method.
    number_of_iterations : int, optional
        Iteration count for 'Subdivide' method.
    sampling : int, optional
        Target triangle count for 'Decimation' method.
    decimation_method : str, optional
        Either 'Triangle Count' or 'Reduction Factor'. Default is 'Triangle Count'.
    smooth : bool, optional
        For 'Subdivide': use Loop subdivision instead of midpoint.
        For 'Decimation': use quadric decimation. Default is False.

    Returns
    -------
    :py:class:`mosaic.geometry.Geometry` or None
        Remeshed geometry, or None if input has no mesh model.
    """
    from .geometry import Geometry
    from .parametrization import TriangularMesh

    if not isinstance(mesh := geometry.model, TriangularMesh):
        return None

    method = MethodRegistry.resolve_method("remesh", method).lower()
    mesh = meshing.to_open3d(mesh.vertices.copy(), mesh.triangles.copy())
    if method == "edge_length" or method == "edge length":
        mesh = meshing.remesh(mesh=mesh, **kwargs)
    elif method == "vertex_clustering" or method == "vertex clustering":
        mesh = mesh.simplify_vertex_clustering(**kwargs)
    elif method == "subdivide":
        func = mesh.subdivide_midpoint
        if kwargs.get("smooth"):
            func = mesh.subdivide_loop
        kwargs = {k: v for k, v in kwargs.items() if k != "smooth"}
        mesh = func(**kwargs)
    elif method == "decimation":
        dec_method = kwargs.get("decimation_method", "Triangle Count").lower()
        sampling = kwargs.get("sampling")
        if dec_method == "reduction factor":
            sampling = np.asarray(mesh.triangles).shape[0] // sampling

        if kwargs.get("smooth", False):
            mesh = mesh.simplify_quadric_decimation(int(sampling))
        else:
            import pyfqmr

            simplifier = pyfqmr.Simplify()
            simplifier.setMesh(np.asarray(mesh.vertices), np.asarray(mesh.triangles))
            simplifier.simplify_mesh(
                target_count=int(sampling),
                aggressiveness=5.5,
                preserve_border=True,
                verbose=False,
            )

            vertices, faces, normals = simplifier.getMesh()
            mesh = meshing.to_open3d(vertices, faces)
    else:
        raise ValueError(f"Unsupported remeshing method: {method}")

    return Geometry(
        model=TriangularMesh(mesh),
        sampling_rate=geometry.sampling_rate,
        meta=_get_meta(geometry),
    )


def smooth(geometry, method: str, **kwargs):
    """
    Smooth a triangle mesh.

    Parameters
    ----------
    geometry : :py:class:`mosaic.geometry.Geometry`
        Input geometry with a TriangularMesh model.
    method : str
        Smoothing algorithm. Options are:
        - 'Taubin' : Taubin smoothing (volume-preserving)
        - 'Laplacian' : Laplacian smoothing
        - 'Average' : Simple neighbor averaging
    n_iterations : int, optional
        Number of smoothing iterations. Default is 10.

    Returns
    -------
    :py:class:`mosaic.geometry.Geometry` or None
        Smoothed geometry, or None if input has no mesh model.
    """
    from .geometry import Geometry
    from .parametrization import TriangularMesh

    if not isinstance(mesh := geometry.model, TriangularMesh):
        return None

    method = MethodRegistry.resolve_method("smooth", method).lower()
    mesh = meshing.to_open3d(mesh.vertices.copy(), mesh.triangles.copy())
    n_iterations = int(kwargs.get("number_of_iterations", 10))
    if method == "taubin":
        mesh = mesh.filter_smooth_taubin(n_iterations)
    elif method == "laplacian":
        mesh = mesh.filter_smooth_laplacian(n_iterations)
    elif method == "average":
        mesh = mesh.filter_smooth_simple(n_iterations)
    else:
        raise ValueError(f"Unsupported smoothing method: {method}")

    return Geometry(model=TriangularMesh(mesh), sampling_rate=geometry.sampling_rate)


def fit(geometry, method: str, **kwargs):
    """
    Fit a model to a point cloud.

    Parameters
    ----------
    geometry : :py:class:`mosaic.geometry.Geometry`
        Input point cloud geometry.
    method : str
        Fitting method. Options are:
        - 'sphere' : Sphere fit
        - 'ellipsoid' : Ellipsoid fit
        - 'cylinder' : Cylinder fit
        - 'rbf' : Radial basis function interpolation
        - 'spline' : Spline curve fit
        - 'convexhull' : Convex hull (Alpha Shape)
        - 'mesh' : Ball pivoting surface reconstruction
        - 'poissonmesh' : Poisson surface reconstruction
        - 'clusterballpivoting' : Cluster-based ball pivoting
        - 'flyingedges' : Flying edges isosurface extraction

    Returns
    -------
    :py:class:`mosaic.geometry.Geometry`
        Geometry with fitted model attached.

    Raises
    ------
    ValueError
        If method is unsupported or point count is insufficient (<50).
    """
    from .geometry import Geometry
    from .parametrization import PARAMETRIZATION_TYPE

    method = MethodRegistry.resolve_method("fit", method)

    if method == "mesh":
        radii = kwargs.get("radii", None)
        try:
            kwargs["radii"] = [float(x) for x in radii.split(",")]
        except Exception as e:
            raise ValueError(f"Incorrect radius specification {radii}.") from e

    kwargs["voxel_size"] = np.max(geometry.sampling_rate)
    if method == "flyingedges" and kwargs.get("distance", -1) != -1:
        kwargs["voxel_size"] = kwargs.get("distance")

    fit_object = PARAMETRIZATION_TYPE.get(method)
    if fit_object is None:
        raise ValueError(f"{method} is not supported ({PARAMETRIZATION_TYPE.keys()}).")

    points = geometry.points

    n = points.shape[0]
    if n < 50 and method not in ["convexhull", "spline"]:
        raise ValueError(f"Insufficient points for fit ({n}<50).")

    fit = fit_object.fit(points, **kwargs)
    if hasattr(fit, "mesh"):
        new_points = fit.vertices
        normals = fit.compute_vertex_normals()
    else:
        new_points = fit.sample(n_samples=1000)
        normals = fit.compute_normal(new_points)

    return Geometry(
        points=new_points,
        normals=normals,
        sampling_rate=geometry.sampling_rate,
        model=fit,
        meta=_get_meta(geometry),
    )


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
    ("sample", sample),
    ("cluster", cluster),
    ("remove_outliers", remove_outliers),
    ("compute_normals", compute_normals),
    ("duplicate", duplicate),
    ("visibility", visibility),
    ("remesh", remesh),
    ("smooth", smooth),
    ("fit", fit),
]:
    GeometryOperations.register(operation_name, operation_func)
