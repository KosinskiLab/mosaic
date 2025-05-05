from enum import Enum
from abc import ABC, abstractmethod
from typing import List, Tuple, Callable, Any


class DynamicOption:
    """Represents a dynamic option that gets populated at runtime"""

    def __init__(
        self, getter: Callable[[Any], List[tuple]], dependencies: List[str] = None
    ):
        self.getter = getter
        self.dependencies = dependencies or []

    def __call__(self, context: Any) -> List[tuple]:
        """Get options from the context"""
        return self.getter(context)


class AnimationType(Enum):
    TRAJECTORY = {
        "name": "Trajectory",
        "color": "#3b82f6",
        "parameters": {},
        "settings": [
            {
                "label": "trajectory",
                "type": "select",
                "options": DynamicOption(
                    lambda ctx: [(t.name, t) for t in ctx.trajectories]
                ),
                "default": [],
                "description": "Select trajectories to animate.",
            },
        ],
    }
    CAMERA = {
        "name": "Camera Orbit",
        "parameters": {"axis": "y", "degrees": 360, "center": [0, 0, 0]},
        "color": "#10b981",
        "settings": [
            {
                "label": "axis",
                "type": "select",
                "options": ["x", "y", "z"],
                "default": "y",
                "description": "Axis to rotate over.",
            },
            {
                "label": "degrees",
                "type": "float",
                "min": -180,
                "default": 40,
                "description": "Angle to rotate over axis.",
            },
        ],
    }
    SLICE = {
        "name": "Volume",
        "parameters": {"axis": "z", "direction": "forward", "volumeId": None},
        "color": "#f59e0b",
        "settings": [
            {
                "label": "axis",
                "type": "select",
                "options": ["x", "y", "z"],
                "default": "y",
                "description": "Axis to rotate over.",
            },
            {
                "label": "direction",
                "type": "select",
                "options": ["forward", "backward"],
                "description": "Direction to slice through.",
            },
        ],
    }
    VISIBILITY = {
        "name": "Visibility Fade",
        "parameters": {"targets": [], "fadeIn": True, "easing": "ease-in-out"},
        "color": "#8b5cf6",
        "settings": [
            {
                "label": "fadeIn",
                "type": "select",
                "options": ["in", "out"],
                "default": "in",
                "description": "Fade in mode.",
            },
            {
                "label": "easing",
                "type": "select",
                "options": ["linear", "ease-in", "ease-out", "ease-in-out"],
                "description": "Easing method",
            },
        ],
    }


class BaseAnimation(ABC):
    """Base class for all animation types"""

    def __init__(self, vtk_widget, duration: int):
        self.vtk_widget = vtk_widget

    @abstractmethod
    def update(self, frame: int) -> None:
        """Update the animation state for the given frame"""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset the animation to its initial state"""
        pass

    def get_settings_widget(self):
        """Return a QWidget with animation-specific settings"""
        return None


class TrajectoryAnimation(BaseAnimation):
    """Animation for molecular trajectories"""

    def __init__(self, vtk_widget, geometries, duration: int):
        super().__init__(vtk_widget, duration)
        self.geometries = geometries

    def update(self, frame: int) -> None:
        for geometry in self.geometries:
            geometry.display_frame(frame)
        self.state.frame = frame

    def reset(self) -> None:
        self.state.frame = 0
        self.update(0)


class RotationAnimation(BaseAnimation):
    """360-degree rotation animation"""

    def __init__(
        self, vtk_widget, duration: int, axis: str = "y", degrees: float = 360
    ):
        super().__init__(vtk_widget, duration)
        self.axis = axis
        self.degrees = degrees
        self.camera = (
            vtk_widget.GetRenderWindow()
            .GetRenderers()
            .GetFirstRenderer()
            .GetActiveCamera()
        )
        self.initial_position = self.camera.GetPosition()

    def update(self, frame: int) -> None:
        angle = (frame / self.duration) * self.degrees
        self.camera.OrbitY(angle)
        self.state.frame = frame

    def reset(self) -> None:
        self.state.frame = 0
        self.camera.SetPosition(self.initial_position)


class FlyThroughAnimation(BaseAnimation):
    """Camera fly-through with actor visibility control"""

    def __init__(
        self, vtk_widget, duration: int, waypoints: List[Tuple[float, float, float]]
    ):
        super().__init__(vtk_widget, duration)
        self.waypoints = waypoints
        self.renderer = vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer()
        self.camera = self.renderer.GetActiveCamera()
        self.actors = self.renderer.GetActors()
        self.initial_camera_pos = self.camera.GetPosition()

    def update(self, frame: int) -> None:
        t = frame / self.duration
        # Interpolate between waypoints
        current_pos = self._interpolate_position(t)
        self.camera.SetPosition(current_pos)

        # Control actor visibility based on camera height
        show_actors = current_pos[2] < self.initial_camera_pos[2]
        self._set_actors_visibility(show_actors)

        self.state.frame = frame

    def _interpolate_position(self, t: float) -> Tuple[float, float, float]:
        if len(self.waypoints) < 2:
            return self.initial_camera_pos

        # Simple linear interpolation between waypoints
        segment_count = len(self.waypoints) - 1
        segment = int(t * segment_count)
        segment_t = (t * segment_count) % 1.0

        start = self.waypoints[segment]
        end = self.waypoints[segment + 1]

        return tuple(start[i] + (end[i] - start[i]) * segment_t for i in range(3))

    def _set_actors_visibility(self, visible: bool) -> None:
        self.actors.InitTraversal()
        actor = self.actors.GetNextItem()
        while actor:
            actor.SetVisibility(visible)
            actor = self.actors.GetNextItem()

    def reset(self) -> None:
        self.state.frame = 0
        self.camera.SetPosition(self.initial_camera_pos)
        self._set_actors_visibility(True)
