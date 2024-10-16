""" Parametrize point clouds and define methods for equidistant sampling
    of points and corresponding normal vectors.

    Copyright (c) 2023 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""
from typing import Tuple
from abc import ABC, abstractmethod

import numpy as np
import open3d as o3d
from scipy.spatial import ConvexHull
from scipy import optimize, interpolate

from .mesh_repair import triangulate_refine_fair, com_cluster_points


def _sample_from_mesh(mesh, n_samples: int, mesh_init_factor: int = None) -> np.ndarray:
    if mesh_init_factor is None:
        point_cloud = mesh.sample_points_uniformly(
            number_of_points=n_samples,
        )
    else:
        point_cloud = mesh.sample_points_poisson_disk(
            number_of_points=n_samples,
            init_factor=mesh_init_factor,
        )

    positions_xyz = np.asarray(point_cloud.points)
    return positions_xyz


def _sample_from_chull(
    positions_xyz: np.ndarray, n_samples: int, mesh_init_factor: int = None
) -> np.ndarray:
    hull = ConvexHull(positions_xyz)
    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(positions_xyz[hull.vertices])
    mesh.triangles = o3d.utility.Vector3iVector(hull.simplices)

    return _sample_from_mesh(mesh, n_samples, mesh_init_factor)


class Parametrization(ABC):
    """
    A strategy class to represent parametrizations of point clouds
    """

    def __init__(self, *args, **kwargs):
        pass

    @abstractmethod
    def fit(self, positions: np.ndarray, *args, **kwargs) -> "Parametrization":
        """
        Fit a parametrization to a point cloud.

        Parameters
        ----------
        positions : np.ndarray
            Point coordinates with shape (n x 3)
        *args : List
            Additional arguments
        **kwargs : Dict
            Additional keywoard arguments.

        Returns
        -------
        Parametrization
            Parametrization instance.
        """

    @abstractmethod
    def sample(self, n_samples: int, *args, **kwargs):
        """
        Samples points from the surface of the parametrization.

        Parameters
        ----------
        n_samples : int
            Number of samples to draw
        *args : List
            Additional arguments
        **kwargs : Dict
            Additional keywoard arguments.

        Returns
        -------
        np.ndarray
            Sampled points.
        """


class TriangularMesh(Parametrization):
    """
    Represent a point cloud as triangular mesh.
    """

    def __init__(self, mesh):
        self.mesh = mesh

    @classmethod
    def fit(cls, positions: np.ndarray, voxel_size: float = 10):
        # Surface reconstruction normal estimation
        ellipsoid = Ellipsoid.fit(positions)

        # Reduce membrane thickness
        positions = com_cluster_points(positions, cutoff=4 * voxel_size)
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(positions)
        pcd.normals = o3d.utility.Vector3dVector(ellipsoid.compute_normal(positions))
        pcd = pcd.voxel_down_sample(voxel_size=2 * voxel_size)

        pcd.estimate_normals(
            search_param=o3d.geometry.KDTreeSearchParamHybrid(
                radius=10 * voxel_size, max_nn=30
            )
        )
        mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(
            pcd, o3d.utility.DoubleVector([5 * voxel_size])
        )
        # print("Writing out initial mesh")
        # o3d.io.write_triangle_mesh("initial_mesh.obj", mesh)

        # Remove noisy small meshes
        clusters, cluster_n, _ = mesh.cluster_connected_triangles()
        clusters = np.asarray(clusters)
        cluster_n = np.asarray(cluster_n)
        cutoff = 0.02 * cluster_n.sum()
        triangles_to_remove = cluster_n[clusters] < cutoff
        mesh.remove_triangles_by_mask(triangles_to_remove)

        # Repair and smooth
        mesh = mesh.remove_non_manifold_edges()
        mesh = mesh.remove_degenerate_triangles()
        mesh = mesh.remove_duplicated_triangles()
        mesh = mesh.remove_unreferenced_vertices()
        mesh = mesh.remove_duplicated_vertices()
        mesh = mesh.filter_smooth_taubin(number_of_iterations=5)

        # Hole filling and triangulation
        new_vs, new_fs = triangulate_refine_fair(
            np.asarray(mesh.vertices), np.asarray(mesh.triangles), fair_alpha=1
        )
        mesh = o3d.geometry.TriangleMesh()
        mesh.vertices = o3d.utility.Vector3dVector(new_vs)
        mesh.triangles = o3d.utility.Vector3iVector(new_fs)
        mesh = mesh.filter_smooth_taubin(number_of_iterations=100)

        return cls(mesh=mesh)

    def sample(
        self, n_samples: int, mesh_init_factor: bool = None, **kwargs
    ) -> np.ndarray:
        """
        Samples points from the Triangular mesh.

        Parameters
        ----------
        n_samples : int
            Number of samples to draw
        sample_mesh : bool, optional
            Whether the samples should be drawn from a triangular mesh instead.
            This can yield more equidistantly spaced points.
        mesh_init_factor : int, optional
            Number of times the mesh should be initialized for Poisson sampling.
            Five appears to be a reasonable number. Higher values typically yield
            better sampling.

        Returns
        -------
        np.ndarray
            Sampled points.
        """
        return _sample_from_mesh(self.mesh, n_samples, mesh_init_factor)

    def compute_normal(self, points: np.ndarray) -> np.ndarray:
        """
        Compute the normal vector at a given point on mesh.

        Parameters
        ----------
        points : np.ndarray
            Points on the sphere surface with shape n x d

        Returns
        -------
        np.ndarray
            Normal vectors at the given points
        """
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        pcd.estimate_normals()
        pcd.normalize_normals()
        pcd.orient_normals_consistent_tangent_plane(k=50)
        return np.asarray(pcd.normals)

    def points_per_sampling(self, sampling_density: float) -> int:
        """
        Computes the apporximate number of random samples
        required to achieve a given sampling_density.

        Parameters
        ----------
        sampling_density : float
            Average distance between points.

        Returns
        -------
        int
            Number of required random samples.
        """
        area_per_sample = np.square(sampling_density)
        n_points = np.ceil(np.divide(self.mesh.get_surface_area(), area_per_sample))

        return int(n_points)


class Sphere(Parametrization):
    """
    Parametrize a point cloud as sphere.
    """

    def __init__(self, radius: np.ndarray, center: np.ndarray):
        """
        Initialize the Ellipsoid parametrization.

        Parameters
        ----------
        radius : np.ndarray
            Radius of the sphere
        center : np.ndarray
            Center of the sphere along each axis.
        """
        self.radius = radius
        self.center = center

    @classmethod
    def fit(cls, positions: np.ndarray) -> "Sphere":
        """
        Fit an sphere to a set of 3D points.

        Parameters
        ----------
        positions : np.ndarray
            Point coordinates with shape (n x 3)

        Returns
        -------
        Sphere
            Class instance with fitted parameters.
        """
        A = np.column_stack((2 * positions, np.ones(len(positions))))
        b = (positions**2).sum(axis=1)

        x, res, _, _ = np.linalg.lstsq(A, b, rcond=None)

        radius = np.sqrt(x[0] ** 2 + x[1] ** 2 + x[2] ** 2 + x[3])
        return cls(radius=radius, center=x[:3])

    def sample(
        self,
        n_samples: int,
        radius: np.ndarray = None,
        center: np.ndarray = None,
        sample_mesh: bool = False,
        mesh_init_factor: int = None,
    ) -> np.ndarray:
        """
        Samples points from the surface of a sphere.

        Parameters
        ----------
        n_samples : int
            Number of samples to draw
        radius : np.ndarray, optional
            Radius of the sphere
        center : np.ndarray, optional
            Center of the sphere along each axis
        sample_mesh : bool, optional
            Whether the samples should be drawn from a triangular mesh instead.
            This can yield more equidistantly spaced points.
        mesh_init_factor : int, optional
            Number of times the mesh should be initialized for Poisson sampling.
            Five appears to be a reasonable number. Higher values typically yield
            better sampling.

        Returns
        -------
        np.ndarray
            Sampled points.
        """
        center = self.center if center is None else center
        radius = self.radius if radius is None else radius

        indices = np.arange(0, n_samples, dtype=float) + 0.5
        phi = np.arccos(1 - 2 * indices / n_samples)
        theta = np.pi * (1 + 5**0.5) * indices

        positions_xyz = np.column_stack(
            [np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)]
        )
        positions_xyz = np.multiply(positions_xyz, radius)
        positions_xyz = np.add(positions_xyz, center)

        if sample_mesh:
            positions_xyz = _sample_from_chull(
                positions_xyz=positions_xyz,
                mesh_init_factor=mesh_init_factor,
                n_samples=n_samples,
            )

        return positions_xyz

    def compute_normal(self, points: np.ndarray) -> np.ndarray:
        """
        Compute the normal vector at a given point on the sphere surface.

        Parameters
        ----------
        points : np.ndarray
            Points on the sphere surface with shape n x d

        Returns
        -------
        np.ndarray
            Normal vectors at the given points
        """
        return (points - self.center) / self.radius

    def points_per_sampling(self, sampling_density: float) -> int:
        """
        Computes the apporximate number of random samples
        required to achieve a given sampling_density.

        Parameters
        ----------
        sampling_density : float
            Average distance between points.

        Returns
        -------
        int
            Number of required random samples.
        """
        n_points = np.multiply(
            np.square(np.pi),
            np.ceil(np.power(np.divide(self.radius, sampling_density), 2)),
        )
        return int(n_points)


class Ellipsoid(Parametrization):
    """
    Parametrize a point cloud as ellipsoid.
    """

    def __init__(self, radii: np.ndarray, center: np.ndarray, orientations: np.ndarray):
        """
        Initialize the Ellipsoid parametrization.

        Parameters
        ----------
        radii : np.ndarray
            Radii of the ellipse along each axis
        center : np.ndarray
            Center of the ellipse along each axis
        orientations : np.ndarray
            Square orientation matrix
        """
        self.radii = radii
        self.center = center
        self.orientations = orientations

    @classmethod
    def fit(cls, positions) -> "Ellipsoid":
        """
        Fit an ellipsoid to a set of 3D points.

        Parameters
        ----------
        positions: np.ndarray
            Point coordinates with shape (n x 3)

        Returns
        -------
        Ellipsoid
            Class instance with fitted parameters.

        Raises
        ------
        NotImplementedError
            If the points are not 3D.

        References
        ----------
        .. [1]  https://de.mathworks.com/matlabcentral/fileexchange/24693-ellipsoid-fit
        """
        positions = np.asarray(positions, dtype=np.float64)
        if positions.shape[1] != 3 or len(positions.shape) != 2:
            raise NotImplementedError(
                "Only three-dimensional point clouds are supported."
            )

        x, y, z = positions[:, 0], positions[:, 1], positions[:, 2]
        D = np.array(
            [
                x * x + y * y - 2 * z * z,
                x * x + z * z - 2 * y * y,
                2 * x * y,
                2 * x * z,
                2 * y * z,
                2 * x,
                2 * y,
                2 * z,
                1 - 0 * x,
            ]
        )
        d2 = np.array(x * x + y * y + z * z).T
        u = np.linalg.solve(D.dot(D.T), D.dot(d2))
        v = np.concatenate(
            [
                np.array([u[0] + 1 * u[1] - 1]),
                np.array([u[0] - 2 * u[1] - 1]),
                np.array([u[1] - 2 * u[0] - 1]),
                u[2:],
            ],
            axis=0,
        ).flatten()
        A = np.array(
            [
                [v[0], v[3], v[4], v[6]],
                [v[3], v[1], v[5], v[7]],
                [v[4], v[5], v[2], v[8]],
                [v[6], v[7], v[8], v[9]],
            ]
        )

        center = np.linalg.solve(-A[:3, :3], v[6:9])
        T = np.eye(4)
        T[3, :3] = center.T

        R = T.dot(A).dot(T.T)
        evals, evecs = np.linalg.eig(R[:3, :3] / -R[3, 3])
        radii = np.sign(evals) * np.sqrt(1.0 / np.abs(evals))

        return cls(radii=radii, center=center, orientations=evecs)

    def sample(
        self,
        n_samples: int,
        radii: np.ndarray = None,
        center: np.ndarray = None,
        orientations: np.ndarray = None,
        sample_mesh: bool = True,
        mesh_init_factor: int = 5,
    ) -> np.ndarray:
        """
        Samples points from the surface of an ellisoid.

        Parameters
        ----------
        n_samples : int
            Number of samples to draw
        radii : np.ndarray
            Radii of the ellipse along each axis
        center : np.ndarray
            Center of the ellipse along each axis
        orientations : np.ndarray
            Square orientation matrix
        sample_mesh : bool, optional
            Whether the samples should be drawn from a triangular mesh instead.
            This can yield more equidistantly spaced points.
        mesh_init_factor : int, optional
            Number of times the mesh should be initialized for Poisson sampling.
            Five appears to be a reasonable number. Higher values typically yield
            better sampling.

        Returns
        -------
        np.ndarray
            Sampled points.
        """
        radii = self.radii if radii is None else radii
        center = self.center if center is None else center
        orientations = self.orientations if orientations is None else orientations

        positions_xyz = np.zeros((n_samples, self.center.size))
        samples_drawn = 0
        np.random.seed(42)
        radii_fourth, r_min = np.power(radii, 4), np.min(radii)
        while samples_drawn < n_samples:
            point = np.random.normal(size=3)
            point /= np.linalg.norm(point)

            np.multiply(point, radii, out=point)

            p = r_min * np.sqrt(np.divide(np.square(point), radii_fourth).sum())
            u = np.random.uniform(0, 1)
            if u <= p:
                positions_xyz[samples_drawn] = point
                samples_drawn += 1

        positions_xyz = positions_xyz.dot(orientations.T)
        positions_xyz = np.add(positions_xyz, center)

        if sample_mesh:
            positions_xyz = _sample_from_chull(
                positions_xyz=positions_xyz,
                mesh_init_factor=mesh_init_factor,
                n_samples=n_samples,
            )

        return positions_xyz

    def compute_normal(self, points: np.ndarray) -> np.ndarray:
        """
        Compute the normal vector at a given point on the ellipsoid surface.

        Parameters
        ----------
        points : np.ndarray
            Points on the sphere surface with shape n x d

        Returns
        -------
        np.ndarray
            Normal vectors at the given points
        """
        # points_norm = (points - self.center) / self.radii

        norm_points = (points - self.center).dot(np.linalg.inv(self.orientations.T))
        normals = np.divide(np.multiply(norm_points, 2), np.square(self.radii))
        normals = np.dot(normals, self.orientations.T)
        normals /= np.linalg.norm(normals, axis=1)[:, None]

        return normals

    def points_per_sampling(self, sampling_density: float) -> int:
        """
        Computes the apporximate number of random samples
        required to achieve a given sampling_density.

        Parameters
        ----------
        sampling_density : float
            Average distance between points.

        Returns
        -------
        int
            Number of required random samples.
        """
        area_points = np.pi * np.square(sampling_density)
        area_ellipsoid = np.power(self.radii[0] * self.radii[1], 1.6075)
        area_ellipsoid += np.power(self.radii[0] * self.radii[2], 1.6075)
        area_ellipsoid += np.power(self.radii[1] * self.radii[2], 1.6075)

        area_ellipsoid = np.power(np.divide(area_ellipsoid, 3), 1 / 1.6075)
        area_ellipsoid *= 4 * np.pi

        n_points = np.ceil(np.divide(area_ellipsoid, area_points))
        return int(n_points)


class Cylinder(Parametrization):
    """
    Parametrize a point cloud as cylinder.
    """

    def __init__(
        self,
        centers: np.ndarray,
        orientations: np.ndarray,
        radius: float,
        height: float,
    ):
        """
        Initialize the Cylinder parametrization.

        Parameters
        ----------
        centers : np.ndarray
            Center coordinates of the cylinder in X and Y.
        orientations : np.ndarray
            Square orientation matrix
        radius: float
            Radius of the cylinder.
        height : float
            Height of the cylinder.
        """
        self.centers = centers
        self.orientations = orientations
        self.radius = radius
        self.height = height

    @classmethod
    def fit(cls, positions: np.ndarray) -> "Cylinder":
        """
        Fit a 3D point cloud to a cylinder.

        Parameters
        ----------
        positions : np.ndarray
            Point coordinates with shape (n x 3)

        Returns
        -------
        Cylinder
            Class instance with fitted parameters.

        Raises
        ------
        ValueError
            If th number of initial parameters is not equal to five.
        NotImplementedError
            If the points are not 3D.
        """

        positions = np.asarray(positions, dtype=np.float64)
        if positions.shape[1] != 3 or len(positions.shape) != 2:
            raise NotImplementedError(
                "Only three-dimensional point clouds are supported."
            )

        center = positions.mean(axis=0)
        positions_centered = positions - center

        cov_mat = np.cov(positions_centered, rowvar=False)
        evals, evecs = np.linalg.eigh(cov_mat)

        sort_indices = np.argsort(evals)[::-1]
        evals = evals[sort_indices]
        evecs = evecs[:, sort_indices]

        initial_radii = 2 * np.sqrt(evals)

        def cylinder_loss(params, data_points, orientations):
            radii, center = params[0], params[1:]
            transformed_points = np.dot(data_points - center, orientations)

            normalized_points = transformed_points / radii

            distances = np.sum(normalized_points**2, axis=1) - 1

            loss = np.sum(distances**2)
            return loss

        result = optimize.minimize(
            cylinder_loss,
            np.array([np.max(initial_radii), *center]),
            args=(positions, evecs),
            method="Nelder-Mead",
        )
        radius, center = result.x[0], result.x[1:]
        rotated_points = positions_centered.dot(evecs)
        heights = rotated_points.max(axis=0) - rotated_points.min(axis=0)
        height = heights[np.argmax(np.abs(np.diff(heights))) + 1]
        return cls(radius=radius, centers=center, orientations=evecs, height=height)

    def sample(
        self,
        n_samples: int,
        centers: np.ndarray = None,
        orientations: np.ndarray = None,
        radius: float = None,
        height: float = None,
        sample_mesh: bool = False,
        mesh_init_factor: int = None,
    ) -> np.ndarray:
        """
        Sample points from the surface of a cylinder.

        Parameters
        ----------
        centers : np.ndarray
            Center coordinates of the cylinder in X and Y.
        orientations : np.ndarray
            Square orientation matrix
        radius: float
            Radius of the cylinder.
        height : float
            Height of the cylinder.
        sample_mesh : bool, optional
            Whether the samples should be drawn from a triangular mesh instead.
            This can yield more equidistantly spaced points.
        mesh_init_factor : int, optional
            Number of times the mesh should be initialized for Poisson sampling.
            Five appears to be a reasonable number. Higher values typically yield
            better sampling.

        Returns
        -------
        np.ndarray
            Array of sampled points from the cylinder surface.
        """
        centers = self.centers if centers is None else centers
        orientations = self.orientations if orientations is None else orientations
        radius = self.radius if radius is None else radius
        height = self.height if height is None else height

        n_samples = int(np.ceil(np.sqrt(n_samples)))
        theta = np.linspace(0, 2 * np.pi, n_samples)
        h = np.linspace(-height / 2, height / 2, n_samples)

        mesh = np.asarray(np.meshgrid(theta, h)).reshape(2, -1).T

        x = radius * np.cos(mesh[:, 0])
        y = radius * np.sin(mesh[:, 0])
        z = mesh[:, 1]
        samples = np.column_stack((x, y, z))

        samples = samples.dot(orientations.T)
        samples += centers

        if sample_mesh:
            samples = _sample_from_chull(
                positions_xyz=samples,
                mesh_init_factor=mesh_init_factor,
                n_samples=n_samples,
            )

        return samples

    def points_per_sampling(self, sampling_density: float) -> int:
        """
        Computes the apporximate number of random samples
        required to achieve a given sampling_density.

        Parameters
        ----------
        sampling_density : float
            Average distance between points.

        Returns
        -------
        int
            Number of required random samples.
        """
        area_points = np.square(sampling_density)
        area = 2 * self.radius * (self.radius + self.height)

        n_points = np.ceil(np.divide(area, area_points))
        return int(n_points)


class RBF(Parametrization):
    """
    Parametrize a point cloud as sphere.
    """

    def __init__(self, rbf: type, direction: str, grid: Tuple):
        """
        Initialize the Ellipsoid parametrization.

        Parameters
        ----------
        rbf : scipy.interpolate.Rbf
            Radial basis function interpolator instance.
        direction : str
            Direction of interpolation relative to positions.
        grid: Tuple
            2D interpolation grid ranges.
        """
        self.rbf = rbf
        self.grid = grid
        self.direction = direction

    @classmethod
    def fit(
        cls, positions: np.ndarray, direction: str = "xz", function="linear", smooth=5
    ) -> "RBF":
        """
        Fit a RBF to a set of 3D points.

        Parameters
        ----------
        positions : np.ndarray
            Point coordinates with shape (n x 3)
        direction : str
            Direction of interpolation relative to positions.
        function : str
            Function type to use.
        smooth : int
            Smoothing factor.

        Returns
        -------
        RBF
            Class instance with fitted parameters.
        """
        n_positions = positions.shape[0] // 50
        positions = positions[::n_positions]

        swap = (2, 1, 0)
        if direction == "yz":
            swap = (0, 2, 1)
        elif direction == "xy":
            swap = (0, 1, 2)

        sx, sy, sz = swap
        X, Y, Z = positions[:, sx], positions[:, sy], positions[:, sz]
        rbf = interpolate.Rbf(X, Y, Z, function=function, smooth=smooth)

        grid = ((np.min(X), np.max(X)), (np.min(Y), np.max(Y)))
        return cls(rbf=rbf, direction=direction, grid=grid)

    def sample(
        self,
        n_samples: int,
    ) -> np.ndarray:
        """
        Samples points from the RBF.

        Parameters
        ----------
        n_samples : int
            Number of samples to draw

        Returns
        -------
        np.ndarray
            Sampled points.
        """
        (xmin, xmax), (ymin, ymax) = self.grid

        n_samples = int(np.ceil(np.sqrt(n_samples)))
        x, y = np.meshgrid(
            np.linspace(xmin, xmax, n_samples), np.linspace(ymin, ymax, n_samples)
        )
        z = self.rbf(x, y)

        positions_xyz = np.vstack((x.ravel(), y.ravel(), z.ravel())).T
        if self.direction == "xz":
            positions_xyz[:, [0, 2]] = positions_xyz[:, [2, 0]]
        elif self.direction == "yz":
            positions_xyz[:, [1, 2]] = positions_xyz[:, [2, 1]]

        return positions_xyz

    def compute_normal(self, points: np.ndarray) -> np.ndarray:
        """
        Compute the normal vector at a given point on the surface.

        Parameters
        ----------
        points : np.ndarray
            Points on the surface with shape n x d

        Returns
        -------
        np.ndarray
            Normal vectors at the given points
        """
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        pcd.estimate_normals()
        pcd.normalize_normals()
        pcd.orient_normals_consistent_tangent_plane(k=50)

        return np.asarray(pcd.normals)

    def points_per_sampling(self, sampling_density: float) -> int:
        """
        Computes the apporximate number of random samples
        required to achieve a given sampling_density.

        Parameters
        ----------
        sampling_density : float
            Average distance between points.

        Returns
        -------
        int
            Number of required random samples.
        """
        (xmin, xmax), (ymin, ymax) = self.grid
        surface_area = (xmax - xmin) * (ymax - xmin)

        n_points = np.ceil(np.divide(surface_area, sampling_density))
        return int(n_points)


PARAMETRIZATION_TYPE = {
    "sphere": Sphere,
    "ellipsoid": Ellipsoid,
    "cylinder": Cylinder,
    "mesh": TriangularMesh,
    "rbf": RBF,
}
