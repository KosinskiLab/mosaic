"""
Implements ViewportInteractor, which owns viewport-wide state shared
across the DataContainerInteractor panes (Clusters and Models):
the event filter, world-position pickers, draw/pick mode, the active
interaction target, and renderer-level actor reconciliation.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import vtk
import numpy as np
from qtpy.QtCore import Qt, QObject, QEvent, QTimer, Signal

__all__ = ["ViewportInteractor"]


class ViewportInteractor(QObject):
    """Viewport-wide interaction state shared across DataContainerInteractor panes."""

    render_update = Signal()
    vtk_pre_render = Signal()

    def __init__(self, vtk_widget, panes):
        super().__init__()
        self.vtk_widget = vtk_widget
        self.panes = list(panes)
        self.current_target = self.panes[0]
        self.rendered_actors = set()
        self._interaction_mode = None
        self.point_picker = vtk.vtkWorldPointPicker()
        self._last_lod_budget = None

        for pane in self.panes:
            pane.attach_viewport(self)
            pane.data_changed.connect(self.refresh_lod)

        self.attach_area_picker()
        self.vtk_widget.installEventFilter(self)
        self._setup_interaction_lod()

    def set_target(self, pane):
        """Set the active interaction target and return all panes to viewing."""
        if pane not in self.panes:
            raise ValueError("Pane is not registered with this viewport.")
        self.current_target = pane
        self.activate_viewing_mode()

    def swap_target(self):
        """Cycle to the next registered pane, return to viewing, and re-attach the area picker."""
        idx = self.panes.index(self.current_target)
        self.set_target(self.panes[(idx + 1) % len(self.panes)])
        return self.attach_area_picker()

    def activate_viewing_mode(self):
        self._interaction_mode = None
        for pane in self.panes:
            pane.set_active_cluster(None)

    def activate_drawing_mode(self):
        """Drawing always operates on the current target."""
        for pane in self.panes:
            pane.set_active_cluster(None)
        self._interaction_mode = "draw"
        new_cluster_index = self.current_target.add(
            points=np.empty((0, 3), dtype=np.float32)
        )
        new_uuid = self.current_target.container.get(new_cluster_index).uuid
        self.current_target.set_active_cluster(new_uuid)

    def activate_picking_mode(self):
        self._interaction_mode = "pick"

    def attach_area_picker(self):
        self.interactor = self.vtk_widget.GetRenderWindow().GetInteractor()
        if self.interactor is None:
            raise ValueError("Initialize an Interactor first.")
        self.area_picker = vtk.vtkAreaPicker()
        style = vtk.vtkInteractorStyleRubberBandPick()

        self.interactor.SetPicker(self.area_picker)
        self.interactor.SetInteractorStyle(style)
        self.area_picker.AddObserver("EndPickEvent", self._on_area_pick)

    def get_event_position(self, event, return_event_position: bool = True):
        pos = event.pos()
        return self._get_event_position(
            (pos.x(), pos.y(), 0), return_event_position=return_event_position
        )

    def _get_event_position(self, position, return_event_position: bool = True):
        dpr = self.vtk_widget.devicePixelRatio()
        y = (self.vtk_widget.height() - position[1]) * dpr
        event_position = (position[0] * dpr, y, 0)
        r = self.vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer()
        self.point_picker.Pick(*event_position, r)
        world_position = self.point_picker.GetPickPosition()

        camera = r.GetActiveCamera()
        camera_plane = vtk.vtkPlane()
        camera_plane.SetNormal(camera.GetDirectionOfProjection())
        camera_plane.SetOrigin(world_position)

        t = vtk.mutable(0.0)
        x = [0, 0, 0]
        camera_plane.IntersectWithLine(camera.GetPosition(), world_position, t, x)
        if return_event_position:
            return x, event_position
        return x

    def eventFilter(self, watched_obj, event):
        if self._interaction_mode in ("draw", "pick") and event.type() in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseMove,
        ):
            if event.buttons() & Qt.MouseButton.LeftButton:
                world_position, event_position = self.get_event_position(event, True)
                if self._interaction_mode == "draw":
                    self.current_target.add_point(world_position)
                elif self._interaction_mode == "pick":
                    self.current_target.pick_prop(self._pick_prop_at(event_position))
                return True
        return super().eventFilter(watched_obj, event)

    def _pick_prop_at(self, event_position):
        """Run a VTK prop-pick at *event_position* and return the picked prop (or None)."""
        picker = vtk.vtkPropPicker()
        renderer = self.vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer()
        picker.Pick(*event_position, renderer)
        return picker.GetViewProp()

    def _on_area_pick(self, obj, event):
        frustum = obj.GetFrustum()
        interactor = self.vtk_widget.GetRenderWindow().GetInteractor()
        target = self.current_target
        if not interactor.GetShiftKey():
            target.deselect_points()

        num_planes = frustum.GetNumberOfPlanes()
        plane_norm = np.empty((num_planes, 3), dtype=np.float32)
        plane_orig = np.empty((num_planes, 3), dtype=np.float32)
        for i in range(num_planes):
            plane = frustum.GetPlane(i)
            plane_norm[i] = plane.GetNormal()
            plane_orig[i] = plane.GetOrigin()

        frustum_min, frustum_max = _compute_frustum_bound(plane_norm, plane_orig)
        for geometry in target.container.data:
            if not geometry.visible:
                continue

            bounds = geometry._data.GetBounds()
            if not _bounds_in_frustum(bounds, plane_norm, plane_orig):
                continue

            points = geometry.points
            if len(points) == 0:
                continue

            mask = (
                (points[:, 0] >= frustum_min[0])
                & (points[:, 0] <= frustum_max[0])
                & (points[:, 1] >= frustum_min[1])
                & (points[:, 1] <= frustum_max[1])
                & (points[:, 2] >= frustum_min[2])
                & (points[:, 2] <= frustum_max[2])
            )
            if not mask.any():
                continue

            ids = np.flatnonzero(mask)
            ids = ids[_points_in_frustum(points[ids], plane_norm, plane_orig)]
            if len(ids) == 0:
                continue

            uuid = geometry.uuid
            if uuid not in target.point_selection:
                target.point_selection[uuid] = np.array([], dtype=np.int32)

            union = np.union1d(ids, target.point_selection[uuid])
            target.point_selection[uuid] = union.astype(np.int32, copy=False)
        target.highlight_selected_points(color=None)

    def refresh_lod(self, force: bool = False):
        """Recompute interaction-LOD budgets across all panes.

        Returns
        -------
        bool
            True when LOD actors were created or destroyed (caller
            should expect the renderer to have re-synced).
        """
        from . import lod

        budget = lod.get_point_budget()
        force = force or (budget != self._last_lod_budget)
        self._last_lod_budget = budget

        geometries = [g for pane in self.panes for g in pane.container.data]
        budgets = lod.compute_scene_lod(geometries, budget)

        changed = False
        for g in geometries:
            per_geom = budgets.get(g.uuid)
            if per_geom is not None:
                if force or getattr(g, "_lod_indices", None) is None:
                    g.setup_lod(per_geom)
                    changed = True
            elif getattr(g, "_lod_actor", None) is not None:
                g.setup_lod(lod.LOD_DISABLED)
                changed = True

        if changed:
            self.render()
        return changed

    def _setup_interaction_lod(self):
        """Register VTK interaction observers for point-budget LOD."""
        self._lod_restore_timer = QTimer(self.vtk_widget)
        self._lod_restore_timer.setSingleShot(True)
        self._lod_restore_timer.setInterval(50)
        self._lod_restore_timer.timeout.connect(self._restore_full_data)

        if (interactor := self.vtk_widget.GetRenderWindow().GetInteractor()) is None:
            return None

        interactor.AddObserver("StartInteractionEvent", self._on_interaction_start)
        interactor.AddObserver("EndInteractionEvent", self._on_interaction_end)

    def _on_interaction_start(self, obj, event):
        self._lod_restore_timer.stop()
        for pane in self.panes:
            for geom in pane.container.data:
                geom.begin_interaction()

    def _on_interaction_end(self, obj, event):
        self._lod_restore_timer.start()

    def _restore_full_data(self):
        for pane in self.panes:
            for geom in pane.container.data:
                geom.end_interaction()
        self.vtk_widget.GetRenderWindow().Render()

    def render(self, defer_render: bool = False):
        """Synchronize VTK actors and pane tree widgets, then render."""
        renderer = self.vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer()

        current_actors = set()
        for pane in self.panes:
            for geom in pane.container.data:
                current_actors.add(geom.actor)
                lod_actor = getattr(geom, "_lod_actor", None)
                if lod_actor is not None:
                    current_actors.add(lod_actor)

        actors_to_remove = self.rendered_actors - current_actors
        for actor in actors_to_remove:
            renderer.RemoveViewProp(actor)
            self.rendered_actors.remove(actor)

        actors_to_add = current_actors - self.rendered_actors
        for actor in actors_to_add:
            renderer.AddViewProp(actor)
            self.rendered_actors.add(actor)

        for pane in self.panes:
            pane.data_list.update(pane._uuid_to_items())

        if defer_render:
            return None

        self.render_vtk()
        self.render_update.emit()

    def render_vtk(self):
        self.vtk_pre_render.emit()
        return self.vtk_widget.GetRenderWindow().Render()

    def set_coloring_mode(self, mode: str):
        """Apply a coloring mode to every pane and render once."""
        for pane in self.panes:
            pane.set_coloring_mode(mode)
        self.render_vtk()

    def highlight_clusters_from_selected_points(self):
        """Promote point-selection to cluster-selection on the active pane."""
        return self.current_target.highlight_clusters_from_selected_points()

    def visibility_unselected(self, visible: bool = True):
        """Toggle visibility for geometries not selected on each pane."""
        for pane in self.panes:
            kept = set(pane.point_selection.keys())
            kept.update(pane._get_selected_uuids())
            unselected = pane.data_list.to_state().get_all_uuids() - kept
            pane.visibility(
                geometries=[pane.container.get(uuid) for uuid in unselected],
                visible=visible,
            )


def _compute_frustum_bound(plane_normals, plane_origins, tol=1e-6):
    from itertools import combinations

    vertices = []
    for i, j, k in combinations(range(len(plane_normals)), 3):
        A = np.array([plane_normals[i], plane_normals[j], plane_normals[k]])
        b = np.array(
            [
                np.dot(plane_normals[i], plane_origins[i]),
                np.dot(plane_normals[j], plane_origins[j]),
                np.dot(plane_normals[k], plane_origins[k]),
            ]
        )

        if abs(np.linalg.det(A)) > np.finfo(np.float32).resolution:
            vertex = np.linalg.solve(A, b)
            vertices.append(vertex)

    vertices = np.array(vertices)
    return vertices.min(axis=0), vertices.max(axis=0)


def _points_in_frustum(points, plane_normals, plane_origins):
    offsets = (plane_origins * plane_normals).sum(axis=1)
    return ((points @ plane_normals.T) <= offsets).all(axis=1)


def _bounds_in_frustum(bounds, plane_normals, plane_origins):
    xmin, xmax, ymin, ymax, zmin, zmax = bounds
    corners = np.array(
        [
            [xmin, ymin, zmin],
            [xmax, ymin, zmin],
            [xmin, ymax, zmin],
            [xmax, ymax, zmin],
            [xmin, ymin, zmax],
            [xmax, ymin, zmax],
            [xmin, ymax, zmax],
            [xmax, ymax, zmax],
        ],
        dtype=np.float32,
    )

    for normal, origin in zip(plane_normals, plane_origins):
        distances = np.dot(corners - origin, normal)
        if np.all(distances > 0):
            return False
    return True
