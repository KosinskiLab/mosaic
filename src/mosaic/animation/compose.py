import sys
from dataclasses import dataclass
from typing import Dict, List, Any

from qtpy.QtCore import Qt, QTimer
from qtpy.QtWidgets import (
    QApplication,
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QGroupBox,
    QSplitter,
    QScrollArea,
    QFrame,
)
import qtawesome as qta

from .timeline import TimelineWidget
from .animations import AnimationType
from .settings import AnimationSettings, ExportSettings

from mosaic.stylesheets import (
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
)
from mosaic.widgets import DialogFooter


@dataclass
class Track:
    id: int
    animation: object
    color: str


class AnimationComposerDialog(QDialog):
    def __init__(self, vtk_widget, volume_viewer=None, cdata=None, parent=None):
        super().__init__(parent)
        self.tracks: List[Track] = []
        self.selected_track = None
        self.current_frame = 0

        self.is_playing = False
        self.timer = QTimer()
        self.timer.timeout.connect(self.advance_frame)

        self.cdata = cdata
        self.vtk_widget = vtk_widget
        self.volume_viewer = volume_viewer

        self.setWindowTitle("Animation Composer")
        self.setup_ui()

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

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(0)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        sidebar_widget = QWidget()
        sidebar_layout = QVBoxLayout(sidebar_widget)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(10)

        presets_group = QGroupBox("Presets")
        presets_layout = QHBoxLayout(presets_group)
        traj_btn = QPushButton("Trajectory")
        traj_btn.clicked.connect(lambda: self._load_preset("trajectory"))
        presets_layout.addWidget(traj_btn)
        slice_btn = QPushButton("Slices")
        slice_btn.clicked.connect(lambda: self._load_preset("slices"))
        presets_layout.addWidget(slice_btn)
        reveal_btn = QPushButton("Reveal")
        reveal_btn.clicked.connect(lambda: self._load_preset("reveal"))
        presets_layout.addWidget(reveal_btn)
        sidebar_layout.addWidget(presets_group)

        animations_group = QGroupBox("Animations")
        animations_layout = QVBoxLayout(animations_group)
        for anim_type in AnimationType:
            preset = anim_type.value
            btn = QPushButton(f"{preset['name']}")
            btn.clicked.connect(lambda checked, t=anim_type: self.add_animation(t))
            animations_layout.addWidget(btn)
        sidebar_layout.addWidget(animations_group)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(10)

        self.properties_panel = AnimationSettings()
        self.properties_panel.setTitle("Properties")
        self.properties_panel.animationChanged.connect(self.on_animation_changed)
        scroll_layout.addWidget(self.properties_panel, 1)

        self.export_settings = ExportSettings()
        scroll_layout.addWidget(self.export_settings, 0)
        scroll_layout.addStretch()

        scroll_area.setWidget(scroll_content)
        sidebar_layout.addWidget(scroll_area, 1)

        timeline_widget = QWidget()
        timeline_layout = QVBoxLayout(timeline_widget)
        timeline_layout.setContentsMargins(0, 0, 0, 0)

        timeline_group = QGroupBox("Timeline")
        timeline_inner_layout = QVBoxLayout(timeline_group)

        controls_group = QWidget()
        controls_layout = QHBoxLayout(controls_group)

        back_btn = QPushButton()
        back_btn.setIcon(qta.icon("fa5s.step-backward"))
        back_btn.clicked.connect(lambda: self.set_current_frame(0))

        self.play_btn = QPushButton()
        self.play_btn.setIcon(qta.icon("fa5s.play"))
        self.play_btn.clicked.connect(self.toggle_play)

        forward_btn = QPushButton()
        forward_btn.setIcon(qta.icon("fa5s.step-forward"))
        forward_btn.clicked.connect(lambda: self.set_current_frame(self.current_frame))

        controls_layout.addWidget(back_btn)
        controls_layout.addWidget(self.play_btn)
        controls_layout.addWidget(forward_btn)

        controls_layout.addWidget(QLabel("Frame:"))
        self.frame_spin = QSpinBox()
        self.frame_spin.setRange(0, 2 << 29)
        self.frame_spin.valueChanged.connect(self.set_current_frame)
        controls_layout.addWidget(self.frame_spin)
        controls_layout.addStretch()

        timeline_inner_layout.addWidget(controls_group)

        self.timeline = TimelineWidget()
        self.timeline.content.trackSelected.connect(self.on_track_selected)
        self.timeline.frameMoved.connect(self.set_current_frame)
        self.timeline.trackMoved.connect(self.on_track_moved)
        self.timeline.trackRemoved.connect(self.delete_track)
        timeline_inner_layout.addWidget(self.timeline, 1)

        timeline_layout.addWidget(timeline_group)

        main_splitter.addWidget(sidebar_widget)
        main_splitter.addWidget(timeline_widget)
        main_splitter.setSizes([300, 800])

        content_layout.addWidget(main_splitter)
        main_layout.addWidget(content_widget, 1)

        footer = DialogFooter(
            dialog=self,
            margin=(0, 10, 0, 0),
        )
        main_layout.addWidget(footer, 0)

        self.resize(1100, 800)

    def _load_preset(self, preset_type):
        """Load a preset configuration for the animation"""
        print(f"Loading preset: {preset_type}")
        pass

    def add_animation(self, anim_type: AnimationType):
        animation_class = anim_type.value["class"]

        animation = animation_class(
            cdata=self.cdata,
            vtk_widget=self.vtk_widget,
            volume_viewer=self.volume_viewer,
            global_start_frame=0,
            enabled=True,
            name=f"{anim_type.value['name']} {len(self.tracks) + 1}",
        )

        track = Track(
            id=str(id(animation)),
            animation=animation,
            color=anim_type.value["color"],
        )

        self.tracks.append(track)
        self.timeline.set_tracks(self.tracks)

    def _get_track(self, track_id: int):
        return next((t for t in self.tracks if t.id == track_id), None)

    def delete_track(self, track_id: str):
        self.tracks = [t for t in self.tracks if t.id != track_id]
        if self.selected_track == track_id:
            self.selected_track = None
        self.timeline.set_tracks(self.tracks)

    def on_track_selected(self, track_id: int):
        if (track := self._get_track(track_id)) is None:
            return None

        self.selected_track = track_id
        self.properties_panel.set_animation(track.animation)

    def on_track_moved(self, track_id: str, new_frame: int):
        if (track := self._get_track(track_id)) is None:
            return None

        track.animation.global_start_frame = new_frame
        self.properties_panel.global_start_spin.setValue(new_frame)
        self.timeline.update()

    def on_animation_changed(self, changes: Dict[str, Any]):
        return self.timeline.update()

    def set_current_frame(self, frame: int):
        if not self.tracks:
            return None

        total_frames = max(
            (x.animation.frames + x.animation.global_start_frame for x in self.tracks)
        )

        self.current_frame = max(0, min(total_frames, frame))
        self.frame_spin.setValue(self.current_frame)
        self.timeline.set_current_frame(self.current_frame)

        if self.current_frame >= total_frames and self.is_playing:
            self.toggle_play()

        for track in self.tracks:
            track.animation.update(frame - 1)
        self.vtk_widget.GetRenderWindow().Render()

    def toggle_play(self):
        self.is_playing = not self.is_playing

        if self.is_playing:
            self.play_btn.setIcon(qta.icon("fa5s.pause"))
            self.timer.start(1000 // 30)
        else:
            self.play_btn.setIcon(qta.icon("fa5s.play"))
            self.timer.stop()

    def advance_frame(self):
        if self.is_playing:
            self.set_current_frame(self.current_frame + 1)

    def export_animation(self):
        """Export the animation with current settings"""
        print("Exporting animation...")
        pass


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(
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
    dialog = AnimationComposerDialog()
    dialog.show()
    sys.exit(app.exec())
