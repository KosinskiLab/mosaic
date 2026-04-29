"""
Rich terminal theme for the Mosaic scripting interface.

Derives the terminal palette from :class:`~mosaic.stylesheets.Colors`,
adapting the GUI's indigo/slate/emerald system for dark terminal backgrounds.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from io import StringIO

from rich.box import ROUNDED, SIMPLE_HEAD
from rich.console import Console
from rich.theme import Theme

from ..stylesheets import Colors

__all__ = [
    "MOSAIC_THEME",
    "get_console",
    "render_to_text",
    "BOX_TABLE",
    "BOX_PANEL",
]

BOX_TABLE = SIMPLE_HEAD
BOX_PANEL = ROUNDED

MOSAIC_THEME = Theme(
    {
        "mosaic.heading": f"bold {Colors.PRIMARY}",
        "mosaic.accent": Colors.PRIMARY,
        "mosaic.data": Colors.BORDER_HOVER,
        "mosaic.muted": Colors.TEXT_SECONDARY,
        "mosaic.error": f"bold {Colors.ERROR}",
        "mosaic.success": Colors.SUCCESS,
        "mosaic.command": Colors.CATEGORY["preprocessing"],
        "mosaic.param": Colors.CATEGORY["analysis"],
        "mosaic.index": f"bold {Colors.PRIMARY}",
        "mosaic.border": Colors.TEXT_SECONDARY,
        "mosaic.banner.title": f"bold {Colors.PRIMARY}",
        "mosaic.banner.version": Colors.WARNING,
        "mosaic.prompt.name": f"bold {Colors.PRIMARY}",
        "mosaic.prompt.sep": Colors.TEXT_SECONDARY,
        "mosaic.bar.complete": Colors.PRIMARY,
        "mosaic.bar.finished": Colors.SUCCESS,
        "mosaic.bar.remaining": Colors.TEXT_SECONDARY,
        "mosaic.warning": Colors.WARNING,
        "mosaic.rule": Colors.TEXT_SECONDARY,
        "mosaic.type": Colors.CATEGORY["parametrization"],
        "mosaic.group": Colors.CATEGORY["analysis"],
    }
)

_console: Console | None = None


def get_console() -> Console:
    """Return the singleton themed :class:`~rich.console.Console`."""
    global _console
    if _console is None:
        _console = Console(theme=MOSAIC_THEME, highlight=False)
    return _console


def render_to_text(renderable) -> str:
    """Render a rich renderable to plain text (no ANSI codes).

    Used for ``$()`` substitution and script output where markup
    would interfere with downstream parsing.

    Parameters
    ----------
    renderable
        Any rich renderable (Table, Panel, Text, str, ...).

    Returns
    -------
    str
        Plain-text representation.
    """
    buf = StringIO()
    console = Console(file=buf, theme=MOSAIC_THEME, no_color=True, width=120)
    console.print(renderable)
    return buf.getvalue()
