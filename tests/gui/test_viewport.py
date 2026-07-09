from mosaic.data import MosaicData


class TestViewportInteractor:
    def test_panes_back_reference_viewport(self, qapp, mock_vtk_widget):
        md = MosaicData(mock_vtk_widget)
        assert md.data.viewport is md.viewport
        assert md.models.viewport is md.viewport

    def test_set_target_returns_to_viewing(self, qapp, mock_vtk_widget):
        md = MosaicData(mock_vtk_widget)
        md.viewport._interaction_mode = "pick"
        md.viewport.set_target(md.models)
        assert md.viewport.current_target is md.models
        assert md.viewport._interaction_mode is None

    def test_swap_target_cycles_through_panes(self, qapp, mock_vtk_widget):
        md = MosaicData(mock_vtk_widget)
        md.viewport.swap_target()
        assert md.viewport.current_target is md.models
        md.viewport.swap_target()
        assert md.viewport.current_target is md.data
