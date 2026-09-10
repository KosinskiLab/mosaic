import numpy as np
import pytest

from mosaic.geometry import GeometryData


@pytest.fixture
def cloud():
    """200-point cloud with normals for general operation tests."""
    rng = np.random.RandomState(42)
    pts = rng.rand(200, 3).astype(np.float32) * 50
    nrm = rng.rand(200, 3).astype(np.float32) - 0.5
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
    return GeometryData(points=pts, normals=nrm)


@pytest.fixture
def two_blobs():
    """Two spatially separated blobs (80 points each) for clustering tests."""
    rng = np.random.RandomState(0)
    a = rng.rand(80, 3).astype(np.float32) * 10
    b = rng.rand(80, 3).astype(np.float32) * 10 + 100
    pts = np.concatenate([a, b])
    return GeometryData(points=pts)


@pytest.fixture
def sphere_cloud():
    """400-point sphere surface for fitting and parametrization tests."""
    pts = (
        np.array(
            [
                [np.sin(t) * np.cos(p), np.sin(t) * np.sin(p), np.cos(t)]
                for t in np.linspace(0.1, np.pi - 0.1, 20)
                for p in np.linspace(0, 2 * np.pi, 20, endpoint=False)
            ],
            dtype=np.float32,
        )
        * 50
    )
    return GeometryData(points=pts)
