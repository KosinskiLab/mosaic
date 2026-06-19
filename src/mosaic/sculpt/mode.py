"""Sculpt-mode adapter that owns the viewport-side wiring for sculpting.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import Optional

import vtk
from qtpy.QtCore import Qt
from qtpy.QtGui import QCursor

from .controller import EventKind
from .shortcuts import SculptShortcutFilter


__all__ = ["SculptInteractorStyle", "SculptMode", "sync_palette"]


def sync_palette(hud, controller) -> None:
    """Push the controller's per-mesh radius scale to ``hud``."""
    if hud is None:
        return None
    hud.set_radius_range(*controller.radius_bounds)
    hud.set_radius(controller.brush.radius)
    return None


def _first_triangular_mesh(models_pane):
    """Return the first visible (geometry, actor) pair whose model is a TriangularMesh."""
    from mosaic.parametrization import TriangularMesh

    container = models_pane.container
    for geom, actor in zip(container.data, container.get_actors()):
        if isinstance(geom.model, TriangularMesh) and geom.visible:
            return geom, actor
    return None


class SculptMode:
    """Owns sculpt-specific viewport binding for one active session."""

    def __init__(self, viewport, models_pane, sculpt_hud, controller) -> None:
        self._viewport = viewport
        self._vtk_widget = viewport.vtk_widget
        self._models_pane = models_pane
        self._hud = sculpt_hud
        self.controller = controller
        self.style = None
        self.camera_style: Optional[vtk.vtkInteractorStyleTrackballCamera] = None
        self.shortcut_filter = None
        self._models_listener = None

    def activate(self) -> None:
        """Install styles, shortcut filter, HUD signals, and bind to the first mesh."""
        renderer = self._vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer()
        self.controller.bind_renderer(
            renderer, mesh_actor=None, render_callback=self._viewport.render_vtk
        )
        # Undo/redo resolves its target by uuid against the live container, so a
        # sculpt undo lands on the mesh currently shown (e.g. a copy restored by
        # the interactor's own undo) rather than a stale, orphaned object.
        self.controller.set_geometry_resolver(self._models_pane.container.get)

        interactor = self._vtk_widget.GetRenderWindow().GetInteractor()
        if interactor is not None:
            self.style = SculptInteractorStyle(
                self._vtk_widget,
                self._models_pane,
                self.controller,
                sculpt_hud=self._hud,
            )
            # Cached so View tool can hand off to it (and back) without
            # re-creating either interactor each time.
            self.camera_style = vtk.vtkInteractorStyleTrackballCamera()
            interactor.SetInteractorStyle(self.style)

        default = _first_triangular_mesh(self._models_pane)
        if default is not None:
            geom, actor = default
            self.controller.attach_geometry(geom)
            if self._hud is not None:
                self.controller.set_tool(self._hud.current_tool())
            self.controller.bind_mesh_actor(actor)
            if self.style is not None:
                self.style._bound_actor = actor

        sync_palette(self._hud, self.controller)

        self.shortcut_filter = SculptShortcutFilter(
            self.controller, mode=self, sculpt_hud=self._hud
        )
        self._vtk_widget.installEventFilter(self.shortcut_filter)

        self._connect_hud_signals()
        self._setup_geometry_watcher()

        self._update_cursor("view")

        if self._hud is not None:
            self._hud.show()

        local = self._vtk_widget.mapFromGlobal(QCursor.pos())
        dpr = self._vtk_widget.devicePixelRatio()
        x = int(local.x() * dpr)
        y = int((self._vtk_widget.height() - local.y()) * dpr)
        self.controller.handle_event(EventKind.MOUSE_MOVE, x, y)

    def deactivate(self) -> None:
        """Tear everything down. Safe to call when partially initialised."""
        if self._hud is not None:
            self._hud.hide()
        self._disconnect_hud_signals()

        if self.style is not None:
            self.style.cleanup()

        interactor = self._vtk_widget.GetRenderWindow().GetInteractor()
        if interactor is not None:
            current = interactor.GetInteractorStyle()
            if isinstance(current, SculptInteractorStyle):
                current.cleanup()

        self.controller.detach()

        if self.shortcut_filter is not None:
            self._vtk_widget.removeEventFilter(self.shortcut_filter)

        self._teardown_geometry_watcher()

        self.style = None
        self.camera_style = None
        self.shortcut_filter = None

    def set_tool(self, tool: str) -> None:
        """Switch the active sculpt tool everywhere: HUD, controller, cursor.

        Single entry point for tool changes from any source (HUD click, hotkey,
        default-on-attach). ``hud.set_tool`` is suppress-signal so this is safe
        to call from inside the HUD's own ``toolChanged`` handler without
        re-entering.
        """
        if self._hud is not None:
            self._hud.set_tool(tool)
        self.controller.set_tool(tool)
        self._update_cursor(tool)

    def _connect_hud_signals(self) -> None:
        if self._hud is None:
            return None
        self._hud.toolChanged.connect(self._on_hud_tool_changed)
        self._hud.radiusChanged.connect(self._on_hud_radius_changed)
        self._hud.strengthChanged.connect(self._on_hud_strength_changed)
        return None

    def _disconnect_hud_signals(self) -> None:
        if self._hud is None:
            return None
        for sig, slot in (
            (self._hud.toolChanged, self._on_hud_tool_changed),
            (self._hud.radiusChanged, self._on_hud_radius_changed),
            (self._hud.strengthChanged, self._on_hud_strength_changed),
        ):
            try:
                sig.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        return None

    def _on_hud_tool_changed(self, tool: str) -> None:
        self.set_tool(tool)
        self._viewport.render_vtk()

    def _on_hud_radius_changed(self, value: float) -> None:
        self.controller.set_radius(value)

    def _on_hud_strength_changed(self, value: float) -> None:
        self.controller.set_smooth_strength(float(value))

    def _update_cursor(self, tool: str) -> None:
        """Swap to the View-tool interactor (and cursor) for the given tool."""
        is_view = tool == "view"
        self._vtk_widget.setCursor(
            Qt.CursorShape.ArrowCursor if is_view else Qt.CursorShape.BlankCursor
        )
        interactor = self._vtk_widget.GetRenderWindow().GetInteractor()
        if interactor is not None:
            target = self.camera_style if is_view else self.style
            if target is not None and interactor.GetInteractorStyle() is not target:
                interactor.SetInteractorStyle(target)
        if hasattr(self.controller, "set_brush_overlay_visible"):
            self.controller.set_brush_overlay_visible(not is_view)

    def _setup_geometry_watcher(self) -> None:
        """Drop the controller's geometry binding if its mesh is removed."""

        def _on_models_changed():
            geom = self.controller._geometry
            if geom is None:
                return None
            if geom in self._models_pane.container.data:
                return None
            self.controller.release_geometry()
            if self.style is not None:
                self.style._bound_actor = None
            return None

        self._models_pane.data_changed.connect(_on_models_changed)
        self._models_listener = _on_models_changed

    def _teardown_geometry_watcher(self) -> None:
        if self._models_listener is not None:
            try:
                self._models_pane.data_changed.disconnect(self._models_listener)
            except (TypeError, RuntimeError):
                pass
        self._models_listener = None


class SculptInteractorStyle(vtk.vtkInteractorStyleTrackballCamera):
    """VTK interactor style for sculpt mode."""

    def __init__(self, vtk_widget, models_pane, controller, sculpt_hud=None):
        super().__init__()
        self.vtk_widget = vtk_widget
        self.models_pane = models_pane
        self.controller = controller
        self.sculpt_hud = sculpt_hud
        self.renderer = vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer()
        self._bound_actor = None
        self._mesh_picker = vtk.vtkCellPicker()
        self._mesh_picker.SetTolerance(0.001)

        self.AddObserver("LeftButtonPressEvent", self._on_left_button_down)
        self.AddObserver("LeftButtonReleaseEvent", self._on_left_button_up)
        self.AddObserver("MouseMoveEvent", self._on_mouse_move)
        self.AddObserver("MiddleButtonPressEvent", self._swallow)
        self.AddObserver("MiddleButtonReleaseEvent", self._swallow)
        self.AddObserver("RightButtonPressEvent", self._swallow)
        self.AddObserver("RightButtonReleaseEvent", self._swallow)
        self.AddObserver("MouseWheelForwardEvent", self._swallow)
        self.AddObserver("MouseWheelBackwardEvent", self._swallow)

    def cleanup(self):
        if self.controller is not None:
            self.controller.detach()
        self._bound_actor = None
        return None

    def _swallow(self, obj, event):
        return None

    def _event_position(self):
        return self.GetInteractor().GetEventPosition()

    def _pick_mesh_geometry_at(self, x, y):
        from mosaic.parametrization import TriangularMesh

        result = self._mesh_picker.Pick(x, y, 0, self.renderer)
        if not result:
            return None

        actor = self._mesh_picker.GetActor()
        if actor is None:
            return None

        models = self.models_pane.container
        try:
            index = models.get_actors().index(actor)
        except ValueError:
            return None

        geometry = models.get(index)
        if geometry is None:
            return None

        if not isinstance(geometry.model, TriangularMesh):
            return None

        return geometry, actor

    def _ensure_bound(self, x, y):
        if self._bound_actor is not None and self.controller.session is not None:
            return True

        picked = self._pick_mesh_geometry_at(x, y)
        if picked is None:
            return False
        self._bind_to(*picked)
        return True

    def _bind_to(self, geometry, actor) -> None:
        """Attach the controller to ``geometry`` and sync the HUD to its scale."""
        self.controller.attach_geometry(geometry)
        if self.sculpt_hud is not None:
            self.controller.set_tool(self.sculpt_hud.current_tool())
        else:
            self.controller.set_tool("grab")
        self.controller.bind_mesh_actor(actor)
        self._bound_actor = actor
        sync_palette(self.sculpt_hud, self.controller)

    def _is_view_mode(self) -> bool:
        session = self.controller.session
        return session is not None and session.tool == "view"

    def _on_left_button_down(self, obj, event):
        if self._is_view_mode():
            return None
        x, y = self._event_position()
        if not self._ensure_bound(x, y):
            return None
        self.controller.handle_event(EventKind.LMB_DOWN, x, y)
        return None

    def _on_left_button_up(self, obj, event):
        if self.controller.session is None or self._is_view_mode():
            return None
        x, y = self._event_position()
        self.controller.handle_event(EventKind.LMB_UP, x, y)
        return None

    def _on_mouse_move(self, obj, event):
        x, y = self._event_position()
        self._maybe_rebind(x, y)
        self.controller.handle_event(EventKind.MOUSE_MOVE, x, y)
        return None

    def _maybe_rebind(self, x: int, y: int) -> None:
        """Fluid hover-bind: if the cursor moved over a different triangular
        mesh and we are not mid-stroke, swap the controller's target so the
        brush highlights and edits whatever the cursor is over.
        """
        if self._is_view_mode():
            return None
        session = self.controller.session
        if session is not None and session.in_stroke:
            return None
        picked = self._pick_mesh_geometry_at(x, y)
        if picked is None:
            return None
        geometry, actor = picked
        if geometry is self.controller._geometry:
            return None
        self._bind_to(geometry, actor)
        return None
