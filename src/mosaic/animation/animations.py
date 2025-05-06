from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Dict, Any

from vtk import vtkTransform


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
        self.frames = 100

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

    def _init_parameters(self) -> Dict[str, Any]:
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
            self.frames = self._trajectory.frames
            self.start_frame, self.stop_frame = 0, self.frames

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
        selected_indices = self.cdata.models._get_selected_indices()
        if selected_indices:
            self.cdata.models.set_selection(selected_indices)


class VolumeAnimation(BaseAnimation):
    """Volume slicing animation"""

    def _init_parameters(self) -> Dict[str, Any]:
        self.parameters.clear()
        self.parameters["direction"] = "forward"
        self.update_parameters(
            axis=self.volume_viewer.primary.orientation_selector.currentText().lower()
        )

    def update_parameters(self, **kwargs):
        new_axis = kwargs.get("axis")
        if new_axis and new_axis != self.parameters.get("axis"):
            _mapping = {"x": 0, "y": 1, "z": 2}
            shape = self.volume_viewer.primary.get_dimensions()
            self.frames = shape[_mapping.get(new_axis, 0)]
            self.start_frame, self.stop_frame = 0, self.frames

        return super().update_parameters(**kwargs)

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
                "default": self.parameters.get("axis", "x"),
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
        ]

    def _update(self, frame: int) -> None:
        self.volume_viewer.primary.slice_slider.setValue(frame)


class CameraAnimation(BaseAnimation):
    """Camera orbit animation"""

    def _init_parameters(self) -> None:
        self.parameters.clear()
        self.parameters.update(
            {
                "axis": "y",
                "degrees": 180,
            }
        )
        self._initial_position = None
        self.frames = 2 << 29

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
                "default": "forward",
                "description": "Direction to rotate in.",
            },
        ]

    def _update(self, frame: int) -> None:
        camera, renderer = self._get_rendering_context(return_renderer=True)
        delta_angle = 0.5 * self.parameters["degrees"] / self.stop_frame

        if frame == self.start_frame:
            delta_angle *= frame

        current_pos = camera.GetPosition()
        current_focal = camera.GetFocalPoint()
        current_view_up = camera.GetViewUp()

        transform = vtkTransform()
        transform.Identity()
        transform.Translate(*current_focal)

        if self.parameters["axis"] == "x":
            transform.RotateWXYZ(delta_angle, 1, 0, 0)
        elif self.parameters["axis"] == "y":
            transform.RotateWXYZ(delta_angle, 0, 1, 0)
        elif self.parameters["axis"] == "z":
            transform.RotateWXYZ(delta_angle, 0, 0, 1)

        transform.Translate(-current_focal[0], -current_focal[1], -current_focal[2])

        new_pos = transform.TransformPoint(current_pos)
        new_view_up = transform.TransformVector(current_view_up)

        camera.SetPosition(*new_pos)
        camera.SetViewUp(*new_view_up)
        renderer.ResetCameraClippingRange()


class VisibilityAnimation(BaseAnimation):
    """Visibility fade animation"""

    def _init_parameters(self) -> Dict[str, Any]:
        self.parameters.clear()

        self.parameters.update(
            {"start_opacity": 1.0, "target_opacity": 0.0, "easing": "instant"}
        )

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
        ]

    def _update(self, frame: int) -> None:
        _, renderer = self._get_rendering_context(return_renderer=True)

        diff = self.parameters["start_opacity"] - self.parameters["target_opacity"]
        progress = frame * diff / self.stop_frame

        if self.parameters["easing"] == "ease-in":
            progress_adj = progress * progress
        elif self.parameters["easing"] == "ease-out":
            progress_adj = 1.0 - (1.0 - progress) * (1.0 - progress)
        elif self.parameters["easing"] == "ease-in-out":
            if progress < 0.5:
                progress_adj = 0.5 * (
                    1.0 - (1.0 - 2.0 * progress) * (1.0 - 2.0 * progress)
                )
            else:
                progress_adj = 0.5 + 0.5 * (
                    (2.0 * progress - 1.0) * (2.0 * progress - 1.0)
                )
        else:
            progress_adj = progress

        progress_adj = self.parameters["start_opacity"] - progress
        if self.parameters["easing"] == "instant":
            progress_adj = self.parameters["target_opacity"]

        actors = renderer.GetActors()
        actors.InitTraversal()
        actor = actors.GetNextItem()
        while actor:
            actor.GetProperty().SetOpacity(progress_adj)
            actor = actors.GetNextItem()


class WaypointAnimation(BaseAnimation):
    """Animation that smoothly moves between defined waypoints"""

    def _init_parameters(self) -> Dict[str, Any]:
        self.parameters.clear()
        self.parameters.update(
            {"waypoints": [], "spline_order": 3, "target_position": [0.0, 0.0, 0.0]}
        )
        self.frames = 100

        camera = self._get_rendering_context()
        self.parameters["waypoints"].append(camera.GetPosition())

    def update_parameters(self, **kwargs):
        if "target_position" in kwargs:
            target = kwargs["target_position"].split(",")
            try:
                target = [float(x) for x in target]
            except ValueError:
                return None
            if len(target) == 3:
                self.parameters["waypoints"].append(target)
                self._init_spline()

        if "spline_order" in kwargs:
            self.parameters["spline_order"] = kwargs["spline_order"]
            self._init_spline()

        return super().update_parameters(**kwargs)

    def _init_spline(self):
        """Initialize the spline curve from waypoints"""
        from mosaic.parametrization import SplineCurve

        waypoints = self.parameters.get("waypoints", [])
        if len(waypoints) < 2:
            print("Need at least two waypoints")
            return None

        self._curve = SplineCurve(
            positions=waypoints, order=int(self.parameters.get("spline_order", 3))
        )
        self._positions = self._curve.sample(self.stop_frame)

        # Save initial state
        camera, renderer = self._get_rendering_context(return_renderer=True)
        self._initial_position = camera.GetPosition()
        self._initial_focal = camera.GetFocalPoint()
        self._initial_view_up = camera.GetViewUp()

    def get_settings(self) -> List[Dict[str, Any]]:
        current_position = self._get_rendering_context().GetPosition()
        current_position = ",".join([str(round(x, 2)) for x in current_position])
        settings = [
            {
                "label": "target_position",
                "type": "text",
                "default": current_position,
                "description": "Target position to move to (format: x, y, z)",
            },
            {
                "label": "spline_order",
                "type": "select",
                "options": ["1", "2", "3"],
                "default": str(self.parameters.get("spline_order", 3)),
                "description": "Order of spline interpolation (1=linear, 2=quadratic, 3=cubic)",
            },
        ]
        return settings

    def _update(self, frame: int) -> None:
        if not hasattr(self, "_curve"):
            self._init_spline()
            # Spline creation failed for some reason
            if not hasattr(self, "_curve"):
                return None

        if len(self._positions) != self.duration:
            self._positions = self._curve.sample(self.duration)

        camera, renderer = self._get_rendering_context(return_renderer=True)

        new_pos = self._positions[frame]
        displacement = [
            new_pos[0] - self._initial_position[0],
            new_pos[1] - self._initial_position[1],
            new_pos[2] - self._initial_position[2],
        ]

        new_focal = [
            self._initial_focal[0] + displacement[0],
            self._initial_focal[1] + displacement[1],
            self._initial_focal[2] + displacement[2],
        ]
        camera.SetPosition(*new_pos)
        camera.SetFocalPoint(*new_focal)

        renderer.ResetCameraClippingRange()


class AnimationType(Enum):
    TRAJECTORY = {
        "name": "Trajectory",
        "color": "#3b82f6",
        "class": TrajectoryAnimation,
    }
    CAMERA = {"name": "Camera Orbit", "color": "#10b981", "class": CameraAnimation}
    SLICE = {"name": "Volume", "color": "#f59e0b", "class": VolumeAnimation}
    VISIBILITY = {
        "name": "Visibility Fade",
        "color": "#8b5cf6",
        "class": VisibilityAnimation,
    }
    WAYPOINT = {"name": "Waypoint Path", "color": "#ec4899", "class": WaypointAnimation}
