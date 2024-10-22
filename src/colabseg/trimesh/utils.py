import h5py
import textwrap
from subprocess import run
from tempfile import NamedTemporaryFile

import numpy as np
import open3d as o3d
from scipy.spatial.distance import cdist, pdist


def compute_edge_lengths(mesh):
    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.triangles)

    coordinates = vertices[faces]
    distances = np.array([pdist(coordinates[x]) for x in range(faces.shape[0])])
    return distances.ravel()


def remesh(mesh, target_edge_length, n_iter=100, featuredeg=10, **kwargs):
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

    remeshed = ms.current_mesh()
    ret = o3d.geometry.TriangleMesh()
    ret.vertices = o3d.utility.Vector3dVector(remeshed.vertex_matrix())
    ret.triangles = o3d.utility.Vector3iVector(remeshed.face_matrix())
    return ret


def equilibrate_edges(mesh, lower_bound, upper_bound, steps=2000):
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
        lc1 = 0.15

        [ENERGY]
        kappa_b = 300.0
        kappa_a = 1.0e6
        kappa_v = 1.0e6
        kappa_c = 0.0
        kappa_t = 1.0e5
        kappa_r = 1.0e3
        area_fraction = 1.0
        volume_fraction = 1.0
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
    print(f"Requested lower {lower_bound}, actual {edge_lengths.min()}")
    print(f"Requested upper {upper_bound}, actual {edge_lengths.max()}")

    return ret


def com_cluster_points(postions, cutoff):
    com_list = []
    tag = np.zeros(len(postions))
    acc = False
    while acc is False:
        if len(np.where(tag == 0)[0]) == 0:
            acc = True
            break
        randint = np.random.randint(0, len(np.where(tag == 0)[0]))
        randint = np.where(tag == 0)[0][randint]

        if tag[randint] != 0:
            continue

        dist_arr = cdist([postions[randint]], postions)
        indices = np.where(dist_arr[0] < cutoff)[0]
        pos_cluster = postions[dist_arr[0] < cutoff]
        center = np.average(pos_cluster, axis=0)
        for index in indices:
            tag[index] = 1
        com_list.append(center)

    com_list = np.asarray(com_list)
    return com_list
