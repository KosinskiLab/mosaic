from mosaic.widgets.dialog_footer import DialogFooter


def test_set_info_toggles_note(qapp):
    footer = DialogFooter(info_text="")
    footer.set_info("2 to resolve")
    assert footer.info_label.text() == "2 to resolve"
    assert not footer.info_label.isHidden() and not footer.info_icon.isHidden()
    footer.set_info(None)
    assert footer.info_label.isHidden() and footer.info_icon.isHidden()
