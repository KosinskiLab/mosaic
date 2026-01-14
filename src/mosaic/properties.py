import warnings
from functools import wraps
from typing import Callable, List, Union

import numpy as np
from .geometry import Geometry

__all__ = ["GeometryProperties"]


def get_mesh(func):
    @wraps(func)
    def wrapper(geometry: Geometry, *args, **kwargs):
        fit = geometry.model
        if not hasattr(fit, "mesh"):
            return None
        return func(fit, *args, **kwargs)

    return wrapper


def _aggregate(data, mode: str):
    """
    Aggregate data based on mode.

    Parameters
    ----------
    data : np.ndarray
        Data to aggregate. Can be shape (n,) or (n, d). Will only aggregate
        data of shape (n, d).
    mode : str
        Aggregation mode, supported are 'mean', 'min', 'max' and 'median'.

    Returns
    -------
    np.ndarray
        Aggregated data with shape (n,)
    """
    mode = mode.lower()
    if data.ndim == 2:
        if mode == "mean":
            data = data.mean(axis=1)
        elif mode == "min":
            data = data.min(axis=1)
        elif mode == "max":
            data = data.max(axis=1)
        elif mode == "median":
            data = np.median(data, axis=1)
    return data


@get_mesh
def mesh_curvature(fit, curvature: str, radius: int, **kwargs):
    return fit.compute_curvature(curvature=curvature, radius=radius, **kwargs)


@get_mesh
def mesh_area(fit, area_type: str = "Total", **kwargs):
    """Compute mesh area.

    Parameters
    ----------
    fit : object
        Fitted mesh model.
    area_type : str
        "Total" for total surface area, "Per-Triangle" for per-triangle areas.

    Returns
    -------
    float or np.ndarray
        Total surface area or array of triangle areas.
    """
    if area_type == "Per-Triangle":
        vertices, triangles = fit.vertices, fit.triangles
        v0 = vertices[triangles[:, 0]]
        v1 = vertices[triangles[:, 1]]
        v2 = vertices[triangles[:, 2]]
        return np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1) / 2
    return fit.mesh.get_surface_area()


@get_mesh
def mesh_volume(fit, volume_type: str = "Total", **kwargs):
    """Compute mesh volume.

    Parameters
    ----------
    fit : object
        Fitted mesh model.
    volume_type : str
        "Total" for total volume, "Per-Triangle" for summed triangle volumes.

    Returns
    -------
    float or np.ndarray
        Total volume or summed absolute triangle volumes.
    """
    if volume_type == "Per-Triangle":
        vertices, triangles = fit.vertices, fit.triangles
        v0 = vertices[triangles[:, 0]]
        v1 = vertices[triangles[:, 1]]
        v2 = vertices[triangles[:, 2]]
        face_volumes = np.sum(np.cross(v0, v1) * v2, axis=1) / 6.0
        return np.array([np.sum(np.abs(face_volumes))])
    return fit.mesh.get_volume()


@get_mesh
def mesh_statistics(fit, stat_type: str = "Vertex Count", **kwargs):
    """Compute mesh statistics.

    Parameters
    ----------
    fit : object
        Fitted mesh model.
    stat_type : str
        "Vertex Count", "Triangle Count", or "Edge Length".

    Returns
    -------
    int or np.ndarray
        Requested mesh statistic.
    """
    if stat_type == "Triangle Count":
        return fit.triangles.shape[0]
    elif stat_type == "Edge Length":
        from .meshing.utils import compute_edge_lengths

        return compute_edge_lengths(fit.mesh)
    return fit.vertices.shape[0]


def distance(
    geometry: Geometry,
    queries: List[Union[np.ndarray, Geometry]] = [],
    k: int = 1,
    k_start: int = 1,
    aggregation: str = "mean",
    include_self: bool = False,
    only_self: bool = False,
    *args,
    **kwargs,
):
    from mosaic.utils import find_closest_points

    if k_start > k:
        raise ValueError("k_start must be <= k")

    if not isinstance(queries, (list, tuple)):
        queries = [queries]

    if only_self:
        queries, include_self = [geometry], True

    distance = None
    for query in queries:
        if not include_self and id(query) == id(geometry):
            continue

        if isinstance(query, Geometry) and hasattr(query.model, "compute_distance"):
            dist = query.model.compute_distance(geometry.points)
        else:
            # Fetch k+1 for self-queries to skip self-match
            is_self_query = False
            if isinstance(query, Geometry):
                is_self_query = query.uuid == geometry.uuid
                query = query.points

            fetch_k = k + 1 if is_self_query else k
            dist, _ = find_closest_points(query, geometry.points, k=fetch_k)
            if is_self_query:
                dist = dist[:, 1:] if dist.ndim == 2 else dist

        if distance is None:
            distance = dist
        distance = np.minimum(distance, dist)

    if distance is None:
        return None

    if distance.ndim == 2:
        distance = distance[:, k_start - 1 : k]
    return _aggregate(distance, mode=aggregation)


def box_size(geometry, axis: int = None):
    shape = geometry.points.max(axis=0) - geometry.points.min(axis=0)
    if axis is None:
        return shape
    return shape[axis]


def width(geometry, *args, **kwargs):
    return geometry.points[:, 0]


def depth(geometry, *args, **kwargs):
    return geometry.points[:, 1]


def height(geometry, *args, **kwargs):
    return geometry.points[:, 2]


def n_points(geometry, *args, **kwargs):
    return geometry.points.shape[0]


def projected_angle(geometry: Geometry, queries: List[Geometry], **kwargs):
    from .parametrization import TriangularMesh

    queries = [x for x in queries if isinstance(x.model, TriangularMesh)]

    if len(queries) == 0:
        return None
    elif len(queries) > 1:
        warnings.warn("Using the first query instance.")

    if (fit := queries[0].model) is None:
        return None

    _, indices = fit.compute_distance(points=geometry.points, return_indices=True)
    normals = fit.compute_vertex_normals()[indices]

    dot = np.sum(np.multiply(normals, geometry.normals), axis=-1)
    return np.degrees(np.arccos(dot))


def projected_curvature(
    geometry: Geometry, queries: List[Geometry], curvature: str, radius: int, **kwargs
):
    if len(queries) == 0:
        return None
    elif len(queries) > 1:
        warnings.warn("Using the first query instance.")

    if (fit := queries[0].model) is None:
        return None

    curvature = fit.compute_curvature(curvature=curvature, radius=radius, **kwargs)
    _, indices = fit.compute_distance(points=geometry.points, return_indices=True)
    return curvature[indices]


def geodesic_distance(
    geometry: Geometry,
    queries: List[Geometry],
    k: int = 1,
    k_start=1,
    aggregation: str = "mean",
):
    if len(queries) == 0:
        return None
    elif len(queries) > 1:
        warnings.warn("Using the first query instance.")

    if (fit := queries[0].model) is None:
        return None

    _, projections, triangles = fit.compute_distance(
        points=geometry.points,
        return_indices=False,
        return_triangles=True,
        return_projection=True,
    )

    mesh, _ = fit.add_projections(projections, triangles, return_indices=True)
    _, idx = mesh.compute_distance(points=projections, return_indices=True)
    distance = mesh.geodesic_distance(target_vertices=idx, source_vertices=idx, k=k)

    if distance.ndim == 2:
        distance = distance[:, max(k_start - 1, 0) : k]
    return _aggregate(distance, mode=aggregation)


def vertex_property(geometry, name: str, *args, **kwargs):
    if geometry.vertex_properties is None:
        return None
    # We copy as safeguard as values may be modified
    return geometry.vertex_properties.get_property(name).copy()


def thickness(
    geometry: Geometry,
    queries: List[Union[np.ndarray, Geometry]] = [],
    smoothing_radius: float = 0.0,
    *args,
    **kwargs,
):
    """
    Estimate point cloud thickness along mesh normals using signed distances.

    Parameters
    ----------
    geometry : Geometry
        Mesh geometry with a fitted model.
    queries : list
        Single cluster geometry to measure thickness from.
    smoothing_radius : float, optional
        Radius for spatial smoothing of thickness values. If > 0, thickness
        at each vertex is averaged with neighbors within this radius.
        Default is 0 (no smoothing).

    Returns
    -------
    np.ndarray
        Thickness values for each vertex.
    """
    model = geometry.model
    if model is None or not hasattr(model, "compute_distance"):
        return None

    if not isinstance(queries, (list, tuple)):
        queries = [queries]

    if len(queries) == 0:
        return None

    query = queries[0]
    cluster_points = query.points if isinstance(query, Geometry) else np.asarray(query)

    signed_dist, triangles = model.compute_distance(
        cluster_points, signed=True, return_triangles=True
    )

    n_triangles = model.triangles.shape[0]
    max_dist = np.full(n_triangles, -np.inf, dtype=np.float32)
    min_dist = np.full(n_triangles, np.inf, dtype=np.float32)
    min_abs_dist = np.full(n_triangles, np.inf, dtype=np.float32)

    np.maximum.at(max_dist, triangles, signed_dist)
    np.minimum.at(min_dist, triangles, signed_dist)
    np.minimum.at(min_abs_dist, triangles, np.abs(signed_dist))

    max_distance = 2.0 * float(np.mean(geometry.sampling_rate))
    drop = (min_abs_dist > max_distance) | (max_dist == -np.inf)

    max_dist[drop] = 0
    min_dist[drop] = 0

    triangle_thickness = max_dist - min_dist

    n_vertices = model.vertices.shape[0]
    vertex_thickness = np.zeros(n_vertices, dtype=np.float32)
    vertex_counts = np.zeros(n_vertices, dtype=np.float32)

    for i in range(3):
        np.add.at(vertex_thickness, model.triangles[:, i], triangle_thickness)
        np.add.at(vertex_counts, model.triangles[:, i], 1)

    vertex_counts = np.maximum(vertex_counts, 1)
    vertex_thickness /= vertex_counts

    if smoothing_radius > 0:
        from scipy.spatial import cKDTree
        from scipy.sparse import csr_matrix

        tree = cKDTree(model.vertices)
        dist_matrix = tree.sparse_distance_matrix(tree, max_distance=smoothing_radius)
        dist_matrix = csr_matrix(dist_matrix)

        sigma = smoothing_radius / 2.0
        weights = dist_matrix.copy()
        weights.data = np.exp(-0.5 * (weights.data / sigma) ** 2)

        # Add self-connections (distance 0 -> weight 1)
        n_vertices = model.vertices.shape[0]
        weights = weights + csr_matrix(np.eye(n_vertices))

        # Weighted average: (W @ thickness) / row_sums
        weighted_sum = weights @ vertex_thickness
        row_sums = np.asarray(weights.sum(axis=1)).ravel()
        vertex_thickness = (weighted_sum / row_sums).astype(np.float32)

    return vertex_thickness


class GeometryProperties:
    """Registry for property calculators."""

    _calculators = {
        "distance": distance,
        "box_size": box_size,
        "width": width,
        "depth": depth,
        "height": height,
        "n_points": n_points,
        "mesh_curvature": mesh_curvature,
        "mesh_area": mesh_area,
        "mesh_volume": mesh_volume,
        "mesh_statistics": mesh_statistics,
        "projected_curvature": projected_curvature,
        "geodesic_distance": geodesic_distance,
        "vertex_property": vertex_property,
        "projected_angle": projected_angle,
        "thickness": thickness,
    }

    @classmethod
    def register(cls, property_name: str, func: Callable):
        """Register a calculator function for a specific property."""
        cls._calculators[property_name] = func

    @classmethod
    def compute(cls, property_name, *args, **kwargs):
        """Compute a property for a geometry object."""
        func = cls._calculators.get(property_name, None)
        if func is None:
            raise ValueError(f"Unknown property: {property_name}")

        return func(*args, **kwargs)
