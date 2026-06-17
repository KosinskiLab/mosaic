"""Qt event filter that intercepts sculpt-mode shortcuts before VTK sees them.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import Optional

from qtpy.QtCore import QEvent, QObject, Qt

from .session import TOOLS


__all__ = ["SculptShortcutFilter"]


_TOOL_FOR_KEY = {Qt.Key(ord(t.hotkey)): t.id for t in TOOLS}


class SculptShortcutFilter(QObject):
    """Eats keys and Shift+Wheel intended for sculpt actions on the vtk widget."""

    def __init__(self, controller, mode=None, sculpt_hud=None, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._mode = mode
        self._hud = sculpt_hud

    def _sync_radius(self) -> None:
        if self._hud is not None:
            self._hud.set_radius(self._controller.brush.radius)

    def _set_tool(self, tool: str) -> None:
        if self._mode is not None:
            self._mode.set_tool(tool)
            return None
        # Fallback for tests that exercise the filter without a mode object.
        if self._hud is not None:
            self._hud.set_tool(tool)
        if self._controller.session is not None:
            self._controller.set_tool(tool)
        return None

    def eventFilter(self, watched, event) -> bool:
        etype = event.type()
        if etype == QEvent.Type.KeyPress:
            return self._on_key(event)
        if etype == QEvent.Type.Wheel:
            return self._on_wheel(event)
        return False

    def _on_key(self, event) -> bool:
        key = event.key()

        # Escape bubbles to the gui-level shortcut that requests viewing mode.
        if key == Qt.Key.Key_Escape:
            return False

        tool: Optional[str] = _TOOL_FOR_KEY.get(key)
        if tool is not None:
            self._set_tool(tool)
            return True

        if key == Qt.Key.Key_BracketLeft:
            self._controller.handle_hotkey("[")
            self._sync_radius()
            return True
        if key == Qt.Key.Key_BracketRight:
            self._controller.handle_hotkey("]")
            self._sync_radius()
            return True

        return True

    def _on_wheel(self, event) -> bool:
        if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            return False
        delta = event.angleDelta().y()
        if delta == 0:
            return False
        if delta > 0:
            self._controller.handle_hotkey("]")
        else:
            self._controller.handle_hotkey("[")
        self._sync_radius()
        return True
