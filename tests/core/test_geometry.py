import numpy as np
import warnings
from unittest.mock import Mock, patch, ANY

from mosaic.geometry import Geometry


class TestGeometry:
    """Test suite for Geometry class."""

    def test_init_default(self):
        """Test Geometry initialization with defaults."""
        geom = Geometry()

        assert geom._meta == {}
        assert geom._representation == "pointcloud"
        np.testing.assert_array_equal(geom.sampling_rate, (1, 1, 1))

    def test_init(self, sample_points):
        """Test Geometry initialization with points."""
        geom = Geometry(points=sample_points)
        np.testing.assert_array_equal(geom.points, sample_points)

    def test_init_with_normals(self, sample_points, sample_normals):
        """Test Geometry initialization with normals."""
        geom = Geometry(points=sample_points, normals=sample_normals)
        np.testing.assert_array_equal(geom.points, sample_points)
        np.testing.assert_array_equal(geom.normals, sample_normals)

    def test_init_with_quaternions(self, sample_points):
        """Test Geometry initialization with quaternions."""
        quaternions = np.array([[1, 0, 0, 0]] * len(sample_points))

        with patch("mosaic.geometry.apply_quat") as mock_apply_quat:
            mock_apply_quat.return_value = np.random.rand(len(sample_points), 3)

            _ = Geometry(points=sample_points, quaternions=quaternions)

            mock_apply_quat.assert_called_once_with(quaternions)

    def test_points_property_setter_invalid_shape(self):
        """Test points setter with invalid shape."""
        geom = Geometry()

        with warnings.catch_warnings(record=True) as w:
            geom.points = np.array([[1, 2]])
            assert len(w) == 1
            assert "3D point clouds" in str(w[0].message)

    def test_normals_property_setter_mismatch(self, sample_points):
        """Test normals setter with mismatched size."""
        geom = Geometry(points=sample_points)

        with warnings.catch_warnings(record=True) as w:
            geom.normals = np.array([[1, 0, 0]])
            assert len(w) == 1

    def test_quaternions_property_from_normals(self, sample_points, sample_normals):
        """Test quaternions property computed from normals."""
        geom = Geometry(points=sample_points, normals=sample_normals)

        with patch("mosaic.geometry.normals_to_rot") as mock_normals_to_rot:
            mock_quaternions = np.random.rand(len(sample_points), 4)
            mock_normals_to_rot.return_value = mock_quaternions

            _ = geom.quaternions

            mock_normals_to_rot.assert_called_once_with(ANY, scalar_first=True)

            call_args = mock_normals_to_rot.call_args[0]
            np.testing.assert_array_equal(call_args[0], sample_normals)

    def test_set_visibility(self, sample_points):
        """Test visibility setting."""
        geom = Geometry(points=sample_points, vtk_actor=Mock())

        geom.set_visibility(False)
        geom.actor.SetVisibility.assert_called_with(False)

        geom.set_visibility(True)
        geom.actor.SetVisibility.assert_called_with(True)

    def test_set_color(self, sample_points):
        """Test color setting."""
        geom = Geometry(points=sample_points, vtk_actor=Mock())

        color = (1.0, 0.0, 0.0)
        geom.set_color(color)

    def test_indexing_operation(self, sample_points, sample_normals):
        """Test geometry indexing with boolean mask."""
        geom = Geometry(points=sample_points, normals=sample_normals)

        mask = np.zeros(len(sample_points), dtype=bool)
        mask[:50] = True

        result = geom[mask]

        np.testing.assert_array_equal(result.points, sample_points[mask])
        np.testing.assert_array_equal(result.normals, sample_normals[mask])


def test_apply_lod_indices_attaches_actor():
    pts = np.random.default_rng(0).uniform(0, 10, size=(100, 3)).astype(np.float32)
    g = Geometry(points=pts, sampling_rate=1.0)

    g.lod.apply(np.array([0, 5, 10, 20]))

    assert g.lod.indices.tolist() == [0, 5, 10, 20]
    assert g.lod.actor is not None
    assert g.lod.data is not None
    assert g.lod._sync_mtime == -1
