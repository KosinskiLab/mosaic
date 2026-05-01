"""
Base classes for onboarding chapters.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import Callable, Literal
from dataclasses import dataclass, field


@dataclass
class OnboardingStep:
    id: str
    target: str
    title: str
    body: str
    mode: Literal["passive", "action"] = "passive"
    completion_signal: str | None = None
    highlight_padding: int = 8
    position: Literal["auto", "above", "below", "left", "right", "center"] = "auto"
    show_spotlight: bool = True
    dim: bool = True
    auto_advance: bool = False
    before_next: Callable | None = field(default=None, repr=False)


class OnboardingChapter:
    id: str = ""
    title: str = ""
    description: str = ""
    duration: str = ""

    def __init__(self):
        self._main_window = None
        self._stash: dict[str, tuple[list, list]] = {}

    def setup(self, main_window) -> None:
        self._main_window = main_window

    def steps(self) -> list[OnboardingStep]:
        raise NotImplementedError

    def teardown(self, main_window) -> None:
        pass

    def snapshot(self, key: str) -> None:
        """Stash a copy of the current data + models geometries under *key*."""
        if self._main_window is None:
            return None

        cdata = self._main_window.cdata
        self._stash[key] = (
            [x[...] for x in cdata.data.container.data],
            [x[...] for x in cdata.models.container.data],
        )

    def restore(self, key: str) -> None:
        """Replace live data + models geometries with what was stashed under *key*."""
        if self._main_window is None or key not in self._stash:
            return None

        data_geoms, model_geoms = self._stash[key]
        cdata = self._main_window.cdata

        cdata.data.container.clear()
        for g in data_geoms:
            cdata.data.container.add(g[...])

        cdata.models.container.clear()
        for g in model_geoms:
            cdata.models.container.add(g[...])

        cdata.data.data_changed.emit()
        cdata.models.data_changed.emit()
        cdata.data.render(defer_render=False)
        cdata.models.render(defer_render=False)

    def transition(
        self,
        *,
        restore: str | None = None,
        transform: Callable | None = None,
        snapshot: str | None = None,
    ) -> Callable[[], None]:
        """Return a callable that runs restore -> transform -> snapshot in order.

        Convenient for ``before_next`` so each chapter step can declare its state
        choreography in one line instead of a dedicated method.
        """

        def _run() -> None:
            if restore is not None:
                self.restore(restore)

            if transform is not None:
                transform()

            if snapshot is not None:
                self.snapshot(snapshot)

        return _run
