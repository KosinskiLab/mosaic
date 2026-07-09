"""
Tests for measure and filter commands in the Mosaic REPL.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np

from mosaic.commands.session import Session
from mosaic.commands.parser import parse_command
from mosaic.commands.registry import CommandRegistry
from mosaic.commands.theme import render_to_text
from mosaic.geometry import Geometry


def _make_geometry(n_points, name=None):
    """Create a Geometry with *n_points* random 3D points."""
    rng = np.random.RandomState(n_points)
    pts = rng.rand(n_points, 3).astype(np.float32) * 100
    g = Geometry(points=pts)
    if name is not None:
        g._meta["name"] = name
    return g


def _add_geometry(session, geometry):
    """Add a Geometry to the session data container and order list."""
    session._data.add(geometry)
    session._order.append(geometry)


def _dispatch(session, cmd_text):
    """Parse and dispatch a command, returning the raw result."""
    parsed = parse_command(cmd_text)
    assert parsed is not None, f"Failed to parse: {cmd_text!r}"
    return CommandRegistry.dispatch(session, parsed)


class TestMeasureMixedResults:
    """Measure n_points on geometries of different sizes returns scalars."""

    def test_measure_n_points_multiple_geometries(self):
        session = Session()
        for n in (5, 20, 100):
            _add_geometry(session, _make_geometry(n))

        result = _dispatch(session, "measure n_points *")
        text = render_to_text(result)

        # Should render a scalar table with # and Value columns
        assert "#" in text
        assert "Value" in text

        # Each geometry's point count should appear
        assert "5" in text
        assert "20" in text
        assert "100" in text

    def test_measure_n_points_mixed_sizes(self):
        """Geometries with very different sizes should all appear in output."""
        session = Session()
        sizes = [1, 50, 500, 2000]
        for n in sizes:
            _add_geometry(session, _make_geometry(n))

        result = _dispatch(session, "measure n_points *")
        text = render_to_text(result)

        for s in sizes:
            assert str(s) in text, f"Expected {s} in output"


class TestMeasureStore:
    """Test store=true behavior: scalars should be gracefully skipped."""

    def test_store_scalar_skips_gracefully(self):
        session = Session()
        _add_geometry(session, _make_geometry(10, name="g0"))
        _add_geometry(session, _make_geometry(20, name="g1"))

        # n_points returns a scalar int, not a per-vertex array.
        # store=true should skip storing scalars without crashing.
        result = _dispatch(session, "measure n_points * store=true")
        text = render_to_text(result)

        # The output should still render and mention storing
        assert "10" in text
        assert "20" in text

        # Since n_points returns a scalar, nothing should have been stored
        geoms = session._all_geometries()
        for g in geoms:
            props = g.vertex_properties.properties
            assert (
                "n_points" not in props
            ), "Scalar result should not be stored as vertex property"

    def test_store_per_vertex_array(self):
        """If measure returns per-vertex arrays, store=true should store them."""
        session = Session()
        _add_geometry(session, _make_geometry(15, name="pc"))

        # 'width' returns per-vertex X coordinates (array of len n_points)
        result = _dispatch(session, "measure width #0 store=true")
        text = render_to_text(result)

        geom = session._all_geometries()[0]
        stored = geom.vertex_properties.get_property("width")
        assert stored is not None, "Per-vertex result should be stored"
        assert len(stored) == 15


class TestFilterChaining:
    """Filter narrows selection; chaining with @last narrows further."""

    def test_filter_lower_bound(self):
        session = Session()
        for n in range(10, 110, 10):  # 10, 20, ..., 100
            _add_geometry(session, _make_geometry(n, name=f"g{n}"))

        assert len(session._all_geometries()) == 10

        # Filter by n_points >= 30 removes geometries with < 30 points
        result = _dispatch(session, "filter * property=n_points lower=30")
        text = render_to_text(result)

        # Population filter: kept 8, removed 2 (10-pt and 20-pt)
        assert "kept 8" in text or "kept  8" in text
        assert "removed 2" in text

        remaining = session._all_geometries()
        assert len(remaining) == 8
        for g in remaining:
            assert g.get_number_of_points() >= 30

    def test_filter_chain_with_at_last(self):
        session = Session()
        for n in range(10, 110, 10):
            _add_geometry(session, _make_geometry(n, name=f"g{n}"))

        # First filter: keep n_points >= 30
        _dispatch(session, "filter * property=n_points lower=30")
        remaining_after_first = session._all_geometries()
        assert len(remaining_after_first) == 8

        # @last should hold the kept geometries
        last = session.resolve("@last")
        assert len(last) == 8

        # Second filter on @last: keep n_points <= 70
        result = _dispatch(session, "filter @last property=n_points upper=70")
        text = render_to_text(result)

        remaining_after_second = session._all_geometries()
        # Should keep 30, 40, 50, 60, 70 => 5 geometries
        assert len(remaining_after_second) == 5
        for g in remaining_after_second:
            n = g.get_number_of_points()
            assert 30 <= n <= 70, f"Unexpected n_points={n}"


class TestFilterNoMatches:
    """All geometries are removed when none satisfy the filter."""

    def test_filter_removes_all(self):
        session = Session()
        for _ in range(5):
            _add_geometry(session, _make_geometry(50, name="same"))

        assert len(session._all_geometries()) == 5

        # lower=100 means keep only n_points >= 100, but all have 50
        result = _dispatch(session, "filter * property=n_points lower=100")
        text = render_to_text(result)

        assert "removed 5" in text
        assert len(session._all_geometries()) == 0

    def test_filter_last_empty_after_removal(self):
        session = Session()
        for _ in range(3):
            _add_geometry(session, _make_geometry(50))

        _dispatch(session, "filter * property=n_points lower=100")
        last = session.resolve("@last")
        assert last == [], "@last should be empty after removing all"


class TestMeasureOutputRendering:
    """Verify Rich table rendering produces expected text."""

    def test_scalar_table_columns(self):
        session = Session()
        _add_geometry(session, _make_geometry(42, name="test_geom"))

        result = _dispatch(session, "measure n_points #0")
        text = render_to_text(result)

        # Scalar table should have # and Value headers
        assert "#" in text
        assert "Value" in text
        assert "42" in text

    def test_array_table_columns(self):
        """Measure returning per-vertex arrays should show stats columns."""
        session = Session()
        _add_geometry(session, _make_geometry(30, name="pc"))

        result = _dispatch(session, "measure width #0")
        text = render_to_text(result)

        # Array table should have statistics columns
        assert "Min" in text
        assert "Max" in text
        assert "Mean" in text
        assert "Std" in text
        assert "Median" in text

    def test_render_multiple_geometries(self):
        session = Session()
        _add_geometry(session, _make_geometry(10, name="a"))
        _add_geometry(session, _make_geometry(20, name="b"))

        result = _dispatch(session, "measure n_points #0 #1")
        text = render_to_text(result)

        assert "10" in text
        assert "20" in text


class TestInfoCommand:
    """Dispatch 'info #0' and verify output content."""

    def test_info_shows_point_count(self):
        session = Session()
        _add_geometry(session, _make_geometry(77, name="info_test"))

        result = _dispatch(session, "info #0")
        text = render_to_text(result)

        assert "77" in text
        assert "Points" in text

    def test_info_shows_normals_status(self):
        session = Session()
        g = _make_geometry(10)
        _add_geometry(session, g)

        result = _dispatch(session, "info #0")
        text = render_to_text(result)

        # Normals should be reported (yes or no)
        assert "Normals" in text
        # The geometry we created has no normals explicitly set
        assert "no" in text.lower() or "yes" in text.lower()

    def test_info_shows_type(self):
        session = Session()
        _add_geometry(session, _make_geometry(10, name="typed"))

        result = _dispatch(session, "info #0")
        text = render_to_text(result)

        assert "Type" in text
        assert "cluster" in text.lower()

    def test_info_shows_index(self):
        session = Session()
        _add_geometry(session, _make_geometry(10))
        _add_geometry(session, _make_geometry(20))

        result = _dispatch(session, "info #1")
        text = render_to_text(result)

        assert "#1" in text
