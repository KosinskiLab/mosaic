from mosaic.data import MosaicData
from mosaic.formats import open_session


class TestMosaicData:
    def test_init(self, qapp, mock_vtk_widget):
        md = MosaicData(mock_vtk_widget)
        assert md.shape is None
        assert md.viewport.current_target is md.data

    def test_shape(self, qapp, mock_vtk_widget):
        md = MosaicData(mock_vtk_widget)
        md.shape = (128, 128, 128)
        assert md.shape == (128, 128, 128)

    def test_save_load_roundtrip(self, qapp, mock_vtk_widget, tmp_path):
        md = MosaicData(mock_vtk_widget)
        md.shape = (64, 64, 64)

        path = str(tmp_path / "session.pickle")
        md.to_file(path)

        state = open_session(path)
        assert "shape" in state["metadata"]

    def test_reset(self, qapp, mock_vtk_widget):
        md = MosaicData(mock_vtk_widget)
        md.shape = (100, 100, 100)
        md.reset()
        assert md.shape is None
        assert len(md.data.container) == 0
        assert len(md.models.container) == 0

    def test_swap_target(self, qapp, mock_vtk_widget):
        md = MosaicData(mock_vtk_widget)
        assert md.viewport.current_target is md.data
        md.viewport.swap_target()
        assert md.viewport.current_target is md.models
        md.viewport.swap_target()
        assert md.viewport.current_target is md.data

    def test_format_datalist_empty(self, qapp, mock_vtk_widget):
        md = MosaicData(mock_vtk_widget)
        result = md.format_datalist(type="data")
        assert result == []
