from unittest.mock import Mock, patch

import pytest
from qtpy.QtCore import QObject


class _MockVTKWidget(QObject):
    """Real QObject so it can parent QTimers and receive event filters,
    while exposing mocked VTK methods for the render pipeline."""


@pytest.fixture
def mock_vtk_widget():
    """Mock VTK widget for testing without rendering."""
    widget = _MockVTKWidget()
    render_window = Mock()
    interactor = Mock()

    widget.GetRenderWindow = Mock(return_value=render_window)
    render_window.GetInteractor.return_value = interactor
    render_window.AddRenderer = Mock()

    return widget


@pytest.fixture
def mock_geometry():
    """Fixture for properly mocked Geometry class."""
    with patch("mosaic.geometry.Geometry") as mock_geom:
        mock_geom.__bases__ = ()
        mock_geom.__name__ = "Geometry"
        yield mock_geom


@pytest.fixture
def mock_interactor():
    """Fixture for properly mocked DataContainerInteractor."""
    with patch("mosaic.interactor.DataContainerInteractor") as mock_int:
        mock_int.__bases__ = ()
        mock_int.__name__ = "DataContainerInteractor"
        yield mock_int


@pytest.fixture
def mock_container():
    """Fixture for properly mocked DataContainer."""
    with patch("mosaic.container.DataContainer") as mock_cont:
        mock_cont.__bases__ = ()
        mock_cont.__name__ = "DataContainer"
        yield mock_cont


@pytest.fixture
def mock_settings():
    """Mock settings with default values."""
    with patch("mosaic.gui.Settings") as mock_settings:
        mock_settings.rendering.background_color = [0.1, 0.1, 0.1]
        mock_settings.rendering.background_color_alt = [0.2, 0.2, 0.2]
        mock_settings.rendering.use_depth_peeling = True
        mock_settings.rendering.occlusion_ratio = 0.1
        mock_settings.rendering.max_depth_peels = 4
        mock_settings.rendering.enable_fxaa = True
        mock_settings.rendering.multisamples = 0
        mock_settings.rendering.point_smoothing = True
        mock_settings.rendering.line_smoothing = True
        mock_settings.rendering.polygon_smoothing = True
        mock_settings.rendering.target_fps = 30

        mock_settings.ui.recent_files = []

        mock_settings.warnings.suppress_large_file_warning = False

        yield mock_settings
