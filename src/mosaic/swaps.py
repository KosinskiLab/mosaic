"""
Container-level geometry swaps shared by the GUI interactor and the REPL.

Holds the reversible-change dataclasses plus the apply/restore helpers.
Everything operates DataContainerInteractors that expose the underlying
DataContainer instance as well as their add policy.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

__all__ = [
    "GeometrySwap",
    "GeometrySubset",
    "restore_geometry",
    "undo_subset_removal",
    "redo_subset_removal",
    "apply_changes",
    "record",
    "build_changes",
    "place",
]


@dataclass
class GeometrySwap:
    """Restore a uuid to an exact geometry (or absence) in either direction."""

    uuid: str
    before: Optional["Geometry"]
    after: Optional["Geometry"]


@dataclass
class GeometrySubset:
    """Point subset removed from a surviving geometry; undo re-appends the slice."""

    uuid: str
    removed: "Geometry"
    n_kept: int


def restore_geometry(target, uuid: str, geom) -> None:
    """Set ``uuid`` to ``geom`` exactly, or remove it when ``geom`` is None."""
    prev = target.container.get(uuid)
    if geom is None:
        if prev is not None:
            target.container.remove(uuid)
    elif prev is None:
        geom.uuid = uuid
        # DataContainerInteractor.add applies custom base colors to implement
        # coloring mode By Entity. When undoing we want to retain the old color
        target.add(geom, color=geom._appearance.get("base_color"))
    else:
        target.container.update(uuid, geom)
    return None


def undo_subset_removal(target, record) -> None:
    """Re-append a removed point slice to its surviving geometry."""
    from .geometry import merge_geometries

    slice_copy = record.removed[...]
    slice_copy.uuid = record.uuid
    if (current := target.container.get(record.uuid)) is None:
        target.add(slice_copy)
        return None

    merged = merge_geometries((current, slice_copy))
    merged.uuid = record.uuid
    target.container.update(record.uuid, merged)
    return None


def redo_subset_removal(target, record) -> None:
    """Re-remove the slice by keeping only the first ``n_kept`` points."""
    if (current := target.container.get(record.uuid)) is None:
        return None
    keep = np.zeros(current.get_number_of_points(), dtype=bool)
    keep[: record.n_kept] = True
    target.container.update(record.uuid, current.subset(keep, copy=True))
    return None


def apply_changes(target, changes: List, *, undo: bool) -> None:
    """Apply each change to ``target`` in the given direction."""
    for change in changes:
        if isinstance(change, GeometrySubset):
            if undo:
                undo_subset_removal(target, change)
            else:
                redo_subset_removal(target, change)
        else:
            restore_geometry(
                target, change.uuid, change.before if undo else change.after
            )
    return None


def record(target, changes: List, label: str) -> None:
    """Register one undo entry for an already-applied set of changes.

    The caller has performed the forward mutation; this only wires undo/redo
    closures over ``target.apply`` onto the shared stack.
    """
    from .undo import STACK

    STACK.push_pair(
        label,
        undo=lambda: target.apply(changes, undo=True),
        redo=lambda: target.apply(changes, undo=False),
    )
    return None


def build_changes(*, add=(), remove=()) -> List[GeometrySwap]:
    """Map add/remove geometries to a flat swap list (removals first).

    Parameters
    ----------
    add : iterable of Geometry, optional
        Geometries to add; each becomes a swap with ``before=None``.
    remove : iterable of Geometry, optional
        Geometries to remove; each becomes a swap with ``after=None``.
        A copy is captured at call time so later mutations do not affect undo.

    Returns
    -------
    List[GeometrySwap]
        Removal swaps followed by addition swaps.
    """
    changes = [GeometrySwap(g.uuid, before=g[...], after=None) for g in remove]
    changes += [GeometrySwap(g.uuid, before=None, after=g) for g in add]
    return changes


def place(target, *, add=(), remove=(), label: str) -> list:
    """Apply an add/remove placement on ``target`` and record one undo entry.

    Parameters
    ----------
    target : object
        Must expose ``.container``, ``.add(geom)``, and ``.apply(changes, *, undo)``.
    add : iterable of Geometry, optional
        Geometries to place into ``target``.
    remove : iterable of Geometry, optional
        Geometries to remove from ``target``.
    label : str
        Human-readable label for the undo stack entry.

    Returns
    -------
    list
        The added geometries (same objects, same order as ``add``).
    """
    add, remove = list(add), list(remove)
    changes = build_changes(add=add, remove=remove)
    target.apply(changes, undo=False)
    record(target, changes, label)
    return add
