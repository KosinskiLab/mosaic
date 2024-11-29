import h5py
import textwrap
from subprocess import run
from tempfile import NamedTemporaryFile

import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree
from scipy.spatial.distance import pdist


def to_open3d(vertices, faces):
    ret = o3d.geometry.TriangleMesh()
    ret.vertices = o3d.utility.Vector3dVector(np.asarray(vertices, dtype=np.float64))
    ret.triangles = o3d.utility.Vector3iVector(np.asarray(faces, dtype=np.float32))
    return ret


def _compute_edge_lengths(filename):
    mesh = o3d.io.read_triangle_mesh(filename)
    return compute_edge_lengths(mesh)


def compute_edge_lengths(mesh):
    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.triangles)

    coordinates = vertices[faces]
    distances = np.array([pdist(coordinates[x]) for x in range(faces.shape[0])])
    return distances.ravel()


def scale(mesh, scaling):
    vertices = np.multiply(np.asarray(mesh.vertices).copy(), scaling)
    triangles = np.asarray(mesh.triangles).copy()
    return to_open3d(vertices, triangles)


def remesh(mesh, target_edge_length, n_iter=100, featuredeg=30, **kwargs):
    from pymeshlab import MeshSet, Mesh, PureValue

    vertices = np.asarray(mesh.vertices)
    triangles = np.asarray(mesh.triangles)

    ms = MeshSet()
    ms.add_mesh(Mesh(vertices, triangles))

    ms.meshing_isotropic_explicit_remeshing(
        targetlen=PureValue(target_edge_length),
        iterations=n_iter,
        featuredeg=featuredeg,
        **kwargs,
    )
    ms.meshing_merge_close_vertices(threshold=PureValue(target_edge_length / 3))

    remeshed = ms.current_mesh()
    ret = to_open3d(remeshed.vertex_matrix(), remeshed.face_matrix())
    return ret


def equilibrate_edges(mesh, lower_bound, upper_bound, steps=2000, **kwargs):
    default_args = {
        "area_fraction": 1.2,
        "volume_fraction": 1.2,
    }
    default_args.update(kwargs)

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
        r = 2
        lc0 = {upper_bound}
        lc1 = {lower_bound}

        [SURFACEREPULSION]
        n_search = cell-list
        rlist = 0.2
        exclusion_level = 2
        refresh = 10
        r = 2

        [ENERGY]
        kappa_b = 300.0
        kappa_a = 1.0e6
        kappa_v = 1.0e6
        kappa_c = 0.0
        kappa_t = 1.0e5
        kappa_r = 1.0e3
        area_fraction = {default_args['area_fraction']}
        volume_fraction = {default_args['volume_fraction']}
        curvature_fraction = 1.0
        continuation_delta = 0.0
        continuation_lambda = 1.0

        [MINIMIZATION]
        maxiter = {steps}
        out_every = 0
    """
    )
    config = config.strip()

    with NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as tfile:
        tfile.write(config)
        tfile.flush()

        ret = run(["mc_app", "run", "--conf", str(tfile.name)])
        if ret.stderr:
            print(ret.stdout)
            print(ret.stderr)

        output_file = f"{tfile.name.replace('.conf', '')}.cpt.p0.h5"

        with h5py.File(output_file, mode="r") as infile:
            faces = infile["cells"][()]
            vertices = infile["points"][()]

    ret = o3d.geometry.TriangleMesh()
    ret.vertices = o3d.utility.Vector3dVector(vertices)
    ret.triangles = o3d.utility.Vector3iVector(faces)

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


def find_closest_points(positions1, positions2, k=1):
    positions1, positions2 = np.asarray(positions1), np.asarray(positions2)

    tree = cKDTree(positions1)
    return tree.query(positions2, k=k)


def com_cluster_points(positions: np.ndarray, cutoff: float) -> np.ndarray:
    if not isinstance(positions, np.ndarray):
        positions = np.array(positions)

    if isinstance(cutoff, np.ndarray):
        cutoff = np.max(cutoff)

    tree = cKDTree(positions)
    n_points = len(positions)
    unassigned = np.ones(n_points, dtype=bool)
    clusters = []

    unassigned_indices = np.where(unassigned)[0]
    while np.any(unassigned):
        seed_idx = np.random.choice(unassigned_indices)

        cluster_indices = tree.query_ball_point(positions[seed_idx], cutoff)
        cluster_indices = np.array([idx for idx in cluster_indices if unassigned[idx]])

        if len(cluster_indices) > 0:
            cluster_center = np.mean(positions[cluster_indices], axis=0)
            clusters.append(cluster_center)
            unassigned[cluster_indices] = False
            unassigned_indices = np.where(unassigned)[0]

    return np.array(clusters)
