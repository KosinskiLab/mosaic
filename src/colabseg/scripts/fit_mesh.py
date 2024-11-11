import copy
import numpy as np
import open3d as o3d
from colabseg.trimesh import triangulate_refine_fair
import open3d as o3d
import numpy as np
from sklearn.neighbors import NearestNeighbors
import open3d as o3d
import numpy as np
from scipy.spatial.distance import cdist

from colabseg.parametrization import TriangularMesh, FairHull


def get_min_distance(points1, points2, metric="euclidean"):
    return cdist(points1, points2, metric=metric)


def find_and_connect_mesh_boundaries(mesh, k=10):
    he_mesh = o3d.geometry.HalfEdgeTriangleMesh.create_from_triangle_mesh(mesh)

    boundary_vertices = he_mesh.get_boundaries()
    if len(boundary_vertices) == 1:
        return mesh

    mesh_points = np.asarray(he_mesh.vertices)

    all_boundary_vertices, submesh_indices = [], []
    for i, x in enumerate(boundary_vertices):
        all_boundary_vertices.extend(np.asarray(x).tolist())
        submesh_indices.extend([i] * len(x))

    boundary_vertices = all_boundary_vertices.copy()
    submesh_copy = submesh_indices.copy()

    new_triangles = []
    while True:
        if not len(all_boundary_vertices):
            break

        vertex = all_boundary_vertices.pop(0)
        submesh_index = submesh_indices.pop(0)

        distances = get_min_distance(
            mesh_points[vertex][None], mesh_points[boundary_vertices]
        )[0]

        # Simple self-collapse avoidance for now
        submesh_mask = [x == submesh_index for x in submesh_copy]
        distances[submesh_mask] = np.max(distances) + 1

        closest_pair = np.argsort(distances)[:2]
        if len(closest_pair) != 2:
            break

        closest_pair = [boundary_vertices[x] for x in closest_pair]
        new_triangles.append([vertex, *closest_pair])

    new_triangles = np.concatenate(
        [np.asarray(mesh.triangles), np.asarray(new_triangles)]
    )
    new_vertices = np.asarray(mesh.vertices)

    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(new_vertices.astype(np.float64))
    mesh.triangles = o3d.utility.Vector3iVector(new_triangles.astype(np.int32))

    return mesh


ret = o3d.io.read_triangle_mesh("initial_mesh2.obj")


positions = np.asarray(ret.vertices)
# scale = positions.max(axis=0)
# pcd = o3d.geometry.PointCloud()
# pcd.points = o3d.utility.Vector3dVector(positions / scale)
# alpha = 0.5
# with o3d.utility.VerbosityContextManager(o3d.utility.VerbosityLevel.Error):
#     mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_alpha_shape(pcd, alpha)

# mesh.vertices = o3d.utility.Vector3dVector(
#     np.multiply(np.asarray(mesh.vertices), scale)
# )
# o3d.io.write_triangle_mesh("hull.obj", mesh)

mesh = FairHull.fit(positions)
o3d.io.write_triangle_mesh("mesh_repair.obj", mesh.mesh)

# new_vs, new_fs = triangulate_refine_fair(
#     vs = np.asarray(ret.vertices),
#     fs = np.asarray(ret.triangles),
#     _close_hole_fast=True,
#     hole_len_thr=1e50
# )

# mesh = o3d.geometry.TriangleMesh()
# mesh.vertices = o3d.utility.Vector3dVector(new_vs.astype(np.float64))
# mesh.triangles = o3d.utility.Vector3iVector(new_fs.astype(np.int32))
# o3d.io.write_triangle_mesh("mesh_repair.obj", mesh)
