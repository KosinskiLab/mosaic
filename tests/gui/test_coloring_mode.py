import numpy as np
import pytest
import vtk

from mosaic.data import MosaicData
from mosaic.stylesheets import Colors


@pytest.fixture
def make_data(qapp, mock_vtk_widget):
    window = mock_vtk_widget.GetRenderWindow()
    window.GetRenderers.return_value.GetFirstRenderer.return_value = vtk.vtkRenderer()
    return lambda: MosaicData(mock_vtk_widget)


def test_loaded_session_follows_entity_coloring(make_data, tmp_path):
    rng = np.random.default_rng(0)
    saved = make_data()
    for _ in range(2):
        saved.data.add(points=rng.random((20, 3)).astype(np.float32))
    path = saved.to_file(str(tmp_path / "s.mosaic"))

    loaded = make_data()
    loaded.viewport.set_coloring_mode("entity")
    loaded.load_session(path)

    colors = [tuple(g._appearance["base_color"]) for g in loaded.data.container.data]
    assert colors == [tuple(Colors.ENTITY[0]), tuple(Colors.ENTITY[1])]
