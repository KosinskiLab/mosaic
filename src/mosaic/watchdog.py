"""
Stop child processes when their combined resident memory exceeds a limit.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from contextlib import suppress
from threading import Event, Thread
from types import TracebackType

import psutil

__all__ = ["MemoryWatchdog"]


class MemoryWatchdog:
    """Monitor the combined resident memory of child processes.

    Parameters
    ----------
    limit_bytes : int or None, optional
        Resident memory limit in bytes. Defaults to 80% of physical memory.
    interval : float, optional
        Seconds between memory checks.

    Attributes
    ----------
    tripped : bool
        Whether the memory limit was exceeded during the current context.
    """

    def __init__(self, limit_bytes: int | None = None, interval: float = 0.5):
        if limit_bytes is None:
            limit_bytes = psutil.virtual_memory().total * 4 // 5
        self._limit_bytes = limit_bytes
        self._interval = interval
        self._stop = Event()
        self.tripped: bool = False

    def __enter__(self) -> "MemoryWatchdog":
        self.tripped = False
        self._stop.clear()
        self._thread = Thread(target=self._watch, daemon=True)
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._stop.set()
        self._thread.join()

    def _watch(self) -> None:
        """Poll child memory and kill the largest child above the limit."""
        parent = psutil.Process()
        while not self._stop.wait(self._interval):
            try:
                children = parent.children(recursive=True)
            except psutil.Error:
                continue

            sizes = {}
            for child in children:
                with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                    sizes[child] = child.memory_info().rss

            # Killing only the runaway worker lets its pool fail just that task.
            if sizes and sum(sizes.values()) > self._limit_bytes:
                self.tripped = True
                with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                    max(sizes, key=sizes.get).kill()
