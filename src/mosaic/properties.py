import warnings
from functools import wraps
from typing import Callable, List, Union

import numpy as np
from .geometry import Geometry


def get_mesh(func):
    @wraps(func)
    def wrapper(geometry: Geometry, *args, **kwargs):
        fit = geometry._meta.get("fit")
        if not hasattr(fit, "mesh"):
            return None
        return func(fit, *args, **kwargs)

    return wrapper


@get_mesh
def mesh_curvature(fit, curvature: str, radius: int, **kwargs):
    return fit.compute_curvature(curvature=curvature, radius=radius, **kwargs)


@get_mesh
def mesh_edge_length(fit, **kwargs):
    from .meshing.utils import compute_edge_lengths

    return compute_edge_lengths(fit.mesh)


@get_mesh
def mesh_surface_area(fit, **kwargs):
    return fit.mesh.get_surface_area()


@get_mesh
def mesh_volume(fit, **kwargs):
    return fit.mesh.get_volume()


@get_mesh
def mesh_triangle_area(fit, **kwargs):
    vertices, triangles = fit.vertices, fit.triangles
    v0 = vertices[triangles[:, 0]]
    v1 = vertices[triangles[:, 1]]
    v2 = vertices[triangles[:, 2]]
    return np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1) / 2


@get_mesh
def mesh_triangle_volume(fit, **kwargs):
    vertices, triangles = fit.vertices, fit.triangles
    v0 = vertices[triangles[:, 0]]
    v1 = vertices[triangles[:, 1]]
    v2 = vertices[triangles[:, 2]]
    face_volumes = np.sum(np.cross(v0, v1) * v2, axis=1) / 6.0
    return np.array([np.sum(np.abs(face_volumes))])


@get_mesh
def mesh_vertices(fit, **kwargs):
    return fit.vertices.shape[0]


@get_mesh
def mesh_triangles(fit, **kwargs):
    return fit.triangles.shape[0]


def distance(
    geometry: Geometry,
    queries: List[Union[np.ndarray, Geometry]],
    k: int = 1,
    k_start: int = 1,
    include_self: bool = False,
    *args,
    **kwargs,
):
    from mosaic.utils import find_closest_points

    if not isinstance(queries, List):
        queries = [
            queries,
        ]

    distance = None
    for query in queries:
        if not include_self and id(query) == id(geometry):
            continue

        if isinstance(query, Geometry):
            dist = query.compute_distance(geometry.points, k=k)
        else:
            dist, _ = find_closest_points(query, geometry.points, k=k)

        if distance is None:
            distance = dist
        distance = np.minimum(distance, dist)

    if distance is None:
        return None

    k_start = max(k_start - 1, 0)
    if k_start == k:
        raise ValueError("k_start needs to be smaller than k")

    if distance.ndim == 2:
        distance = distance[(slice(None), slice(k_start, k))].mean(axis=1)

    return distance


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


def projected_curvature(
    geometry: Geometry, queries: List[Geometry], curvature: str, radius: int, **kwargs
):
    if len(queries) == 0:
        return None
    elif len(queries) > 1:
        warnings.warn("Using the first query instance.")

    fit = queries[0]._meta.get("fit")
    if fit is None:
        return None

    curvature = fit.compute_curvature(curvature=curvature, radius=radius, **kwargs)
    _, indices = fit.compute_distance(points=geometry.points, return_indices=True)
    return curvature[indices]


def geodesic_distance(
    geometry: Geometry, queries: List[Geometry], k: int = 1, k_start=1
):
    if len(queries) == 0:
        return None
    elif len(queries) > 1:
        warnings.warn("Using the first query instance.")

    fit = queries[0]._meta.get("fit")
    if fit is None:
        return None

    _, indices = fit.compute_distance(points=geometry.points, return_indices=True)
    distance = fit.geodesic_distance(
        target_vertices=indices, source_vertices=indices, k=k
    )

    k_start = max(k_start - 1, 0)
    if distance.ndim == 2:
        distance = distance[(slice(None), slice(k_start, k))].mean(axis=1)

    return distance


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
        "mesh_edge_length": mesh_edge_length,
        "mesh_surface_area": mesh_surface_area,
        "mesh_triangle_area": mesh_triangle_area,
        "mesh_volume": mesh_volume,
        "mesh_triangle_volume": mesh_triangle_volume,
        "mesh_vertices": mesh_vertices,
        "mesh_triangles": mesh_triangles,
        "projected_curvature": projected_curvature,
        "geodesic_distance": geodesic_distance,
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
            print(f"Unknown property: {property_name}")
            return None

        return func(*args, **kwargs)
