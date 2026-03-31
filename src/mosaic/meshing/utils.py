"""
Utilities for triangular meshes.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import sys
import h5py
import warnings
import textwrap

from subprocess import run
from typing import List, Dict
from tempfile import NamedTemporaryFile

import numpy as np
import open3d as o3d

__all__ = [
    "to_open3d",
    "compute_edge_lengths",
    "scale",
    "remesh",
    "merge_meshes",
    "equilibrate_edges",
    "compute_scale_factor",
    "compute_scale_factor_lower",
    "center_mesh",
    "to_tsi",
    "fill_mesh",
]


def to_open3d(vertices, faces, normals=None) -> o3d.geometry.TriangleMesh:
    ret = o3d.geometry.TriangleMesh()
    ret.vertices = o3d.utility.Vector3dVector(np.asarray(vertices, dtype=np.float64))
    ret.triangles = o3d.utility.Vector3iVector(np.asarray(faces, dtype=np.int32))
    if normals is not None:
        ret.vertex_normals = o3d.utility.Vector3dVector(
            np.asarray(normals, dtype=np.float64)
        )
    return ret


def _compute_edge_lengths(filename):
    mesh = o3d.io.read_triangle_mesh(filename)
    return compute_edge_lengths(mesh)


def compute_edge_lengths(mesh: o3d.geometry.TriangleMesh) -> np.ndarray:
    return _edge_lengths(
        vertices=np.asarray(mesh.vertices),
        faces=np.asarray(mesh.triangles),
    ).ravel()


def _edge_lengths(vertices, faces):
    vertices = vertices[faces]
    edge_01 = np.linalg.norm(vertices[:, 1] - vertices[:, 0], axis=1)
    edge_02 = np.linalg.norm(vertices[:, 2] - vertices[:, 0], axis=1)
    edge_12 = np.linalg.norm(vertices[:, 2] - vertices[:, 1], axis=1)
    return np.column_stack([edge_01, edge_02, edge_12])


def scale(mesh, scaling):
    vertices = np.multiply(np.asarray(mesh.vertices).copy(), scaling)
    triangles = np.asarray(mesh.triangles).copy()
    return to_open3d(vertices, triangles)


def remesh(mesh, target_edge_length=None, n_iter=100, feature=None):
    """Remesh to target edge length using Botsch-Kobbelt isotropic remeshing.

    Parameters
    ----------
    mesh : open3d.geometry.TriangleMesh
        Input mesh.
    target_edge_length : float, optional
        Desired edge length. None uses the average edge length.
    n_iter : int, optional
        Number of remeshing iterations. Default is 100.
    feature : ndarray, optional
        Indices of feature vertices that are preserved and placed at the
        beginning of the output vertex array. Default is None.
    """
    from gpytoolbox import remesh_botsch

    mesh = mesh.remove_duplicated_vertices()
    mesh = mesh.remove_unreferenced_vertices()
    mesh = mesh.remove_degenerate_triangles()

    v = np.asarray(mesh.vertices, dtype=np.float64)
    f = np.asarray(mesh.triangles, dtype=np.int32)

    if target_edge_length is not None and target_edge_length <= 0:
        target_edge_length = None

    kw = {"h": target_edge_length, "i": n_iter}
    if feature is not None:
        kw["feature"] = np.asarray(feature, dtype=np.int64)

    v_new, f_new = remesh_botsch(v, f, **kw)
    return to_open3d(v_new, f_new)


def merge_meshes(
    vertices: List[np.ndarray],
    faces: List[np.ndarray],
    normals: List[np.ndarray] = None,
):
    if len(vertices) != len(faces):
        raise ValueError("Length of vertex and face list needs to match.")
    elif len(vertices) == 1:
        if normals is not None:
            return *vertices, *faces, *normals
        return *vertices, *faces, None

    faces = [np.asarray(x) for x in faces]
    vertices = [np.asarray(x) for x in vertices]

    vertex_ct = np.zeros(len(vertices) + 1, np.uint32)
    vertex_ct[1:] = np.cumsum([len(x) for x in vertices])

    concat_normals = None
    if normals is not None:
        concat_normals = np.concatenate([np.asarray(x) for x in normals])

    mesh = to_open3d(
        vertices=np.concatenate([x for x in vertices]),
        faces=np.concatenate([face + vertex_ct[i] for i, face in enumerate(faces)]),
        normals=concat_normals,
    )
    mesh = mesh.remove_duplicated_vertices()

    out_normals = None
    if mesh.has_vertex_normals():
        out_normals = np.asarray(mesh.vertex_normals)

    return np.asarray(mesh.vertices), np.asarray(mesh.triangles), out_normals


def equilibrate_edges(mesh, lower_bound, upper_bound, steps=2000, **kwargs):
    default_args = {
        "bond_r": 2,
        "area_fraction": 1.2,
        "volume_fraction": 1.2,
        "kappa_a": 1.0e6,
        "kappa_b": 300.0,
        "kappa_c": 0.0,
        "kappa_v": 1.0e6,
        "kappa_t": 1.0e5,
        "kappa_r": 1.0e3,
        "curvature_fraction": 1.0,
        "continuation_delta": 0.0,
        "continuation_lambda": 1.0,
    }
    default_args.update(kwargs)
    default_args["lc0"] = upper_bound
    default_args["lc1"] = lower_bound

    if lower_bound > upper_bound:
        raise ValueError("upper_bound needs to be larger than lower_bound.")

    with NamedTemporaryFile(suffix=".stl", delete=False) as tfile:
        temp_mesh = tfile.name

    if not mesh.has_triangle_normals():
        mesh = mesh.compute_vertex_normals()

    o3d.io.write_triangle_mesh(temp_mesh, mesh)

    config = textwrap.dedent(
        f"""
        [GENERAL]
        algorithm = minimize
        info = 100
        input = {temp_mesh}
        output_format = vtu

        [BONDS]
        bond_type = Edge
        r = {default_args['bond_r']}
        lc0 = {default_args['lc0']}
        lc1 = {default_args['lc1']}

        [SURFACEREPULSION]
        n_search = cell-list
        rlist = 0.2
        exclusion_level = 2
        refresh = 10
        r = 2

        [ENERGY]
        kappa_a = {default_args['kappa_a']}
        kappa_b = {default_args['kappa_b']}
        kappa_c = {default_args['kappa_c']}
        kappa_v = {default_args['kappa_v']}
        kappa_t = {default_args['kappa_t']}
        kappa_r = {default_args['kappa_r']}
        area_fraction = {default_args['area_fraction']}
        volume_fraction = {default_args['volume_fraction']}
        curvature_fraction = {default_args['curvature_fraction']}
        continuation_delta = {default_args['continuation_delta']}
        continuation_lambda = {default_args['continuation_lambda']}

        [MINIMIZATION]
        maxiter = {steps}
        out_every = 0
    """
    )
    config = config.strip()

    warnings.warn(
        "Running Trimem - Corresponding Citation: "
        "[1] Siggel, M. et al. (2022) J. Chem. Phys, doi.org/10.1063/5.0101118."
    )
    with NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as tfile:
        tfile.write(config)
        tfile.flush()

        ret = run(["mc_app", "run", "--conf", str(tfile.name)], capture_output=True)
        output_file = f"{tfile.name.replace('.conf', '')}.cpt.p0.h5"

        try:
            with h5py.File(output_file, mode="r") as infile:
                faces = infile["cells"][()]
                vertices = infile["points"][()]
        except Exception as e:
            print(f"{str(ret.stderr).strip()}\n\n", file=sys.stderr)
            raise ValueError("Calibration Failed - Check Trimem installation.") from e

    ret = to_open3d(vertices, faces)
    edge_lengths = compute_edge_lengths(ret)
    print(f"Total edges {edge_lengths.size}")
    print(f"Mean edge length {np.mean(edge_lengths)} [+/- {np.std(edge_lengths)}]")

    n_lower = np.sum(edge_lengths < lower_bound - 1)
    n_upper = np.sum(edge_lengths > upper_bound + 1)
    print(f"Requested lower {lower_bound}, actual {edge_lengths.min()} [N={n_lower}]")
    print(f"Requested upper {upper_bound}, actual {edge_lengths.max()} [N={n_upper}]")

    return ret


def compute_scale_factor(mesh, lower_bound=1.0, upper_bound=1.7):
    if lower_bound > upper_bound:
        raise ValueError("lower_bound larger than upper_bound.")

    edge_lengths = compute_edge_lengths(mesh)

    min_val, max_val = np.min(edge_lengths), np.max(edge_lengths)
    bin_edges = np.linspace(min_val, max_val, 1000)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    max_count, peak_bin_center = 0, None
    mean_bound = 1 + (upper_bound - lower_bound) / 2

    for bin_center in bin_centers:
        lb = bin_center * (lower_bound / mean_bound)
        ub = bin_center * (upper_bound / mean_bound)

        count = np.sum(np.logical_and(edge_lengths > lb, edge_lengths < ub))
        if count >= max_count:
            max_count, peak_bin_center = count, bin_center

    count_rel = np.round(100 * max_count / edge_lengths.size, 2)
    scale_factor = mean_bound / peak_bin_center
    print(f"{count_rel}% of edges [N={max_count}] are within range of {scale_factor}")

    return scale_factor


def compute_scale_factor_lower(mesh, lower_bound=1.05):
    edge_lengths = compute_edge_lengths(mesh)
    scale_factor = lower_bound / edge_lengths.min()
    return scale_factor


def center_mesh(mesh, center: bool = True, margin=20):
    vertices = np.asarray(mesh.vertices)

    offset = 0
    if center:
        offset = vertices.min(axis=0) - margin
        offset = np.sign(offset) * np.ceil(np.abs(offset))
        vertices -= offset

    data = to_tsi(vertices, mesh.triangles, margin=margin)
    return data, offset


def to_tsi(vertices, faces, margin: int = 0) -> Dict:
    vertices = np.asarray(vertices)
    faces = np.asarray(faces)

    box_size = tuple(int(x) for x in np.ceil(vertices.max(axis=0) + margin))

    _vertices = np.zeros((vertices.shape[0], 5))
    _vertices[:, 0] = np.arange(_vertices.shape[0])
    _vertices[:, 1:4] = vertices

    _faces = np.zeros((faces.shape[0], 5))
    _faces[:, 0] = np.arange(faces.shape[0])
    _faces[:, 1:4] = faces

    return {
        "version": "1.0a",
        "box": box_size,
        "n_vertices": _vertices.shape[0],
        "vertices": _vertices,
        "n_faces": _faces.shape[0],
        "faces": _faces,
    }


def fill_mesh(vertices, triangles, voxel_size):
    """
    Fill the interior of a closed triangle mesh with regularly spaced points.

    Parameters
    ----------
    vertices : np.ndarray
        Mesh vertex positions (N, 3).
    triangles : np.ndarray
        Mesh triangle indices (M, 3).
    voxel_size : float
        Spacing between interior points.

    Returns
    -------
    interior_points : np.ndarray
        Coordinates of interior points in world space (K, 3).
    """
    vertices = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(triangles, dtype=np.int32)

    padding = voxel_size * 2
    grid_min = vertices.min(axis=0) - padding
    grid_max = vertices.max(axis=0) + padding
    grid_shape = np.ceil((grid_max - grid_min) / voxel_size).astype(int)

    scene = o3d.t.geometry.RaycastingScene()
    mesh_t = o3d.t.geometry.TriangleMesh.from_legacy(to_open3d(vertices, triangles))
    scene.add_triangles(mesh_t)

    xi = np.arange(grid_shape[0]) * voxel_size + grid_min[0]
    yi = np.arange(grid_shape[1]) * voxel_size + grid_min[1]
    zi = np.arange(grid_shape[2]) * voxel_size + grid_min[2]
    X, Y, Z = np.meshgrid(xi, yi, zi, indexing="ij")
    points = np.stack([X, Y, Z], axis=-1).reshape(-1, 3).astype(np.float32)

    inside = scene.compute_occupancy(o3d.core.Tensor(points)).numpy() > 0.5
    return points[inside]
