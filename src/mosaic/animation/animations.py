from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Dict, Any

from vtk import vtkTransform
from qtpy.QtWidgets import QDialog

from ..stylesheets import Colors, QPushButton_style


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
            self.cdata.models.set_selection_by_uuids(uuids)


class VolumeAnimation(BaseAnimation):
    """Volume slicing animation"""

    def _init_parameters(self) -> None:
        self.parameters.clear()
        self.parameters["direction"] = "forward"
        self.parameters["projection"] = "Off"
        try:
            self.update_parameters(
                axis=self.volume_viewer.primary.orientation_selector.currentText().lower()
            )
        except Exception:
            pass

    def update_parameters(self, **kwargs):
        new_axis = kwargs.get("axis")
        if new_axis and new_axis != self.parameters.get("axis"):
            _mapping = {"x": 0, "y": 1, "z": 2}
            shape = self.volume_viewer.primary.get_dimensions()
            self.start_frame = 0
            self.stop_frame = shape[_mapping.get(new_axis, 0)]
            kwargs["axis"] = new_axis.upper()

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
        if self.parameters["direction"] == "backward":
            frame = self.stop_frame - frame

        viewer = self.volume_viewer.primary

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

        # Calculate progress through the animation
        duration = self.stop_frame - self.start_frame
        if duration <= 0:
            return

        progress = (frame - self.start_frame) / duration
        progress = max(0.0, min(1.0, progress))

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
        self.setStyleSheet(QPushButton_style)

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
                item.setSelected(id(obj) in current_selection)
                uuid_to_item[uuid] = item

            tree.apply_state(state, uuid_to_item)
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

    def _update(self, frame: int) -> None:
        # Calculate progress through the animation
        duration = self.stop_frame - self.start_frame
        if duration <= 0:
            return

        progress = (frame - self.start_frame) / duration
        progress = max(0.0, min(1.0, progress))

        # Apply easing
        eased_progress = self._ease(progress)

        # Interpolate opacity
        start_opacity = self.parameters["start_opacity"]
        target_opacity = self.parameters["target_opacity"]
        current_opacity = (
            start_opacity + (target_opacity - start_opacity) * eased_progress
        )

        for actor in self._get_actors():
            actor.GetProperty().SetOpacity(current_opacity)


class WaypointAnimation(BaseAnimation):
    """Animation that smoothly moves between defined waypoints"""

    def _init_parameters(self) -> None:
        self.parameters.clear()
        self.parameters.update(
            {"waypoints": [], "spline_order": 3, "target_position": [0.0, 0.0, 0.0]}
        )
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
            if not hasattr(self, "_curve"):
                return None

        duration = self.stop_frame - self.start_frame
        if duration <= 0:
            return

        # Resample if duration changed
        if len(self._positions) != duration + 1:
            self._positions = self._curve.sample(duration + 1)

        # Calculate local frame index
        local_frame = frame - self.start_frame
        local_frame = max(0, min(len(self._positions) - 1, local_frame))

        camera, renderer = self._get_rendering_context(return_renderer=True)

        new_pos = self._positions[local_frame]
        displacement = [new_pos[i] - self._initial_position[i] for i in range(3)]

        new_focal = [self._initial_focal[i] + displacement[i] for i in range(3)]
        camera.SetPosition(*new_pos)
        camera.SetFocalPoint(*new_focal)

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

        duration = self.stop_frame - self.start_frame
        if duration <= 0:
            return

        progress = (frame - self.start_frame) / duration
        progress = max(0.0, min(1.0, progress))
        eased_progress = self._ease(progress)

        zoom_factor = self.parameters["zoom_factor"]
        target_distance = self._initial_distance / zoom_factor

        current_distance = (
            self._initial_distance
            + (target_distance - self._initial_distance) * eased_progress
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
