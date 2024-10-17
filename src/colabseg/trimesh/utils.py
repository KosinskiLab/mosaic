# import pymeshlab
import numpy as np
import open3d as o3d
from scipy.spatial.distance import cdist, pdist


def compute_edge_lengths(mesh):
    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.triangles)

    coordinates = vertices[faces]
    distances = np.array([pdist(coordinates[x]) for x in range(faces.shape[0])])
    return distances.ravel()


def remesh_iter(mesh, min_length=1.0, max_length=np.sqrt(3), max_iterations=10):
    vertices = np.asarray(mesh.vertices)
    triangles = np.asarray(mesh.triangles)
    ms = pymeshlab.MeshSet()
    ms.add_mesh(pymeshlab.Mesh(vertices, triangles))

    ms.meshing_repair_non_manifold_edges()
    ms.meshing_repair_non_manifold_vertices()
    ms.apply_coord_developability_of_mesh()
    # ms.meshing_isotropic_explicit_remeshing(
    #     targetlen=pymeshlab.PureValue(min_length), iterations=10, adaptive=True
    # )

    remeshed = ms.current_mesh()
    ret = o3d.geometry.TriangleMesh()
    ret.vertices = o3d.utility.Vector3dVector(remeshed.vertex_matrix())
    ret.triangles = o3d.utility.Vector3iVector(remeshed.face_matrix())
    edge_lengths = compute_edge_lengths(ret)
    min_edge = np.min(edge_lengths)
    max_edge = np.max(edge_lengths)
    avg_edge = np.mean(edge_lengths)

    print(
        f"{0} Min edge: {min_edge:.4f}, Max edge: {max_edge:.4f}, Avg edge: {avg_edge:.4f}"
    )

    for i in range(max_iterations):
        scale = np.sin((((i + 1) / max_iterations) * np.pi) / 2)
        ms.meshing_isotropic_explicit_remeshing(
            targetlen=pymeshlab.PureValue(13),
            iterations=20,
            adaptive=True,
            swapflag=True,
            splitflag=True,
            reprojectflag=False,
            collapseflag=True,
        )


        split_length = max_edge - scale * (max_edge - max_length)
        merge_length = min_edge + scale * (min_length - min_edge)

        # ms.meshing_surface_subdivision_ls3_loop(
        #     # loopweight="Loop",
        #     loopweight="Enhance regularity",
        #     threshold=pymeshlab.PureValue(split_length),
        # )

        ms.meshing_merge_close_vertices(threshold=pymeshlab.PureValue(merge_length))

        ms.meshing_repair_non_manifold_edges()
        ms.meshing_repair_non_manifold_vertices()

        ms.meshing_remove_duplicate_faces()
        ms.meshing_remove_duplicate_vertices()
        ms.meshing_remove_unreferenced_vertices()
        ms.meshing_remove_null_faces()


        ms.meshing_surface_subdivision_ls3_loop(
            loopweight="Enhance regularity",
            threshold=pymeshlab.PureValue(split_length),
        )

        remeshed = ms.current_mesh()
        ret = o3d.geometry.TriangleMesh()
        ret.vertices = o3d.utility.Vector3dVector(remeshed.vertex_matrix())
        ret.triangles = o3d.utility.Vector3iVector(remeshed.face_matrix())

        edge_lengths = compute_edge_lengths(ret)
        min_edge = np.min(edge_lengths)
        max_edge = np.max(edge_lengths)
        avg_edge = np.mean(edge_lengths)

        # ms.meshing_isotropic_explicit_remeshing(
        #     targetlen=pymeshlab.PureValue(min_length), iterations=10
        # )


        print(
            f"{i+1} Min edge: {min_edge:.4f}, Max edge: {max_edge:.4f}, Avg edge: {avg_edge:.4f}"
        )

        if min_edge >= min_length and max_edge <= max_length:
            print("Desired edge length distribution achieved.")
            break

    print(split_length)


    remeshed = ms.current_mesh()
    ret = o3d.geometry.TriangleMesh()
    ret.vertices = o3d.utility.Vector3dVector(remeshed.vertex_matrix())
    ret.triangles = o3d.utility.Vector3iVector(remeshed.face_matrix())

    edge_lengths = compute_edge_lengths(ret)
    min_edge = np.min(edge_lengths)
    max_edge = np.max(edge_lengths)
    avg_edge = np.mean(edge_lengths)

    print(
        f"{i+1} Min edge: {min_edge:.4f}, Max edge: {max_edge:.4f}, Avg edge: {avg_edge:.4f}"
    )

    return ret


def remesh(mesh, target_edge_length, n_iter=10, featuredeg=10, **kwargs):
    vertices = np.asarray(mesh.vertices)
    triangles = np.asarray(mesh.triangles)

    ms = pymeshlab.MeshSet()
    ms.add_mesh(pymeshlab.Mesh(vertices, triangles))

    ms.meshing_isotropic_explicit_remeshing(
        targetlen=pymeshlab.PureValue(target_edge_length),
        iterations=n_iter,
        featuredeg=featuredeg,
        **kwargs,
    )

    remeshed = ms.current_mesh()
    ret = o3d.geometry.TriangleMesh()
    ret.vertices = o3d.utility.Vector3dVector(remeshed.vertex_matrix())
    ret.triangles = o3d.utility.Vector3iVector(remeshed.face_matrix())
    return ret


def merge_vertices(mesh, target_edge_length, **kwargs):
    vertices = np.asarray(mesh.vertices)
    triangles = np.asarray(mesh.triangles)

    ms = pymeshlab.MeshSet()
    ms.add_mesh(pymeshlab.Mesh(vertices, triangles))

    ms.meshing_merge_close_vertices(threshold=pymeshlab.PureValue(target_edge_length))

    remeshed = ms.current_mesh()
    ret = o3d.geometry.TriangleMesh()
    ret.vertices = o3d.utility.Vector3dVector(remeshed.vertex_matrix())
    ret.triangles = o3d.utility.Vector3iVector(remeshed.face_matrix())
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
