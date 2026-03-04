from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Dict, Any

from vtk import vtkTransform
from qtpy.QtWidgets import QDialog

from ..stylesheets import Colors, QPushButton_style, QScrollArea_style


class BaseAnimation(ABC):
    """Base class for all animations"""

    def __init__(
        self,
        vtk_widget,
        cdata,
        volume_viewer,
        global_start_frame=0,
        enabled=True,
        name: str = "",
    ):
        self.cdata = cdata
        self.vtk_widget = vtk_widget
        self.volume_viewer = volume_viewer
        self.global_start_frame = global_start_frame

        self.name = name
        self.enabled = enabled

        self.start_frame = 0
        self.stop_frame = 100
        self.stride = 1

        self.parameters = {}
        self._init_parameters()

    @abstractmethod
    def _init_parameters(self) -> None:
        """Initialize animation-specific parameters"""
        pass

    @abstractmethod
    def get_settings(self) -> List[Dict[str, Any]]:
        """Return a list of setting definitions for the UI"""
        pass

    @abstractmethod
    def _update(self, frame: int) -> None:
        """Implementation of frame update logic"""
        pass

    @property
    def duration(self) -> int:
        """Calculate animation duration in frames"""
        return int(self.stop_frame - self.start_frame)

    def update_parameters(self, **kwargs) -> None:
        """Update parameter settings and handle associated depencies"""
        self.parameters.update(**kwargs)

    def reset(self) -> None:
        """Reset any externally-modified state before a new frame is applied.

        Called by the composer before each frame so that animations which
        modify shared state (e.g. actor opacity) can restore defaults first.
        Override in subclasses that need this; the base implementation is a no-op.
        """
        pass

    def update(self, global_frame: int) -> None:
        """Update animation state for the given global frame"""
        if not self.enabled:
            return None

        local_frame = global_frame - self.global_start_frame + self.start_frame
        if local_frame > self.stop_frame:
            return None

        if (local_frame >= self.start_frame) and (local_frame % self.stride) == 0:
            self._update(local_frame)

    def _get_rendering_context(self, return_renderer: bool = False):
        """Return the current camera instance"""
        renderer = self.vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer()
        camera = renderer.GetActiveCamera()
        if return_renderer:
            return camera, renderer
        return camera

    def _get_progress(self, frame: int):
        """Compute eased progress in [0, 1] for the given local frame.

        Returns None if the animation has zero duration.
        """
        duration = self.stop_frame - self.start_frame
        if duration <= 0:
            return None
        t = (frame - self.start_frame) / duration
        return self._ease(max(0.0, min(1.0, t)))

    def _ease(self, t: float) -> float:
        """Apply easing function to progress value t in [0, 1]."""
        easing = self.parameters.get("easing", "linear")

        if easing == "ease-in":
            return t * t
        elif easing == "ease-out":
            return 1.0 - (1.0 - t) * (1.0 - t)
        elif easing == "ease-in-out":
            if t < 0.5:
                return 2.0 * t * t
            return 1.0 - (-2.0 * t + 2.0) ** 2 / 2.0
        elif easing == "instant":
            return 1.0 if t > 0 else 0.0
        return t  # linear


class TrajectoryAnimation(BaseAnimation):
    """Animation for molecular trajectories"""

    def _available_trajectories(self):
        from mosaic.geometry import GeometryTrajectory

        models = self.cdata.format_datalist("models")

        trajectories = []
        for name, obj in models:
            if isinstance(obj, GeometryTrajectory):
                trajectories.append(name)
        return trajectories

    def _get_trajectory(self, name: str):
        models = self.cdata.format_datalist("models")
        return next((x for t, x in models if t == name), None)

    def _init_parameters(self) -> None:
        trajectories = self._available_trajectories()
        if (default := self.parameters.get("trajectory")) is None:
            try:
                default = trajectories[0]
            except IndexError:
                default = None
            self.update_parameters(trajectory=default)

    def update_parameters(self, **kwargs):
        new_trajectory = kwargs.get("trajectory")
        if new_trajectory and new_trajectory != self.parameters.get("trajectory"):
            self._trajectory = self._get_trajectory(new_trajectory)
            self.start_frame = 0
            self.stop_frame = self._trajectory.frames

        return super().update_parameters(**kwargs)

    def get_settings(self) -> List[Dict[str, Any]]:
        return [
            {
                "label": "trajectory",
                "type": "select",
                "options": self._available_trajectories(),
                "default": self.parameters.get("trajectory"),
                "description": "Select trajectories to animate.",
            },
        ]

    def _update(self, frame: int) -> None:
        if not hasattr(self, "_trajectory"):
            print("No trajectory associated with object")
            return None

        self._trajectory.display_frame(frame)
        uuids = self.cdata.models._get_selected_uuids()
        if uuids:
            self.cdata.models.set_selection_by_uuid(uuids)


class VolumeAnimation(BaseAnimation):
    """Volume slicing animation"""

    def _init_parameters(self) -> None:
        self.parameters.clear()
        self.parameters["direction"] = "forward"
        self.parameters["projection"] = "Off"
        self.parameters["axis"] = "Z"
        self.parameters["hide"] = False
        self._original_visibility = None
        try:
            self.update_parameters(
                axis=self.volume_viewer.primary.orientation_selector.currentText().lower()
            )
        except Exception:
            pass

    def reset(self) -> None:
        """Restore volume visibility to the state before this animation touched it.

        Uses the VTK actor directly to avoid triggering intermediate renders
        that would cause flickering during playback.
        """
        if self._original_visibility is not None:
            self.volume_viewer.primary.slice.SetVisibility(self._original_visibility)

    def get_settings(self) -> List[Dict[str, Any]]:
        projection = [
            self.volume_viewer.primary.project_selector.itemText(i)
            for i in range(self.volume_viewer.primary.project_selector.count())
        ]
        return [
            {
                "label": "axis",
                "type": "select",
                "options": ["x", "y", "z"],
                "default": "z",
                "description": "Axis to slice over.",
            },
            {
                "label": "direction",
                "type": "select",
                "options": ["forward", "backward"],
                "description": "Direction to slice through.",
            },
            {
                "label": "projection",
                "type": "select",
                "options": projection,
                "default": self.volume_viewer.primary.orientation_selector.currentText(),
                "description": "Direction to slice through.",
            },
            {
                "label": "hide",
                "type": "select",
                "options": ["False", "True"],
                "default": str(self.parameters.get("hide", False)),
                "description": "Hide the volume during the animation.",
            },
        ]

    def update_parameters(self, **kwargs):
        if "hide" in kwargs:
            value = kwargs["hide"]
            if isinstance(value, str):
                value = value == "True"
            kwargs["hide"] = value

        new_axis = kwargs.get("axis")
        if new_axis and new_axis != self.parameters.get("axis"):
            _mapping = {"x": 0, "y": 1, "z": 2}
            shape = self.volume_viewer.primary.get_dimensions()
            self.start_frame = 0
            self.stop_frame = shape[_mapping.get(new_axis, 0)]
            kwargs["axis"] = new_axis.upper()

        # Skip the duplicate axis handling in the parent by calling grandparent
        self.parameters.update(**kwargs)

    def update(self, global_frame: int) -> None:
        """Apply hide visibility with forwards-fill semantics.

        Before the range the volume keeps whatever visibility was set by
        ``reset()`` or an earlier animation. During and after the range
        the hide state persists so that later animations can build on it.
        """
        if not self.enabled:
            return
        local_frame = global_frame - self.global_start_frame + self.start_frame
        if local_frame < self.start_frame:
            return
        local_frame = min(self.stop_frame, local_frame)
        if (local_frame >= self.start_frame) and (local_frame % self.stride) == 0:
            self._update(local_frame)

    def _update(self, frame: int) -> None:
        if self.parameters["direction"] == "backward":
            frame = self.stop_frame - frame

        viewer = self.volume_viewer.primary

        # Track original visibility so reset() can restore it
        if self._original_visibility is None:
            self._original_visibility = viewer.is_visible

        if self.parameters.get("hide", False):
            viewer.slice.SetVisibility(False)

        # We change the widgets rather than calling the underlying functions
        # to ensure the GUI is updated accordingly for interactive views
        current_orientation = viewer.get_orientation()
        if current_orientation != self.parameters["axis"]:
            viewer.orientation_selector.setCurrentText(self.parameters["axis"])

        current_state = self.volume_viewer.primary.get_projection()
        if current_state != self.parameters["projection"]:
            viewer.project_selector.setCurrentText(self.parameters["projection"])

        viewer.slice_row.setValue(frame)


class CameraAnimation(BaseAnimation):
    """Camera orbit animation with absolute positioning for proper scrubbing."""

    def _init_parameters(self) -> None:
        self.parameters.clear()
        self.parameters.update(
            {
                "axis": "y",
                "degrees": 180,
                "direction": "forward",
            }
        )
        self._initial_position = None
        self._initial_focal = None
        self._initial_view_up = None
        self.stop_frame = 180

    def get_settings(self) -> List[Dict[str, Any]]:
        return [
            {
                "label": "axis",
                "type": "select",
                "options": ["x", "y", "z"],
                "default": self.parameters.get("axis", "y"),
                "description": "Axis to rotate over.",
            },
            {
                "label": "degrees",
                "type": "float",
                "min": 0,
                "max": 360,
                "default": self.parameters.get("degrees", 180),
                "description": "Total angle to rotate over axis.",
            },
            {
                "label": "direction",
                "type": "select",
                "options": ["forward", "reverse"],
                "default": self.parameters.get("direction", "forward"),
                "description": "Direction to rotate in.",
            },
        ]

    def _update(self, frame: int) -> None:
        camera, renderer = self._get_rendering_context(return_renderer=True)

        # Capture initial state on first frame
        if self._initial_position is None or frame == self.start_frame:
            self._initial_position = camera.GetPosition()
            self._initial_focal = camera.GetFocalPoint()
            self._initial_view_up = camera.GetViewUp()

        progress = self._get_progress(frame)
        if progress is None:
            return

        # Calculate total rotation angle at this point
        total_degrees = self.parameters["degrees"]
        if self.parameters.get("direction") == "reverse":
            total_degrees = -total_degrees

        angle = total_degrees * progress

        # Apply rotation from initial position
        transform = vtkTransform()
        transform.Identity()
        transform.Translate(*self._initial_focal)

        axis = self.parameters["axis"]
        if axis == "x":
            transform.RotateWXYZ(angle, 1, 0, 0)
        elif axis == "y":
            transform.RotateWXYZ(angle, 0, 1, 0)
        elif axis == "z":
            transform.RotateWXYZ(angle, 0, 0, 1)

        transform.Translate(
            -self._initial_focal[0],
            -self._initial_focal[1],
            -self._initial_focal[2],
        )

        new_pos = transform.TransformPoint(self._initial_position)
        new_view_up = transform.TransformVector(self._initial_view_up)

        camera.SetPosition(*new_pos)
        camera.SetViewUp(*new_view_up)
        renderer.ResetCameraClippingRange()


class ActorSelectionDialog(QDialog):
    """Dialog for selecting actors using ContainerTreeWidget."""

    def __init__(self, cdata, current_selection=None, parent=None):
        from qtpy.QtWidgets import (
            QVBoxLayout,
            QHBoxLayout,
            QTreeWidget,
            QLabel,
            QFrame,
            QPushButton,
            QGroupBox,
        )

        from mosaic.widgets import DialogFooter
        from mosaic.widgets.container_list import (
            ContainerTreeWidget,
            StyledTreeWidgetItem,
        )

        super().__init__(parent)
        self.setWindowTitle("Select Objects")
        self.resize(400, 500)
        self.setModal(True)
        self.setStyleSheet(QPushButton_style + QScrollArea_style)

        self._cdata = cdata
        self._trees = []
        self._tree_labels = []

        layout = QVBoxLayout(self)
        current_selection = set(current_selection or [])

        # Quick select buttons
        quick_group = QGroupBox("Quick Select")
        quick_layout = QHBoxLayout(quick_group)
        quick_layout.setContentsMargins(8, 8, 8, 8)
        quick_layout.setSpacing(6)

        for label, callback in [
            ("All", self._select_all),
            ("Clusters", lambda: self._select_by_type("data")),
            ("Models", lambda: self._select_by_type("models")),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(callback)
            quick_layout.addWidget(btn)

        layout.addWidget(quick_group)

        for label, data_type, interactor in [
            ("Clusters", "data", cdata.data),
            ("Models", "models", cdata.models),
        ]:
            objects = {obj.uuid: obj for _, obj in cdata.format_datalist(data_type)}
            if not objects:
                continue

            header = QLabel(label)
            header.setStyleSheet("font-weight: 500; font-size: 12px;")
            layout.addWidget(header)

            tree = ContainerTreeWidget(border=False)
            tree.tree_widget.setSelectionMode(
                QTreeWidget.SelectionMode.ExtendedSelection
            )
            self._trees.append(tree)
            self._tree_labels.append(data_type)

            state = interactor.data_list.to_state()
            uuid_to_item = {}
            for uuid, obj in objects.items():
                item = StyledTreeWidgetItem(
                    obj._meta.get("name"),
                    obj.visible,
                    {"object_id": id(obj), "data_type": data_type, **obj._meta},
                )
                uuid_to_item[uuid] = item

            tree.apply_state(state, uuid_to_item)

            for uuid, obj in objects.items():
                if uuid in uuid_to_item and id(obj) in current_selection:
                    uuid_to_item[uuid].setSelected(True)
            layout.addWidget(tree)

            separator = QFrame()
            separator.setFrameShape(QFrame.Shape.HLine)
            separator.setStyleSheet("color: #6b7280;")
            layout.addWidget(separator)

        layout.addWidget(DialogFooter(dialog=self, margin=(0, 10, 0, 0)))

    def _select_all(self):
        """Select all items in all trees."""
        for tree in self._trees:
            tree.tree_widget.selectAll()

    def _select_by_type(self, data_type: str):
        """Select only items of a specific type (data or models)."""
        for tree, label in zip(self._trees, self._tree_labels):
            if label == data_type:
                tree.tree_widget.selectAll()
            else:
                tree.tree_widget.clearSelection()

    def get_selected_objects(self):
        selected = []
        for tree in self._trees:
            selected.extend(
                item.metadata["object_id"] for item in tree.selected_items()
            )
        return selected


class VisibilityAnimation(BaseAnimation):
    """Visibility fade animation"""

    def _init_parameters(self) -> None:
        self.parameters.clear()
        self.parameters.update(
            {"start_opacity": 1.0, "target_opacity": 0.0, "easing": "instant"}
        )
        self._original_opacities = {}

    def get_settings(self) -> List[Dict[str, Any]]:
        return [
            {
                "label": "start_opacity",
                "type": "float",
                "min": 0.0,
                "max": 1.0,
                "default": self.parameters.get("start_opacity", 1.0),
                "description": "Start opacity (0.0 for invisible, 1.0 for fully visible)",
            },
            {
                "label": "target_opacity",
                "type": "float",
                "min": 0.0,
                "max": 1.0,
                "default": self.parameters.get("target_opacity", 1.0),
                "description": "Target opacity (0.0 for invisible, 1.0 for fully visible)",
            },
            {
                "label": "easing",
                "type": "select",
                "options": ["linear", "ease-in", "ease-out", "ease-in-out", "instant"],
                "default": self.parameters.get("easing", "instant"),
                "description": "Animation style (instant for immediate change)",
            },
            {
                "label": "Objects",
                "type": "button",
                "text": "Select",
                "callback": self._open_object_selection_dialog,
                "description": "Choose which objects should be affected by the animation",
            },
        ]

    def _open_object_selection_dialog(self, _checked=None):
        """Open dialog to select which objects should be affected"""
        try:
            current_selection = self.parameters.get("selected_objects", [])
            dialog = ActorSelectionDialog(
                cdata=self.cdata, current_selection=current_selection
            )
            if dialog.exec():
                selected_objects = dialog.get_selected_objects()
                self.update_parameters(selected_objects=selected_objects)

        except Exception as e:
            print(f"Error opening object selection dialog: {e}")

        return False

    def _get_actors(self):
        actors = []
        object_ids = self.parameters.get("selected_objects", [])
        try:
            all_objects = {}
            for name, obj in self.cdata.format_datalist("data"):
                all_objects[id(obj)] = obj
            for name, obj in self.cdata.format_datalist("models"):
                all_objects[id(obj)] = obj

            actors = [all_objects[x].actor for x in object_ids if x in all_objects]

        except Exception as e:
            print(f"Error getting actors for object IDs: {e}")

        return actors

    def reset(self) -> None:
        """Restore actors to the opacity they had before this animation touched them."""
        for actor in self._get_actors():
            original = self._original_opacities.get(id(actor))
            if original is not None:
                actor.GetProperty().SetOpacity(original)

    def update(self, global_frame: int) -> None:
        """Forwards-fill: apply during and after the range, skip before.

        Before the range the actor keeps whatever opacity was set by reset()
        or an earlier animation.  After the range the end state persists.
        """
        if not self.enabled:
            return
        local_frame = global_frame - self.global_start_frame + self.start_frame
        if local_frame < self.start_frame:
            return
        local_frame = min(self.stop_frame, local_frame)
        self._update(local_frame)

    def _update(self, frame: int) -> None:
        progress = self._get_progress(frame)
        if progress is None:
            return

        start_opacity = self.parameters["start_opacity"]
        target_opacity = self.parameters["target_opacity"]
        current_opacity = start_opacity + (target_opacity - start_opacity) * progress

        for actor in self._get_actors():
            if id(actor) not in self._original_opacities:
                self._original_opacities[id(actor)] = actor.GetProperty().GetOpacity()
            actor.GetProperty().SetOpacity(current_opacity)


class WaypointAnimation(BaseAnimation):
    """Animation that smoothly moves the camera between captured waypoints.

    Each waypoint stores the full camera state (position, focal point, view-up)
    so that the camera orientation is interpolated correctly along the path.
    """

    def _init_parameters(self) -> None:
        self.parameters.clear()
        self.parameters.update(
            {
                "waypoints": [],
                "spline_order": 3,
                "easing": "linear",
            }
        )
        self._path_actors = []
        self._curve = None
        self._positions = None
        self._focal_points = None
        self._view_ups = None

    def update_parameters(self, **kwargs):
        if "add_waypoint" in kwargs:
            self._capture_waypoint()
            kwargs.pop("add_waypoint")

        if "remove_waypoint" in kwargs:
            self._remove_last_waypoint()
            kwargs.pop("remove_waypoint")

        if "clear_waypoints" in kwargs:
            self._clear_waypoints()
            kwargs.pop("clear_waypoints")

        if "waypoints" in kwargs:
            self.parameters["waypoints"] = kwargs.pop("waypoints")
            self._init_spline()

        if "spline_order" in kwargs:
            self.parameters["spline_order"] = int(kwargs.pop("spline_order"))
            self._init_spline()
            self._update_path_preview()

        if "easing" in kwargs:
            self.parameters["easing"] = kwargs.pop("easing")

        return super().update_parameters(**kwargs)

    def _capture_waypoint(self):
        """Capture the current camera state as a new waypoint."""
        camera = self._get_rendering_context()
        waypoint = {
            "position": list(camera.GetPosition()),
            "focal_point": list(camera.GetFocalPoint()),
            "view_up": list(camera.GetViewUp()),
        }
        self.parameters["waypoints"].append(waypoint)
        self._init_spline()
        self._update_path_preview()

    def _remove_last_waypoint(self):
        """Remove the most recently added waypoint."""
        waypoints = self.parameters["waypoints"]
        if waypoints:
            waypoints.pop()
            self._init_spline()
            self._update_path_preview()

    def _clear_waypoints(self):
        """Remove all waypoints."""
        self.parameters["waypoints"].clear()
        self._init_spline()
        self.cleanup_preview()

    def _init_spline(self):
        """Initialize the spline curve from waypoints."""
        import numpy as np
        from mosaic.parametrization import SplineCurve

        waypoints = self.parameters.get("waypoints", [])
        if len(waypoints) < 2:
            self._curve = None
            self._positions = None
            self._focal_points = None
            self._view_ups = None
            return

        positions = np.array([w["position"] for w in waypoints])
        focal_points = np.array([w["focal_point"] for w in waypoints])
        view_ups = np.array([w["view_up"] for w in waypoints])

        order = int(self.parameters.get("spline_order", 3))
        order = min(order, len(waypoints) - 1)

        self._curve = SplineCurve(positions=positions, order=order)

        n_samples = max(self.stop_frame - self.start_frame + 1, 2)
        self._positions = self._curve.sample(n_samples)

        # Linear interpolation for focal points and view-up vectors
        t = np.linspace(0, 1, n_samples)
        t_wp = np.linspace(0, 1, len(waypoints))
        self._focal_points = np.column_stack(
            [np.interp(t, t_wp, focal_points[:, i]) for i in range(3)]
        )
        self._view_ups = np.column_stack(
            [np.interp(t, t_wp, view_ups[:, i]) for i in range(3)]
        )

    def _update_path_preview(self):
        """Visualize the camera path in the 3D viewport.

        Draws from the same sampled positions used by the animation so the
        preview exactly matches what plays back.
        """
        import vtk

        _, renderer = self._get_rendering_context(return_renderer=True)

        # Remove old preview actors
        self.cleanup_preview()

        waypoints = self.parameters.get("waypoints", [])

        # Show point markers even for a single waypoint
        if len(waypoints) < 2 or self._positions is None:
            for wp in waypoints:
                actor = self._create_waypoint_marker(wp["position"])
                renderer.AddActor(actor)
                self._path_actors.append(actor)
            self.vtk_widget.GetRenderWindow().Render()
            return

        # Build a polyline from the sampled animation positions
        vtk_points = vtk.vtkPoints()
        for pos in self._positions:
            vtk_points.InsertNextPoint(pos)

        lines = vtk.vtkCellArray()
        n_pts = len(self._positions)
        lines.InsertNextCell(n_pts)
        for i in range(n_pts):
            lines.InsertCellPoint(i)

        poly_data = vtk.vtkPolyData()
        poly_data.SetPoints(vtk_points)
        poly_data.SetLines(lines)

        tube_filter = vtk.vtkTubeFilter()
        tube_filter.SetInputData(poly_data)
        tube_filter.SetRadius(1.0)
        tube_filter.SetNumberOfSides(8)
        tube_filter.SetVaryRadiusToVaryRadiusOff()
        tube_filter.Update()

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(tube_filter.GetOutputPort())
        mapper.SetResolveCoincidentTopologyToPolygonOffset()
        mapper.SetScalarVisibility(False)

        path_actor = vtk.vtkActor()
        path_actor.SetMapper(mapper)
        # Pink #ec4899 → RGB
        path_actor.GetProperty().SetColor(0.925, 0.286, 0.6)
        path_actor.GetProperty().SetOpacity(0.7)
        renderer.AddActor(path_actor)
        self._path_actors.append(path_actor)

        # Add sphere markers at each waypoint
        for wp in waypoints:
            actor = self._create_waypoint_marker(wp["position"])
            renderer.AddActor(actor)
            self._path_actors.append(actor)

        self.vtk_widget.GetRenderWindow().Render()

    def _create_waypoint_marker(self, position):
        """Create a small sphere actor at the given position."""
        import vtk

        point_data = vtk.vtkPoints()
        point_data.InsertNextPoint(position)

        vertices = vtk.vtkCellArray()
        vertices.InsertNextCell(1)
        vertices.InsertCellPoint(0)

        poly_data = vtk.vtkPolyData()
        poly_data.SetPoints(point_data)
        poly_data.SetVerts(vertices)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(poly_data)
        mapper.SetResolveCoincidentTopologyToPolygonOffset()

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        # Pink #ec4899
        actor.GetProperty().SetColor(0.925, 0.286, 0.6)
        actor.GetProperty().SetPointSize(12)
        actor.GetProperty().SetRenderPointsAsSpheres(True)

        return actor

    def cleanup_preview(self):
        """Remove all preview actors from the renderer."""
        try:
            _, renderer = self._get_rendering_context(return_renderer=True)
            for actor in self._path_actors:
                renderer.RemoveActor(actor)
            self._path_actors.clear()
            self.vtk_widget.GetRenderWindow().Render()
        except Exception:
            self._path_actors.clear()

    def get_settings(self) -> List[Dict[str, Any]]:
        n = len(self.parameters.get("waypoints", []))
        count_text = f"{n} waypoint{'s' if n != 1 else ''} defined"
        return [
            {
                "label": "Capture Current View",
                "type": "button",
                "text": "Capture",
                "callback": lambda _=None: self.update_parameters(add_waypoint=True),
                "description": "Add the current camera position as a waypoint",
            },
            {
                "label": "Remove Last",
                "type": "button",
                "text": "Remove",
                "callback": lambda _=None: self.update_parameters(remove_waypoint=True),
                "description": "Remove the last waypoint",
            },
            {
                "label": "Clear All",
                "type": "button",
                "text": "Clear",
                "callback": lambda _=None: self.update_parameters(clear_waypoints=True),
                "description": "Remove all waypoints",
            },
            {
                "label": "waypoints_count",
                "type": "label",
                "text": count_text,
                "description": "Number of waypoints defined",
            },
            {
                "label": "spline_order",
                "type": "select",
                "options": ["1", "2", "3"],
                "default": str(self.parameters.get("spline_order", 3)),
                "description": "Spline interpolation order (1=linear, 2=quadratic, 3=cubic)",
            },
            {
                "label": "easing",
                "type": "select",
                "options": ["linear", "ease-in", "ease-out", "ease-in-out"],
                "default": self.parameters.get("easing", "linear"),
                "description": "Easing function for playback speed",
            },
        ]

    def _update(self, frame: int) -> None:
        import numpy as np

        if len(self.parameters.get("waypoints", [])) < 2:
            return

        # (Re)sample if needed
        n_samples = self.stop_frame - self.start_frame + 1
        if self._positions is None or len(self._positions) != n_samples:
            self._init_spline()
            if self._positions is None:
                return

        progress = self._get_progress(frame)
        if progress is None:
            return

        # Map eased progress to sample index
        idx = progress * (n_samples - 1)
        idx_low = int(idx)
        idx_high = min(idx_low + 1, n_samples - 1)
        frac = idx - idx_low

        # Linearly interpolate between adjacent samples
        new_pos = (1 - frac) * self._positions[idx_low] + frac * self._positions[
            idx_high
        ]
        new_focal = (1 - frac) * self._focal_points[
            idx_low
        ] + frac * self._focal_points[idx_high]
        new_up = (1 - frac) * self._view_ups[idx_low] + frac * self._view_ups[idx_high]

        # Normalize view-up vector
        up_len = np.linalg.norm(new_up)
        if up_len > 0:
            new_up = new_up / up_len

        camera, renderer = self._get_rendering_context(return_renderer=True)
        camera.SetPosition(*new_pos)
        camera.SetFocalPoint(*new_focal)
        camera.SetViewUp(*new_up)
        renderer.ResetCameraClippingRange()


class ZoomAnimation(BaseAnimation):
    """Camera zoom animation"""

    def _init_parameters(self) -> None:
        self.parameters.clear()
        self.parameters.update(
            {
                "zoom_factor": 2.0,
                "easing": "ease-in-out",
            }
        )
        self._initial_distance = None

    def get_settings(self) -> List[Dict[str, Any]]:
        return [
            {
                "label": "zoom_factor",
                "type": "float",
                "min": 0.1,
                "max": 10.0,
                "default": self.parameters.get("zoom_factor", 2.0),
                "description": "Target zoom factor (>1 zooms in, <1 zooms out)",
            },
            {
                "label": "easing",
                "type": "select",
                "options": ["linear", "ease-in", "ease-out", "ease-in-out"],
                "default": self.parameters.get("easing", "ease-in-out"),
                "description": "Easing function for smooth zoom",
            },
        ]

    def _update(self, frame: int) -> None:
        camera, renderer = self._get_rendering_context(return_renderer=True)

        if frame == self.start_frame or self._initial_distance is None:
            self._initial_distance = camera.GetDistance()
            self._initial_position = camera.GetPosition()
            self._initial_focal = camera.GetFocalPoint()

        progress = self._get_progress(frame)
        if progress is None:
            return

        zoom_factor = self.parameters["zoom_factor"]
        target_distance = self._initial_distance / zoom_factor

        current_distance = (
            self._initial_distance
            + (target_distance - self._initial_distance) * progress
        )

        # Move camera along the view direction
        direction = [
            self._initial_position[i] - self._initial_focal[i] for i in range(3)
        ]
        length = sum(d * d for d in direction) ** 0.5
        if length > 0:
            direction = [d / length for d in direction]

        new_position = [
            self._initial_focal[i] + direction[i] * current_distance for i in range(3)
        ]

        camera.SetPosition(*new_position)
        renderer.ResetCameraClippingRange()


class AnimationType(Enum):
    TRAJECTORY = {
        "name": "Trajectory",
        "color": Colors.CATEGORY["trajectory"],
        "class": TrajectoryAnimation,
    }
    CAMERA = {
        "name": "Orbit",
        "color": Colors.CATEGORY["camera"],
        "class": CameraAnimation,
    }
    ZOOM = {"name": "Zoom", "color": Colors.CATEGORY["zoom"], "class": ZoomAnimation}
    SLICE = {
        "name": "Volume",
        "color": Colors.CATEGORY["volume"],
        "class": VolumeAnimation,
    }
    VISIBILITY = {
        "name": "Visibility",
        "color": Colors.CATEGORY["visibility"],
        "class": VisibilityAnimation,
    }
    WAYPOINT = {
        "name": "Waypoint",
        "color": Colors.CATEGORY["waypoint"],
        "class": WaypointAnimation,
    }
