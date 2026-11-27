"""
Short display strings for file paths.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import re

from qtpy.QtCore import Qt
from qtpy.QtGui import QFontMetrics
from qtpy.QtWidgets import QLabel, QTableWidgetItem

__all__ = ["display_path", "display_paths", "set_path_text"]


def _parent_and_name(path: str) -> tuple[str, str]:
    parts = re.split(r"[/\\]", path.rstrip("/\\"))
    return parts[-2] if len(parts) > 1 else "", parts[-1]


def _with_parent(path: str) -> str:
    parent, name = _parent_and_name(path)
    return f"…/{parent}/{name}" if parent else name


def display_path(path: str, root: str | None = None) -> str:
    """Return a short display form of a path.

    Parameters
    ----------
    path : str
        Path or URL to shorten.
    root : str, optional
        Directory that ``path`` is shown relative to.

    Returns
    -------
    str
        Path relative to ``root``, ``…/parent/name`` if outside ``root``,
        or the base name if no ``root`` is given.
    """
    path = path.rstrip("/\\")
    if root is None:
        return _parent_and_name(path)[1]

    prefix = root.rstrip("/\\").replace("\\", "/") + "/"
    if path.replace("\\", "/").startswith(prefix):
        return path[len(prefix) :]
    return _with_parent(path)


def display_paths(paths: list[str], root: str | None = None) -> list[str]:
    """Apply :py:func:`display_path`, adding the parent to colliding entries.

    Parameters
    ----------
    paths : list of str
        Paths to shorten.
    root : str, optional
        Directory that paths are shown relative to.

    Returns
    -------
    list of str
        Display strings in the order of ``paths``.
    """
    shown = [display_path(p, root) for p in paths]
    return [_with_parent(p) if shown.count(s) > 1 else s for p, s in zip(paths, shown)]


def set_path_text(
    widget: QLabel | QTableWidgetItem,
    path: str,
    root: str | None = None,
    prefix: str = "",
    width: int | None = None,
) -> None:
    """Show a shortened path on a widget with the full path as tooltip.

    Parameters
    ----------
    widget : QWidget
        Widget with ``setText`` and ``setToolTip``.
    path : str
        Path to display.
    root : str, optional
        Directory that ``path`` is shown relative to.
    prefix : str, optional
        Text placed before the path. Defaults to empty.
    width : int, optional
        Pixel width to elide to. Defaults to the widget width.
    """
    width = widget.width() if width is None else width
    text = QFontMetrics(widget.font()).elidedText(
        prefix + display_path(path, root), Qt.TextElideMode.ElideMiddle, width
    )
    widget.setText(text)
    widget.setToolTip(prefix + path)
    return None
