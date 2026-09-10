import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from mosaic.geometry import Geometry


@pytest.fixture
def points():
    """20 random 3D points for format I/O tests."""
    np.random.seed(0)
    return np.random.rand(20, 3).astype(np.float32) * 100


@pytest.fixture
def quaternions():
    """20 random unit quaternions (scalar-first) for orientation I/O tests."""
    np.random.seed(0)
    rots = Rotation.random(20, random_state=0)
    return rots.as_quat(scalar_first=True).astype(np.float32)


@pytest.fixture
def geom(points, quaternions):
    """Geometry with points and quaternions."""
    return Geometry(points=points, quaternions=quaternions)


@pytest.fixture
def tmp(tmp_path):
    """Base path (without extension) inside a temporary directory."""
    return str(tmp_path / "out")
