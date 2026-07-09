"""Regression: SegmentationGeometry must initialize visibility like its base.

SegmentationGeometry.__init__ does not call super().__init__(), so it has to set
the same intent-visibility state the base Geometry sets. Without it, reading
``.visible`` (e.g. in __getstate__ during change_representation) raised
AttributeError.
"""

import numpy as np

from mosaic.geometry import SegmentationGeometry


def _points(n: int = 50, seed: int = 0) -> np.ndarray:
    return (
        np.random.default_rng(seed).uniform(0.0, 10.0, size=(n, 3)).astype(np.float32)
    )


def test_visible_after_construction():
    seg = SegmentationGeometry(points=_points(), sampling_rate=1.0)
    assert seg.visible is True


def test_getstate_after_construction():
    seg = SegmentationGeometry(points=_points(), sampling_rate=1.0)
    assert seg.__getstate__()["visible"] is True
