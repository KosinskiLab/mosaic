"""
Single process-wide undo/redo stack used by every mutating subsystem.

Subsystems import ``STACK`` directly and push one ``UndoEntry`` per
mutation. Closures carry whatever state each op needs (snapshots, indices,
geometry references); the stack itself stays oblivious.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional


__all__ = ["UndoEntry", "UndoStack", "STACK"]


@dataclass(frozen=True)
class UndoEntry:
    """One reversible operation. Both callables must be no-arg."""

    label: str
    undo: Callable[[], None]
    redo: Callable[[], None]


class UndoStack:
    """Bounded deque of ``UndoEntry``. Push clears redo; redo refills it."""

    def __init__(self, capacity: int = 32) -> None:
        self._undo: deque[UndoEntry] = deque(maxlen=capacity)
        self._redo: deque[UndoEntry] = deque(maxlen=capacity)

    def push(self, entry: UndoEntry) -> None:
        self._undo.append(entry)
        self._redo.clear()

    def undo(self) -> Optional[UndoEntry]:
        if not self._undo:
            return None
        entry = self._undo.pop()
        entry.undo()
        self._redo.append(entry)
        return entry

    def redo(self) -> Optional[UndoEntry]:
        if not self._redo:
            return None
        entry = self._redo.pop()
        entry.redo()
        self._undo.append(entry)
        return entry

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()


STACK = UndoStack()
