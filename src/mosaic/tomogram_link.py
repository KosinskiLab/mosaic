"""
Link between a session and the tomogram it was created from.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import os
from collections.abc import Callable

__all__ = ["TomogramLink"]


class TomogramLink:
    """Store a tomogram path in the session metadata and load it on restore.

    Parameters
    ----------
    loader : callable
        Loads the tomogram at a path.
    notify : callable
        Called as ``notify(prefix, path, warning, persist)`` to report status.
    enabled : callable
        Returns whether linked tomograms are loaded.
    on_change : callable
        Called with the path whenever a tomogram is linked.
    """

    def __init__(
        self,
        loader: Callable[[str], None],
        notify: Callable[[str, str, bool, bool], None],
        enabled: Callable[[], bool],
        on_change: Callable[[str], None],
    ):
        self.loader = loader
        self.notify = notify
        self.enabled = enabled
        self.on_change = on_change
        self.path: str | None = None

    def collect(self) -> dict:
        return {"tomogram": self.path}

    def restore(self, meta: dict) -> None:
        self.path = meta.get("tomogram")
        if self.path:
            self.on_change(self.path)
        self.load()
        return None

    def set(self, path: str | None, load: bool = True) -> None:
        """Set the linked tomogram and optionally load it."""
        self.path = path
        if path:
            self.on_change(path)
        if load:
            self.load()
        return None

    def load(self) -> None:
        """Load the linked tomogram and report the outcome."""
        path = self.path
        if path is None or not self.enabled():
            return None

        if not path.startswith("s3://") and not os.path.exists(path):
            self.notify("Tomogram missing: ", path, True, True)
            return None

        try:
            self.loader(path)
        except Exception as e:
            print(f"Could not load tomogram {path}: {e}")
            self.notify("Could not load ", path, True, True)
            return None

        self.notify("Loaded ", path, False, False)
        return None
