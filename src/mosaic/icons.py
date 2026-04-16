"""
Central icon factory. All icons in the application should be created
through this module as it enforces the palette convention and
provides graceful fallbacks.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import warnings
from typing import Optional, Tuple

import qtawesome as qta

from .stylesheets import Colors

__all__ = ["icon", "icon_pixmap", "icon_button"]


def _role_color(role: str) -> str:
    """Map a semantic role to the current palette color."""
    if role == "muted":
        return Colors.ICON
    if role == "active":
        return Colors.ICON_ACTIVE
    if role == "primary":
        return Colors.PRIMARY
    if role == "success":
        return Colors.SUCCESS
    if role == "warning":
        return Colors.WARNING
    if role == "error":
        return Colors.ERROR
    raise ValueError(f"unknown icon role: {role!r}")


def _resolve_colors(
    role: str,
    color: Optional[str],
    color_disabled: Optional[str],
) -> Tuple[str, str]:
    """Resolve (enabled_color, disabled_color) for an icon."""
    enabled = color if color is not None else _role_color(role)
    disabled = color_disabled if color_disabled is not None else Colors.ICON
    return enabled, disabled


def icon(
    name: str,
    *,
    role: str = "muted",
    color: Optional[str] = None,
    color_disabled: Optional[str] = None,
    **qta_kwargs,
):
    """Build a QIcon.

    If *name* is unknown to qtawesome, we emit a warning and return a
    placeholder, if that also cant be rendered an empty QIcon.
    """
    fallback = "ph.question"
    enabled, disabled = _resolve_colors(role, color, color_disabled)
    try:
        return qta.icon(name, color=enabled, color_disabled=disabled, **qta_kwargs)
    except Exception as exc:
        warnings.warn(
            f"Icon {name!r} unavailable ({exc}); falling back to {fallback!r}",
            stacklevel=2,
        )
    try:
        return qta.icon(fallback, color=enabled, color_disabled=disabled)
    except Exception as exc:
        warnings.warn(
            f"Fallback icon {fallback!r} also unavailable ({exc}); "
            "returning empty QIcon",
            stacklevel=2,
        )
        from qtpy.QtGui import QIcon

        return QIcon()


def icon_pixmap(
    name: str,
    size: int,
    *,
    role: str = "muted",
    color: Optional[str] = None,
    **qta_kwargs,
):
    """Build a QPixmap of the given size. Uses the same fallback as ``icon``."""
    return icon(name, role=role, color=color, **qta_kwargs).pixmap(size, size)


def icon_button(
    name: str,
    *,
    role: str = "active",
    size: int = 22,
    tooltip: str = "",
    flat: bool = True,
):
    """Build a ``QPushButton`` with a palette-driven icon."""
    from qtpy.QtWidgets import QPushButton

    btn = QPushButton()
    btn.setIcon(icon(name, role=role))
    btn.setFixedSize(size, size)
    btn.setToolTip(tooltip)
    btn.setFlat(flat)
    return btn


# Backwards compatibility
_COMPAT_SHIMS = {
    "dialog_accept_icon": ("ph.caret-right", "primary"),
    "dialog_reject_icon": ("ph.x", "muted"),
    "dialog_next_icon": ("ph.skip-forward", "primary"),
    "dialog_previous_icon": ("ph.skip-back", "primary"),
    "dialog_apply_icon": ("ph.checks", "primary"),
    "dialog_selectall_icon": ("ph.check-square", "primary"),
    "dialog_selectnone_icon": ("ph.x-square", "primary"),
}


def __getattr__(attr):
    if attr in _COMPAT_SHIMS:
        name, role = _COMPAT_SHIMS[attr]
        return icon(name, role=role)
    if attr == "info_icon":
        return icon_pixmap("ph.info", 18, role="primary")
    raise AttributeError(f"module 'mosaic.icons' has no attribute {attr!r}")
