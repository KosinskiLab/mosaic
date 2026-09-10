import pytest

from mosaic.dialogs.import_data import ImportDataDialog
from mosaic.dialogs.export import ExportDialog
from mosaic.dialogs.properties import GeometryPropertiesDialog
from mosaic.geometry import BASE_COLOR

from .conftest import save_widget_screenshot


@pytest.mark.gui
class TestDialogs:

    def test_import_dialog(self, mosaic_app, output_dir, qapp):
        dialog = ImportDataDialog(mosaic_app)
        dialog.set_files(["membrane_segmentation.star"])
        dialog.show()
        qapp.processEvents()
        save_widget_screenshot(dialog, output_dir / "import_data.png")
        dialog.close()

    def test_export_dialog(self, mosaic_app, output_dir, qapp):
        dialog = ExportDialog(parent=mosaic_app)
        dialog.show()
        qapp.processEvents()
        save_widget_screenshot(dialog, output_dir / "export_data.png")
        dialog.close()

    def test_properties_dialog(self, mosaic_app, output_dir, qapp):
        props = {
            "base_color": BASE_COLOR,
            "highlight_color": (0.8, 0.2, 0.2),
            "size": 8,
            "opacity": 1.0,
            "ambient": 0.3,
            "diffuse": 0.7,
            "specular": 0.2,
            "volume_path": None,
            "sampling_rate": (6.8, 6.8, 6.8),
        }
        dialog = GeometryPropertiesDialog(initial_properties=props, parent=mosaic_app)
        dialog.show()
        qapp.processEvents()
        save_widget_screenshot(dialog, output_dir / "properties_dialog.png")
        dialog.close()
