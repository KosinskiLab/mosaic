from os.path import basename
from qtpy.QtCore import Qt, QTimer, Signal
from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QSlider,
    QLabel,
    QFrame,
    QSizePolicy,
)
import qtawesome as qta

from ..stylesheets import QSlider_style


class TimelineBar(QWidget):
    """A custom widget that combines a slider with a visual timeline bar."""

    valueChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Container for the slider to control its width
        self.slider_container = QWidget()
        container_layout = QHBoxLayout(self.slider_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.valueChanged.connect(self.valueChanged.emit)

        self.slider.setStyleSheet(QSlider_style)
        container_layout.addWidget(self.slider)
        layout.addWidget(self.slider_container)

        self.spacer = QWidget()
        self.spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.spacer.setStyleSheet("background: transparent;")
        layout.addWidget(self.spacer)

    def setRange(self, min_val, max_val):
        self.slider.setRange(min_val, max_val)

    def setValue(self, value):
        self.slider.setValue(value)

    def value(self):
        return self.slider.value()

    def setRelativeWidth(self, frames, max_frames):
        """Set the width of the timeline relative to the maximum number of frames."""
        if max_frames > 0:
            ratio = frames / max_frames
            total_width = self.width()
            self.slider_container.setFixedWidth(int(total_width * ratio))


class TrajectoryRow(QFrame):
    """Represents a single trajectory row with integrated timeline."""

    frameChanged = Signal()

    def __init__(self, trajectory, max_frames, parent=None):
        super().__init__(parent)
        self.trajectory = trajectory
        self.max_frames = max_frames
        self.current_frame = 0
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        name = basename(self.trajectory._meta.get("filename", "Unnamed Trajectory"))
        if isinstance(name, (list, tuple)) and len(name) > 0:
            name = name[0]
        name_label = QLabel(str(name))
        name_label.setMinimumWidth(150)
        name_label.setMaximumWidth(200)
        layout.addWidget(name_label)

        # Center: Timeline with integrated slider
        self.timeline = TimelineBar()
        self.timeline.setRange(0, self.trajectory.frames - 1)
        self.timeline.valueChanged.connect(self._update_frame)
        self.timeline.setRelativeWidth(self.trajectory.frames, self.max_frames)
        layout.addWidget(self.timeline, 1)  # 1 = stretch factor

        # Right side: Frame counter
        self.frame_label = QLabel(f"0/{self.trajectory.frames-1}")
        self.frame_label.setMinimumWidth(70)
        self.frame_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(self.frame_label)

    def resizeEvent(self, event):
        """Update relative width when the widget is resized."""
        super().resizeEvent(event)
        self.timeline.setRelativeWidth(self.trajectory.frames, self.max_frames)

    def _update_frame(self, frame_idx):
        """Update the displayed frame using the trajectory's display_frame method."""

        update = self.trajectory.display_frame(frame_idx)
        if not update:
            return None

        self.current_frame = frame_idx
        self.frame_label.setText(f"{frame_idx}/{self.trajectory.frames-1}")
        self.frameChanged.emit()


class TrajectoryPlayer(QWidget):
    def __init__(self, cdata, parent=None):
        super().__init__(parent)
        self.cdata = cdata
        self.current_frame = 0
        self.play_timer = QTimer()
        self.play_timer.timeout.connect(self.next_frame)
        self.play_timer.setInterval(100)

        self.cdata.models.data_changed.connect(self.update_trajectories)
        self.setup_ui()
        self.update_trajectories()

        self.playing = False

    @property
    def playing(self):
        return self._playing

    @playing.setter
    def playing(self, playing: bool):
        from ..icons import icon_color

        self._playing = playing
        if not hasattr(self, "play_button"):
            return None

        if not playing:
            self.play_button.setIcon(qta.icon("fa5s.play", color=icon_color))
        else:
            self.play_button.setIcon(qta.icon("fa5s.pause", color=icon_color))

    @property
    def trajectories(self):
        ret = []
        for i in range(self.rows_layout.count()):
            ret.append(self.rows_layout.itemAt(i).widget())
        return ret

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(4)

        # Controls section with frame counter on right
        controls_container = QWidget()
        controls_layout = QHBoxLayout(controls_container)
        controls_layout.setContentsMargins(0, 0, 0, 0)

        # Center-aligned play controls
        play_controls = QWidget()
        play_layout = QHBoxLayout(play_controls)
        play_layout.setContentsMargins(0, 0, 0, 8)
        play_layout.setSpacing(4)
        play_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        button_size = 32
        self.first_button = QPushButton()
        self.first_button.setIcon(qta.icon("fa5s.step-backward", color="#475569"))
        self.first_button.setFixedSize(button_size, button_size)
        self.first_button.clicked.connect(lambda: self.sync_frame(0))

        self.prev_button = QPushButton(autoRepeat=True)
        self.prev_button.setIcon(qta.icon("fa5s.backward", color="#475569"))
        self.prev_button.setFixedSize(button_size, button_size)
        self.prev_button.clicked.connect(self.prev_frame)

        self.play_button = QPushButton()
        self.play_button.setIcon(qta.icon("fa5s.play"))
        self.play_button.setFixedSize(button_size, button_size)
        self.play_button.clicked.connect(self.toggle_play)

        self.next_button = QPushButton(autoRepeat=True)
        self.next_button.setIcon(qta.icon("fa5s.forward", color="#475569"))
        self.next_button.setFixedSize(button_size, button_size)
        self.next_button.clicked.connect(self.next_frame)

        self.last_button = QPushButton()
        self.last_button.setIcon(qta.icon("fa5s.step-forward", color="#475569"))
        self.last_button.setFixedSize(button_size, button_size)
        self.last_button.clicked.connect(lambda: self.sync_frame(self.max_frame()))

        for button in [
            self.first_button,
            self.prev_button,
            self.play_button,
            self.next_button,
            self.last_button,
        ]:
            button.setStyleSheet(
                """
                QPushButton {
                    border: none;
                    border-radius: 16px;
                    padding: 8px;
                }
                QPushButton:hover {
                    background-color: #f3f4f6;
                }
                QPushButton:pressed {
                    background-color: #e5e7eb;
                }
            """
            )
            play_layout.addWidget(button)

        controls_layout.addStretch()
        controls_layout.addWidget(play_controls)
        controls_layout.addStretch()

        # Frame counter on right with consistent width
        frame_container = QWidget()
        frame_layout = QHBoxLayout(frame_container)
        frame_layout.setContentsMargins(4, 0, 4, 0)

        self.current_frame_label = QLabel("0/0")
        self.current_frame_label.setMinimumWidth(70)  # Match trajectory row label width
        self.current_frame_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        frame_layout.addWidget(self.current_frame_label)

        controls_layout.addWidget(frame_container)

        main_layout.addWidget(controls_container)

        self.trajectory_area = QWidget()
        self.trajectory_area.setLayout(QHBoxLayout())
        self.trajectory_area.layout().setContentsMargins(0, 0, 0, 0)
        self.trajectory_area.layout().setSpacing(0)

        # Trajectories container
        self.rows_widget = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_widget)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(2)
        self.trajectory_area.layout().addWidget(self.rows_widget)

        # Need a container for proper overlay positioning
        trajectory_container = QWidget()
        container_layout = QVBoxLayout(trajectory_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self.trajectory_area)

        main_layout.addWidget(trajectory_container, 1)

    def update_trajectories(self):
        from ..geometry import GeometryTrajectory

        """Update trajectories from MosaicData models."""
        for i in reversed(range(self.rows_layout.count())):
            self.rows_layout.itemAt(i).widget().setParent(None)

        # Find all GeometryTrajectory instances and determine max frames
        geometry_trajectories = [
            model
            for model in self.cdata._models.data
            if isinstance(model, GeometryTrajectory)
        ]

        if not geometry_trajectories:
            self.current_frame_label.setText("0/0")
            return

        max_frames = max(t.frames for t in geometry_trajectories)
        for model in geometry_trajectories:
            row = TrajectoryRow(model, max_frames)
            row.frameChanged.connect(lambda: self.cdata.models.render_vtk())
            self.rows_layout.addWidget(row)

        self.current_frame_label.setText(f"0/{max_frames-1}")

    def sync_frame(self, frame_idx, from_row=False):
        """Synchronize frame across all trajectories."""
        self.current_frame = frame_idx
        self.current_frame_label.setText(f"{frame_idx}/{self.max_frame() - 1}")

        # Changing the timeline value will trigger the frame update
        for trajectory in self.trajectories:
            trajectory.timeline.setValue(frame_idx)

    def toggle_play(self):
        """Toggle playback state."""
        self.playing = not self.playing
        if self.playing:
            return self.play_timer.start()

        self.play_timer.stop()

    def max_frame(self):
        if len(self.trajectories) == 0:
            return 0
        return max(t.trajectory.frames for t in self.trajectories)

    def next_frame(self):
        """Advance to next frame."""
        if self.current_frame < self.max_frame() - 1:
            return self.sync_frame(self.current_frame + 1)

        self.play_timer.stop()
        self.playing = False

    def prev_frame(self):
        """Go to previous frame."""
        if self.current_frame > 0:
            self.sync_frame(self.current_frame - 1)
