from mosaic.pipeline.builder import PipelineBuilderDialog
from mosaic.pipeline.widgets import OperationCardWidget


def _import_card(dialog):
    return next(
        card
        for card in dialog.findChildren(OperationCardWidget)
        if card.operation_id == "import_batch"
    )


def test_run_enabled_once_files_are_picked(qapp):
    dialog = PipelineBuilderDialog()
    dialog._load_preset("Import")
    assert not dialog.footer.accept_button.isEnabled()

    card = _import_card(dialog)
    card.input_files = ["/data/TS_001.mrc"]
    card._update_file_list()

    assert dialog.footer.accept_button.isEnabled()


def test_empty_pipeline_cannot_run(qapp):
    dialog = PipelineBuilderDialog()
    dialog._load_preset("Clear")
    assert not dialog.footer.accept_button.isEnabled()


def test_clear_disables_run(qapp):
    dialog = PipelineBuilderDialog()
    dialog._load_preset("Import")
    card = _import_card(dialog)
    card.input_files = ["/data/TS_001.mrc"]
    card._update_file_list()
    assert dialog.footer.accept_button.isEnabled()

    dialog._load_preset("Clear")

    assert not dialog.footer.accept_button.isEnabled()
