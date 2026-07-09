"""Unit tests for the mesh-resolution helpers used by Cylinder/RBF backing."""

import numpy as np
import pytest

from mosaic.parametrization import (
    _MESH_CHORD_TOL,
    _MESH_MAX_SEG,
    _edge_length_from_curvature,
    _n_segments,
    _grid_faces,
)


def test_edge_length_matches_sagitta_law():
    # L = sqrt(8*tol)/kappa
    kappa = 0.25
    expected = np.sqrt(8.0 * _MESH_CHORD_TOL) / kappa
    assert _edge_length_from_curvature(kappa) == pytest.approx(expected)


def test_edge_length_guards_zero_curvature():
    # Flat surface: kappa -> 0 must not divide by zero, returns a large finite L
    L = _edge_length_from_curvature(0.0)
    assert np.isfinite(L)
    assert L > 0


def test_cylinder_angular_count_matches_closed_form():
    # For a circle: extent = 2*pi*R, kappa = 1/R -> N = ceil(pi / sqrt(2*tol))
    radius = 7.3
    L = _edge_length_from_curvature(1.0 / radius)
    n = _n_segments(2.0 * np.pi * radius, L, min_seg=12)
    closed_form = int(np.ceil(np.pi / np.sqrt(2.0 * _MESH_CHORD_TOL)))
    assert n == closed_form


def test_n_segments_is_scale_invariant_for_circle():
    # Doubling the radius leaves the angular count unchanged
    r1, r2 = 3.0, 30.0
    n1 = _n_segments(2 * np.pi * r1, _edge_length_from_curvature(1 / r1), 12)
    n2 = _n_segments(2 * np.pi * r2, _edge_length_from_curvature(1 / r2), 12)
    assert n1 == n2


def test_n_segments_respects_min_and_max():
    assert _n_segments(1e-9, 1.0, min_seg=8) == 8
    assert _n_segments(1e9, 1.0, min_seg=8) == _MESH_MAX_SEG


def test_finer_tolerance_gives_more_segments():
    radius = 5.0
    coarse = _n_segments(
        2 * np.pi * radius, _edge_length_from_curvature(1 / radius, tol=1e-2), 12
    )
    fine = _n_segments(
        2 * np.pi * radius, _edge_length_from_curvature(1 / radius, tol=1e-4), 12
    )
    assert fine > coarse


def test_grid_faces_shape_and_bounds():
    rows, cols = 4, 5
    faces = _grid_faces(rows, cols)
    assert faces.shape == (2 * (rows - 1) * (cols - 1), 3)
    assert faces.min() >= 0
    assert faces.max() == rows * cols - 1
    # Every quad contributes two triangles that together cover 4 distinct verts
    assert faces.dtype == np.int32
