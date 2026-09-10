import subprocess
import sys
import tempfile
from functools import lru_cache

import numpy as np
import pytest
from qtpy.QtWidgets import QApplication

_RENDER_PROBE = """
import vtk

window = vtk.vtkRenderWindow()
window.SetOffScreenRendering(1)
window.SetSize(32, 32)
window.AddRenderer(vtk.vtkRenderer())
window.Render()
window.Finalize()
"""


@lru_cache(maxsize=1)
def vtk_offscreen_available() -> bool:
    """Whether VTK can build and draw an offscreen render window here.

    Runners without a GL driver abort the process rather than raising, so the
    probe runs in a subprocess and a dead child counts as unavailable.
    """
    try:
        probe = subprocess.run(
            [sys.executable, "-c", _RENDER_PROBE],
            capture_output=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return probe.returncode == 0


@pytest.fixture(scope="session")
def require_vtk_render_window():
    """Skip tests that need a real ``vtkRenderWindow`` where none can exist."""
    if not vtk_offscreen_available():
        pytest.skip("VTK cannot create an offscreen render window here")
    return None


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication instance for testing session."""
    if not QApplication.instance():
        app = QApplication(sys.argv)
    else:
        app = QApplication.instance()
    yield app


@pytest.fixture
def sample_points():
    """Generate sample 3D point cloud data."""
    np.random.seed(42)
    return np.random.rand(100, 3).astype(np.float32) * 10


@pytest.fixture
def sample_normals():
    """Generate sample normal vectors."""
    np.random.seed(42)
    normals = np.random.rand(100, 3).astype(np.float32) - 0.5
    return normals / np.linalg.norm(normals, axis=1, keepdims=True)


@pytest.fixture
def temp_filepath():
    """Create temporary file path for testing."""
    with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
        yield tmp.name


@pytest.fixture
def make_session():
    """Factory fixture: create a Session with *n* random point-cloud geometries."""
    from mosaic.commands.session import Session
    from mosaic.geometry import Geometry

    def _factory(n=3, n_points=50, seed=42):
        rng = np.random.RandomState(seed)
        session = Session(quiet=True)
        for i in range(n):
            pts = rng.rand(n_points, 3).astype(np.float32) * 100
            g = Geometry(points=pts)
            g._meta["name"] = f"cloud_{i}"
            session._data.add(g)
            session._order.append(g)
        return session

    return _factory
