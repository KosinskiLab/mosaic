"""
Controller that orchestrates the onboarding walkthrough flow.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import re

from qtpy.QtCore import QObject, Signal

from .overlay import SpotlightOverlay
from .base import OnboardingChapter, OnboardingStep


_CALL_PATTERN = re.compile(r"^(\w+)\(\s*(?:(['\"])([^'\"]*)\2)?\s*\)$")
_INDEX_PATTERN = re.compile(r"^(\w+)((?:\[[^\[\]]+\])+)$")


def resolve_widget(root, path: str):
    obj = root
    for attr in path.split("."):
        idx_match = _INDEX_PATTERN.match(attr)
        if idx_match:
            name, idx_block = idx_match.groups()
            obj = getattr(obj, name)
            for raw in re.findall(r"\[([^\[\]]+)\]", idx_block):
                key = raw.strip()
                if (key.startswith("'") and key.endswith("'")) or (
                    key.startswith('"') and key.endswith('"')
                ):
                    key = key[1:-1]
                else:
                    try:
                        key = int(key)
                    except ValueError:
                        pass
                obj = obj[key]
            continue
        match = _CALL_PATTERN.match(attr)
        if match:
            name, _, arg = match.groups()
            method = getattr(obj, name)
            obj = method(arg) if arg else method()
        else:
            obj = getattr(obj, attr)
    return obj


class OnboardingController(QObject):
    finished = Signal()

    def __init__(self, main_window):
        super().__init__(main_window)
        self._window = main_window
        self._overlay = SpotlightOverlay(main_window)
        self._overlay.skip_requested.connect(self.finish)
        self._overlay._tooltip.action_clicked.connect(self.advance)

        self._chapter: OnboardingChapter | None = None
        self._steps: list[OnboardingStep] = []
        self._current_index = 0
        self._signal_connection = None

    def start(self, chapter: OnboardingChapter):
        self._chapter = chapter
        self._chapter.setup(self._window)
        self._steps = chapter.steps()
        self._current_index = 0
        self._overlay.activate()
        self._show_current_step()

    def _show_current_step(self):
        if self._current_index >= len(self._steps):
            self.finish()
            return

        step = self._steps[self._current_index]
        target = resolve_widget(self._window, step.target)

        button_text = (
            "Finish" if self._current_index == len(self._steps) - 1 else "Next"
        )

        progress = f"{self._current_index + 1} / {len(self._steps)}"
        self._overlay._tooltip.set_content(step.title, step.body, progress, button_text)
        self._overlay.spotlight(
            target, step.highlight_padding, step.position, step.show_spotlight, step.dim
        )

        gated = step.mode == "action" and step.completion_signal is not None
        self._overlay._tooltip.set_action_enabled(not (gated and step.auto_advance))
        if gated:
            self._connect_signal(step.completion_signal)

    def _connect_signal(self, signal_path: str):
        self._disconnect_signal()
        signal = resolve_widget(self._window, signal_path)
        signal.connect(self._on_signal_completed)
        self._signal_connection = signal

    def _disconnect_signal(self):
        if self._signal_connection is not None:
            try:
                self._signal_connection.disconnect(self._on_signal_completed)
            except (TypeError, RuntimeError):
                pass
            self._signal_connection = None

    def _on_signal_completed(self, *_):
        self._disconnect_signal()
        step = self._steps[self._current_index]
        if step.auto_advance:
            self.advance()
        else:
            self._overlay._tooltip.set_action_enabled(True)
            self._overlay._tooltip._action_btn.setText("Next")

    def advance(self):
        step = self._steps[self._current_index]
        if step.before_next is not None:
            step.before_next()

        self._disconnect_signal()
        self._current_index += 1
        self._show_current_step()

    def finish(self):
        self._disconnect_signal()
        self._overlay.deactivate()
        if self._chapter:
            self._chapter.teardown(self._window)

        self._chapter = None
        self.finished.emit()
