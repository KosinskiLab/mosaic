"""
Utilities for triangular meshes.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

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
    "poisson_mesh",
    "merge_meshes",
    "equilibrate_edges",
    "compute_scale_factor",
    "compute_scale_factor_lower",
    "center_mesh",
    "to_tsi",
]


def to_open3d(vertices, faces) -> o3d.geometry.TriangleMesh:
    ret = o3d.geometry.TriangleMesh()
    ret.vertices = o3d.utility.Vector3dVector(np.asarray(vertices, dtype=np.float64))
    ret.triangles = o3d.utility.Vector3iVector(np.asarray(faces, dtype=np.int32))
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


def poisson_mesh(
    positions: np.ndarray,
    voxel_size: float = None,
    depth: int = 9,
    k_neighbors=50,
    smooth_iter=1,
    pointweight=0.1,
    deldist=1.5,
    scale=1.2,
    samplespernode=5.0,
    **kwargs,
):
    """
    Triangulate positions using Poisson reconstruction.

    Notes
    -----
    On Darwin platforms this used to spawn a new process to
    avoid instabilities from mosaic's Qt6 and pymeshlab's Qt5 for
    mosaic version <=1.0.4
    """
    from pymeshlab import MeshSet, Mesh

    voxel_size = 1 if voxel_size is None else voxel_size
    positions = np.divide(np.asarray(positions, dtype=np.float64), voxel_size)

    ms = MeshSet()
    ms.add_mesh(Mesh(positions))
    ms.compute_normal_for_point_clouds(k=k_neighbors, smoothiter=smooth_iter)
    ms.generate_surface_reconstruction_screened_poisson(
        depth=depth,
        pointweight=pointweight,
        samplespernode=samplespernode,
        iters=10,
        scale=scale,
    )
    if deldist > 0:
        ms.compute_scalar_by_distance_from_another_mesh_per_vertex(
            measuremesh=1,
            refmesh=0,
            signeddist=False,
        )
        ms.compute_selection_by_condition_per_vertex(condselect=f"(q>{deldist})")
        ms.compute_selection_by_condition_per_face(
            condselect=f"(q0>{deldist} || q1>{deldist} || q2>{deldist})"
        )
        ms.meshing_remove_selected_vertices_and_faces()

    mesh = ms.current_mesh()
    return to_open3d(mesh.vertex_matrix() * voxel_size, mesh.face_matrix())


def remesh(mesh, target_edge_length, n_iter=100, featuredeg=30, **kwargs):
    """
    Remesh to target edge length

    Notes
    -----
    On Darwin platforms this used to spawn a new process to
    avoid instabilities from mosaic's Qt6 and pymeshlab's Qt5 for
    mosaic version <=1.0.4
    """
    from pymeshlab import MeshSet, Mesh, PureValue

    mesh = mesh.remove_duplicated_vertices()
    mesh = mesh.remove_unreferenced_vertices()
    mesh = mesh.remove_degenerate_triangles()

    ms = MeshSet()
    ms.add_mesh(Mesh(np.asarray(mesh.vertices), np.asarray(mesh.triangles)))
    ms.meshing_isotropic_explicit_remeshing(
        targetlen=PureValue(target_edge_length),
        iterations=n_iter,
        featuredeg=featuredeg,
        **kwargs,
    )
    ms.meshing_merge_close_vertices(threshold=PureValue(target_edge_length / 3))
    remeshed = ms.current_mesh()
    return to_open3d(remeshed.vertex_matrix(), remeshed.face_matrix())


def merge_meshes(vertices: List[np.ndarray], faces: List[np.ndarray]):
    if len(vertices) != len(faces):
        raise ValueError("Length of vertex and face list needs to match.")
    elif len(vertices) == 1:
        return *vertices, *faces

    faces = [np.asarray(x) for x in faces]
    vertices = [np.asarray(x) for x in vertices]

    vertex_ct = np.zeros(len(vertices) + 1, np.uint32)
    vertex_ct[1:] = np.cumsum([len(x) for x in vertices])

    mesh = to_open3d(
        vertices=np.concatenate([x for x in vertices]),
        faces=np.concatenate([face + vertex_ct[i] for i, face in enumerate(faces)]),
    )
    mesh = mesh.remove_duplicated_vertices()
    return np.asarray(mesh.vertices), np.asarray(mesh.triangles)


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
        except Exception:
            warnings.warn(
                f"{str(ret.stderr).strip()}\n\n"
                f"Skipping calibration - Check Trimem installation."
            )
            return mesh

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
