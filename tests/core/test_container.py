"""
Tests for DataContainer geometry collection management.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from mosaic.container import DataContainer
from mosaic.geometry import Geometry


def _make_geom(n=50, seed=0):
    rng = np.random.RandomState(seed)
    return Geometry(points=rng.rand(n, 3).astype(np.float32) * 100)


@pytest.fixture(autouse=True)
def _patch_lod():
    """Prevent LOD computation from touching VTK/settings during unit tests."""
    mock_lod = MagicMock()
    mock_lod.get_point_budget.return_value = 0
    mock_lod.compute_scene_lod.return_value = {}
    with patch.dict("sys.modules", {"mosaic.lod": mock_lod}):
        yield


class TestDataContainer:

    def test_init_defaults(self):
        c = DataContainer()
        assert c.base_color == (0.7, 0.7, 0.7)
        assert c.highlight_color == (0.8, 0.2, 0.2)
        assert len(c) == 0

    def test_init_custom_colors(self):
        c = DataContainer(base_color=(0.1, 0.2, 0.3), highlight_color=(1, 0, 0))
        assert c.base_color == (0.1, 0.2, 0.3)
        assert c.highlight_color == (1, 0, 0)

    def test_add_points_array(self, sample_points):
        c = DataContainer()
        idx = c.add(sample_points)
        assert idx == 0
        assert len(c) == 1
        assert c.data[0].get_number_of_points() == 100

    def test_add_geometry_object(self):
        c = DataContainer()
        g = _make_geom()
        idx = c.add(g)
        assert idx == 0
        assert c.data[0] is g

    def test_add_multiple(self):
        c = DataContainer()
        c.add(_make_geom(seed=0))
        c.add(_make_geom(seed=1))
        assert len(c) == 2

    def test_remove_by_geometry(self):
        c = DataContainer()
        g0 = _make_geom(seed=0)
        g1 = _make_geom(seed=1)
        c.add(g0)
        c.add(g1)
        c.remove([g0])
        assert len(c) == 1
        assert c.data[0] is g1

    def test_clear(self):
        c = DataContainer()
        c.data = [_make_geom(), _make_geom()]
        c.clear()
        assert len(c) == 0

    def test_get_by_index(self):
        c = DataContainer()
        g = _make_geom()
        c.add(g)
        assert c.get(0) is g

    def test_get_invalid_index(self):
        c = DataContainer()
        assert c.get(-1) is None
        assert c.get(100) is None

    def test_get_by_uuid(self):
        c = DataContainer()
        g = _make_geom()
        c.add(g)
        assert c.get(g.uuid) is g

    def test_uuid_to_index(self):
        c = DataContainer()
        g0 = _make_geom(seed=0)
        g1 = _make_geom(seed=1)
        c.add(g0)
        c.add(g1)
        assert c.uuid_to_index(g0.uuid) == 0
        assert c.uuid_to_index(g1.uuid) == 1
        assert c.uuid_to_index("nonexistent") is None
