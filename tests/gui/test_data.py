import pytest

from mosaic.data import MosaicData
from mosaic.formats import open_session, read_session_meta, write_session


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

        path = md.to_file(str(tmp_path / "session.mosaic"))

        state = open_session(path)
        assert "shape" in state["metadata"]

    def test_to_file_returns_mosaic_path(self, qapp, mock_vtk_widget, tmp_path):
        md = MosaicData(mock_vtk_widget)
        with pytest.warns(UserWarning):
            out = md.to_file(str(tmp_path / "s.pickle"))
        assert out == str(tmp_path / "s.mosaic")

    def test_hook_meta_persisted(self, qapp, mock_vtk_widget, tmp_path):
        md = MosaicData(mock_vtk_widget)
        md.register_session_hook(lambda: {"tomogram": "/t.mrc"}, lambda m: None)
        path = md.to_file(str(tmp_path / "s.mosaic"))
        assert read_session_meta(path)["tomogram"] == "/t.mrc"

    def test_foreign_meta_survives_and_none_deletes(
        self, qapp, mock_vtk_widget, tmp_path
    ):
        path = str(tmp_path / "s.mosaic")
        write_session(
            path,
            {},
            sections={"meta": ("json", b'{"run_id":"r1","tomogram":"/old.mrc"}')},
        )
        md = MosaicData(mock_vtk_widget)
        md.register_session_hook(lambda: {"tomogram": None}, lambda m: None)
        md.load_session(path)
        md.to_file(path)
        assert read_session_meta(path) == {"run_id": "r1"}

    def test_reset_drops_previous_file_sections(self, qapp, mock_vtk_widget, tmp_path):
        src = str(tmp_path / "a.mosaic")
        write_session(src, {}, sections={"meta": ("json", b'{"run_id":"r1"}')})
        md = MosaicData(mock_vtk_widget)
        md.load_session(src)
        md.reset()
        out = md.to_file(str(tmp_path / "b.mosaic"))
        assert read_session_meta(out) == {}

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
