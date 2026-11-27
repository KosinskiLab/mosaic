from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

from qtpy.QtWidgets import QDialog
from vtk import vtkTransform

from ..stylesheets import Colors, Typography


class BaseAnimation(ABC):
    """Base class for all animations"""

    #: Whether playback speed is meaningful, i.e. duration derives from a
    #: reference length divided by rate. Span-like animations disable this.
    has_rate = True

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
        self.rate = 1.0
        self._base_duration = None
        self._forward_fill = False

        self.parameters = {}
        self._init_parameters()

    @abstractmethod
    def _init_parameters(self) -> None:
        """Initialize animation-specific parameters"""
        pass

    @abstractmethod
    def get_settings(self) -> list[dict[str, Any]]:
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
        if "data_start" in kwargs or "data_stop" in kwargs:
            data_start = kwargs.get("data_start", self.parameters.get("data_start", 0))
            data_stop = kwargs.get(
                "data_stop",
                self.parameters.get("data_stop", self.stop_frame),
            )
            self._base_duration = max(1, data_stop - data_start)
            self.stop_frame = max(1, int(self._base_duration / self.rate))
        self.parameters.update(**kwargs)

    def _reference_duration(self) -> float:
        if self._base_duration is None:
            self._base_duration = self.duration * self.rate
        return self._base_duration

    def set_duration(self, frames: int) -> None:
        """Set the animation length in frames.

        For animations with a rate, the rate is adjusted so that the
        reference duration plays back over the requested number of frames.
        """
        frames = max(1, int(frames))
        if self.has_rate:
            self.rate = self._reference_duration() / frames
        self.stop_frame = self.start_frame + frames
        return None

    def set_rate(self, rate: float) -> None:
        """Set the playback rate, deriving the duration from the reference length."""
        if rate <= 0 or not self.has_rate:
            return None
        frames = max(1, int(self._reference_duration() / rate))
        self.rate = rate
        self.stop_frame = self.start_frame + frames
        return None

    def reset(self) -> None:
        """Reset any externally-modified state before a new frame is applied.

        Called by the composer before each frame so that animations which
        modify shared state (e.g. actor opacity) can restore defaults first.
        Override in subclasses that need this; the base implementation is a no-op.
        """
        pass

    def commit(self) -> None:
        """Apply state accumulated across all tracks after a frame's updates.

        Called by the composer once every track has been updated, so that
        animations sharing targets can combine their contributions and write
        to VTK once. The base implementation is a no-op.
        """
        return None

    def update(self, global_frame: int) -> None:
        """Update animation state for the given global frame"""
        if not self.enabled:
            return None

        local_frame = global_frame - self.global_start_frame + self.start_frame
        if local_frame < self.start_frame:
            return None

        if self._forward_fill:
            local_frame = min(self.stop_frame, local_frame)
            self._update(local_frame)
        else:
            if local_frame > self.stop_frame:
                return None
            if (local_frame - self.start_frame) % self.stride == 0:
                self._update(local_frame)

    def _get_rendering_context(self, return_renderer: bool = False):
        """Return the current camera instance (cached)."""
        if not hasattr(self, "_cached_renderer") or self._cached_renderer is None:
            self._cached_renderer = (
                self.vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer()
            )
        camera = self._cached_renderer.GetActiveCamera()
        if return_renderer:
            return camera, self._cached_renderer
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
    """Animation for molecular trajectories.

    Before its first track starts, a trajectory shows that track's first
    frame; after a track ends, it holds the last one. When several tracks
    animate the same trajectory, the most recently started track drives it.
    """

    # Keyed by trajectory: (rank, local frame, track) of the driving track.
    _claims: dict[int, tuple[tuple[bool, int], int, "TrajectoryAnimation"]] = {}

    def _available_trajectories(self):
        """Return (name, uuid) pairs for all trajectory objects."""
        from mosaic.geometry import GeometryTrajectory

        models = self.cdata.format_datalist("models")

        trajectories = []
        for name, obj in models:
            if isinstance(obj, GeometryTrajectory):
                trajectories.append((name, obj.uuid))
        return trajectories

    def _get_trajectory(self, uuid: str):
        """Resolve a trajectory object by its UUID."""
        models = self.cdata.format_datalist("models")
        return next((x for _, x in models if x.uuid == uuid), None)

    def _init_parameters(self) -> None:
        trajectories = self._available_trajectories()
        if (default := self.parameters.get("trajectory")) is None:
            try:
                _name, default = trajectories[0]
            except IndexError:
                default = None
            self.update_parameters(trajectory=default)

    def update_parameters(self, **kwargs):
        new_trajectory = kwargs.get("trajectory")
        if new_trajectory and new_trajectory != self.parameters.get("trajectory"):
            self._trajectory = self._get_trajectory(new_trajectory)
            if self._trajectory is None:
                return super().update_parameters(**kwargs)
            n_frames = self._trajectory.frames
            kwargs.setdefault("data_start", 0)
            kwargs.setdefault("data_stop", n_frames)
            data_range = kwargs.get("data_stop", n_frames) - kwargs.get("data_start", 0)
            self._base_duration = data_range
            self.stop_frame = data_range

        return super().update_parameters(**kwargs)

    def get_settings(self) -> list[dict[str, Any]]:
        n_frames = getattr(self, "_trajectory", None)
        n_frames = n_frames.frames if n_frames is not None else 0
        available = self._available_trajectories()
        names = [name for name, _ in available]
        uuids = [uuid for _, uuid in available]
        return [
            {
                "label": "trajectory",
                "type": "select",
                "options": names,
                "option_values": uuids,
                "default": self.parameters.get("trajectory"),
                "description": "Select trajectories to animate.",
            },
            {
                "label": "data_start",
                "type": "number",
                "min": 0,
                "max": n_frames,
                "default": self.parameters.get("data_start", 0),
                "description": "First trajectory frame to animate.",
            },
            {
                "label": "data_stop",
                "type": "number",
                "min": 0,
                "max": n_frames,
                "default": self.parameters.get("data_stop", n_frames),
                "description": "Last trajectory frame to animate.",
            },
        ]

    def reset(self) -> None:
        """Withdraw this track's claim on its trajectory; applied on commit."""
        for key, claim in list(self._claims.items()):
            if claim[2] is self:
                del self._claims[key]
        return None

    def update(self, global_frame: int) -> None:
        """Bid for the trajectory, also before the track starts."""
        if not self.enabled or getattr(self, "_trajectory", None) is None:
            return None

        local_frame = global_frame - self.global_start_frame + self.start_frame
        started = local_frame >= self.start_frame
        local_frame = max(self.start_frame, min(self.stop_frame, local_frame))
        local_frame -= (local_frame - self.start_frame) % self.stride

        # Started tracks beat pending ones; among started tracks the latest
        # start wins, among pending ones the earliest. Ties go to later tracks.
        start = self.global_start_frame
        rank = (started, start if started else -start)

        key = id(self._trajectory)
        claim = self._claims.get(key)
        if claim is None or rank >= claim[0]:
            self._claims[key] = (rank, local_frame, self)
        return None

    def commit(self) -> None:
        trajectory = getattr(self, "_trajectory", None)
        if trajectory is None:
            return None

        claim = self._claims.get(id(trajectory))
        if claim is not None and claim[2] is self:
            self._update(claim[1])
        return None

    def _update(self, frame: int) -> None:
        if getattr(self, "_trajectory", None) is None:
            return None

        progress = self._get_progress(frame)
        if progress is None:
            return

        data_start = self.parameters.get("data_start", 0)
        data_stop = self.parameters.get("data_stop", self._trajectory.frames)
        data_frame = int(data_start + progress * (data_stop - data_start))
        data_frame = max(data_start, min(data_stop - 1, data_frame))

        if self._trajectory.current_frame == data_frame:
            return None

        self._trajectory.display_frame(data_frame)
        # display_frame drops the highlight color. Restore it via the container,
        # since the interactor would render mid-frame, before later tracks
        # have updated, and the scene would flicker between frames.
        models = self.cdata.models
        uuids = models._get_selected_uuids()
        if self._trajectory.uuid in uuids:
            models.container.highlight(uuids)


class VolumeAnimation(BaseAnimation):
    """Volume slicing animation.

    Volume tracks hold their last slice after they end, so several can be
    active at once. Each frame, the most recently started track drives the
    viewer; the others yield instead of rewriting slice and orientation.
    """

    # Keyed by viewer: (global start frame, local frame, track) of the
    # track that drives the viewer this frame.
    _claims: dict[int, tuple[int, int, "VolumeAnimation"]] = {}

    # Keyed by viewer: slice visibility before any volume track touched it.
    _original_visibility: dict[int, bool] = {}

    def _init_parameters(self) -> None:
        self._forward_fill = True
        self.parameters.clear()
        self.parameters["direction"] = "forward"
        self.parameters["projection"] = "Off"
        self.parameters["axis"] = "Z"
        self.parameters["hide"] = False
        try:
            self.update_parameters(
                axis=self.volume_viewer.primary.orientation_selector.currentText().lower()
            )
        except Exception:
            pass

    @property
    def _viewer_key(self) -> int:
        return id(self.volume_viewer.primary)

    def reset(self) -> None:
        """Withdraw this track's claim on the viewer; applied on commit."""
        claim = self._claims.get(self._viewer_key)
        if claim is not None and claim[2] is self:
            del self._claims[self._viewer_key]
        return None

    def commit(self) -> None:
        """Apply the winning track's state, or restore the viewer if none."""
        key = self._viewer_key
        claim = self._claims.get(key)
        if claim is None:
            original = self._original_visibility.pop(key, None)
            if original is not None:
                self.volume_viewer.primary.slice.SetVisibility(original)
            return None

        if claim[2] is self:
            self._apply(claim[1])
        return None

    def _get_axis_size(self, axis=None):
        _mapping = {"x": 0, "y": 1, "z": 2}
        if axis is None:
            axis = self.parameters.get("axis", "Z")
        try:
            shape = self.volume_viewer.primary.get_dimensions()
        except AttributeError:
            return 0
        return shape[_mapping.get(axis.lower(), 0)]

    def get_settings(self) -> list[dict[str, Any]]:
        projection = [
            self.volume_viewer.primary.project_selector.itemText(i)
            for i in range(self.volume_viewer.primary.project_selector.count())
        ]
        n_slices = self._get_axis_size()
        return [
            {
                "label": "axis",
                "type": "select",
                "options": ["x", "y", "z"],
                "default": "z",
                "description": "Axis to slice over.",
            },
            {
                "label": "data_start",
                "type": "number",
                "min": 0,
                "max": n_slices,
                "default": self.parameters.get("data_start", 0),
                "description": "First slice index.",
            },
            {
                "label": "data_stop",
                "type": "number",
                "min": 0,
                "max": n_slices,
                "default": self.parameters.get("data_stop", n_slices),
                "description": "Last slice index.",
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
            n_slices = self._get_axis_size(new_axis)
            kwargs.setdefault("data_start", 0)
            kwargs.setdefault("data_stop", n_slices)
            data_range = kwargs.get("data_stop", n_slices) - kwargs.get("data_start", 0)
            self._base_duration = data_range
            self.stop_frame = data_range
            kwargs["axis"] = new_axis.upper()

        super().update_parameters(**kwargs)

    def _update(self, frame: int) -> None:
        key = self._viewer_key
        claim = self._claims.get(key)
        if claim is None or self.global_start_frame >= claim[0]:
            self._claims[key] = (self.global_start_frame, frame, self)
        return None

    def _apply(self, frame: int) -> None:
        progress = self._get_progress(frame)
        if progress is None:
            return None

        if self.parameters["direction"] == "backward":
            progress = 1.0 - progress

        data_start = self.parameters.get("data_start", 0)
        data_stop = self.parameters.get("data_stop", self.stop_frame)
        data_frame = int(data_start + progress * (data_stop - data_start))
        data_frame = max(data_start, min(data_stop - 1, data_frame))

        viewer = self.volume_viewer.primary

        # Uses the VTK actor directly; set_visibility would render mid-frame
        original = self._original_visibility.setdefault(
            self._viewer_key, viewer.is_visible
        )
        viewer.slice.SetVisibility(original and not self.parameters.get("hide", False))

        # Suppress intermediate renders
        viewer._rendering_suspended = True
        try:
            current_orientation = viewer.get_orientation()
            if current_orientation != self.parameters["axis"]:
                viewer.orientation_selector.setCurrentText(self.parameters["axis"])

            current_state = self.volume_viewer.primary.get_projection()
            if current_state != self.parameters["projection"]:
                viewer.project_selector.setCurrentText(self.parameters["projection"])

            viewer.set_slice(data_frame)
        finally:
            viewer._rendering_suspended = False


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
        self._last_progress = 0.0
        self.stop_frame = 180
        self._transform = vtkTransform()

    def get_settings(self) -> list[dict[str, Any]]:
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

        progress = self._get_progress(frame)
        if progress is None:
            return

        total_degrees = self.parameters["degrees"]
        if self.parameters.get("direction") == "reverse":
            total_degrees = -total_degrees

        delta_angle = total_degrees * (progress - self._last_progress)
        self._last_progress = progress

        if abs(delta_angle) < 1e-10:
            return

        # Compute rotation axis from the current camera orientation
        pos = list(camera.GetPosition())
        focal = list(camera.GetFocalPoint())
        view_up = list(camera.GetViewUp())

        view_dir = [focal[i] - pos[i] for i in range(3)]
        vd_len = sum(d * d for d in view_dir) ** 0.5
        if vd_len > 0:
            view_dir = [d / vd_len for d in view_dir]

        right = [
            view_dir[1] * view_up[2] - view_dir[2] * view_up[1],
            view_dir[2] * view_up[0] - view_dir[0] * view_up[2],
            view_dir[0] * view_up[1] - view_dir[1] * view_up[0],
        ]
        r_len = sum(d * d for d in right) ** 0.5
        if r_len > 0:
            right = [d / r_len for d in right]

        axis = self.parameters["axis"]
        if axis == "x":
            rot_axis = right
        elif axis == "y":
            rot_axis = view_up
        else:  # z
            rot_axis = view_dir

        self._transform.Identity()
        self._transform.Translate(*focal)
        self._transform.RotateWXYZ(delta_angle, *rot_axis)
        self._transform.Translate(-focal[0], -focal[1], -focal[2])

        new_pos = self._transform.TransformPoint(pos)
        new_view_up = self._transform.TransformVector(view_up)

        camera.SetPosition(*new_pos)
        camera.SetViewUp(*new_view_up)
        renderer.ResetCameraClippingRange()


class ActorSelectionDialog(QDialog):
    """Pick the objects a visibility track affects.

    Lists clusters and models with the same rows, grouping and section
    headers as the object browser sidebar.
    """

    def __init__(self, cdata, current_selection=None, parent=None):
        from qtpy.QtCore import Qt
        from qtpy.QtWidgets import (
            QAbstractItemView,
            QHBoxLayout,
            QLabel,
            QToolButton,
            QVBoxLayout,
        )

        from mosaic.widgets import DialogFooter, SearchWidget
        from mosaic.widgets.container_list import (
            ContainerTreeWidget,
            StyledTreeWidgetItem,
        )

        super().__init__(parent)
        self.setWindowTitle("Select Objects")
        self.setModal(True)
        self.resize(360, 520)

        current_selection = set(current_selection or [])
        self._trees = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(8)

        search = SearchWidget(placeholder="Filter objects")
        search.searchTextChanged.connect(self._filter)
        layout.addWidget(search)

        quick = QHBoxLayout()
        quick.setContentsMargins(0, 0, 0, 0)
        quick.setSpacing(2)
        for text, data_types in (
            ("All", ("data", "models")),
            ("None", ()),
            ("Clusters", ("data",)),
            ("Models", ("models",)),
        ):
            button = QToolButton()
            button.setText(text)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.clicked.connect(lambda _, x=data_types: self._select(x))
            quick.addWidget(button)
        quick.addStretch(1)

        self._count = QLabel()
        self._count.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: {Typography.LABEL}px;"
        )
        quick.addWidget(self._count)
        layout.addLayout(quick)

        for title, data_type, interactor in (
            ("Clusters", "data", cdata.data),
            ("Models", "models", cdata.models),
        ):
            objects = {obj.uuid: obj for _, obj in cdata.format_datalist(data_type)}
            if not objects:
                continue

            tree = ContainerTreeWidget()
            tree.tree_widget.setSelectionMode(
                QAbstractItemView.SelectionMode.MultiSelection
            )
            tree.tree_widget.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)

            uuid_to_item = {}
            for uuid, obj in objects.items():
                item = StyledTreeWidgetItem(geometry=obj, visible=obj.visible)
                item.metadata["object_id"] = id(obj)
                if not obj.visible:
                    item.setToolTip(0, "Hidden. Stays hidden during playback.")
                uuid_to_item[uuid] = item

            # Mirror the sidebar's order and groups
            state = interactor.data_list.to_state()
            placed = state.get_all_uuids()
            tree.apply_state(state, uuid_to_item)
            for uuid, item in uuid_to_item.items():
                if uuid not in placed:
                    tree.tree_widget.addTopLevelItem(item)
            tree.tree_widget.expandAll()

            for uuid, obj in objects.items():
                uuid_to_item[uuid].setSelected(id(obj) in current_selection)
            tree.tree_widget.itemSelectionChanged.connect(self._update_count)

            header = QLabel(title)
            header.setStyleSheet(
                f"""
                font-size: {Typography.LABEL}px; font-weight: 600;
                color: {Colors.TEXT_MUTED};
                padding: 8px 0px 4px 0px;
                background: transparent;
                """
            )
            section = QVBoxLayout()
            section.setContentsMargins(0, 0, 0, 0)
            section.setSpacing(2)
            section.addWidget(header)
            section.addWidget(tree, 1)
            layout.addLayout(section, 1)
            self._trees[data_type] = tree

        layout.addWidget(
            DialogFooter(
                info_text="Hidden objects stay hidden.",
                dialog=self,
                margin=(0, 8, 0, 0),
            )
        )
        self._update_count()

    def _items(self, data_types=None):
        """Yield object rows, skipping group headers."""
        from mosaic.widgets.container_list import StyledTreeWidgetItem

        for data_type, tree in self._trees.items():
            if data_types is not None and data_type not in data_types:
                continue
            for item, _parent, _index in tree.traverse():
                if isinstance(item, StyledTreeWidgetItem):
                    yield item

    def _select(self, data_types):
        """Select every listed object of the given types, deselect the rest."""
        for data_type, tree in self._trees.items():
            tree.tree_widget.blockSignals(True)
            for item in self._items((data_type,)):
                item.setSelected(data_type in data_types and not item.isHidden())
            tree.tree_widget.blockSignals(False)
        self._update_count()

    def _filter(self, text):
        from mosaic.widgets.container_list import GroupTreeWidgetItem

        text = text.strip().lower()
        for item in self._items():
            item.setHidden(bool(text) and text not in item.text(0).lower())

        for tree in self._trees.values():
            for item, _parent, _index in tree.traverse():
                if not isinstance(item, GroupTreeWidgetItem):
                    continue
                children = [item.child(i) for i in range(item.childCount())]
                item.setHidden(bool(text) and all(c.isHidden() for c in children))

    def _update_count(self):
        items = list(self._items())
        selected = sum(item.isSelected() for item in items)
        self._count.setText(f"{selected} of {len(items)} selected")

    def get_selected_objects(self):
        return [
            item.metadata["object_id"] for item in self._items() if item.isSelected()
        ]


@dataclass
class _FadeState:
    """Original appearance of an actor and the track currently fading it."""

    geometry: Any
    actor: Any
    opacity: float
    #: (global start frame, opacity factor, track) of the driving track.
    claim: tuple[int, float, Any] | None = None
    hidden: bool = False


class VisibilityAnimation(BaseAnimation):
    """Hide or fade objects for the span of the track.

    Outside the track objects keep their own appearance. Inside, their
    opacity is scaled by a factor that moves from ``start_opacity`` to
    ``target_opacity`` over the track, or jumps to the target with instant
    easing. Objects faded to zero are switched off rather than drawn fully
    transparent, which keeps them out of depth peeling.
    """

    has_rate = False

    # Shared across tracks so overlapping visibility tracks resolve to one
    # winner per actor, and the captured opacity is never a value another
    # track wrote earlier.
    _ledger: dict[int, _FadeState] = {}

    def _init_parameters(self) -> None:
        self.parameters.clear()
        self.parameters.update(
            {
                "start_opacity": 1.0,
                "target_opacity": 0.0,
                "easing": "instant",
            }
        )
        self._cached_geometries = None

    def get_settings(self) -> list[dict[str, Any]]:
        return [
            {
                "label": "start_opacity",
                "type": "float",
                "min": 0.0,
                "max": 1.0,
                "default": self.parameters.get("start_opacity", 1.0),
                "description": "Opacity at the start of the track, relative to "
                "each object's own opacity (0 hides objects).",
            },
            {
                "label": "target_opacity",
                "type": "float",
                "min": 0.0,
                "max": 1.0,
                "default": self.parameters.get("target_opacity", 0.0),
                "description": "Opacity at the end of the track, relative to "
                "each object's own opacity (0 hides objects).",
            },
            {
                "label": "easing",
                "type": "select",
                "options": ["instant", "linear", "ease-in", "ease-out", "ease-in-out"],
                "default": self.parameters.get("easing", "instant"),
                "description": "Instant holds the target for the whole track; "
                "other easings fade from start to target across the track.",
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
                self.update_parameters(selected_objects=dialog.get_selected_objects())
        except Exception:
            pass

        return False

    def update_parameters(self, **kwargs) -> None:
        if "selected_objects" in kwargs:
            self._cached_geometries = None
        return super().update_parameters(**kwargs)

    def _get_geometries(self):
        if self._cached_geometries is not None:
            return self._cached_geometries

        object_ids = set(self.parameters.get("selected_objects", []))
        try:
            self._cached_geometries = [
                obj
                for data_type in ("data", "models")
                for _name, obj in self.cdata.format_datalist(data_type)
                if id(obj) in object_ids
            ]
        except Exception:
            return []
        return self._cached_geometries

    def _fade_factor(self, frame: int):
        """Opacity multiplier at the given local frame, or None outside the span."""
        duration = self.duration
        elapsed = frame - self.start_frame
        if not 0 <= elapsed < duration:
            return None

        progress = 1.0
        if self.parameters.get("easing", "instant") != "instant" and duration > 1:
            progress = self._ease(elapsed / (duration - 1))

        start = float(self.parameters.get("start_opacity", 1.0))
        target = float(self.parameters.get("target_opacity", 0.0))
        return start + (target - start) * progress

    def reset(self) -> None:
        """Withdraw this track's claims; actors are restored on commit."""
        for state in self._ledger.values():
            if state.claim is not None and state.claim[2] is self:
                state.claim = None
        return None

    def _update(self, frame: int) -> None:
        if (factor := self._fade_factor(frame)) is None:
            return None

        start = self.global_start_frame
        for geometry in self._get_geometries():
            if not geometry.visible:
                continue
            actor = geometry.actor
            state = self._ledger.get(id(actor))
            if state is None:
                state = _FadeState(geometry, actor, actor.GetProperty().GetOpacity())
                self._ledger[id(actor)] = state

            # Most recently started track wins; ties go to the later track
            if state.claim is None or start >= state.claim[0]:
                state.claim = (start, factor, self)
        return None

    def commit(self) -> None:
        """Write the winning fade of each actor, restoring unclaimed ones.

        VTK setters skip unchanged values, so actors whose fade is constant
        between frames are not marked modified.
        """
        for key in list(self._ledger):
            state = self._ledger[key]
            factor = 1.0 if state.claim is None else state.claim[1]

            if factor <= 0:
                state.actor.GetProperty().SetOpacity(state.opacity)
                state.actor.SetVisibility(False)
                state.hidden = True
                continue

            state.actor.GetProperty().SetOpacity(state.opacity * factor)
            if state.hidden:
                state.actor.SetVisibility(state.geometry.visible)
                state.hidden = False

            if state.claim is None:
                del self._ledger[key]
        return None


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

    def _remove_last_waypoint(self):
        """Remove the most recently added waypoint."""
        waypoints = self.parameters["waypoints"]
        if waypoints:
            waypoints.pop()
            self._init_spline()

    def _clear_waypoints(self):
        """Remove all waypoints."""
        self.parameters["waypoints"].clear()
        self._init_spline()

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

    def get_settings(self) -> list[dict[str, Any]]:
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

    def get_settings(self) -> list[dict[str, Any]]:
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
