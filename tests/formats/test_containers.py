"""
Tests for format data containers (GeometryDataContainer, VertexPropertyContainer).

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np
import pytest

from mosaic.formats.parser import GeometryDataContainer, VertexPropertyContainer


class TestGeometryDataContainer:
    def test_single_geometry(self, points):
        gdc = GeometryDataContainer(vertices=[points])
        assert len(gdc) == 1
        assert gdc[0].vertices.shape == (20, 3)

    def test_multiple_geometries(self, points):
        gdc = GeometryDataContainer(vertices=[points, points[:5]])
        assert len(gdc) == 2
        assert gdc[1].vertices.shape == (5, 3)

    def test_normals_normalized(self):
        raw = np.array([[3, 0, 0], [0, 5, 0]], dtype=np.float32)
        gdc = GeometryDataContainer(vertices=[raw], normals=[raw.copy()])
        norms = np.linalg.norm(gdc[0].normals, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-6)

    def test_iteration(self, points):
        gdc = GeometryDataContainer(vertices=[points, points])
        items = list(gdc)
        assert len(items) == 2


class TestVertexPropertyContainer:
    def test_basic(self):
        vpc = VertexPropertyContainer({"score": np.arange(10, dtype=np.float32)})
        assert "score" in vpc.properties
        assert len(vpc.get_property("score")) == 10

    def test_indexing(self):
        vpc = VertexPropertyContainer({"val": np.arange(5, dtype=np.float32)})
        sub = vpc[1:3]
        np.testing.assert_array_equal(sub.get_property("val"), [1, 2])

    def test_bool_indexing(self):
        vpc = VertexPropertyContainer({"x": np.arange(4, dtype=np.float32)})
        mask = np.array([True, False, True, False])
        sub = vpc[mask]
        np.testing.assert_array_equal(sub.get_property("x"), [0, 2])

    def test_merge(self):
        a = VertexPropertyContainer({"k": np.array([1, 2])})
        b = VertexPropertyContainer({"k": np.array([3])})
        merged = VertexPropertyContainer.merge([a, b])
        np.testing.assert_array_equal(merged.get_property("k"), [1, 2, 3])

    def test_set_remove(self):
        vpc = VertexPropertyContainer()
        vpc.set_property("new", np.zeros(3))
        assert "new" in vpc.properties
        vpc.remove_property("new")
        assert "new" not in vpc.properties
