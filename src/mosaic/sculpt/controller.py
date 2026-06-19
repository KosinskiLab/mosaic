"""
The viewport feeds raw screen events through ``handle_event``. The controller
owns the brush settings, the active ``SculptSession``, the polydata writer that
syncs every stamp back to VTK in place, and the overlay actors.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Tuple

import numpy as np
import vtk

from mosaic.meshing.utils import _edge_lengths

from .adapter import (
    PolyDataPointWriter,
    read_geometry_arrays,
    swap_geometry_topology,
    sync_model_vertices,
)
from .overlay import SculptOverlay
from .session import (
    SculptSession,
    SculptTarget,
    TOOL_BY_HOTKEY,
    TOOL_BY_ID,
)
from .tools import (
    ActiveSet,
    brush_query,
    grab_apply,
    patch_touched_loops,
    smooth_stamp,
)


__all__ = ["Brush", "EventKind", "MeshHit", "SculptController"]


class EventKind(Enum):
    LMB_DOWN = auto()
    LMB_UP = auto()
    MOUSE_MOVE = auto()


@dataclass
class Brush:
    radius: float = 10.0


@dataclass
class MeshHit:
    world_position: np.ndarray
    normal: np.ndarray


def pick_mesh(
    picker, renderer, screen_x: int, screen_y: int, actor
) -> Optional["MeshHit"]:
    """Cell-pick at the given screen coords. Returns None on miss or wrong actor."""
    if picker.Pick(screen_x, screen_y, 0, renderer) == 0:
        return None
    if picker.GetActor() is not actor:
        return None
    return MeshHit(
        world_position=np.asarray(picker.GetPickPosition(), dtype=np.float64),
        normal=np.asarray(picker.GetPickNormal(), dtype=np.float64),
    )


# Default per-stamp Laplacian step for Smooth. Small enough that several stamps
# build up gradually but large enough that a single tap is visible.
_DEFAULT_SMOOTH_STRENGTH = 0.25


def _radius_defaults(
    vs: np.ndarray, fs: np.ndarray
) -> Tuple[float, Tuple[float, float]]:
    """Pick a default brush radius + slider bounds from mesh scale."""
    mean_edge = float(_edge_lengths(vs, fs).mean()) if len(fs) else 0.0
    diag = float(np.linalg.norm(vs.max(axis=0) - vs.min(axis=0))) if len(vs) else 0.0

    if mean_edge > 1e-6:
        default = mean_edge * 8.0
        high = mean_edge * 40.0
    elif diag > 1e-6:
        default = diag * 0.05
        high = diag * 0.5
    else:
        default = 10.0
        high = 1000.0

    if diag > 1e-6:
        high = min(high, diag * 0.5)

    high = max(high, default * 2.0)
    low = max(mean_edge * 0.5, 1e-3)
    return default, (low, high)


class SculptController:
    def __init__(self, brush: Optional[Brush] = None) -> None:
        self.brush = brush or Brush()

        # Track whether the user explicitly chose a radius. If they didn't,
        # ``attach_geometry`` picks a sensible default from the mesh's average
        # edge length so the brush is meaningfully sized on any mesh scale.
        self._radius_set_by_user = brush is not None
        self.session: Optional[SculptSession] = None
        self._geometry = None
        self._writer: Optional[PolyDataPointWriter] = None
        self._renderer = None
        self._mesh_actor = None
        self._picker: Optional[vtk.vtkCellPicker] = None
        self._overlay: Optional[SculptOverlay] = None
        self._render_callback = None

        # Resolves a geometry uuid to the object currently holding it, mirroring
        # ``container.get(uuid)``. Undo/redo closures resolve their target this
        # way at apply-time instead of capturing the geometry object: the
        # interactor's own undo restores *copies* under the same uuid, so a stale
        # object reference would edit an orphan while the visible mesh keeps the
        # sculpted edit. None means "no container wired" (headless/tests), in
        # which case we fall back to the actively-bound geometry.
        self._resolve_geometry = None
        self._last_cursor_world: Optional[np.ndarray] = None
        self._tint_color: Tuple[float, float, float] = TOOL_BY_ID["view"].color

        # Avoid round-tripping ``set_color()`` every move when already cleared.
        self._tint_active: bool = False
        self.radius_bounds: Tuple[float, float] = (0.5, 500.0)
        self.smooth_strength: float = _DEFAULT_SMOOTH_STRENGTH

    def attach_geometry(self, geometry) -> None:
        vs, fs = read_geometry_arrays(geometry)
        target = SculptTarget(vs=vs, fs=fs)
        default_radius, self.radius_bounds = _radius_defaults(vs, fs)
        if not self._radius_set_by_user:
            self.brush.radius = default_radius

        if self._geometry is not None and self._geometry is not geometry:
            self._clear_tint()

        self._geometry = geometry
        self.session = SculptSession(target)
        self.session.set_tool(self._initial_tool())
        self._writer = PolyDataPointWriter(geometry._data)
        self._tint_active = False
        self._apply_tool_color(self.session.tool)

    def detach(self) -> None:
        # Push the rolled-back vertices back to the polydata so the mesh
        # visibly snaps to its pre-stroke state before we tear everything down.
        if (
            self.session is not None
            and self.session.in_stroke
            and self._writer is not None
        ):
            self.session.cancel_stroke()
            self._writer.write(self.session.target.vs)
        self.release_geometry()
        self.unbind_renderer()

    def release_geometry(self) -> None:
        """Drop the bound geometry but keep renderer/overlay alive for rebinding."""
        if self.session is not None:
            self.session.cancel_stroke()
        self._clear_tint()
        self.session = None
        self._geometry = None
        self._writer = None
        self._mesh_actor = None

    def bind_renderer(self, renderer, mesh_actor=None, render_callback=None) -> None:
        if self._overlay is not None and self._renderer is not None:
            self._overlay.detach(self._renderer)

        self._renderer = renderer
        self._mesh_actor = mesh_actor
        self._render_callback = render_callback
        self._picker = vtk.vtkCellPicker()
        self._picker.SetTolerance(0.001)
        self._overlay = SculptOverlay()
        self._overlay.attach(renderer)
        if self.session is not None:
            self._apply_tool_color(self.session.tool)

    def set_geometry_resolver(self, resolver) -> None:
        """Wire how undo/redo finds the live geometry for a uuid."""
        self._resolve_geometry = resolver

    def _resolve_live(self, uuid):
        """Return the geometry currently under ``uuid``, or None if it is gone."""
        if uuid is None:
            return None
        if self._resolve_geometry is None:
            return self._geometry
        return self._resolve_geometry(uuid)

    def bind_mesh_actor(self, mesh_actor) -> None:
        """Record which actor the cell-picker should match against."""
        self._mesh_actor = mesh_actor

    def unbind_renderer(self) -> None:
        if self._overlay is not None and self._renderer is not None:
            self._overlay.detach(self._renderer)

        self._overlay = None
        self._renderer = None
        self._mesh_actor = None
        self._picker = None
        self._render_callback = None

    def _apply_tint(self, indices: np.ndarray) -> None:
        """Color ``indices`` with the active tool's tint, on the source mesh."""
        if self._geometry is None or indices.size == 0:
            self._clear_tint()
            return None

        self._geometry.color_points(
            indices.astype(np.int32, copy=False), self._tint_color
        )
        self._tint_active = True
        return None

    def _clear_tint(self) -> None:
        """Restore the mesh to its base color (a no-op if it already is)."""
        if not self._tint_active or self._geometry is None:
            return None

        self._geometry.set_color()
        self._tint_active = False
        return None

    def set_tool(self, tool: str) -> None:
        self._apply_tool_color(tool)
        if self.session is None:
            return None

        self.session.set_tool(tool)
        return None

    def set_radius(self, value: float) -> None:
        self.brush.radius = max(float(value), 1e-3)
        self._radius_set_by_user = True
        self.refresh_cursor_radius()

    def set_smooth_strength(self, value: float) -> None:
        """Update the Smooth-tool per-stamp Laplacian alpha. Clamped to [0, 1]."""
        self.smooth_strength = max(0.0, min(1.0, float(value)))

    def handle_hotkey(self, key: str) -> None:
        if self.session is None:
            return None
        tool = TOOL_BY_HOTKEY.get(key)
        if tool is not None:
            self.set_tool(tool)
        elif key == "]":
            self.set_radius(self.brush.radius * 1.1)
        elif key == "[":
            self.set_radius(self.brush.radius / 1.1)
        return None

    def handle_event(self, kind: EventKind, screen_x: int, screen_y: int) -> None:
        if kind is EventKind.MOUSE_MOVE:
            self._update_hover(screen_x, screen_y)
        if self.session is None:
            return None
        if kind is EventKind.LMB_DOWN:
            self._on_lmb_down(screen_x, screen_y)
        elif kind is EventKind.MOUSE_MOVE:
            self._on_mouse_move(screen_x, screen_y)
        elif kind is EventKind.LMB_UP:
            self._on_lmb_up()
        return None

    def _on_lmb_down(self, x: int, y: int) -> None:
        session = self.session
        if session is None:
            return None

        tool = session.tool
        if tool == "view":
            return None

        hit = self._pick(x, y)
        if hit is None:
            return None

        active = self._brush_active(hit)
        if active.indices.size == 0 and tool != "patch":
            return None

        if tool == "grab":
            session.begin_stroke(
                anchor_world=active.hit_point,
                locked_indices=active.indices,
                locked_weights=active.weights,
            )
            if self._overlay is not None:
                self._overlay.set_drag_vector(active.hit_point, active.hit_point)
            return self._request_render()

        if tool == "patch":
            session.begin_stroke()
            self._stamp_patch(session, active)
            return self._request_render()

        session.begin_stroke()
        self._stamp_smooth(session, active)
        return self._request_render()

    def _on_mouse_move(self, x: int, y: int) -> None:
        session = self.session
        if session is None or not session.in_stroke:
            return None

        tool = session.tool
        if tool == "grab":
            self._step_grab(session, x, y)
            return None

        hit = self._pick(x, y)
        if hit is None:
            return None

        active = self._brush_active(hit)
        if active.indices.size == 0:
            return None

        if tool == "smooth":
            self._stamp_smooth(session, active)
            return self._request_render()

        if tool == "patch":
            self._stamp_patch(session, active)
            return self._request_render()
        return None

    def _on_lmb_up(self) -> None:
        session = self.session
        if session is None or not session.in_stroke:
            return None
        if session.tool == "patch":
            self._commit_patch(session)
        else:
            record = session.commit_stroke()
            if self._writer is not None:
                self._writer.write(session.target.vs)
            if self._geometry is not None:
                sync_model_vertices(self._geometry, session.target.vs)
            if record is not None:
                self._push_stroke_undo(session, record)
        if self._overlay is not None:
            self._overlay.clear_drag_vector()
        self._request_render()
        return None

    def _stamp_smooth(self, session: SculptSession, active: ActiveSet) -> None:
        target = session.target
        smooth_stamp(
            vs=target.vs,
            adjacency=target.adjacency,
            indices=active.indices,
            weights=active.weights,
            strength=self.smooth_strength,
        )
        if self._writer is not None:
            self._writer.write(target.vs)
        self._apply_tint(active.indices)

    def _step_grab(self, session: SculptSession, x: int, y: int) -> None:
        state = session.grab_state()
        if state is None:
            return None
        indices, weights, rest, anchor = state
        world_delta = self._screen_delta_to_world(x, y, anchor)
        if world_delta is None:
            return None

        target = session.target
        grab_apply(target.vs, indices, weights, rest, world_delta, strength=1.0)
        if self._writer is not None:
            self._writer.write(target.vs)
        if self._overlay is not None:
            self._overlay.set_drag_vector(anchor, anchor + world_delta)
        self._request_render()
        return None

    def _stamp_patch(self, session: SculptSession, active: ActiveSet) -> None:
        """Accumulate brushed vertices that lie on an open boundary; mark them up."""
        target = session.target
        boundary_mask = target.boundary_mask
        on_boundary = boundary_mask[active.indices]
        boundary_indices = active.indices[on_boundary]
        session.accumulate_patch(boundary_indices)
        painted = session.painted_boundary_indices()
        if painted.size > 0:
            self._apply_tint(painted)
        else:
            self._clear_tint()

    def _commit_patch(self, session: SculptSession) -> None:
        painted = session.painted_boundary_indices()
        target = session.target
        if painted.size == 0:
            session.cancel_stroke()
            self._clear_tint()
            return None

        result = patch_touched_loops(target.vs, target.fs, painted)
        if result is None:
            session.cancel_stroke()
            self._clear_tint()
            return None

        new_vs, new_fs = result
        record = session.apply_topology_change(new_vs, new_fs)
        geometry = self._geometry
        if geometry is None:
            return None

        self._tint_active = False
        swap_geometry_topology(geometry, target.vs, target.fs)
        self._writer = PolyDataPointWriter(geometry._data)
        self._push_patch_undo(geometry, record)
        return None

    def _update_hover(self, x: int, y: int) -> None:
        if self._overlay is None or self._renderer is None:
            return None
        hit = (
            self._pick(x, y)
            if (self._mesh_actor is not None and self.session is not None)
            else None
        )
        on_mesh = hit is not None
        if on_mesh:
            self._last_cursor_world = hit.world_position
        else:
            focal = np.asarray(
                self._renderer.GetActiveCamera().GetFocalPoint(), dtype=np.float64
            )
            self._last_cursor_world = focal
        pixels = self._world_radius_to_pixels(
            self._last_cursor_world, self.brush.radius
        )
        self._overlay.set_cursor_screen_position(x, y, on_mesh=on_mesh)
        self._overlay.set_cursor_radius(pixels)
        if self.session is not None and not self.session.in_stroke:
            tool = self.session.tool
            if hit is None or tool == "view":
                self._clear_tint()
            elif tool == "patch":
                target = self.session.target
                active = self._brush_active(hit)
                if active.indices.size > 0:
                    on_boundary = target.boundary_mask[active.indices]
                    self._apply_tint(active.indices[on_boundary])
                else:
                    self._clear_tint()
            else:
                active = self._brush_active(hit)
                self._apply_tint(active.indices)
        self._request_render()
        return None

    def set_brush_overlay_visible(self, visible: bool) -> None:
        """Show or hide the cursor ring + surface tint (used by View tool)."""
        if self._overlay is not None:
            self._overlay.cursor_ring.SetVisibility(int(bool(visible)))
            if not visible:
                self._overlay.clear_drag_vector()
        if not visible:
            self._clear_tint()
        self._request_render()
        return None

    def refresh_cursor_radius(self) -> None:
        if self._overlay is None or self._renderer is None:
            return None

        if self._last_cursor_world is None:
            self._last_cursor_world = np.asarray(
                self._renderer.GetActiveCamera().GetFocalPoint(), dtype=np.float64
            )
        pixels = self._world_radius_to_pixels(
            self._last_cursor_world, self.brush.radius
        )
        self._overlay.set_cursor_radius(pixels)
        self._request_render()
        return None

    def _pick(self, x: int, y: int) -> Optional[MeshHit]:
        if self._renderer is None or self._picker is None or self._mesh_actor is None:
            return None
        return pick_mesh(self._picker, self._renderer, x, y, self._mesh_actor)

    def _brush_active(self, hit: MeshHit) -> ActiveSet:
        if self.session is None:
            return ActiveSet.empty()
        target = self.session.target
        camera_pos = None
        normals = None

        # Back-face culling only applies to Grab. Smooth needs every vertex in
        # range so a tilted neighbour can't be silently dropped; Patch reads
        # boundary state which has no front/back notion.
        if self.session.tool == "grab" and self._renderer is not None:
            camera_pos = np.asarray(
                self._renderer.GetActiveCamera().GetPosition(), dtype=np.float64
            )
            normals = target.normals
        return brush_query(
            vs=target.vs,
            hit_point=hit.world_position,
            radius=self.brush.radius,
            vertex_normals=normals,
            camera_position=camera_pos,
        )

    def _screen_delta_to_world(
        self, cursor_x: int, cursor_y: int, anchor: np.ndarray
    ) -> Optional[np.ndarray]:
        if self._renderer is None:
            return None
        self._renderer.SetWorldPoint(
            float(anchor[0]), float(anchor[1]), float(anchor[2]), 1.0
        )
        self._renderer.WorldToDisplay()
        anchor_display = self._renderer.GetDisplayPoint()
        self._renderer.SetDisplayPoint(
            float(cursor_x), float(cursor_y), float(anchor_display[2])
        )
        self._renderer.DisplayToWorld()
        world = self._renderer.GetWorldPoint()
        if abs(world[3]) < 1e-12:
            return None
        current = np.array([world[0], world[1], world[2]], dtype=np.float64) / world[3]
        return current - anchor

    def _world_radius_to_pixels(
        self, world_point: np.ndarray, world_radius: float
    ) -> float:
        if self._renderer is None:
            return 24.0
        camera = self._renderer.GetActiveCamera()
        view_up = np.asarray(camera.GetViewUp(), dtype=np.float64)
        direction = np.asarray(camera.GetDirectionOfProjection(), dtype=np.float64)
        right = np.cross(direction, view_up)
        norm = float(np.linalg.norm(right))
        if norm < 1e-12:
            return 24.0
        right /= norm
        p1 = np.asarray(world_point, dtype=np.float64)
        p2 = p1 + right * float(world_radius)
        self._renderer.SetWorldPoint(float(p1[0]), float(p1[1]), float(p1[2]), 1.0)
        self._renderer.WorldToDisplay()
        d1 = self._renderer.GetDisplayPoint()
        self._renderer.SetWorldPoint(float(p2[0]), float(p2[1]), float(p2[2]), 1.0)
        self._renderer.WorldToDisplay()
        d2 = self._renderer.GetDisplayPoint()
        return float(np.hypot(d2[0] - d1[0], d2[1] - d1[1]))

    def _apply_tool_color(self, tool: str) -> None:
        spec = TOOL_BY_ID.get(tool)
        rgb: Tuple[float, float, float] = spec.color if spec else (1.0, 1.0, 1.0)
        self._tint_color = rgb
        if self._overlay is not None:
            self._overlay.set_tool_color(rgb)
        return None

    def _initial_tool(self) -> str:
        if self.session is not None and self.session.tool in TOOL_BY_ID:
            return self.session.tool
        return "view"

    def _push_stroke_undo(self, session, record) -> None:
        from ..undo import STACK

        uuid = getattr(self._geometry, "uuid", None)
        # Capture the render trigger now: the global undo outlives sculpt mode,
        # and unbind_renderer nulls _render_callback. Without this, an undo fired
        # after leaving sculpt mode swaps the data but never repaints.
        render = self._render_callback
        indices = record.indices
        before = record.before_positions
        after = record.after_positions

        def apply(positions):
            geom = self._resolve_live(uuid)
            if geom is None or indices.size == 0:
                return None

            if self._geometry is geom and self.session is not None:
                # Still the active mesh: drive the live session target + writer.
                vs = self.session.target.vs
                if vs.shape[0] <= int(indices.max()):
                    return None
                vs[indices] = positions
                self.session.target.invalidate_normals()
                writer = self._writer
            else:
                # Detached, or replaced by a restored copy under the same uuid:
                # edit the live mesh's own points so undo lands on what is shown.
                vs = np.ascontiguousarray(geom.points, dtype=np.float64)
                if vs.shape[0] <= int(indices.max()):
                    return None
                vs[indices] = positions
                writer = PolyDataPointWriter(geom._data)

            if writer is not None:
                writer.write(vs)
            sync_model_vertices(geom, vs)
            if render is not None:
                render()
            return None

        STACK.push_pair(
            f"Sculpt: {session.tool}",
            undo=lambda: apply(before),
            redo=lambda: apply(after),
        )
        return None

    def _push_patch_undo(self, geometry, record) -> None:
        from ..undo import STACK

        uuid = getattr(geometry, "uuid", None)
        # Capture the render trigger now; see _push_stroke_undo for why the
        # controller's live callback is unreliable once sculpt mode is gone.
        render = self._render_callback

        def swap(vs, fs):
            geom = self._resolve_live(uuid)
            if geom is None:
                return None
            swap_geometry_topology(geom, vs, fs)
            if self._geometry is geom:
                # We are still the active mesh: keep the live session in sync and
                # rebind the controller's writer to the freshly-rebuilt polydata.
                if self.session is not None:
                    self.session.target.replace_topology(vs, fs)
                self._writer = PolyDataPointWriter(geom._data)
            self._tint_active = False
            if render is not None:
                render()
            return None

        STACK.push_pair(
            "Sculpt: patch",
            undo=lambda: swap(record.before_vs, record.before_fs),
            redo=lambda: swap(record.after_vs, record.after_fs),
        )
        return None

    def _request_render(self) -> None:
        if self._render_callback is not None:
            self._render_callback()
