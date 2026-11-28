import subprocess
import sys

import pytest

_SCRIPT = """
import numpy as np
from mosaic.utils import {func}
rng = np.random.default_rng(0)
data = np.concatenate([rng.normal(c, 1.0, size=(80, 3)) for c in (0, 2, 4)])
print(",".join(map(str, {func}(data, {kwargs}))))
"""


def _labels_in_fresh_process(func, kwargs):
    code = _SCRIPT.format(func=func, kwargs=kwargs)
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout


@pytest.mark.parametrize(
    "func, kwargs",
    [("kmeans_clustering", "k=3"), ("leiden_clustering", "resolution_parameter=-2")],
)
def test_clustering_is_reproducible_across_processes(func, kwargs):
    runs = {_labels_in_fresh_process(func, kwargs) for _ in range(3)}
    assert len(runs) == 1
