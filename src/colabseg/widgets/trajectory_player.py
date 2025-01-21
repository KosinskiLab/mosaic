from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QSlider,
    QLabel,
    QFrame,
    QStyle,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from ..geometry import GeometryTrajectory


class TimelineBar(QWidget):
    """A custom widget that combines a slider with a visual timeline bar."""

    valueChanged = pyqtSignal(int)

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

        # Make slider look integrated with the timeline
        self.slider.setStyleSheet(
            """
            QSlider::groove:horizontal {
                border: none;
                height: 24px;
                background: #e0e0e0;
            }
            QSlider::handle:horizontal {
                background: #2563eb;
                width: 2px;
                margin: -4px 0;
                border-radius: 0;
                border: 4px solid #2563eb;
            }
            QSlider::sub-page:horizontal {
                background: #c6dbfd;
            }
        """
        )

        container_layout.addWidget(self.slider)
        layout.addWidget(self.slider_container)

        # Add spacer to fill remaining width
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

    frameChanged = pyqtSignal(int)

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

        # Left side: Trajectory name
        from os.path import basename

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
        self.timeline.valueChanged.connect(self.update_frame)
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

    def update_frame(self, frame_idx):
        """Update the displayed frame using the trajectory's display_frame method."""
        if frame_idx >= self.trajectory.frames:
            return

        self.current_frame = frame_idx
        self.frame_label.setText(f"{frame_idx}/{self.trajectory.frames-1}")
        self.trajectory.display_frame(frame_idx)
        self.frameChanged.emit(frame_idx)


class TrajectoryPlayer(QWidget):
    def __init__(self, cdata, parent=None):
        super().__init__(parent)
        self.cdata = cdata
        self.trajectories = []
        self.current_frame = 0
        self.playing = False
        self.play_timer = QTimer()
        self.play_timer.timeout.connect(self.next_frame)
        self.play_timer.setInterval(100)

        self.cdata.models.data_changed.connect(self.update_trajectories)
        self.setup_ui()
        self.update_trajectories()

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
        play_layout.setContentsMargins(0, 0, 0, 0)
        play_layout.setSpacing(4)
        play_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        button_size = 32

        self.first_button = QPushButton()
        self.first_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSkipBackward)
        )
        self.first_button.setFixedSize(button_size, button_size)
        self.first_button.clicked.connect(lambda: self.sync_frame(0))

        self.prev_button = QPushButton()
        self.prev_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSeekBackward)
        )
        self.prev_button.setFixedSize(button_size, button_size)
        self.prev_button.clicked.connect(self.prev_frame)

        self.play_button = QPushButton()
        self.play_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        )
        self.play_button.setFixedSize(button_size, button_size)
        self.play_button.clicked.connect(self.toggle_play)

        self.next_button = QPushButton()
        self.next_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSeekForward)
        )
        self.next_button.setFixedSize(button_size, button_size)
        self.next_button.clicked.connect(self.next_frame)

        self.last_button = QPushButton()
        self.last_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward)
        )
        self.last_button.setFixedSize(button_size, button_size)

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
                    padding: 4px;
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
        """Update trajectories from ColabsegData models."""
        # Clear existing trajectories
        for i in reversed(range(self.rows_layout.count())):
            self.rows_layout.itemAt(i).widget().setParent(None)
        self.trajectories.clear()

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

        # Create rows for each trajectory
        for model in geometry_trajectories:
            row = TrajectoryRow(model, max_frames)
            row.frameChanged.connect(lambda x: self.sync_frame(x, from_row=True))
            self.trajectories.append(row)
            self.rows_layout.addWidget(row)

        self.current_frame_label.setText(f"0/{max_frames-1}")

    def sync_frame(self, frame_idx, from_row=False):
        """Synchronize frame across all trajectories."""
        self.current_frame = frame_idx
        self.current_frame_label.setText(
            f"{frame_idx}/{max(t.trajectory.frames-1 for t in self.trajectories)}"
        )

        if not from_row:
            # Update all trajectory rows
            for trajectory in self.trajectories:
                if frame_idx < trajectory.trajectory.frames:
                    trajectory.timeline.setValue(frame_idx)

        # Trigger render update
        self.cdata.models.render()

    def toggle_play(self):
        """Toggle playback state."""
        self.playing = not self.playing
        if self.playing:
            self.play_button.setIcon(
                self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause)
            )
            self.play_timer.start()
        else:
            self.play_button.setIcon(
                self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
            )
            self.play_timer.stop()

    def next_frame(self):
        """Advance to next frame."""
        max_frame = max(t.trajectory.frames - 1 for t in self.trajectories)
        if self.current_frame < max_frame:
            self.sync_frame(self.current_frame + 1)
        else:
            self.play_timer.stop()
            self.playing = False
            self.play_button.setIcon(
                self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
            )

    def prev_frame(self):
        """Go to previous frame."""
        if self.current_frame > 0:
            self.sync_frame(self.current_frame - 1)
