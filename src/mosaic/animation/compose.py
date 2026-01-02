"""
Animation composer dialog for creating timeline-based animations.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import json
from dataclasses import dataclass
from typing import Dict, List, Any

import imageio
from qtpy.QtCore import Qt, QTimer, QSize
from qtpy.QtGui import QKeySequence, QShortcut
from qtpy.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QPushButton,
    QToolButton,
    QSpinBox,
    QGroupBox,
    QScrollArea,
    QFrame,
    QFileDialog,
    QMessageBox,
    QApplication,
    QSizePolicy,
    QCheckBox,
)
import qtawesome as qta

from .timeline import TimelineWidget
from .animations import AnimationType
from .settings import AnimationSettings, ExportDialog
from ._utils import FrameWriter, capture_frame

from ..__version__ import __version__
from ..stylesheets import (
    QMessageBox_style,
    QLineEdit_style,
    QSpinBox_style,
    QDoubleSpinBox_style,
    QComboBox_style,
    QCheckBox_style,
    QSlider_style,
    QGroupBox_style,
    QListWidget_style,
    QPushButton_style,
    QScrollArea_style,
    Colors,
)


@dataclass
class Track:
    id: str
    animation: object
    color: str


class AnimationComposerDialog(QDialog):
    """Dialog for composing complex, timeline-based animations."""

    FORMAT_SETTINGS = {
        "MP4": {"ext": ".mp4", "video": True},
        "AVI": {"ext": ".avi", "video": True},
        "PNG Sequence": {"ext": ".png", "video": False},
    }

    def __init__(self, vtk_widget, volume_viewer=None, cdata=None, parent=None):
        super().__init__(parent)
        self.tracks: List[Track] = []
        self.selected_track = None
        self.current_frame = 0

        self.is_playing = False
        self.is_looping = False
        self.playback_fps = 30
        self.timer = QTimer()
        self.timer.timeout.connect(self._advance_frame)

        self.cdata = cdata
        self.vtk_widget = vtk_widget
        self.volume_viewer = volume_viewer

        self._setup_ui()
        self._setup_shortcuts()

        self.setStyleSheet(
            QMessageBox_style
            + QLineEdit_style
            + QSpinBox_style
            + QDoubleSpinBox_style
            + QComboBox_style
            + QCheckBox_style
            + QSlider_style
            + QGroupBox_style
            + QListWidget_style
            + QPushButton_style
            + QScrollArea_style
        )

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Icon toolbar for project actions
        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(4)

        for icon, tooltip, callback in [
            ("ph.folder-open", "Load project", self.load_project),
            ("ph.floppy-disk", "Save project", self.save_project),
            ("ph.trash", "Clear all tracks", self.clear_all_tracks),
            ("ph.export", "Export animation", self.export_animation),
        ]:
            btn = QToolButton()
            btn.setIcon(qta.icon(icon, color=Colors.ICON))
            btn.setToolTip(tooltip)
            btn.setIconSize(QSize(20, 20))
            btn.clicked.connect(callback)
            toolbar_layout.addWidget(btn)

        toolbar_layout.addStretch()

        # Loop checkbox
        self.loop_checkbox = QCheckBox("Loop")
        self.loop_checkbox.setToolTip("Loop playback (L)")
        self.loop_checkbox.stateChanged.connect(self._on_loop_changed)
        toolbar_layout.addWidget(self.loop_checkbox)

        main_layout.addWidget(toolbar)

        # Playback controls
        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(4)

        back_btn = QToolButton()
        back_btn.setIcon(qta.icon("ph.skip-back"))
        back_btn.setToolTip("Go to start (Home)")
        back_btn.clicked.connect(lambda: self.set_current_frame(0))

        self.play_btn = QToolButton()
        self.play_btn.setIcon(qta.icon("ph.play"))
        self.play_btn.setToolTip("Play/Pause (Space)")
        self.play_btn.clicked.connect(self.toggle_play)

        forward_btn = QToolButton()
        forward_btn.setIcon(qta.icon("ph.skip-forward"))
        forward_btn.setToolTip("Go to end (End)")
        forward_btn.clicked.connect(self._go_to_end)

        controls_layout.addWidget(back_btn)
        controls_layout.addWidget(self.play_btn)
        controls_layout.addWidget(forward_btn)

        self.frame_spin = QSpinBox()
        self.frame_spin.setRange(0, 2 << 29)
        self.frame_spin.valueChanged.connect(self.set_current_frame)
        controls_layout.addWidget(self.frame_spin, 1)

        main_layout.addWidget(controls)

        # Timeline
        self.timeline = TimelineWidget()
        self.timeline.content.trackSelected.connect(self._on_track_selected)
        self.timeline.frameMoved.connect(self.set_current_frame)
        self.timeline.trackMoved.connect(self._on_track_moved)
        self.timeline.trackRemoved.connect(self.delete_track)
        self.timeline.setMinimumHeight(120)
        self.timeline.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        main_layout.addWidget(self.timeline, 1)

        # Presets group
        presets_group = QGroupBox("Presets")
        presets_layout = QVBoxLayout(presets_group)
        presets_layout.setContentsMargins(8, 12, 8, 8)
        presets_layout.setSpacing(6)

        presets_row = QHBoxLayout()
        presets_row.setSpacing(6)
        for name, tooltip, preset_type in [
            ("Trajectory", "Animate through trajectory frames", "trajectory"),
            ("Volume", "Animate through volume slices", "slices"),
            (
                "Flythrough",
                "Slice through volume, reveal actors, then slice back",
                "reveal_flythrough",
            ),
        ]:
            btn = QPushButton(name)
            btn.setToolTip(tooltip)
            btn.clicked.connect(lambda _, p=preset_type: self._load_preset(p))
            presets_row.addWidget(btn)
        presets_layout.addLayout(presets_row)
        main_layout.addWidget(presets_group)

        # Add Animation group (2 rows x 3 cols for compactness)
        anims_group = QGroupBox("Add Animation")
        anims_layout = QGridLayout(anims_group)
        anims_layout.setContentsMargins(8, 12, 8, 8)
        anims_layout.setSpacing(6)

        anim_types = list(AnimationType)
        cols = 3
        for i, anim_type in enumerate(anim_types):
            btn = QPushButton(anim_type.value["name"])
            btn.setToolTip(anim_type.value.get("description", ""))
            btn.clicked.connect(lambda _, t=anim_type: self.add_animation(t))
            anims_layout.addWidget(btn, i // cols, i % cols)
        main_layout.addWidget(anims_group)

        # Scrollable settings area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_content.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(8)

        self.properties_panel = AnimationSettings()
        self.properties_panel.animationChanged.connect(self._on_animation_changed)
        scroll_layout.addWidget(self.properties_panel)
        scroll_layout.addStretch()

        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area, 1)

        self.setMinimumWidth(280)
        self.resize(300, 700)

    def _load_preset(self, preset_type: str):
        """Load a preset animation configuration."""
        self.tracks.clear()
        self.timeline.set_tracks(self.tracks)

        if preset_type == "trajectory":
            self._load_trajectory_preset()
        elif preset_type == "slices":
            self._load_slices_preset()
        elif preset_type == "reveal_flythrough":
            self._load_reveal_flythrough_preset()

        if self.tracks:
            self._on_track_selected(self.tracks[0].id)

    def _load_trajectory_preset(self):
        """Load preset for trajectory animation."""
        from mosaic.geometry import GeometryTrajectory

        trajectories = [
            x for x in self.cdata._models.data if isinstance(x, GeometryTrajectory)
        ]

        if not trajectories:
            QMessageBox.warning(
                self,
                "No Trajectories",
                "No trajectory data found. Load a trajectory first.",
            )
            return

        self.add_animation(AnimationType.TRAJECTORY)

    def _load_slices_preset(self):
        """Load preset for volume slice animation."""
        if self.volume_viewer is None:
            QMessageBox.warning(
                self, "No Volume", "No volume viewer available for slice animation."
            )
            return

        volume = getattr(self.volume_viewer.primary, "volume", None)
        if volume is None:
            QMessageBox.warning(
                self, "No Volume", "No volume loaded. Load a volume first."
            )
            return

        self.add_animation(AnimationType.SLICE)

    def _load_reveal_flythrough_preset(self):
        """Load preset for reveal flythrough animation.

        This creates a sequence that:
        1. Slices through the volume (forward) with all actors hidden
        2. Reveals all actors at the midpoint
        3. Slices back through the volume (backward)
        """
        if self.volume_viewer is None:
            QMessageBox.warning(
                self, "No Volume", "No volume viewer available for reveal flythrough."
            )
            return

        volume = getattr(self.volume_viewer.primary, "volume", None)
        if volume is None:
            QMessageBox.warning(
                self, "No Volume", "No volume loaded. Load a volume first."
            )
            return

        # Get all actor object IDs
        all_objects = []
        for _, obj in self.cdata.format_datalist("data"):
            all_objects.append(id(obj))
        for _, obj in self.cdata.format_datalist("models"):
            all_objects.append(id(obj))

        # 1. Hide all actors at the start (instant opacity to 0)
        hide_anim = self.add_animation(AnimationType.VISIBILITY)
        if hide_anim:
            hide_anim.name = "Hide Actors"
            hide_anim.update_parameters(
                start_opacity=1.0,
                target_opacity=0.0,
                easing="instant",
                selected_objects=all_objects,
            )
            hide_anim.start_frame = 0
            hide_anim.stop_frame = 1

        # 2. Volume slice forward
        forward_slice = self.add_animation(AnimationType.SLICE)
        if forward_slice:
            forward_slice.name = "Slice Forward"
            forward_slice.update_parameters(direction="forward")

        # 3. Reveal all actors at midpoint (instant opacity to 1)
        reveal_anim = self.add_animation(AnimationType.VISIBILITY)
        if reveal_anim:
            reveal_anim.name = "Reveal Actors"
            reveal_anim.update_parameters(
                start_opacity=0.0,
                target_opacity=1.0,
                easing="instant",
                selected_objects=all_objects,
            )
            reveal_anim.start_frame = 0
            reveal_anim.stop_frame = 1

        # 4. Volume slice backward
        backward_slice = self.add_animation(AnimationType.SLICE)
        if backward_slice:
            backward_slice.name = "Slice Backward"
            backward_slice.update_parameters(direction="backward")

        # Update timeline
        self.timeline.set_tracks(self.tracks)

    def add_animation(self, anim_type: AnimationType):
        """Add a new animation track."""
        animation_class = anim_type.value["class"]

        try:
            animation = animation_class(
                cdata=self.cdata,
                vtk_widget=self.vtk_widget,
                volume_viewer=self.volume_viewer,
                global_start_frame=self._get_next_start_frame(),
                enabled=True,
                name=f"{anim_type.value['name']} {len(self.tracks) + 1}",
            )
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to create animation: {e}")
            return None

        track = Track(
            id=str(id(animation)),
            animation=animation,
            color=anim_type.value["color"],
        )

        self.tracks.append(track)
        self.timeline.set_tracks(self.tracks)

        return animation

    def _get_next_start_frame(self) -> int:
        """Calculate the next available start frame for a new track."""
        if not self.tracks:
            return 0
        return max(
            t.animation.global_start_frame + t.animation.duration for t in self.tracks
        )

    def _get_track(self, track_id: str):
        return next((t for t in self.tracks if t.id == track_id), None)

    def delete_track(self, track_id: str):
        """Remove a track from the timeline."""
        self.tracks = [t for t in self.tracks if t.id != track_id]
        if self.selected_track == track_id:
            self.selected_track = None
        self.timeline.set_tracks(self.tracks)

    def _on_track_selected(self, track_id: str):
        if (track := self._get_track(track_id)) is None:
            return

        self.selected_track = track_id
        self.properties_panel.set_animation(track.animation)

    def _on_track_moved(self, track_id: str, new_frame: int):
        if (track := self._get_track(track_id)) is None:
            return

        track.animation.global_start_frame = new_frame
        self.properties_panel.global_start_spin.setValue(new_frame)
        self.timeline.update()

    def _on_animation_changed(self, changes: Dict[str, Any]):
        self.timeline.update()

    def _get_total_frames(self) -> int:
        """Get the total number of frames across all tracks."""
        if not self.tracks:
            return 0
        return max(
            t.animation.global_start_frame + t.animation.duration for t in self.tracks
        )

    def set_current_frame(self, frame: int):
        """Set the current playback frame and update all animations."""
        if not self.tracks:
            return

        total_frames = self._get_total_frames()
        self.current_frame = max(0, min(total_frames, frame))

        # Prevent recursive updates from spinbox
        self.frame_spin.blockSignals(True)
        self.frame_spin.setValue(self.current_frame)
        self.frame_spin.blockSignals(False)

        self.timeline.set_current_frame(self.current_frame)

        # Stop playback at end (unless looping, which is handled in _advance_frame)
        if (
            self.current_frame >= total_frames
            and self.is_playing
            and not self.is_looping
        ):
            self.toggle_play()

        for track in self.tracks:
            track.animation.update(self.current_frame)

        self.vtk_widget.GetRenderWindow().Render()

    def _go_to_end(self):
        """Jump to the last frame."""
        self.set_current_frame(self._get_total_frames())

    def toggle_play(self):
        """Toggle playback state."""
        self.is_playing = not self.is_playing

        if self.is_playing:
            self.play_btn.setIcon(qta.icon("ph.pause"))
            self.timer.start(1000 // self.playback_fps)
        else:
            self.play_btn.setIcon(qta.icon("ph.play"))
            self.timer.stop()

    def _advance_frame(self):
        if not self.is_playing:
            return

        next_frame = self.current_frame + 1
        total_frames = self._get_total_frames()

        if next_frame >= total_frames:
            if self.is_looping:
                next_frame = 0
            else:
                self.set_current_frame(total_frames)
                self.toggle_play()
                return

        self.set_current_frame(next_frame)

    def _on_loop_changed(self, state):
        """Handle loop checkbox state change."""
        self.is_looping = state == Qt.CheckState.Checked.value

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        # Spacebar for play/pause
        play_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        play_shortcut.activated.connect(self.toggle_play)

        # L for loop toggle
        loop_shortcut = QShortcut(QKeySequence(Qt.Key.Key_L), self)
        loop_shortcut.activated.connect(self._toggle_loop)

        # Home for go to start
        home_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Home), self)
        home_shortcut.activated.connect(lambda: self.set_current_frame(0))

        # End for go to end
        end_shortcut = QShortcut(QKeySequence(Qt.Key.Key_End), self)
        end_shortcut.activated.connect(self._go_to_end)

        # Left/Right arrow for frame stepping
        left_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        left_shortcut.activated.connect(
            lambda: self.set_current_frame(self.current_frame - 1)
        )

        right_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        right_shortcut.activated.connect(
            lambda: self.set_current_frame(self.current_frame + 1)
        )

    def _toggle_loop(self):
        """Toggle loop playback."""
        self.loop_checkbox.setChecked(not self.loop_checkbox.isChecked())

    def clear_all_tracks(self):
        """Clear all animation tracks."""
        if not self.tracks:
            return

        reply = QMessageBox.question(
            self,
            "Clear All Tracks",
            "Are you sure you want to remove all animation tracks?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.tracks.clear()
            self.selected_track = None
            self.timeline.set_tracks(self.tracks)

    def _capture_frame(self, transparent_bg: bool = False, magnification: int = 1):
        """Capture the current frame from the VTK renderer."""
        render_window = self.vtk_widget.GetRenderWindow()
        return capture_frame(
            render_window, transparent_bg=transparent_bg, magnification=magnification
        )

    def export_animation(self):
        """Export the animation with current settings."""
        if not self.tracks:
            QMessageBox.warning(
                self, "No Animation", "Add at least one animation track before export."
            )
            return

        # Get current render window dimensions
        render_window = self.vtk_widget.GetRenderWindow()
        current_size = render_window.GetSize()

        # Show export dialog
        total_frames = self._get_total_frames()
        dialog = ExportDialog(
            total_frames=total_frames,
            current_width=current_size[0],
            current_height=current_size[1],
            parent=self,
        )
        if not dialog.exec():
            return

        settings = dialog.get_settings()
        format_name = settings["format"]
        format_settings = self.FORMAT_SETTINGS.get(format_name, {})
        ext = format_settings.get("ext", ".mp4")
        is_video = format_settings.get("video", True)

        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Animation", "", f"Animation (*{ext})"
        )

        if not filename:
            return

        if not filename.endswith(ext):
            filename += ext

        start_frame = settings["start_frame"]
        end_frame = settings["end_frame"]
        stride = settings["stride"]
        fps = settings["fps"]
        quality = settings["quality"]
        target_width = settings["width"]
        target_height = settings["height"]
        magnification = settings["magnification"]
        multisamples = settings["multisamples"]

        if start_frame >= end_frame:
            QMessageBox.warning(
                self, "Invalid Range", "Start frame must be less than end frame."
            )
            return

        frames = list(range(start_frame, end_frame + 1, stride))

        # Store original state
        original_frame = self.current_frame
        original_size = render_window.GetSize()

        # Use target dimensions from dialog, ensure even for video encoding
        width = target_width
        height = target_height
        if is_video:
            height += height % 2
            width += width % 2

        # Setup writer
        if is_video:
            quality_val = max(min(quality / 10.0, 10), 1)
            writer = imageio.get_writer(
                filename, mode="I", fps=fps, quality=quality_val, macro_block_size=None
            )
        else:
            writer = FrameWriter(filename)

        try:
            from mosaic.dialogs import ProgressDialog

            render_window.SetOffScreenRendering(1)

            # Store original multisamples and apply export settings
            original_multisamples = render_window.GetMultiSamples()
            render_window.SetMultiSamples(multisamples)

            # Set render window to target dimensions
            # capture_frame will handle magnification (render larger, then downscale)
            render_window.SetSize(width, height)
            render_window.Render()

            with ProgressDialog(frames, title="Exporting Animation") as progress:
                for frame_idx in progress:
                    self.set_current_frame(frame_idx)
                    render_window.Render()

                    frame = self._capture_frame(
                        transparent_bg=not is_video, magnification=magnification
                    )
                    writer.append_data(frame)
                    QApplication.processEvents()

            writer.close()
            render_window.SetMultiSamples(original_multisamples)

            QMessageBox.information(
                self, "Export Complete", f"Animation saved to:\n{filename}"
            )

        except Exception as e:
            QMessageBox.warning(self, "Export Error", f"Failed to export: {e}")

        finally:
            render_window.SetOffScreenRendering(0)
            render_window.SetSize(*original_size)
            render_window.Render()
            self.set_current_frame(original_frame)

    def save_project(self):
        """Save the animation project to a JSON file."""
        if not self.tracks:
            QMessageBox.warning(
                self, "No Animation", "Add at least one animation track before saving."
            )
            return

        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Animation Project", "", "Animation Project (*.manim)"
        )

        if not filename:
            return

        if not filename.endswith(".manim"):
            filename += ".manim"

        project_data = {
            "version": __version__,
            "tracks": [],
        }

        for track in self.tracks:
            anim = track.animation
            anim_type = None
            for at in AnimationType:
                if isinstance(anim, at.value["class"]):
                    anim_type = at.name
                    break

            track_data = {
                "type": anim_type,
                "name": anim.name,
                "enabled": anim.enabled,
                "global_start_frame": anim.global_start_frame,
                "start_frame": anim.start_frame,
                "stop_frame": anim.stop_frame,
                "stride": anim.stride,
                "parameters": self._serialize_parameters(anim.parameters),
            }
            project_data["tracks"].append(track_data)

        try:
            with open(filename, "w") as f:
                json.dump(project_data, f, indent=2)

            QMessageBox.information(
                self, "Project Saved", f"Animation project saved to:\n{filename}"
            )
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Failed to save project: {e}")

    def _serialize_parameters(self, params: Dict) -> Dict:
        """Convert parameters to JSON-serializable format."""
        serialized = {}
        for key, value in params.items():
            if isinstance(value, (list, tuple)):
                serialized[key] = [
                    float(v) if isinstance(v, (int, float)) else str(v) for v in value
                ]
            elif isinstance(value, (int, float, str, bool)):
                serialized[key] = value
            else:
                serialized[key] = str(value)
        return serialized

    def load_project(self):
        """Load an animation project from a JSON file."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load Animation Project", "", "Animation Project (*.manim)"
        )

        if not filename:
            return

        try:
            with open(filename, "r") as f:
                project_data = json.load(f)
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Failed to read project file: {e}")
            return

        self.tracks.clear()
        self.timeline.set_tracks(self.tracks)
        for track_data in project_data.get("tracks", []):
            anim_type_name = track_data.get("type")
            if not anim_type_name:
                continue

            try:
                anim_type = AnimationType[anim_type_name]
            except KeyError:
                QMessageBox.warning(
                    self,
                    "Unknown Animation",
                    f"Unknown animation type: {anim_type_name}",
                )
                continue

            animation_class = anim_type.value["class"]

            try:
                animation = animation_class(
                    cdata=self.cdata,
                    vtk_widget=self.vtk_widget,
                    volume_viewer=self.volume_viewer,
                    global_start_frame=track_data.get("global_start_frame", 0),
                    enabled=track_data.get("enabled", True),
                    name=track_data.get("name", anim_type.value["name"]),
                )

                animation.start_frame = track_data.get("start_frame", 0)
                animation.stop_frame = track_data.get("stop_frame", 100)
                animation.stride = track_data.get("stride", 1)

                # Restore parameters
                for key, value in track_data.get("parameters", {}).items():
                    animation.update_parameters(**{key: value})

                track = Track(
                    id=str(id(animation)),
                    animation=animation,
                    color=anim_type.value["color"],
                )
                self.tracks.append(track)

            except Exception as e:
                QMessageBox.warning(
                    self, "Load Error", f"Failed to create animation: {e}"
                )
                continue

        self.timeline.set_tracks(self.tracks)

        if self.tracks:
            self._on_track_selected(self.tracks[0].id)

        QMessageBox.information(
            self,
            "Project Loaded",
            f"Loaded {len(self.tracks)} animation track(s) from:\n{filename}",
        )
