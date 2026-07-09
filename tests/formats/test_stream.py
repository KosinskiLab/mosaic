"""
Tests for ZarrPyramid and ZarrImageSource.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np


def _make_pyramid(shape=(64, 128, 128)):
    levels = []
    s = shape
    for i in range(4):
        levels.append(
            {
                "array": np.random.rand(*s).astype(np.float32),
                "shape": s,
                "spacing": (2.0**i, 2.0**i, 2.0**i),
            }
        )
        s = tuple(max(1, d // 2) for d in s)
    return levels


class TestZarrPyramid:
    def test_level_shape_and_spacing(self):
        from mosaic.formats.stream import ZarrPyramid

        levels = _make_pyramid()
        pyr = ZarrPyramid(levels)
        assert pyr.num_levels == 4
        assert pyr.level_shape(0) == (64, 128, 128)
        assert pyr.level_spacing(0) == (1.0, 1.0, 1.0)
        assert pyr.level_shape(2) == (16, 32, 32)
        assert pyr.level_spacing(2) == (4.0, 4.0, 4.0)

    def test_read_region_returns_correct_shape(self):
        from mosaic.formats.stream import ZarrPyramid

        levels = _make_pyramid()
        pyr = ZarrPyramid(levels)
        result = pyr.read_region(0, 0, 9, 0, 9, 0, 4)
        assert result.shape == (5, 10, 10)
        assert result.dtype == np.float32

    def test_read_region_caches_chunks(self):
        from mosaic.formats.stream import ZarrPyramid

        levels = _make_pyramid()
        pyr = ZarrPyramid(levels)
        assert len(pyr._cache) == 0
        pyr.read_region(0, 0, 127, 0, 127, 0, 63)
        assert len(pyr._cache) > 0

    def test_read_region_at_different_levels(self):
        from mosaic.formats.stream import ZarrPyramid

        levels = _make_pyramid()
        pyr = ZarrPyramid(levels)
        r0 = pyr.read_region(0, 0, 9, 0, 9, 0, 4)
        r2 = pyr.read_region(2, 0, 9, 0, 9, 0, 4)
        assert r0.shape == r2.shape
        # Different levels should produce different data
        assert not np.array_equal(r0, r2)

    def test_cache_retains_across_levels(self):
        from mosaic.formats.stream import ZarrPyramid

        levels = _make_pyramid()
        pyr = ZarrPyramid(levels)
        pyr.read_region(0, 0, 127, 0, 127, 0, 63)
        cached_after_level0 = len(pyr._cache)
        pyr.read_region(2, 0, 31, 0, 31, 0, 15)
        assert len(pyr._cache) >= cached_after_level0

    def test_level_spacings(self):
        from mosaic.formats.stream import ZarrPyramid

        levels = _make_pyramid()
        pyr = ZarrPyramid(levels)
        spacings = pyr.level_spacings()
        assert len(spacings) == 4
        assert spacings[0] == (1.0, 1.0, 1.0)
        assert spacings[3] == (8.0, 8.0, 8.0)


class TestZarrImageSource:
    def test_vtk_pipeline_produces_output(self):
        from mosaic.formats.stream import ZarrPyramid, ZarrImageSource

        levels = _make_pyramid()
        pyramid = ZarrPyramid(levels)
        src = ZarrImageSource(pyramid, initial_level=0)
        src.Update()

        output = src.GetOutputDataObject(0)
        assert output.GetNumberOfPoints() > 0

    def test_level_tracks_independently(self):
        from mosaic.formats.stream import ZarrPyramid, ZarrImageSource

        levels = _make_pyramid()
        pyramid = ZarrPyramid(levels)
        src = ZarrImageSource(pyramid, initial_level=0)
        assert src.level == 0
        src.set_level(2)
        assert src.level == 2
        assert src.shape == pyramid.level_shape(2)
        assert src.spacing == pyramid.level_spacing(2)

    def test_defaults_to_coarsest(self):
        from mosaic.formats.stream import ZarrPyramid, ZarrImageSource

        levels = _make_pyramid()
        pyramid = ZarrPyramid(levels)
        src = ZarrImageSource(pyramid)
        assert src.level == 3
