""" Implements geometric surface models for point cloud data. This includes
    parameteric as well as non-parametric triangular-mesh based approaches.

    Children of the underlying abstract Parametrization class, also define
    means for equidistant sampling and computation of normal vectors.
    Furthermore, there are amenable to native python pickling.

    Copyright (c) 2023-2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import warnings
from typing import Tuple
from abc import ABC, abstractmethod

import igl
import numpy as np
import open3d as o3d
from scipy import optimize, interpolate
from scipy.spatial import ConvexHull as scConvexHull

from .utils import find_closest_points, com_cluster_points
from .meshing import (
    triangulate_refine_fair,
    fair_mesh,
    remesh,
    to_open3d,
    get_ring_vertices,
    poisson_mesh,
)


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
    hull = scConvexHull(positions_xyz)
    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(positions_xyz[hull.vertices])
    mesh.triangles = o3d.utility.Vector3iVector(hull.simplices)

    return _sample_from_mesh(mesh, n_samples, mesh_init_factor)


class Parametrization(ABC):
    """
    A strategy class to represent picklable parametrizations of point clouds
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

    @abstractmethod
    def compute_normal(self, positions: np.ndarray, *args, **kwargs):
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

    @abstractmethod
    def points_per_sampling(self, sampling_density: float) -> int:
        """
        Computes the approximate number of random samples
        required to achieve a given spatial sampling_density.

        Parameters
        ----------
        sampling_density : float
            Average distance between points.

        Returns
        -------
        int
            Number of required random samples.
        """

    def compute_distance(self, points: np.ndarray, **kwargs) -> np.ndarray:
        """
        Computes the distance between points and the parameterization.

        Parameters
        ----------
        points : np.ndarray
            Array of coordinates (n, d).

        Returns
        -------
        np.ndarray
            Distances between points and the parametrization.
        """
        return np.full_like(points, fill_value=0)


class Sphere(Parametrization):
    """
    Parametrize a point cloud as sphere.

    Parameters
    ----------
    radius : np.ndarray
        Radius of the sphere
    center : np.ndarray
        Center of the sphere along each axis.
    """

    def __init__(self, radius: np.ndarray, center: np.ndarray):
        self.radius = radius
        self.center = center

    @classmethod
    def fit(cls, positions: np.ndarray, **kwargs) -> "Sphere":
        positions = np.asarray(positions, dtype=np.float64)
        A = np.column_stack((2 * positions, np.ones(len(positions))))
        b = (positions**2).sum(axis=1)

        x, res, _, _ = np.linalg.lstsq(A, b, rcond=None)

        radius = np.sqrt(x[0] ** 2 + x[1] ** 2 + x[2] ** 2 + x[3])
        return cls(radius=radius, center=x[:3])

    def sample(
        self,
        n_samples: int,
        normal_offset: float = 0.0,
        radius: np.ndarray = None,
        center: np.ndarray = None,
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

        if mesh_init_factor is not None:
            positions_xyz = _sample_from_chull(
                positions_xyz=positions_xyz,
                mesh_init_factor=mesh_init_factor,
                n_samples=n_samples,
            )
        if normal_offset != 0:
            positions_xyz = np.add(
                positions_xyz,
                np.multiply(self.compute_normal(positions_xyz), normal_offset),
            )

        return positions_xyz

    def compute_normal(self, points: np.ndarray) -> np.ndarray:
        normals = (points - self.center) / self.radius
        normals /= np.linalg.norm(normals, axis=1)[:, None]
        return normals

    def compute_distance(self, points: np.ndarray, **kwargs) -> np.ndarray:
        centered = np.linalg.norm(points - self.center, axis=1)
        return np.abs(centered - self.radius)

    def points_per_sampling(self, sampling_density: float) -> int:
        n_points = np.multiply(
            np.square(np.pi),
            np.ceil(np.power(np.divide(self.radius, sampling_density), 2)),
        )
        return int(n_points)


class Ellipsoid(Parametrization):
    """
    Parametrize a point cloud as ellipsoid.

    Parameters
    ----------
    radii : np.ndarray
        Radii of the ellipse along each axis
    center : np.ndarray
        Center of the ellipse along each axis
    orientations : np.ndarray
        Square orientation matrix
    """

    def __init__(self, radii: np.ndarray, center: np.ndarray, orientations: np.ndarray):
        self.radii = np.asarray(radii)
        self.center = np.asarray(center)
        self.orientations = np.asarray(orientations)

    @classmethod
    def fit(cls, positions, **kwargs) -> "Ellipsoid":
        # Adapted from https://de.mathworks.com/matlabcentral/fileexchange/24693-ellipsoid-fit
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
        normal_offset: float = 0.0,
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

        remaining = n_samples
        batch_size = min(n_samples * 5, 10000)
        radii_fourth, r_min = np.power(radii, 4), np.min(radii)
        while remaining > 0:
            points = np.random.normal(size=(batch_size, 3))
            np.divide(points, np.linalg.norm(points, axis=1, keepdims=True), out=points)
            np.multiply(points, radii, out=points)

            p = r_min * np.sqrt(np.divide(np.square(points), radii_fourth).sum(axis=1))
            u = np.random.uniform(0, 1, size=batch_size)

            points = points[u <= p]
            n_accepted = min(points.shape[0], remaining)

            n_add = n_samples - remaining
            positions_xyz[n_add : (n_add + n_accepted)] = points[:n_accepted]
            remaining -= n_accepted

        positions_xyz = positions_xyz.dot(orientations.T)
        positions_xyz = np.add(positions_xyz, center)

        if sample_mesh:
            positions_xyz = _sample_from_chull(
                positions_xyz=positions_xyz,
                mesh_init_factor=mesh_init_factor,
                n_samples=n_samples,
            )
        if normal_offset != 0:
            positions_xyz = np.add(
                positions_xyz,
                np.multiply(self.compute_normal(positions_xyz), normal_offset),
            )

        return positions_xyz

    def compute_normal(self, points: np.ndarray) -> np.ndarray:
        norm_points = (points - self.center).dot(np.linalg.inv(self.orientations.T))

        normals = np.divide(np.multiply(norm_points, 2), np.square(self.radii))
        normals = np.dot(normals, self.orientations.T)
        normals /= np.linalg.norm(normals, axis=1)[:, None]
        return normals

    def compute_distance(self, points: np.ndarray, **kwargs) -> float:
        # Approximate as projected deviation from unit sphere
        norm_points = (points - self.center).dot(np.linalg.inv(self.orientations.T))
        norm_points /= np.linalg.norm(norm_points / self.radii, axis=1)[:, None]
        norm_points = np.dot(norm_points, self.orientations.T) + self.center
        ret = np.linalg.norm(points - norm_points, axis=1)
        return ret

    def points_per_sampling(self, sampling_density: float) -> int:
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
    Parametrize a point cloud as a cylinder with improved stability.

    Parameters
    ----------
    centers : np.ndarray
        Center coordinates of the cylinder in X, Y, and Z.
    orientations : np.ndarray
        Orientation matrix (direction vectors).
    radius : float
        Radius of the cylinder.
    height : float
        Height of the cylinder.
    """

    def __init__(
        self,
        centers: np.ndarray,
        orientations: np.ndarray,
        radius: float,
        height: float,
    ):
        self.centers = np.asarray(centers, dtype=np.float64)
        self.orientations = np.asarray(orientations, dtype=np.float64)
        self.radius = float(radius)
        self.height = float(height)

    @staticmethod
    def _compute_initial_guess(
        positions: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Compute initial guess for cylinder parameters using PCA.

        Parameters
        ----------
        positions : np.ndarray
            Input point cloud positions.

        Returns
        -------
        center : np.ndarray
            Initial guess for cylinder center.
        direction : np.ndarray
            Initial guess for cylinder axis direction.
        radius : float
            Initial guess for cylinder radius.
        """
        center = np.mean(positions, axis=0)
        positions_centered = positions - center

        cov_mat = np.cov(positions_centered, rowvar=False)
        evals, evecs = np.linalg.eigh(cov_mat)

        sort_idx = np.argsort(evals)[::-1]
        evals = evals[sort_idx]
        evecs = evecs[:, sort_idx]

        direction = evecs[:, -1]

        proj_matrix = np.eye(3) - np.outer(direction, direction)
        projected_points = positions_centered @ proj_matrix
        radius = np.mean(np.linalg.norm(projected_points, axis=1))
        return center, direction, radius

    @classmethod
    def fit(cls, positions: np.ndarray, **kwargs) -> "Cylinder":
        """
        Fit a cylinder to point cloud data with improved stability.

        Parameters
        ----------
        positions : np.ndarray
            Input point cloud positions (N x 3).
        **kwargs : dict
            Additional keyword arguments.

        Returns
        -------
        cylinder : Cylinder
            Fitted cylinder instance.
        """
        positions = np.asarray(positions, dtype=np.float64)
        if positions.shape[1] != 3 or len(positions.shape) != 2:
            raise ValueError("Input must be a Nx3 point cloud.")

        center_init, direction_init, radius_init = cls._compute_initial_guess(positions)
        params_init = np.concatenate([center_init, direction_init, [radius_init]])

        def objective(params):
            center = params[:3]
            direction = params[3:6]
            radius = params[6]
            direction = direction / np.linalg.norm(direction)
            diff = positions - center
            proj = np.dot(diff, direction)[:, np.newaxis] * direction
            perp = diff - proj
            distances = np.abs(np.linalg.norm(perp, axis=1) - radius)
            return np.sum(distances**2)

        constraint = {"type": "eq", "fun": lambda params: np.sum(params[3:6] ** 2) - 1}
        result = optimize.minimize(
            objective,
            params_init,
            method="SLSQP",
            constraints=[constraint],
            options={"ftol": 1e-8, "maxiter": 1000},
        )

        if not result.success:
            print("Warning: Optimization did not converge!")

        center = result.x[:3]
        direction = result.x[3:6]
        direction = direction / np.linalg.norm(direction)
        radius = abs(result.x[6])

        projected_heights = np.dot(positions - center, direction)
        height = np.max(projected_heights) - np.min(projected_heights)
        v1 = np.array([1, 0, 0])
        if not np.allclose(direction, [1, 0, 0]):
            v1 = np.array([0, 1, 0])
        v1 = v1 - np.dot(v1, direction) * direction
        v1 = v1 / np.linalg.norm(v1)
        v2 = np.cross(direction, v1)
        orientations = np.column_stack([v1, v2, direction])

        # TODO: Fix the projection offset on result.x[:3]
        center = center_init

        return cls(
            centers=center, orientations=orientations, radius=radius, height=height
        )

    def compute_normal(self, points: np.ndarray) -> np.ndarray:
        """
        Compute surface normals for points on the cylinder.

        Parameters
        ----------
        points : np.ndarray
            Input points to compute normals for.

        Returns
        -------
        normals : np.ndarray
            Computed surface normals.
        """
        points = np.asarray(points)
        diff = points - self.centers
        axis = self.orientations[:, 2]
        proj = np.dot(diff, axis)[:, np.newaxis] * axis
        perp = diff - proj
        norms = np.linalg.norm(perp, axis=1, keepdims=True)
        normals = np.where(norms > 1e-10, perp / norms, axis)
        return normals

    def sample(
        self,
        n_samples: int,
        centers: np.ndarray = None,
        orientations: np.ndarray = None,
        radius: float = None,
        height: float = None,
        normal_offset: float = 0.0,
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

        if normal_offset != 0:
            samples = np.add(
                samples, np.multiply(self.compute_normal(samples), normal_offset)
            )

        return samples

    def points_per_sampling(self, sampling_density: float) -> int:
        area_points = np.square(sampling_density)
        area = 2 * self.radius * (self.radius + self.height)

        n_points = np.ceil(np.divide(area, area_points))
        return int(n_points)


class RBF(Parametrization):
    """
    Parametrize a point cloud as sphere.

    Parameters
    ----------
    rbf : scipy.interpolate.Rbf
        Radial basis function interpolator instance.
    direction : str
        Direction of interpolation relative to positions.
    grid: Tuple
        2D interpolation grid ranges.
    """

    def __init__(self, rbf: type, direction: str, grid: Tuple):
        self.rbf = rbf
        self.grid = grid
        self.direction = direction

    @classmethod
    def fit(
        cls,
        positions: np.ndarray,
        direction: str = "xz",
        function="linear",
        smooth=5,
        **kwargs,
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
            Parametrization instance.
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
        self, n_samples: int, normal_offset: float = 0.0, **kwargs
    ) -> np.ndarray:
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

        if normal_offset != 0:
            positions_xyz = np.add(
                positions_xyz,
                np.multiply(self.compute_normal(positions_xyz), normal_offset),
            )

        return positions_xyz

    def compute_normal(self, points: np.ndarray) -> np.ndarray:
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        pcd.estimate_normals()
        pcd.normalize_normals()
        pcd.orient_normals_consistent_tangent_plane(k=15)
        normals = np.asarray(pcd.normals)
        normals /= np.linalg.norm(normals, axis=1)[:, None]
        return normals

    def points_per_sampling(self, sampling_density: float) -> int:
        (xmin, xmax), (ymin, ymax) = self.grid
        surface_area = (xmax - xmin) * (ymax - xmin)

        n_points = np.ceil(np.divide(surface_area, sampling_density))
        return int(n_points)


class TriangularMesh(Parametrization):
    """
    Represent a point cloud as triangular mesh.

    Parameters
    ----------
    mesh : open3d.cpu.pybind.geometry.TriangleMesh
        Triangular mesh.
    """

    def __init__(self, mesh):
        self.mesh = mesh

    def to_file(self, file_path):
        o3d.io.write_triangle_mesh(file_path, self.mesh)

    @classmethod
    def from_file(cls, file_path):
        return cls(mesh=o3d.io.read_triangle_mesh(file_path))

    def __getstate__(self):
        state = {"vertices": self.vertices, "triangles": self.triangles}

        if self.mesh.has_vertex_normals():
            state["vertex_normals"] = np.asarray(self.mesh.vertex_normals)
        if self.mesh.has_vertex_colors():
            state["vertex_colors"] = np.asarray(self.mesh.vertex_colors)
        if self.mesh.has_triangle_normals():
            state["triangle_normals"] = np.asarray(self.mesh.triangle_normals)
        return state

    def __setstate__(self, state):
        mesh = to_open3d(state["vertices"], state["triangles"])
        attrs = ("vertex_normals", "vertex_colors", "triangle_normals")
        for attr in attrs:
            if attr not in state:
                continue
            setattr(mesh, attr, o3d.utility.Vector3dVector(state.get(attr)))

        self.mesh = mesh

    @property
    def vertices(self):
        return np.asarray(self.mesh.vertices)

    @property
    def triangles(self):
        return np.asarray(self.mesh.triangles)

    @classmethod
    def fit(
        cls,
        positions: np.ndarray,
        radii: Tuple[float] = (5.0,),
        voxel_size: float = 10,
        max_hole_size: float = -1,
        downsample_input: bool = False,
        elastic_weight: float = 1.0,
        curvature_weight: float = 0.0,
        volume_weight: float = 0.0,
        n_smoothing: int = 5,
        k_neighbors=50,
        **kwargs,
    ):
        radii = np.asarray(radii).reshape(-1)
        radii = radii[radii > 0]

        # Surface reconstruction normal estimation
        positions = np.asarray(positions, dtype=np.float64)

        # Reduce membrane thickness
        voxel_size = np.max(voxel_size)
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(positions)
        if downsample_input:
            positions = com_cluster_points(positions, cutoff=4 * voxel_size)
            pcd.points = o3d.utility.Vector3dVector(positions)

        pcd.estimate_normals()
        pcd.normalize_normals()
        pcd.orient_normals_consistent_tangent_plane(k=k_neighbors)

        mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(
            pcd, o3d.utility.DoubleVector(radii)
        )

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
        if n_smoothing > 0:
            mesh = mesh.filter_smooth_taubin(number_of_iterations=n_smoothing)

        if np.asarray(mesh.vertices).shape[0] == 0:
            print("No suitable vertices for mesh creation found.")
            return None

        if max_hole_size == 0:
            return cls(mesh=mesh)

        # Hole triangulation and fairing
        new_vs, new_fs = triangulate_refine_fair(
            vs=np.asarray(mesh.vertices),
            fs=np.asarray(mesh.triangles),
            hole_len_thr=max_hole_size,
            alpha=elastic_weight,
            beta=curvature_weight,
            gamma=volume_weight,
        )
        mesh = to_open3d(new_vs, new_fs)
        mesh = mesh.remove_degenerate_triangles()
        if n_smoothing > 0:
            mesh = mesh.filter_smooth_taubin(number_of_iterations=n_smoothing)

        mesh = mesh.compute_vertex_normals()
        return cls(mesh=mesh)

    def sample(
        self,
        n_samples: int,
        mesh_init_factor: bool = None,
        normal_offset: float = 0.0,
        **kwargs,
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
        mesh = self.mesh
        if normal_offset != 0:
            self.mesh.compute_vertex_normals()
            mesh = to_open3d(
                np.add(self.vertices, normal_offset * np.asarray(mesh.vertex_normals)),
                self.triangles,
            )
        return _sample_from_mesh(mesh, n_samples, mesh_init_factor)

    def _setup_rayscene(self):
        mesh = o3d.t.geometry.TriangleMesh.from_legacy(self.mesh)
        scene = o3d.t.geometry.RaycastingScene()
        scene_id = scene.add_triangles(mesh)
        return scene, scene_id

    def compute_normal(self, points: np.ndarray) -> np.ndarray:
        self.mesh.compute_triangle_normals()

        scene, _ = self._setup_rayscene()
        points_tensor = o3d.core.Tensor(points, dtype=o3d.core.Dtype.Float32)
        closest_info = scene.compute_closest_points(points_tensor)

        normals = closest_info["primitive_normals"].numpy()
        return normals / np.linalg.norm(normals, axis=1, keepdims=True)

    def compute_curvature(
        self, curvature: str = "gaussian", radius: int = 5
    ) -> np.ndarray:
        vertices = np.asarray(self.mesh.vertices)
        faces = np.asarray(self.mesh.triangles)

        use_k_ring = True
        if radius < 2:
            radius, use_k_ring = 2, False

        pd1, pd2, pv1, pv2 = igl.principal_curvature(
            vertices, faces, radius=radius, use_k_ring=use_k_ring
        )

        curvature = curvature.lower()
        if curvature == "gaussian":
            return pv1 * pv2
        elif curvature == "mean":
            return (pv1 + pv2) / 2
        else:
            raise ValueError("Only 'gaussian' and 'mean' curvature supported.")

    def compute_vertex_normals(self) -> np.ndarray:
        self.mesh.compute_vertex_normals()
        return np.asarray(self.mesh.vertex_normals).copy()

    def points_per_sampling(self, sampling_density: float) -> int:
        area_per_sample = np.square(sampling_density)
        n_points = np.ceil(np.divide(self.mesh.get_surface_area(), area_per_sample))
        return int(n_points)

    def compute_distance(
        self,
        points: np.ndarray,
        normals: np.ndarray = None,
        return_projection: bool = False,
        return_indices: bool = False,
        return_triangles: bool = False,
        **kwargs,
    ) -> np.ndarray:
        """
        Compute distance to mesh by ray-casting.

        Parameters
        ----------
        points : np.ndarray
            Points to compute distance from or project onto mesh
        normals : np.ndarray, optional
            Normal vectors for projection direction. If None, computes shortest distance.
        return_projection : bool, optional
            Return points projected onto mesh, defaults to False.
        return_indices : bool, optional
            Return vertex indices closest to projection, defaults to False.
        return_triangles : bool, optional
            Return triangles indices hit by raycasting.

        Returns
        -------
        distances : np.ndarray
            Distance to mesh surface for each point.
        projection : np.ndarray, optional
            Projection of each point onto mesh surface.
        indices : np.ndarray, optional
            Closest vertex to projection.
        triangles : np.ndarray, optional
            Triangle indices hit by projection.
        """
        self.mesh.compute_vertex_normals()
        self.mesh.compute_triangle_normals()

        scene, _ = self._setup_rayscene()

        if normals is None:
            ret = scene.compute_closest_points(
                o3d.core.Tensor(points, dtype=o3d.core.Dtype.Float32)
            )
            projected_points = ret["points"].numpy()
            triangle_indices = ret["primitive_ids"].numpy()
        else:
            rays = o3d.core.Tensor(
                np.hstack([points, normals]), dtype=o3d.core.Dtype.Float32
            )
            hits = scene.cast_rays(rays)

            hit_distances = hits["t_hit"].numpy()
            valid_hits = np.logical_and(hit_distances > 0, np.isfinite(hit_distances))

            n_invalid = valid_hits.size - np.sum(valid_hits)
            if n_invalid > 0:
                warnings.warn(
                    f"{n_invalid} of {valid_hits.size} did not intersect with the mesh. "
                    f"Check the accuracy of the associated normal vectors. Falling back to "
                    "Euclidean distance for those cases."
                )

            projected_points = np.copy(points)
            projected_points[valid_hits] += (
                normals[valid_hits] * hit_distances[valid_hits, np.newaxis]
            )
            triangle_indices = hits["primitive_ids"].numpy()

        dist = np.linalg.norm(points - projected_points, axis=1)
        _, vertex_indices = find_closest_points(self.vertices, projected_points, k=1)

        ret = [dist]

        if return_projection:
            ret.append(projected_points)
        if return_indices:
            ret.append(np.array(vertex_indices))
        if return_triangles:
            ret.append(np.array(triangle_indices))

        if len(ret) == 1:
            return ret[0]
        return ret

    def add_projections(
        self,
        projections: np.ndarray,
        triangle_indices: np.ndarray,
        return_indices: bool = False,
    ) -> Tuple["TriangularMesh", np.ndarray]:
        """
        Add projected points to the mesh by splitting triangles.

        Parameters
        ----------
        projections : np.ndarray
            Projections on the mesh surface to add to the mesh.
        triangle_indices : np.ndarray
            Indices of triangles that each point projects onto.
        return_indices : bool, optional
            Whether to return the index of projections in the new mesh.

        Returns
        -------
        mesh : TriangularMesh
            New mesh with valid projections added
        indices : np.ndarray,
            Array of vertex indices for the added points in the new mesh
        """

        keep = np.logical_and(
            triangle_indices >= 0, triangle_indices < self.triangles.shape[0]
        )
        projections = projections[keep]
        triangle_indices = triangle_indices[keep]

        if len(projections) == 0:
            return to_open3d(self.vertices.copy(), self.triangles.copy())

        n_vertices = self.vertices.shape[0]
        vertices = np.vstack((self.vertices, projections))
        new_indices = np.arange(projections.shape[0]) + n_vertices

        triangles = self.triangles
        triangle_to_points = {}
        for i, tri_idx in enumerate(triangle_indices):
            if tri_idx not in triangle_to_points:
                triangle_to_points[tri_idx] = []
            triangle_to_points[tri_idx].append(i)

        new_triangles = []
        processed_triangles = set()
        for tri_idx, point_indices in triangle_to_points.items():
            v1_idx, v2_idx, v3_idx = triangles[tri_idx]

            processed_triangles.add(tri_idx)

            if len(point_indices) == 1:
                new_vertex_idx = new_indices[point_indices[0]]
                new_triangles.append([v1_idx, v2_idx, new_vertex_idx])
                new_triangles.append([v2_idx, v3_idx, new_vertex_idx])
                new_triangles.append([v3_idx, v1_idx, new_vertex_idx])
                continue

            # Complex case: multiple points in the same triangle
            # Create a Delaunay triangulation of the points plus triangle vertices
            tri_vertices = np.array(
                [vertices[v1_idx], vertices[v2_idx], vertices[v3_idx]]
            )

            point_indices = np.array(point_indices)

            tri_points = projections[point_indices]
            tri_point_indices = new_indices[point_indices]
            all_points = np.vstack((tri_vertices, tri_points))

            # Project points into triangle plan for triangulation
            e1 = tri_vertices[1] - tri_vertices[0]
            normal = np.cross(e1, tri_vertices[2] - tri_vertices[0])

            e1 = e1 / np.linalg.norm(e1)
            e2 = np.cross(normal / np.linalg.norm(normal), e1)
            all_points_2d = np.zeros((all_points.shape[0], 2))
            all_points_2d[:, 0] = np.dot(all_points - tri_vertices[0], e1)
            all_points_2d[:, 1] = np.dot(all_points - tri_vertices[0], e2)

            try:
                from scipy.spatial import Delaunay

                tri = Delaunay(all_points_2d)
                all_indices = np.array(
                    [v1_idx, v2_idx, v3_idx] + tri_point_indices.tolist()
                )

                for simplex in tri.simplices:
                    new_triangles.append(all_indices[simplex])

            except Exception as e:
                warnings.warn(str(e))
                warnings.warn("Falling back to star triangulation instead.")

                # Fallback: Star triangulation adding erach point one by one.
                current_triangle_indices = [[v1_idx, v2_idx, v3_idx]]

                for i, new_vertex_idx in enumerate(tri_point_indices):
                    next_triangle_indices = []

                    for t in current_triangle_indices:
                        new_triangles.append([t[0], t[1], new_vertex_idx])
                        new_triangles.append([t[1], t[2], new_vertex_idx])
                        new_triangles.append([t[2], t[0], new_vertex_idx])

                    current_triangle_indices = next_triangle_indices

        for i in range(len(triangles)):
            if i not in processed_triangles:
                new_triangles.append(triangles[i].tolist())

        new_mesh = TriangularMesh(to_open3d(vertices, np.array(new_triangles)))
        if return_indices:
            return new_mesh, new_indices
        return new_mesh

    def geodesic_distance(
        self,
        target_vertices: np.ndarray,
        source_vertices: np.ndarray = None,
        k: int = 1,
        return_indices: bool = False,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute geodesic distance from target vertices to their k-nearest
        source vertices on the mesh.

        Parameters
        ----------
        target_vertices : np.ndarray
            Target vertex indices for which to compute distances.
        source_vertices : np.ndarray, optional
            Source vertex indices to compute distances from.
            If None, uses all mesh vertices as sources.
        k : int, optional
            Number of closest source vertices to find for each target vertex.
            Minimum and default value is 1 (nearest neighbor).
        return_indices : bool, optional
            Whether to also return an array of closest vertices in terms of geodesic
            distance. Defaults to False.

        Returns
        -------
        distances: ndarray
            Geodesic distances to k closest sources. Shape is (len(target_vertices), k).
        indices: ndarray, optional
            Corresponding source vertex indices. Shape is (len(target_vertices), k).
        """
        if source_vertices is None:
            source_vertices = np.arange(self.vertices.shape[0])

        k = max(1, min(k, len(source_vertices)))
        source_vertices = np.asarray(source_vertices, dtype=np.int32).ravel()
        target_vertices = np.asarray(target_vertices, dtype=np.int32).ravel()

        k_distances, k_indices = [], []
        for i, tgt_idx in enumerate(target_vertices):
            kwargs = {
                "vt": source_vertices[source_vertices != tgt_idx],
                "vs": np.array([tgt_idx], dtype=np.int32),
            }

            # Faster, we only need to find the closest non-trivial neighbor
            if k == 1:
                kwargs = {"vt": kwargs["vs"], "vs": kwargs["vt"]}

            distances = igl.exact_geodesic(v=self.vertices, f=self.triangles, **kwargs)
            distances = np.atleast_1d(distances)

            sorted_indices = np.argsort(distances)[:k]
            k_distances.append(distances[sorted_indices])
            k_indices.append(source_vertices[sorted_indices])

        k_distances = np.asarray(k_distances)
        if return_indices:
            return k_distances, np.asarray(k_indices)
        return k_distances


class PoissonMesh(TriangularMesh):
    @classmethod
    def fit(
        cls,
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
        mesh = poisson_mesh(
            positions=positions,
            voxel_size=voxel_size,
            depth=depth,
            k_neighbors=k_neighbors,
            smooth_iter=smooth_iter,
            pointweight=pointweight,
            deldist=deldist,
            scale=scale,
            samplespernode=samplespernode,
        )
        return cls(mesh=mesh)


class ClusteredBallPivotingMesh(TriangularMesh):
    @classmethod
    def fit(
        cls,
        positions: np.ndarray,
        voxel_size: float = None,
        radius: int = 0,
        k_neighbors=50,
        smooth_iter=1,
        deldist=-1.0,
        creasethr=90,
        **kwargs,
    ):
        from pymeshlab import MeshSet, Mesh, PercentageValue

        voxel_size = 1 if voxel_size is None else voxel_size
        positions = np.divide(np.asarray(positions, dtype=np.float64), voxel_size)

        ms = MeshSet()
        ms.add_mesh(Mesh(positions))
        ms.compute_normal_for_point_clouds(k=k_neighbors, smoothiter=smooth_iter)
        ms.generate_surface_reconstruction_ball_pivoting(
            ballradius=PercentageValue(radius),
            creasethr=creasethr,
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
        return cls(
            mesh=to_open3d(mesh.vertex_matrix() * voxel_size, mesh.face_matrix())
        )


class ConvexHull(TriangularMesh):
    """
    Represent a point cloud as triangular mesh.

    Parameters
    ----------
    mesh : open3d.cpu.pybind.geometry.TriangleMesh
        Triangular mesh.
    """

    @classmethod
    def fit(
        cls,
        positions: np.ndarray,
        voxel_size: float = None,
        alpha: float = 1,
        elastic_weight: float = 0,
        curvature_weight: float = 0,
        volume_weight: float = 0,
        boundary_ring: int = 0,
        k_neighbors=50,
        resampling_factor: float = 12.0,
        distance_cutoff: float = 2.0,
        **kwargs,
    ):
        voxel_size = 1 if voxel_size is None else voxel_size
        voxel_size = np.max(voxel_size)

        positions = np.asarray(positions, dtype=np.float64)

        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(positions.copy())
        pcd = pcd.voxel_down_sample(voxel_size=2 * voxel_size)

        points = np.asarray(pcd.points).copy()
        scale = points.max(axis=0)
        pcd.points = o3d.utility.Vector3dVector(points / scale)

        pcd.estimate_normals()
        pcd.normalize_normals()
        pcd.orient_normals_consistent_tangent_plane(k=k_neighbors)

        try:
            with o3d.utility.VerbosityContextManager(o3d.utility.VerbosityLevel.Error):
                mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_alpha_shape(
                    pcd, alpha
                )
        except Exception as e:
            print(e)
            print("Falling back to scConvexHull.")

            hull = scConvexHull(positions, qhull_options="Qs")
            mesh = to_open3d(positions[hull.vertices], hull.simplices)
            return cls(mesh=mesh)

        mesh.vertices = o3d.utility.Vector3dVector(
            np.multiply(np.asarray(mesh.vertices), scale)
        )
        mesh = mesh.remove_non_manifold_edges()
        mesh = mesh.remove_degenerate_triangles()
        mesh = mesh.remove_duplicated_triangles()
        mesh = mesh.remove_unreferenced_vertices()
        mesh = mesh.remove_duplicated_vertices()

        # Better compression and guaranteed to be watertight
        if alpha == 1:
            mesh = o3d.t.geometry.TriangleMesh.from_legacy(mesh)
            mesh = mesh.compute_convex_hull()
            mesh = mesh.to_legacy()

        if elastic_weight == curvature_weight == volume_weight == 0:
            return cls(mesh=mesh)

        # Fair vertices that are distant to input points
        mesh = remesh(mesh, resampling_factor * voxel_size)
        vs, fs = np.asarray(mesh.vertices), np.asarray(mesh.triangles)
        distances, _ = find_closest_points(positions, vs)

        vids = np.where(distances > (resampling_factor / distance_cutoff * voxel_size))[
            0
        ]
        if len(vids) == 0:
            return cls(mesh=to_open3d(vs, fs))

        vids = np.asarray(list(get_ring_vertices(vs, fs, vids, boundary_ring)))
        out_vs = fair_mesh(
            vs,
            fs,
            vids=vids,
            alpha=elastic_weight,
            beta=curvature_weight,
            gamma=volume_weight,
        )
        return cls(mesh=to_open3d(out_vs, fs))


class FairHull(ConvexHull):
    pass


class SplineCurve(Parametrization):
    """
    Parametrize a point cloud as a spline curve.

    Parameters
    ----------
    positions : np.ndarray
        Control points defining the spline curve
    """

    def __init__(self, positions: np.ndarray, order: int = 1, **kwargs):
        self.positions = np.asarray(positions)

        params = self._compute_params()
        if order == 3:
            self._splines = [
                interpolate.CubicSpline(params, self.positions[:, i])
                for i in range(self.positions.shape[1])
            ]
        else:
            self._splines = [
                interpolate.UnivariateSpline(params, self.positions[:, i], k=order)
                for i in range(self.positions.shape[1])
            ]

    def _compute_params(self) -> np.ndarray:
        diff = np.diff(self.positions, axis=0)
        chord_lengths = np.linalg.norm(diff, axis=1)
        cumulative = np.concatenate(([0], np.cumsum(chord_lengths)))
        return cumulative / cumulative[-1]

    @classmethod
    def fit(cls, positions: np.ndarray, **kwargs) -> "SplineCurve":
        return cls(positions=np.asarray(positions, dtype=np.float64), **kwargs)

    def sample(
        self, n_samples: int, normal_offset: float = 0.0, **kwargs
    ) -> np.ndarray:
        t = np.linspace(0, 1, n_samples)
        points = np.column_stack([spline(t) for spline in self._splines])

        if normal_offset != 0:
            points = np.add(
                points, np.multiply(self.compute_normal(points), normal_offset)
            )

        return points

    def compute_normal(self, points: np.ndarray) -> np.ndarray:
        params = np.linspace(0, 1, len(points))
        tangents = np.column_stack(
            [spline.derivative()(params) for spline in self._splines]
        )
        tangents /= np.linalg.norm(tangents, axis=1)[:, np.newaxis]
        normals = np.zeros_like(tangents)
        normals[:, 0] = -tangents[:, 1]
        normals[:, 1] = tangents[:, 0]
        return normals

    def points_per_sampling(self, sampling_density: float) -> int:
        curve_points = self.sample(1000)
        segments = curve_points[1:] - curve_points[:-1]
        length = np.sum(np.linalg.norm(segments, axis=1))
        n_points = int(np.ceil(length / sampling_density))
        return n_points


PARAMETRIZATION_TYPE = {
    "sphere": Sphere,
    "ellipsoid": Ellipsoid,
    "cylinder": Cylinder,
    "mesh": TriangularMesh,
    "clusterballpivoting": ClusteredBallPivotingMesh,
    "poissonmesh": PoissonMesh,
    "rbf": RBF,
    "convexhull": ConvexHull,
    "spline": SplineCurve,
}
