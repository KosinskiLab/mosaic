"""
Processing of Geometry objects.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import List, Optional

import numpy as np

from .registry import (
    Param,
    Method,
    MethodRegistry,
    operation,
    _DECORATED_OPERATIONS,
    _K_NEIGHBORS,
    _FAIRING_PARAMS,
    _HOLE_SIZE,
    _NORMAL_OFFSET,
    _BIDIRECTIONAL,
)

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


@operation(
    methods=(
        Method(
            "core",
            "core",
            params=(
                Param(
                    "sigma",
                    "float",
                    default=1.0,
                    min=0.1,
                    max=10.0,
                    description="Gaussian smoothing for Hessian computation.",
                ),
            ),
        ),
        Method(
            "boundary",
            "boundary",
            params=(
                Param(
                    "sigma",
                    "float",
                    default=1.0,
                    min=0.1,
                    max=10.0,
                    description="Gaussian smoothing for Hessian computation.",
                ),
            ),
        ),
        Method(
            "outer",
            "outer",
            params=(
                Param(
                    "sigma",
                    "float",
                    default=1.0,
                    min=0.1,
                    max=10.0,
                    description="Gaussian smoothing for Hessian computation.",
                ),
            ),
        ),
        Method(
            "outer_hull",
            "outer_hull",
            params=(
                Param(
                    "sample_fraction",
                    "float",
                    default=0.5,
                    min=0.1,
                    max=1.0,
                    description="Fraction of points to sample from convex hull.",
                ),
            ),
        ),
    ),
)
def skeletonize(geometry, method: str = "core", sigma: float = 1.0, **kwargs):
    """
    Extract structural skeleton from point cloud.

    Parameters
    ----------
    geometry : :py:class:`mosaic.geometry.Geometry`
        Input data.
    method : {'outer', 'core', 'boundary'}, optional
        Structural feature to extract:
        - 'core' : Extract medial axis/centerline through the middle of structures
        - 'boundary' : Extract both inner and outer boundaries for hollow structures
        - 'outer' : Extract outer boundary via skeletonization + convex hull
        - 'outer_hull' : Fast convex hull approximation (no skeletonization)
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
    from .parametrization import AlphaShape
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
        hull = AlphaShape.fit(
            points,
            smoothness=0,
            voxel_size=geometry.sampling_rate,
        )
        sample_frac = kwargs.get("sample_fraction", 0.5)
        hull_points = hull.sample(int(sample_frac * points.shape[0]))
        _, indices = find_closest_points(points, hull_points)
        points = points[np.unique(indices)]

    return Geometry(
        points, sampling_rate=geometry.sampling_rate, meta=_get_meta(geometry)
    )


@operation(
    methods=(
        Method(
            "Radius",
            "radius",
            params=(
                Param(
                    "voxel_size",
                    "float",
                    default=40.0,
                    label="Radius",
                    description="Points within this radius are merged into one.",
                ),
            ),
        ),
        Method(
            "Num Points",
            "number",
            params=(
                Param(
                    "size",
                    "int",
                    default=1000,
                    min=1,
                    label="Num Points",
                    description="Randomly selects this many points from the input.",
                ),
            ),
        ),
        Method(
            "Center of Mass",
            "center_of_mass",
            params=(
                Param(
                    "radius",
                    "float",
                    default=40.0,
                    description="Points within this radius are replaced by their centroid.",
                ),
            ),
        ),
    ),
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
        - 'radius' : Uniform voxel grid downsampling
        - 'center_of_mass' : Replace nearby points by their centroid
        - 'number' : Random subsampling to target count
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


@operation(
    methods=(
        Method(
            "Distance",
            "distance",
            params=(
                Param(
                    "sampling",
                    "float",
                    label="Distance",
                    default=40.0,
                    min=1e-6,
                    description="Average distance between points.",
                ),
            ),
        ),
        Method(
            "Num Points",
            "points",
            params=(
                Param(
                    "sampling",
                    "int",
                    label="Number",
                    default=5000,
                    min=1,
                    description="Number of points to sample.",
                ),
            ),
        ),
    ),
    common_params=(
        _NORMAL_OFFSET,
        _BIDIRECTIONAL,
    ),
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
        Sampling method to use:
        - 'distance' : Sample by average inter-point distance
        - 'points' : Sample by total point count
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


@operation(
    common_params=(
        Param(
            "use_points",
            "bool",
            default=True,
            description="Use spatial coordinates for clustering.",
        ),
        Param(
            "use_normals",
            "bool",
            default=False,
            description="Use normal vectors for clustering.",
        ),
        Param(
            "drop_noise",
            "bool",
            default=True,
            description="Drop noise cluster if available.",
        ),
    ),
    methods=(
        Method(
            "Connected Components",
            "connected_components",
            params=(
                Param(
                    "distance",
                    "float",
                    default=-1.0,
                    min=-1.0,
                    max=1e32,
                    description="Distance between points to be considered connected.",
                    notes="Defaults to the associated sampling rate.",
                ),
            ),
        ),
        Method(
            "Envelope",
            "envelope",
            params=(
                Param(
                    "distance",
                    "float",
                    default=-1.0,
                    min=-1.0,
                    max=1e32,
                    description="Distance between points to be considered connected.",
                    notes="Defaults to the associated sampling rate.",
                ),
            ),
        ),
        Method(
            "Leiden",
            "leiden",
            params=(
                Param(
                    "distance",
                    "float",
                    default=-1.0,
                    min=-1.0,
                    max=1e32,
                    description="Distance between points to be considered connected.",
                    notes="Defaults to the associated sampling rate.",
                ),
                Param(
                    "resolution_parameter",
                    "float",
                    default=-7.3,
                    min=-1e32,
                    max=1e32,
                    decimals=8,
                    label="Resolution (log10)",
                    description="Log10 of resolution parameter for graph clustering.",
                    notes="Smaller values yield larger clusters.",
                ),
            ),
        ),
        Method(
            "DBSCAN",
            "dbscan",
            params=(
                Param(
                    "distance",
                    "float",
                    default=-1.0,
                    min=-1.0,
                    description="Neighborhood radius for density estimation.",
                    notes="Defaults to the associated sampling rate.",
                ),
                Param(
                    "min_points",
                    "int",
                    default=10,
                    min=1,
                    description="Minimum number of points to form a cluster.",
                ),
            ),
        ),
        Method(
            "K-Means",
            "kmeans",
            params=(Param("k", "int", default=2, min=1, label="Clusters"),),
        ),
        Method(
            "Birch",
            "birch",
            params=(
                Param(
                    "n_clusters",
                    "int",
                    default=3,
                    min=1,
                    label="Clusters",
                    description="Number of clusters to form.",
                ),
                Param(
                    "distance",
                    "float",
                    default=-1.0,
                    min=-1.0,
                    description="Radius for merging subclusters.",
                    notes="Defaults to the associated sampling rate.",
                ),
            ),
        ),
    ),
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
        - 'Connected Components' : Connected components by spatial proximity
        - 'Envelope' : Envelope-based connected components
        - 'Leiden' : Leiden graph-based clustering
        - 'DBSCAN' : DBSCAN density-based clustering
        - 'K-Means' : K-Means partitioning
        - 'Birch' : Birch hierarchical clustering
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

    distance = kwargs.pop("distance", -1)
    if np.any(np.array(distance) < 0):
        distance = np.max(geometry.sampling_rate)

    if method in ("connected_components", "envelope", "leiden"):
        if distance == 0:
            raise ValueError("Clustering distance must be non-zero.")
        kwargs["distance"] = distance
        points = np.divide(geometry.points, distance)
    elif method == "dbscan":
        kwargs["distance"] = distance
        points = geometry.points
    elif method == "birch":
        kwargs["threshold"] = distance
        points = geometry.points
    else:
        points = geometry.points

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


@operation(
    common_params=(
        Param(
            "k_neighbors",
            "int",
            default=20,
            min=1,
            label="Neighbors",
            description="k-neighbors for estimating local densities.",
        ),
    ),
    methods=(
        Method(
            "statistical",
            "statistical",
            params=(
                Param(
                    "thresh",
                    "float",
                    default=2.0,
                    min=0.01,
                    label="Std. Ratio",
                    description="Points further than this many standard deviations "
                    "from the mean neighbor distance are removed.",
                ),
            ),
        ),
        Method(
            "eigenvalue",
            "eigenvalue",
            params=(
                Param(
                    "thresh",
                    "float",
                    default=0.05,
                    min=0.0,
                    max=1.0,
                    label="Eigenvalue Ratio",
                    description="Minimum ratio of the largest eigenvalue to the sum. "
                    "Points below this threshold are removed.",
                ),
            ),
        ),
    ),
)
def remove_outliers(geometry, method: str = "statistical", **kwargs):
    """
    Remove statistical outliers from point cloud.

    Parameters
    ----------
    geometry : :py:class:`mosaic.geometry.Geometry`
        Input data.
    method : str, optional
        Outlier detection method. Options are:
        - 'statistical' : General statistical outlier removal
        - 'eigenvalue' : Eigenvalue-based edge noise removal
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


@operation(
    methods=(
        Method(
            "Compute",
            "compute",
            params=(
                Param(
                    "k",
                    "int",
                    default=15,
                    min=3,
                    max=100,
                    label="Neighbors",
                    description="Number of neighboring points for normal estimation.",
                ),
            ),
        ),
        Method("Flip", "flip"),
    ),
)
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
        - 'Flip' : Reverse existing normal directions
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


@operation()
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


@operation(
    common_params=(Param("visible", "bool", default=True),),
)
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


@operation(
    methods=(
        Method(
            "Decimation",
            "decimation",
            params=(
                Param(
                    "decimation_method",
                    "str",
                    label="Method",
                    options=("Triangle Count", "Reduction Factor"),
                    default="Reduction Factor",
                    description="How to specify the decimation target.",
                ),
                Param(
                    "sampling",
                    "float",
                    default=10,
                    min=0,
                    description="Numerical value for reduction method.",
                ),
                Param(
                    "smooth",
                    "bool",
                    default=True,
                    description="Use quadratic decimation instead of pyfqmr.",
                ),
            ),
        ),
        Method(
            "Edge Length",
            "edge_length",
            params=(
                Param(
                    "target_edge_length",
                    "float",
                    default=40.0,
                    min=1e-6,
                    label="Edge Length",
                    description="Average edge length to remesh to.",
                ),
                Param(
                    "n_iter",
                    "int",
                    default=100,
                    min=1,
                    label="Iterations",
                    description="Number of remeshing iterations.",
                ),
            ),
        ),
        Method(
            "Subdivide",
            "subdivide",
            params=(
                Param(
                    "number_of_iterations",
                    "int",
                    default=1,
                    min=1,
                    label="Iterations",
                    description="Number of iterations.",
                    notes="Each iteration splits each triangle into four.",
                ),
                Param(
                    "smooth",
                    "bool",
                    default=True,
                    description="Perform smooth midpoint division.",
                ),
            ),
        ),
        Method(
            "Vertex Clustering",
            "vertex_clustering",
            params=(
                Param(
                    "voxel_size",
                    "float",
                    default=40.0,
                    min=1e-6,
                    label="Radius",
                    description="Radius within which vertices are clustered.",
                ),
            ),
        ),
    ),
)
def remesh(geometry, method: str, **kwargs):
    """
    Remesh by edge length, vertex count, or subdivision.

    Parameters
    ----------
    geometry : :py:class:`mosaic.geometry.Geometry`
        Input geometry with a TriangularMesh model.
    method : str
        Remeshing strategy. Options are:
        - 'Decimation' : Reduce triangle count via decimation
        - 'Edge Length' : Remesh to target edge length
        - 'Subdivide' : Subdivide mesh triangles
        - 'Vertex Clustering' : Simplify via vertex clustering

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


@operation(
    methods=(
        Method(
            "Taubin",
            "taubin",
            params=(
                Param(
                    "number_of_iterations",
                    "int",
                    default=10,
                    min=1,
                    label="Iterations",
                    description="Number of smoothing iterations.",
                    notes="Taubin filter prevents mesh shrinkage.",
                ),
            ),
        ),
        Method(
            "Laplacian",
            "laplacian",
            params=(
                Param(
                    "number_of_iterations",
                    "int",
                    default=10,
                    min=1,
                    label="Iterations",
                    description="Number of smoothing iterations.",
                    notes="May lead to mesh shrinkage with high counts.",
                ),
            ),
        ),
        Method(
            "Average",
            "average",
            params=(
                Param(
                    "number_of_iterations",
                    "int",
                    default=5,
                    min=1,
                    label="Iterations",
                    description="Number of smoothing iterations.",
                ),
            ),
        ),
        Method(
            "Fair",
            "fair",
            params=_FAIRING_PARAMS,
        ),
    ),
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
        - 'Taubin' : Volume-preserving Taubin smoothing
        - 'Laplacian' : Laplacian mesh smoothing
        - 'Average' : Simple neighbor averaging

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

    if method == "fair":
        import numpy as np

        vs = mesh.vertices.copy()
        fs = mesh.triangles.copy()
        vids = kwargs.pop("vids", np.arange(len(vs)))
        vs = meshing.fair_mesh(vs, fs, vids, **kwargs)
        mesh = meshing.to_open3d(vs, fs)
    else:
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


@operation(
    methods=(
        Method(
            "Alpha Shape",
            "alpha_shape",
            params=(
                Param(
                    "alpha",
                    "float",
                    default=1.0,
                    description="Alpha-shape parameter.",
                    notes="Large values yield coarser features.",
                ),
                Param(
                    "target_edge_length",
                    "float",
                    default=-1.0,
                    min=-1.0,
                    label="Edge Length",
                    description="Target edge length for remeshing. -1 uses median.",
                ),
                *_FAIRING_PARAMS,
            ),
        ),
        Method(
            "Ball Pivoting",
            "ball_pivoting",
            params=(
                Param(
                    "radii",
                    "str",
                    default="50",
                    description="Ball radii used for surface reconstruction.",
                    notes="Use commas to specify multiple radii, e.g. '50,30.5,10.0'.",
                ),
                _HOLE_SIZE,
                Param(
                    "target_edge_length",
                    "float",
                    default=-1.0,
                    min=-1.0,
                    label="Edge Length",
                    description="Target edge length for remeshing. -1 uses median.",
                ),
                *_FAIRING_PARAMS,
            ),
        ),
        Method(
            "Poisson",
            "poisson",
            params=(
                Param(
                    "depth",
                    "int",
                    default=9,
                    min=1,
                    description="Depth of the Octree for surface reconstruction.",
                ),
                _K_NEIGHBORS,
                Param(
                    "deldist",
                    "float",
                    default=-1.0,
                    min=-1.0,
                    label="Distance",
                    description="Drop vertices further than distance from input.",
                ),
                Param(
                    "density_quantile",
                    "float",
                    default=0.0,
                    min=0.0,
                    max=1.0,
                    label="Density Quantile",
                    description="Remove low-confidence vertices below this quantile.",
                ),
            ),
        ),
        Method(
            "Flying Edges",
            "flying_edges",
            params=(
                Param(
                    "distance",
                    "float",
                    default=-1.0,
                    min=-1.0,
                    max=1e32,
                    description="Distance between points to be considered connected.",
                    notes="Defaults to the sampling rate of the object.",
                ),
                Param(
                    "smoothing_iterations",
                    "int",
                    default=15,
                    min=0,
                    description="Number of windowed sinc smoothing iterations.",
                ),
                Param(
                    "smoothing_strength",
                    "float",
                    default=80.0,
                    min=0.0,
                    max=100.0,
                    description="Smoothing intensity (0 = none, 100 = maximum).",
                ),
                Param(
                    "feature_angle",
                    "float",
                    default=120.0,
                    min=0.0,
                    max=180.0,
                    description="Edges sharper than this angle are preserved.",
                    notes="180 smooths everything, lower values protect more edges.",
                ),
            ),
        ),
        Method("Sphere", "sphere", gui=False),
        Method("Ellipsoid", "ellipsoid", gui=False),
        Method("Cylinder", "cylinder", gui=False),
        Method(
            "RBF",
            "rbf",
            gui=False,
            params=(
                Param(
                    "direction",
                    "str",
                    default="xz",
                    options=("xy", "xz", "yz"),
                    description="Plane of the independent axes.",
                ),
                Param(
                    "function",
                    "str",
                    default="linear",
                    description="Radial basis function type.",
                ),
                Param(
                    "smooth",
                    "int",
                    default=5,
                    description="Smoothing factor for the RBF interpolator.",
                ),
            ),
        ),
        Method(
            "Spline",
            "spline",
            gui=False,
            params=(
                Param(
                    "order",
                    "int",
                    default=1,
                    min=1,
                    max=5,
                    description="Spline degree. 1 = linear, 3 = cubic.",
                ),
            ),
        ),
    ),
)
def fit(geometry, method: str, **kwargs):
    """
    Fit a model to a point cloud.

    Parameters
    ----------
    geometry : :py:class:`mosaic.geometry.Geometry`
        Input point cloud geometry.
    method : str
        Fitting method. Options are:
        - 'alpha_shape' : Alpha-shape based surface reconstruction
        - 'ball_pivoting' : Ball pivoting surface reconstruction
        - 'poisson' : Poisson surface reconstruction
        - 'flying_edges' : Flying edges isosurface extraction
        - 'sphere' : Least-squares sphere
        - 'ellipsoid' : Ellipsoid via eigenvalue decomposition
        - 'cylinder' : Cylinder via PCA and constrained optimization
        - 'rbf' : Radial basis function interpolation
        - 'spline' : Spline curve through control points

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

    if method == "ball_pivoting":
        radii = kwargs.get("radii", None)
        try:
            kwargs["radii"] = [float(x) for x in radii.split(",")]
        except Exception as e:
            raise ValueError(f"Incorrect radius specification {radii}.") from e

    kwargs["voxel_size"] = np.max(geometry.sampling_rate)
    if method == "flying_edges" and kwargs.get("distance", -1) != -1:
        kwargs["voxel_size"] = kwargs.get("distance")

    fit_object = PARAMETRIZATION_TYPE.get(method)
    if fit_object is None:
        raise ValueError(f"{method} is not supported ({PARAMETRIZATION_TYPE.keys()}).")

    n = geometry.get_number_of_points()
    if n < 15 and method in ("sphere", "ellipsoid", "cylinder"):
        raise ValueError(f"Insufficient points for {method} ({n} < 15).")

    fit = fit_object.fit(geometry.points, **kwargs)
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


for _name, _func in _DECORATED_OPERATIONS:
    GeometryOperations.register(_name, _func)
