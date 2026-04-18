"""
Trajectory player for DTS simulations.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtCore import Qt, QTimer, Signal
from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QSlider,
    QLabel,
    QFrame,
)

from ..icons import icon
from ..stylesheets import Colors, Typography
from ..utils import Throttle

__all__ = ["TrajectoryPlayer"]

SPEED_STEPS = (0.5, 1.0, 2.0, 4.0)
SPEED_LABELS = (".5×", "1×", "2×", "4×")
BASE_INTERVAL_MS = 100


class TrajectoryRow(QFrame):
    """Single trajectory: play/pause · name · slider · frame counter · speed."""

    frameChanged = Signal()

    def __init__(self, trajectory, parent=None):
        super().__init__(parent)
        self.trajectory = trajectory
        self.current_frame = 0
        self._playing = False
        self._speed_idx = 1

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)

        self.setFixedHeight(28)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # Play / pause
        self._play_btn = QPushButton()
        self._play_btn.setFixedSize(22, 22)
        self._play_btn.setFlat(True)
        self._play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play_btn.clicked.connect(self._toggle_play)
        self._update_play_icon()
        lay.addWidget(self._play_btn)

        # Name
        self._name_label = QLabel()
        self._name_label.setFixedWidth(120)
        self._set_name_from_trajectory(trajectory)
        lay.addWidget(self._name_label)

        # Slider — inherits global Mosaic QSlider stylesheet
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, max(trajectory.frames - 1, 0))
        self._slider.setValue(0)
        self._frame_throttle = Throttle(self._on_slider, interval_ms=50)
        self._slider.valueChanged.connect(self._frame_throttle)
        lay.addWidget(self._slider, 1)

        # Frame counter
        self._frame_label = QLabel(self._frame_text())
        self._frame_label.setMinimumWidth(60)
        self._frame_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        lay.addWidget(self._frame_label)

        # Speed button
        self._speed_btn = QPushButton(self._speed_text())
        self._speed_btn.setFixedSize(40, 22)
        self._speed_btn.setFlat(True)
        self._speed_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._speed_btn.clicked.connect(self._cycle_speed)
        lay.addWidget(self._speed_btn)

        self._apply_styles()

    def set_frame(self, frame_idx):
        """Set frame programmatically, bypassing the slider throttle."""
        frame_idx = max(0, min(frame_idx, self.trajectory.frames - 1))
        self._slider.blockSignals(True)
        self._slider.setValue(frame_idx)
        self._slider.blockSignals(False)
        self._update_frame(frame_idx)

    def set_name_from_trajectory(self, trajectory):
        self._set_name_from_trajectory(trajectory)

    def _set_name_from_trajectory(self, trajectory):
        try:
            name = trajectory._meta.get("name", "Unnamed Trajectory")
            self._name_label.setText(name)
        except Exception:
            pass

    def _frame_text(self):
        return f"{self.current_frame}/{max(self.trajectory.frames - 1, 0)}"

    def _speed_text(self):
        return SPEED_LABELS[self._speed_idx]

    def _on_slider(self, value):
        self._update_frame(value)

    def _update_frame(self, frame_idx):
        if not self.trajectory.display_frame(frame_idx):
            return
        self.current_frame = frame_idx
        self._frame_label.setText(self._frame_text())
        self.frameChanged.emit()

    def _toggle_play(self):
        self._playing = not self._playing
        if self._playing:
            interval = int(BASE_INTERVAL_MS / SPEED_STEPS[self._speed_idx])
            self._timer.start(interval)
        else:
            self._timer.stop()
        self._update_play_icon()

    def _advance(self):
        if self.current_frame < self.trajectory.frames - 1:
            next_frame = self.current_frame + 1
            self._slider.blockSignals(True)
            self._slider.setValue(next_frame)
            self._slider.blockSignals(False)
            self._update_frame(next_frame)
        else:
            self._playing = False
            self._timer.stop()
            self._update_play_icon()

    def _cycle_speed(self):
        self._speed_idx = (self._speed_idx + 1) % len(SPEED_STEPS)
        self._speed_btn.setText(self._speed_text())
        if self._playing:
            self._timer.setInterval(
                int(BASE_INTERVAL_MS / SPEED_STEPS[self._speed_idx])
            )

    def _update_play_icon(self):
        name = "ph.pause" if self._playing else "ph.play"
        role = "muted" if self._playing else "primary"
        self._play_btn.setIcon(icon(name, role=role))

    def _apply_styles(self):
        self._play_btn.setStyleSheet(
            f"""
            QPushButton {{
                border: none; background: transparent;
                border-radius: 4px;
            }}
            QPushButton:hover {{ background: {Colors.BG_HOVER}; }}
        """
        )
        self._name_label.setStyleSheet(
            f"""
            font-size: {Typography.SMALL}px;
            color: {Colors.TEXT_SECONDARY};
        """
        )
        self._frame_label.setStyleSheet(
            f"""
            font-size: {Typography.SMALL}px;
            color: {Colors.TEXT_MUTED};
        """
        )
        self._speed_btn.setStyleSheet(
            f"""
            QPushButton {{
                border: none; background: transparent;
                border-radius: 3px;
                font-size: {Typography.SMALL}px;
                color: {Colors.TEXT_MUTED};
            }}
            QPushButton:hover {{
                background: {Colors.BG_HOVER};
                color: {Colors.TEXT_SECONDARY};
            }}
        """
        )


class TrajectoryPlayer(QWidget):
    """Container for trajectory rows — no header, no group box."""

    def __init__(self, cdata, parent=None):
        super().__init__(parent)
        self.cdata = cdata

        self.cdata.models.data_changed.connect(self.update_trajectories)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(2)

        self._placeholder = QLabel("Import a trajectory to display here")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._placeholder)

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        lay.addLayout(self._rows_layout)

        self._apply_styles()
        self.update_trajectories()

    @property
    def trajectories(self):
        ret = []
        for i in range(self._rows_layout.count()):
            widget = self._rows_layout.itemAt(i).widget()
            if widget is not None:
                ret.append(widget)
        return ret

    def update_trajectories(self):
        """Update trajectory rows from MosaicData models."""
        from ..geometry import GeometryTrajectory

        trajectories = [
            model
            for model in self.cdata._models.data
            if isinstance(model, GeometryTrajectory)
        ]

        for i in reversed(range(self._rows_layout.count())):
            widget = self._rows_layout.itemAt(i).widget()
            if widget is None:
                continue
            try:
                index = trajectories.index(widget.trajectory)
                trajectory = trajectories.pop(index)
                widget.set_name_from_trajectory(trajectory)
            except (IndexError, ValueError):
                widget.setParent(None)

        for model in trajectories:
            row = TrajectoryRow(model)
            row.frameChanged.connect(lambda: self.cdata.models._highlight_selection())
            self._rows_layout.addWidget(row)

        has_rows = self._rows_layout.count() > 0
        self._placeholder.setVisible(not has_rows)

    def _apply_styles(self):
        self._placeholder.setStyleSheet(
            f"""
            font-size: {Typography.SMALL}px;
            color: {Colors.TEXT_MUTED};
        """
        )

    def _on_theme_changed(self):
        self._apply_styles()
        for row in self.trajectories:
            row._update_play_icon()
            row._apply_styles()
