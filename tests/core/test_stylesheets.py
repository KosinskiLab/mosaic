from mosaic.stylesheets import Colors


def test_warning_text_token():
    assert Colors.LIGHT["WARNING_TEXT"] == "#b45309"
    assert Colors.DARK["WARNING_TEXT"] == "#fbbf24"
