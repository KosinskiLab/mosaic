"""
Test suite for parametrization module.

Tests all parametrization classes with random point cloud data.
Uses fixtures and parametrize to reduce code duplication.
"""

import pickle
import pytest
import numpy as np

from mosaic.parametrization import PARAMETRIZATION_TYPE, TriangularMesh, BallPivoting

PARAMETRIZATION_CONFIG = [
    ("Sphere", "sphere", {}),
    ("Ellipsoid", "ellipsoid", {}),
    ("Cylinder", "cylinder", {}),
    ("RBF", "cloud", {"direction": "xz"}),
    ("Spline", "spline", {"order": 1}),
]

MESH_PARAMETRIZATION_CONFIG = [
    ("Ball_Pivoting", "sphere", {"radii": [5.0]}),
    (
        "Alpha_Shape",
        "sphere",
        {"elastic_weight": 1.0, "voxel_size": 1.5, "resampling_factor": 3.0},
    ),
    ("Poisson", "sphere", {}),
]

BASE_CONFIG = [*PARAMETRIZATION_CONFIG, *MESH_PARAMETRIZATION_CONFIG]


def generate_random_points(n_points=100, shape="sphere", noise=0.1):
    """Generate random point cloud data for testing."""
    np.random.seed(42)
    if shape in "sphere":
        theta = np.random.uniform(0, 2 * np.pi, n_points)
        phi = np.random.uniform(0, np.pi, n_points)
        r = 10 + np.random.normal(0, noise, n_points)
        x = r * np.sin(phi) * np.cos(theta)
        y = r * np.sin(phi) * np.sin(theta)
        z = r * np.cos(phi)
        return np.column_stack([x, y, z])

    elif shape == "ellipsoid":
        theta = np.random.uniform(0, 2 * np.pi, n_points)
        phi = np.random.uniform(0, np.pi, n_points)
        x = (10 + np.random.normal(0, noise, n_points)) * np.sin(phi) * np.cos(theta)
        y = (5 + np.random.normal(0, noise, n_points)) * np.sin(phi) * np.sin(theta)
        z = (7 + np.random.normal(0, noise, n_points)) * np.cos(phi)
        return np.column_stack([x, y, z])

    elif shape == "cylinder":
        theta = np.random.uniform(0, 2 * np.pi, n_points)
        h = np.random.uniform(-10, 10, n_points)
        r = 10 + np.random.normal(0, noise, n_points)
        x = r * np.cos(theta)
        y = r * np.sin(theta)
        z = h
        return np.column_stack([x, y, z])

    elif shape == "cloud":
        arr = np.random.rand(32, 32, 32)
        indices = np.where(arr > 0.95)
        return np.column_stack(indices).astype(np.float64)

    elif shape == "spline":
        t = np.linspace(0, 2 * np.pi, n_points)
        return np.column_stack([np.cos(t), np.sin(t), t])

    else:
        raise ValueError(f"Unknown shape: {shape}")


@pytest.fixture
def mesh_points():
    return generate_random_points(100, "sphere")


@pytest.fixture(scope="module", params=BASE_CONFIG, ids=lambda x: x[0])
def fitted_param(request):
    """
    Fixture that provides fitted parametrizations.
    Cached at module scope, so each parametrization is fitted only once.
    """
    class_name, shape, fit_kwargs = request.param
    points = generate_random_points(100, shape)

    ParamClass = PARAMETRIZATION_TYPE[class_name.lower()]
    param = ParamClass.fit(points, **fit_kwargs)
    return param, class_name, shape, fit_kwargs


class TestParametrizationBase:
    """Test common functionality across all parametrization classes."""

    def test_fit(self, fitted_param):
        param, class_name, shape, fit_kwargs = fitted_param
        ParamClass = PARAMETRIZATION_TYPE[class_name.lower()]

        assert isinstance(param, ParamClass)

    def test_pickle(self, fitted_param, tmp_path):
        param, class_name, shape, fit_kwargs = fitted_param

        rep = pickle.dumps(param)
        new_param = pickle.loads(rep)
        assert isinstance(new_param, type(param))

    @pytest.mark.parametrize("normal_offset", [0, 2.0])
    @pytest.mark.parametrize("mesh_init_factor", [None, 5])
    def test_sample(self, fitted_param, normal_offset, mesh_init_factor):
        param, class_name, shape, fit_kwargs = fitted_param

        np.random.seed(42)

        n_samples = 1000
        samples = param.sample(
            n_samples=n_samples,
            normal_offset=normal_offset,
            mesh_init_factor=mesh_init_factor,
        )

        assert samples.shape[1] == 3
        assert np.all(np.isfinite(samples))

        # Poisson disk sampling does not guarantee n_samples are drawn
        if mesh_init_factor is None and class_name not in ("RBF", "Cylinder"):
            assert samples.shape == (n_samples, 3)

        if hasattr(param, "compute_distance"):
            atol = 0.5

            # Distance computation is still approximate for these
            if class_name in ("RBF", "SplineCurve"):
                atol = max(normal_offset / 2, atol * 2)

            dist = param.compute_distance(samples)
            assert np.allclose(dist.mean(), normal_offset, atol=atol)

    def test_compute_normal(self, fitted_param):
        param, class_name, shape, fit_kwargs = fitted_param

        test_points = param.sample(n_samples=50)
        normals = param.compute_normal(test_points)

        assert normals.shape == test_points.shape
        assert np.all(np.isfinite(normals))
        assert np.allclose(np.linalg.norm(normals, axis=1), 1)

    @pytest.mark.parametrize("normal_offset", [0, 2.0])
    def test_points_per_sampling(self, fitted_param, normal_offset):
        param, class_name, shape, fit_kwargs = fitted_param

        n_points = param.points_per_sampling(
            sampling_density=1.0, normal_offset=normal_offset
        )

        assert n_points > 0
        assert isinstance(n_points, int)


class TestMeshSpecific:

    @pytest.fixture(scope="class")
    def mesh(self):
        points = generate_random_points(100, "sphere")
        mesh = BallPivoting.fit(points, radii=[5.0])
        mesh.mesh.compute_vertex_normals()
        return mesh

    @pytest.mark.parametrize("formats", [".ply", ".obj", ".stl"])
    def test_io(self, tmp_path, formats, mesh):
        path = tmp_path / f"mesh{formats}"
        mesh.to_file(str(path))
        new_mesh = mesh.from_file(str(path))

        assert new_mesh.vertices.shape[1] == 3
        assert new_mesh.triangles.shape[1] == 3

        # STL does not preserve exact topology (vertices are duplicated per face)
        if formats != ".stl":
            idx1 = np.argsort(mesh.vertices, axis=0)
            idx2 = np.argsort(new_mesh.vertices, axis=0)
            assert new_mesh.triangles.shape == mesh.triangles.shape
            assert np.allclose(new_mesh.vertices[idx2], mesh.vertices[idx1])

    def test_compute_distance(self, mesh):
        np.random.seed(42)
        samples = mesh.sample(50)

        dist = mesh.compute_distance(samples)
        assert dist.shape == (50,)
        assert np.all(np.isfinite(dist))
        assert np.all(dist >= 0)

    def test_geodesic_distance(self, mesh):
        target_vertices = np.array([0, 1, 2])
        distances = mesh.geodesic_distance(target_vertices, k=1)

        assert distances.shape == (3, 1)
        assert np.all(distances >= 0)

    def test_compute_curvature(self, mesh):
        curvature = mesh.compute_curvature(curvature="gaussian")

        assert curvature.shape[0] == mesh.vertices.shape[0]
        assert np.all(np.isfinite(curvature))

    def test_add_projections(self, mesh):
        test_points = mesh.sample(n_samples=5)

        # Provoke points mapping to same triangle for local triangulation
        test_points = np.concatenate((test_points, test_points), axis=0)
        _, projections, _, triangles = mesh.compute_distance(
            test_points,
            return_projection=True,
            return_triangles=True,
            return_indices=True,
        )

        new_mesh, indices = mesh.add_projections(
            projections, triangles, return_indices=True
        )

        assert new_mesh.vertices.shape[0] >= mesh.vertices.shape[0]
        assert len(indices) <= len(projections)


class TestCylinderDistance:
    """Accurate mesh-backed distance for the analytic cylinder."""

    def _axis_aligned_cylinder(self):
        from mosaic.parametrization import Cylinder

        return Cylinder(
            centers=np.zeros(3),
            orientations=np.eye(3),
            radius=10.0,
            height=40.0,
        )

    def test_distance_to_surface_is_accurate(self):
        cyl = self._axis_aligned_cylinder()
        # Points at known perpendicular offset from the axis, mid-height band.
        offsets = np.array([12.0, 15.0, 8.0])
        pts = np.column_stack([offsets, np.zeros(3), np.array([0.0, 5.0, -5.0])])
        dist = cyl.compute_distance(pts)
        expected = np.abs(offsets - cyl.radius)
        assert np.allclose(dist, expected, atol=0.2)

    def test_distance_beats_sampling_fallback(self):
        cyl = self._axis_aligned_cylinder()
        pts = np.array([[13.0, 0.0, 0.0]])
        err = abs(float(cyl.compute_distance(pts)[0]) - 3.0)
        assert err < 0.2

    def test_signed_distance_inside_negative(self):
        cyl = self._axis_aligned_cylinder()
        pts = np.array([[0.0, 0.0, 0.0], [20.0, 0.0, 0.0]])
        signed = cyl.compute_distance(pts, signed=True)
        assert signed[0] < 0  # axis point is inside
        assert signed[1] > 0  # far point is outside

    def test_projection_lands_on_surface(self):
        cyl = self._axis_aligned_cylinder()
        pts = np.array([[13.0, 0.0, 2.0], [0.0, 14.0, -3.0]])
        _, proj = cyl.compute_distance(pts, return_projection=True)
        radial = np.linalg.norm(proj[:, :2], axis=1)
        assert np.allclose(radial, cyl.radius, atol=0.3)

    def test_pickle_preserves_distance(self):
        import pickle

        cyl = self._axis_aligned_cylinder()
        pts = np.array([[13.0, 0.0, 0.0]])
        before = cyl.compute_distance(pts)
        restored = pickle.loads(pickle.dumps(cyl))
        after = restored.compute_distance(pts)
        assert np.allclose(before, after, atol=1e-6)
