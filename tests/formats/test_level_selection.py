"""
Tests for pick_level pyramid level selection.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from mosaic.formats.stream import pick_level


class TestPickLevel:
    def test_zoomed_out_picks_coarsest(self):
        spacings = [(1.0, 1.0, 1.0), (2.0, 2.0, 2.0), (4.0, 4.0, 4.0)]
        assert pick_level(spacings, world_per_pixel=5.0) == 2

    def test_zoomed_in_picks_finest(self):
        spacings = [(1.0, 1.0, 1.0), (2.0, 2.0, 2.0), (4.0, 4.0, 4.0)]
        assert pick_level(spacings, world_per_pixel=0.5) == 0

    def test_exact_match_uses_that_level(self):
        spacings = [(1.0, 1.0, 1.0), (2.0, 2.0, 2.0), (4.0, 4.0, 4.0)]
        assert pick_level(spacings, world_per_pixel=2.0) == 1

    def test_single_level_always_zero(self):
        spacings = [(1.0, 1.0, 1.0)]
        assert pick_level(spacings, world_per_pixel=100.0) == 0
