"""
Tests for the Mosaic shell Rich theme.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from mosaic.commands.theme import MOSAIC_THEME


EXPECTED_MOSAIC_KEYS = {
    "mosaic.heading",
    "mosaic.accent",
    "mosaic.dim",
    "mosaic.success",
    "mosaic.error",
}


def _mosaic_styles():
    """Return only the ``mosaic.*`` style entries.

    Rich's :class:`~rich.theme.Theme` inherits ~170 default style keys
    when ``inherit=True`` (the default), so the full ``MOSAIC_THEME.styles``
    dict is dominated by rich's own keys. The shell's contract is the set
    of ``mosaic.*`` keys it defines and nothing more.
    """
    return {k: v for k, v in MOSAIC_THEME.styles.items() if k.startswith("mosaic.")}


def test_theme_defines_exactly_five_mosaic_keys():
    assert set(_mosaic_styles()) == EXPECTED_MOSAIC_KEYS


def test_mosaic_styles_are_valid_rich_styles():
    # The shell theme intentionally reuses the GUI hex palette for brand
    # consistency; Rich downsamples truecolor to the terminal's depth. We only
    # require that each mosaic.* entry resolves to a well-formed Rich style.
    from rich.style import Style

    for name, style in _mosaic_styles().items():
        assert isinstance(style, Style), f"{name!r} is not a Rich Style"
        # Re-parsing the rendered definition must not raise.
        Style.parse(str(style))
