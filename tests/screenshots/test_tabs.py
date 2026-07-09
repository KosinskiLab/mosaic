import pytest


@pytest.mark.gui
class TestTabs:

    def test_segmentation_tab(self, mosaic_app, qapp):
        mosaic_app.tab_bar.setCurrentIndex(0)
        qapp.processEvents()

    def test_parametrization_tab(self, mosaic_app, qapp):
        mosaic_app.tab_bar.setCurrentIndex(1)
        qapp.processEvents()

    def test_intelligence_tab(self, mosaic_app, qapp):
        mosaic_app.tab_bar.setCurrentIndex(2)
        qapp.processEvents()
