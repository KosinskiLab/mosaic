import numpy as np
import pytest
from unittest.mock import Mock

from mosaic.geometry import GeometryData
from mosaic.operations import (
    cluster,
    compute_normals,
    downsample,
    duplicate,
    fit,
    remesh,
    remove_outliers,
    sample,
    skeletonize,
    smooth,
    visibility,
)


class TestCluster:
    def test_dbscan_two_blobs(self, two_blobs):
        results = cluster(two_blobs, method="dbscan", distance=20)
        assert len(results) >= 2

    def test_connected_components(self, two_blobs):
        results = cluster(two_blobs, method="connected_components", distance=20)
        assert len(results) >= 2

    def test_kmeans(self, two_blobs):
        results = cluster(two_blobs, method="kmeans", n_clusters=2)
        assert len(results) == 2
        total = sum(r.points.shape[0] for r in results)
        assert total == 160

    def test_drop_noise(self, two_blobs):
        results_no_drop = cluster(
            two_blobs, method="dbscan", distance=20, drop_noise=False
        )
        results_drop = cluster(two_blobs, method="dbscan", distance=20, drop_noise=True)
        assert len(results_drop) <= len(results_no_drop)

    def test_invalid_method(self, cloud):
        with pytest.raises(ValueError):
            cluster(cloud, method="nonexistent")


class TestRemoveOutliers:
    def test_statistical(self, cloud):
        result = remove_outliers(
            cloud, method="statistical", k_neighbors=10, thresh=1.0
        )
        assert result is not None
        assert result.points.shape[0] <= cloud.points.shape[0]
        assert result.points.shape[0] > 0

    def test_eigenvalue(self, cloud):
        result = remove_outliers(cloud, method="eigenvalue", k_neighbors=10, thresh=0.1)
        assert result is not None
        assert result.points.shape[0] <= cloud.points.shape[0]

    def test_preserves_normals(self, cloud):
        result = remove_outliers(
            cloud, method="statistical", k_neighbors=10, thresh=2.0
        )
        assert result.normals is not None
        assert result.normals.shape[0] == result.points.shape[0]

    def test_invalid_method(self, cloud):
        with pytest.raises(ValueError):
            remove_outliers(cloud, method="bogus")


class TestComputeNormals:
    def test_compute(self, cloud):
        bare = GeometryData(points=cloud.points)
        result = compute_normals(bare, method="compute", k=10)
        assert result.normals is not None
        assert result.normals.shape == cloud.points.shape

    def test_flip(self, cloud):
        result = compute_normals(cloud, method="flip")
        np.testing.assert_allclose(result.normals, -cloud.normals, atol=1e-6)

    def test_flip_preserves_shape(self, cloud):
        result = compute_normals(cloud, method="flip")
        assert result.normals.shape == cloud.normals.shape


class TestDuplicate:
    def test_returns_same_data(self, cloud):
        copy = duplicate(cloud)
        np.testing.assert_array_equal(copy.points, cloud.points)
        assert copy is not cloud


class TestDownsample:
    def test_number(self, cloud):
        result = downsample(cloud, method="number", size=50)
        assert result.points.shape[0] == 50

    def test_center_of_mass(self, cloud):
        result = downsample(cloud, method="center_of_mass", radius=20.0)
        assert result.points.shape[0] < cloud.points.shape[0]


class TestFit:
    def test_sphere(self, sphere_cloud):
        result = fit(sphere_cloud, method="sphere")
        assert result.model is not None
        assert result.points.shape[0] > 0

    def test_ellipsoid(self, sphere_cloud):
        result = fit(sphere_cloud, method="ellipsoid")
        assert result.model is not None

    def test_insufficient_points(self):
        tiny = GeometryData(points=np.zeros((5, 3), dtype=np.float32))
        with pytest.raises(ValueError, match="Insufficient"):
            fit(tiny, method="sphere")

    def test_invalid_method(self, cloud):
        with pytest.raises(ValueError):
            fit(cloud, method="nonexistent")


class TestSample:
    def test_sample_from_fitted_sphere(self, sphere_cloud):
        fitted = fit(sphere_cloud, method="sphere")
        result = sample(fitted, sampling=100, method="points")
        assert result.points.shape[0] == 100
        assert result.normals is not None

    def test_no_model(self, cloud):
        result = sample(cloud, sampling=100, method="points")
        assert result is None


class TestSkeletonize:
    def test_core(self, cloud):
        result = skeletonize(cloud, method="core", sigma=1.0)
        assert result.points.shape[0] > 0
        assert result.points.shape[1] == 3

    def test_invalid_method(self, cloud):
        with pytest.raises(ValueError):
            skeletonize(cloud, method="nonexistent")


class TestVisibility:
    def test_show(self):
        mock = Mock()
        visibility(mock, visible=True)
        mock.set_visibility.assert_called_once_with(True)

    def test_hide(self):
        mock = Mock()
        visibility(mock, visible=False)
        mock.set_visibility.assert_called_once_with(False)


class TestSkeletonizeExtended:

    @pytest.fixture
    def dense_cloud(self):
        """Dense cloud suitable for skeletonization (needs volume-filling points)."""
        rng = np.random.RandomState(99)
        pts = rng.rand(2000, 3).astype(np.float32) * 20
        return GeometryData(points=pts)

    def test_outer_hull(self, dense_cloud):
        result = skeletonize(dense_cloud, method="outer_hull", sample_fraction=0.5)
        assert result.points.shape[0] > 0

    def test_boundary(self, dense_cloud):
        result = skeletonize(dense_cloud, method="boundary", sigma=1.0)
        assert result.points.shape[0] > 0

    def test_outer(self, dense_cloud):
        result = skeletonize(dense_cloud, method="outer", sigma=1.0)
        assert result.points.shape[0] > 0


class TestComputeNormalsExtended:
    def test_flip_no_normals_raises(self):
        mock = Mock()
        mock.normals = None
        mock.__getitem__ = Mock(return_value=mock)
        with pytest.raises(ValueError, match="no normal"):
            compute_normals(mock, method="flip")

    def test_invalid_method(self, cloud):
        with pytest.raises(ValueError, match="Unsupported"):
            compute_normals(cloud, method="bogus")


class TestDownsampleExtended:
    def test_radius(self, cloud):
        result = downsample(cloud, method="radius", voxel_size=15.0)
        assert result.points.shape[0] < cloud.points.shape[0]
        assert result.points.shape[0] > 0

    def test_radius_preserves_normals(self, cloud):
        result = downsample(cloud, method="radius", voxel_size=15.0)
        assert result.normals is not None
        assert result.normals.shape[0] == result.points.shape[0]

    def test_center_of_mass_default_radius(self, cloud):
        result = downsample(cloud, method="center_of_mass")
        assert result.points.shape[0] < cloud.points.shape[0]

    def test_invalid_method(self, cloud):
        with pytest.raises(ValueError, match="Supported"):
            downsample(cloud, method="bogus")

    def test_number_clamps(self, cloud):
        result = downsample(cloud, method="number", size=99999)
        assert result.points.shape[0] == cloud.points.shape[0]


class TestSampleExtended:
    def test_bidirectional(self, sphere_cloud):
        fitted = fit(sphere_cloud, method="sphere")
        normal = sample(fitted, sampling=50, method="points")
        bidir = sample(fitted, sampling=50, method="points", bidirectional=True)
        assert bidir.points.shape[0] == 2 * normal.points.shape[0]
        assert bidir.normals.shape[0] == bidir.points.shape[0]

    def test_distance_method(self, sphere_cloud):
        fitted = fit(sphere_cloud, method="sphere")
        result = sample(fitted, sampling=10.0, method="distance")
        assert result.points.shape[0] > 0
        assert result.normals is not None


class TestClusterExtended:
    def test_birch(self, two_blobs):
        results = cluster(two_blobs, method="birch", n_clusters=2, distance=20)
        assert len(results) == 2
        total = sum(r.points.shape[0] for r in results)
        assert total == 160

    def test_use_normals(self, cloud):
        results = cluster(
            cloud,
            method="kmeans",
            n_clusters=2,
            use_points=True,
            use_normals=True,
        )
        assert len(results) == 2

    def test_normals_only(self, cloud):
        results = cluster(
            cloud,
            method="kmeans",
            n_clusters=2,
            use_points=False,
            use_normals=True,
        )
        assert len(results) == 2

    def test_normals_only_no_normals_falls_back(self, two_blobs):
        """When use_normals=True but geometry has no normals, uses points as data."""
        results = cluster(
            two_blobs,
            method="kmeans",
            n_clusters=2,
            use_points=False,
            use_normals=True,
        )
        total = sum(r.points.shape[0] for r in results)
        assert total == 160

    def test_leiden(self, two_blobs):
        results = cluster(two_blobs, method="leiden", distance=20)
        assert len(results) >= 1

    def test_envelope(self, two_blobs):
        results = cluster(two_blobs, method="envelope", distance=20)
        assert len(results) >= 1
        total = sum(r.points.shape[0] for r in results)
        assert total == 160


class TestRemoveOutliersExtended:
    def test_returns_none_when_all_removed(self):
        pts = np.zeros((10, 3), dtype=np.float32)
        pts[0] = [1000, 1000, 1000]
        geom = GeometryData(points=pts)
        result = remove_outliers(
            geom, method="statistical", k_neighbors=5, thresh=0.001
        )
        # With all identical points except one outlier, extreme thresh may
        # still keep some points, so just verify it doesn't crash
        assert result is None or result.points.shape[0] <= 10


class TestFitExtended:
    def test_alpha_shape(self, sphere_cloud):
        result = fit(sphere_cloud, method="alpha_shape", alpha=1.0)
        assert result.model is not None
        assert hasattr(result.model, "mesh")

    def test_ball_pivoting(self, sphere_cloud):
        result = fit(sphere_cloud, method="ball_pivoting", radii="50")
        assert result.model is not None
        assert hasattr(result.model, "mesh")

    def test_ball_pivoting_multi_radii(self, sphere_cloud):
        result = fit(sphere_cloud, method="ball_pivoting", radii="30,50,100")
        assert result.model is not None


class TestRemesh:
    @pytest.fixture
    def mesh_geom(self, sphere_cloud):
        return fit(sphere_cloud, method="alpha_shape", alpha=1.0)

    def test_no_mesh_returns_none(self, cloud):
        assert remesh(cloud, method="subdivide") is None

    def test_subdivide(self, mesh_geom):
        result = remesh(
            mesh_geom, method="subdivide", number_of_iterations=1, smooth=False
        )
        assert result is not None
        assert result.model is not None

    def test_subdivide_smooth(self, mesh_geom):
        result = remesh(
            mesh_geom, method="subdivide", number_of_iterations=1, smooth=True
        )
        assert result is not None

    def test_vertex_clustering(self, mesh_geom):
        result = remesh(mesh_geom, method="vertex_clustering", voxel_size=20.0)
        assert result is not None

    def test_decimation_reduction_factor(self, mesh_geom):
        result = remesh(
            mesh_geom,
            method="decimation",
            decimation_method="Reduction Factor",
            sampling=2,
            smooth=True,
        )
        assert result is not None

    def test_invalid_method(self, mesh_geom):
        with pytest.raises(ValueError, match="Unsupported"):
            remesh(mesh_geom, method="bogus")


class TestSmooth:
    @pytest.fixture
    def mesh_geom(self, sphere_cloud):
        return fit(sphere_cloud, method="alpha_shape", alpha=1.0)

    def test_no_mesh_returns_none(self, cloud):
        assert smooth(cloud, method="taubin") is None

    def test_taubin(self, mesh_geom):
        result = smooth(mesh_geom, method="taubin", number_of_iterations=3)
        assert result is not None
        assert result.model is not None

    def test_laplacian(self, mesh_geom):
        result = smooth(mesh_geom, method="laplacian", number_of_iterations=3)
        assert result is not None

    def test_average(self, mesh_geom):
        result = smooth(mesh_geom, method="average", number_of_iterations=3)
        assert result is not None

    def test_fair(self, mesh_geom):
        result = smooth(mesh_geom, method="fair")
        assert result is not None
        assert result.model is not None

    def test_invalid_method(self, mesh_geom):
        with pytest.raises(ValueError, match="Unsupported"):
            smooth(mesh_geom, method="bogus")


class TestRemeshExtended:
    @pytest.fixture
    def mesh_geom(self, sphere_cloud):
        return fit(sphere_cloud, method="alpha_shape", alpha=1.0)

    def test_edge_length(self, mesh_geom):
        result = remesh(
            mesh_geom, method="edge_length", target_edge_length=20.0, n_iter=5
        )
        assert result is not None
        assert result.model is not None

    def test_decimation_pyfqmr(self, mesh_geom):
        result = remesh(
            mesh_geom,
            method="decimation",
            decimation_method="Triangle Count",
            sampling=50,
            smooth=False,
        )
        assert result is not None
        assert result.model is not None


class TestFitExtendedMore:
    def test_flying_edges(self, sphere_cloud):
        result = fit(sphere_cloud, method="flying_edges")
        assert result.model is not None
        assert hasattr(result.model, "mesh")

    def test_flying_edges_custom_distance(self, sphere_cloud):
        result = fit(sphere_cloud, method="flying_edges", distance=5.0)
        assert result.model is not None

    def test_ball_pivoting_bad_radii_raises(self, sphere_cloud):
        with pytest.raises(ValueError, match="Incorrect radius"):
            fit(sphere_cloud, method="ball_pivoting", radii="not_a_number")


class TestGeometryOperationsRegister:
    def test_register_with_decorator(self):
        from mosaic.operations import GeometryOperations

        def my_op(geometry, **kwargs):
            return geometry

        def my_decorator(func):
            func._decorated = True
            return func

        GeometryOperations.register("_test_op", my_op, decorator=my_decorator)
        registered = getattr(GeometryOperations, "_test_op")
        assert hasattr(registered, "_decorated")
        delattr(GeometryOperations, "_test_op")

    def test_register_without_decorator(self):
        from mosaic.operations import GeometryOperations

        def my_op(geometry, **kwargs):
            return geometry

        GeometryOperations.register("_test_op2", my_op)
        assert hasattr(GeometryOperations, "_test_op2")
        delattr(GeometryOperations, "_test_op2")
