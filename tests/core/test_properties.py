"""
Tests for property measurement dispatch and calculators.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np
import pytest

from mosaic.geometry import Geometry
from mosaic.properties import (
    GeometryProperties,
    _aggregate,
    box_size,
    depth,
    distance,
    export_property_csv,
    height,
    n_points,
    vertex_property,
    width,
)


def _geom(n=50, seed=0):
    rng = np.random.RandomState(seed)
    pts = rng.rand(n, 3).astype(np.float32) * 100
    return Geometry(points=pts)


class TestAggregate:

    def test_1d_passthrough(self):
        arr = np.array([1.0, 2.0, 3.0])
        np.testing.assert_array_equal(_aggregate(arr, "mean"), arr)

    @pytest.mark.parametrize(
        "mode, expected",
        [
            ("mean", [2.0, 5.0]),
            ("min", [1.0, 4.0]),
            ("max", [3.0, 6.0]),
            ("median", [2.0, 5.0]),
            ("std", [np.std([1, 2, 3]), np.std([4, 5, 6])]),
        ],
    )
    def test_2d_modes(self, mode, expected):
        arr = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.float64)
        result = _aggregate(arr, mode)
        np.testing.assert_allclose(result, expected, atol=1e-10)

    def test_case_insensitive(self):
        arr = np.array([[1, 2, 3]], dtype=np.float64)
        np.testing.assert_allclose(_aggregate(arr, "MEAN"), [2.0])


class TestCoordinateProperties:

    def test_width(self):
        g = _geom(20)
        result = width(g)
        np.testing.assert_array_equal(result, g.points[:, 0])

    def test_depth(self):
        g = _geom(20)
        result = depth(g)
        np.testing.assert_array_equal(result, g.points[:, 1])

    def test_height(self):
        g = _geom(20)
        result = height(g)
        np.testing.assert_array_equal(result, g.points[:, 2])

    def test_n_points(self):
        assert n_points(_geom(42)) == 42

    def test_box_size_all(self):
        g = _geom(100)
        result = box_size(g)
        expected = g.points.max(axis=0) - g.points.min(axis=0)
        np.testing.assert_allclose(result, expected)

    def test_box_size_single_axis(self):
        g = _geom(100)
        for axis in range(3):
            result = box_size(g, axis=axis)
            expected = g.points[:, axis].max() - g.points[:, axis].min()
            assert result == pytest.approx(expected)


class TestVertexProperty:

    def test_existing_property(self):
        g = _geom(10)
        g.vertex_properties.set_property("score", np.arange(10, dtype=np.float32))
        result = vertex_property(g, name="score")
        np.testing.assert_array_equal(result, np.arange(10, dtype=np.float32))

    def test_returns_copy(self):
        g = _geom(10)
        arr = np.arange(10, dtype=np.float32)
        g.vertex_properties.set_property("x", arr)
        result = vertex_property(g, name="x")
        result[0] = 999
        assert g.vertex_properties.get_property("x")[0] != 999

    def test_missing_property(self):
        g = _geom(10)
        assert vertex_property(g, name="nonexistent") is None


class TestDistance:

    def test_self_distance(self):
        g = _geom(30)
        result = distance(g, queries=[g], include_self=True, k=1)
        assert result is not None
        assert result.shape[0] == 30
        assert np.all(result >= 0)

    def test_only_self(self):
        g = _geom(30)
        result = distance(g, only_self=True, k=2)
        assert result is not None
        assert result.shape[0] == 30

    def test_exclude_self(self):
        g = _geom(30)
        result = distance(g, queries=[g], include_self=False, k=1)
        assert result is None

    def test_two_geometries(self):
        g1 = _geom(20, seed=0)
        g2 = _geom(20, seed=1)
        result = distance(g1, queries=[g2], k=1)
        assert result is not None
        assert result.shape[0] == 20
        assert np.all(result >= 0)

    def test_multi_query_takes_minimum(self):
        g = _geom(10, seed=0)
        q1 = _geom(10, seed=1)
        q2 = _geom(10, seed=2)
        result_single = distance(g, queries=[q1], k=1)
        result_multi = distance(g, queries=[q1, q2], k=1)
        assert np.all(result_multi <= result_single + 1e-6)

    def test_k_start_greater_than_k_raises(self):
        g = _geom(10)
        with pytest.raises(ValueError, match="k_start must be <= k"):
            distance(g, queries=[g], include_self=True, k=1, k_start=2)

    @pytest.mark.parametrize("agg", ["mean", "min", "max", "median", "std"])
    def test_aggregation_modes(self, agg):
        g = _geom(30)
        result = distance(g, queries=[g], include_self=True, k=3, aggregation=agg)
        assert result is not None
        assert result.shape[0] == 30

    def test_single_query_not_list(self):
        g = _geom(20, seed=0)
        q = _geom(20, seed=1)
        result = distance(g, queries=q, k=1)
        assert result is not None
        assert result.shape[0] == 20


class TestGetMeshDecorator:

    def test_no_model_returns_none(self):
        g = _geom(10)
        result = GeometryProperties.compute(
            "mesh_curvature", g, curvature="Mean", radius=5
        )
        assert result is None

    def test_no_mesh_attr_returns_none(self):
        g = _geom(10)
        result = GeometryProperties.compute("mesh_area", g)
        assert result is None

    def test_mesh_volume_no_model(self):
        g = _geom(10)
        assert GeometryProperties.compute("mesh_volume", g) is None

    def test_mesh_statistics_no_model(self):
        g = _geom(10)
        assert GeometryProperties.compute("mesh_statistics", g) is None


class TestGeometryPropertiesDispatch:

    def test_compute_known_property(self):
        g = _geom(25)
        result = GeometryProperties.compute("n_points", g)
        assert result == 25

    def test_compute_unknown_raises(self):
        g = _geom(10)
        with pytest.raises(ValueError, match="Unknown property"):
            GeometryProperties.compute("nonexistent_property_xyz", g)

    def test_register_custom(self):
        def custom_prop(geometry, **kwargs):
            return 42

        GeometryProperties.register("_test_custom", custom_prop)
        assert GeometryProperties.compute("_test_custom", _geom(10)) == 42
        del GeometryProperties._calculators["_test_custom"]

    def test_all_standard_properties_registered(self):
        expected = {
            "distance",
            "box_size",
            "width",
            "depth",
            "height",
            "n_points",
            "mesh_curvature",
            "mesh_area",
            "mesh_volume",
            "mesh_statistics",
            "projected_curvature",
            "geodesic_distance",
            "vertex_property",
            "projected_angle",
            "thickness",
        }
        assert expected.issubset(set(GeometryProperties._calculators.keys()))


class TestMeshProperties:
    """Tests for properties that require a fitted mesh model."""

    @pytest.fixture
    def mesh_geom(self):
        from mosaic.operations import fit
        from mosaic.geometry import GeometryData

        pts = (
            np.array(
                [
                    [np.sin(t) * np.cos(p), np.sin(t) * np.sin(p), np.cos(t)]
                    for t in np.linspace(0.1, np.pi - 0.1, 15)
                    for p in np.linspace(0, 2 * np.pi, 15, endpoint=False)
                ],
                dtype=np.float32,
            )
            * 50
        )
        gd = fit(GeometryData(points=pts), method="alpha_shape", alpha=1.0)
        return Geometry(points=gd.points, model=gd.model)

    def test_mesh_area_total(self, mesh_geom):
        result = GeometryProperties.compute("mesh_area", mesh_geom)
        assert result is not None
        assert result > 0

    def test_mesh_area_per_triangle(self, mesh_geom):
        result = GeometryProperties.compute(
            "mesh_area", mesh_geom, area_type="Per-Triangle"
        )
        assert isinstance(result, np.ndarray)
        assert len(result) > 0
        assert np.all(result >= 0)

    def test_mesh_volume_total(self, mesh_geom):
        result = GeometryProperties.compute("mesh_volume", mesh_geom)
        assert result is not None

    def test_mesh_volume_per_triangle(self, mesh_geom):
        result = GeometryProperties.compute(
            "mesh_volume", mesh_geom, volume_type="Per-Triangle"
        )
        assert isinstance(result, np.ndarray)
        assert len(result) == len(mesh_geom.model.triangles)

    def test_mesh_statistics_vertex_count(self, mesh_geom):
        result = GeometryProperties.compute("mesh_statistics", mesh_geom)
        assert isinstance(result, (int, np.integer))
        assert result > 0

    def test_mesh_statistics_triangle_count(self, mesh_geom):
        result = GeometryProperties.compute(
            "mesh_statistics", mesh_geom, stat_type="Triangle Count"
        )
        assert isinstance(result, (int, np.integer))
        assert result > 0

    def test_mesh_curvature(self, mesh_geom):
        result = GeometryProperties.compute(
            "mesh_curvature",
            mesh_geom,
            curvature="Mean",
            radius=5,
        )
        assert isinstance(result, np.ndarray)
        assert len(result) > 0


class TestExportPropertyCsv:

    def test_scalar_export(self, tmp_path):
        path = str(tmp_path / "scalar.csv")
        g1, g2 = _geom(10), _geom(20)
        export_property_csv(path, "n_points", [g1, g2], [10, 20])

        with open(path) as f:
            lines = f.readlines()
        assert lines[0].strip() == "source,n_points"
        assert len(lines) == 3

    def test_per_point_export(self, tmp_path):
        path = str(tmp_path / "perpoint.csv")
        g = _geom(5)
        vals = np.arange(5, dtype=np.float32)
        export_property_csv(path, "height", [g], [vals])

        with open(path) as f:
            lines = f.readlines()
        assert "point_id" in lines[0]
        assert "x,y,z" in lines[0]
        assert len(lines) == 6

    def test_custom_sources(self, tmp_path):
        path = str(tmp_path / "named.csv")
        g = _geom(3)
        export_property_csv(
            path,
            "val",
            [g],
            [np.ones(3)],
            sources=["cloud_A"],
        )
        with open(path) as f:
            content = f.read()
        assert "cloud_A" in content

    def test_multiple_geometries_per_point(self, tmp_path):
        path = str(tmp_path / "multi.csv")
        g1, g2 = _geom(3, seed=0), _geom(4, seed=1)
        v1, v2 = np.ones(3), np.ones(4) * 2
        export_property_csv(path, "score", [g1, g2], [v1, v2])

        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 1 + 3 + 4
