from qtpy.QtCore import Qt, QRect, Signal
from qtpy.QtWidgets import QWidget, QScrollArea, QApplication
from qtpy.QtGui import QPainter, QColor, QPen, QFont, QMouseEvent

import qtawesome as qta


class TimelineContent(QWidget):
    trackSelected = Signal(str)
    frameMoved = Signal(int)
    trackMoved = Signal(str, int)
    trackRemoved = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tracks = []
        self.current_frame = 0
        self.selected_track = None
        self.dragging_track = None
        self.drag_start_x = 0
        self.drag_start_frame = 0

        self.view_start_frame = 0
        self.view_end_frame = 300
        self.min_visible_frames = 1

        self.track_height = 40
        self.ruler_height = 30
        self.remove_button_size = 16
        self.hovered_remove_button = None

        self.setMouseTracking(True)
        self.update_size()

    def update_size(self):
        min_height = self.ruler_height + 10
        if self.tracks:
            min_height += len(self.tracks) * self.track_height

        self.setMinimumHeight(max(100, min_height))

    def set_tracks(self, tracks):
        self.tracks = tracks
        self.update_view_range()
        self.update_size()
        self.update()

    def set_current_frame(self, frame):
        self.current_frame = frame

        if frame < self.view_start_frame:
            self.view_start_frame = frame
            self.view_end_frame = frame + (self.view_end_frame - self.view_start_frame)
        elif frame > self.view_end_frame:
            self.view_end_frame = frame
            self.view_start_frame = frame - (
                self.view_end_frame - self.view_start_frame
            )

        self.update()

    def update_view_range(self):
        """Update view range based on track content"""
        if not self.tracks:
            return None

        last_frame = 0
        for track in self.tracks:
            track_end = track.animation.global_start_frame + track.animation.duration
            last_frame = max(last_frame, track_end)

        self.view_end_frame = max(self.min_visible_frames, last_frame + 20)

        if self.view_start_frame > self.view_end_frame - self.min_visible_frames:
            self.view_start_frame = max(
                0, self.view_end_frame - self.min_visible_frames
            )

    def frame_to_x(self, frame):
        """Convert frame number to x coordinate"""
        view_range = self.view_end_frame - self.view_start_frame
        if view_range == 0:
            return 0
        return (frame - self.view_start_frame) / view_range * self.width()

    def x_to_frame(self, x):
        """Convert x coordinate to frame number"""
        view_range = self.view_end_frame - self.view_start_frame
        frame = self.view_start_frame + (x / self.width()) * view_range
        return int(round(frame))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        font = QFont(painter.font())
        font.setPointSize(8)
        painter.setFont(font)

        painter.setPen(QPen(Qt.GlobalColor.black, 1))
        painter.drawLine(0, self.ruler_height, self.width(), self.ruler_height)

        view_range = self.view_end_frame - self.view_start_frame
        pixels_per_frame = self.width() / view_range

        target_spacing = 80
        frames_per_tick = max(1, int(target_spacing / pixels_per_frame))

        # Find the smallest interval that's larger than frames_per_tick
        intervals = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
        for interval in intervals:
            if interval >= frames_per_tick:
                frames_per_tick = interval
                break
        else:
            frames_per_tick = 1000 * ((frames_per_tick + 500) // 1000)

        first_visible_tick = (
            int(self.view_start_frame) // frames_per_tick
        ) * frames_per_tick
        if first_visible_tick < self.view_start_frame:
            first_visible_tick += frames_per_tick

        metadata_font = QFont(painter.font())
        metadata_font.setPointSize(12)
        painter.setFont(metadata_font)

        for frame in range(
            first_visible_tick,
            int(self.view_end_frame) + frames_per_tick,
            frames_per_tick,
        ):
            x = self.frame_to_x(frame)
            if x < 0 or x > self.width():
                continue

            painter.drawLine(int(x), self.ruler_height - 5, int(x), self.ruler_height)

            label = str(frame)
            text_width = painter.fontMetrics().horizontalAdvance(label)
            text_x = x - text_width / 2
            if text_x > 0 and text_x + text_width < self.width() - 5:
                painter.drawText(
                    int(text_x), 5, text_width, 20, Qt.AlignmentFlag.AlignCenter, label
                )

        track_y = self.ruler_height + 10
        for track in self.tracks:
            start_x = self.frame_to_x(track.animation.global_start_frame)
            end_x = self.frame_to_x(
                track.animation.global_start_frame + track.animation.duration
            )

            x = max(0, start_x)
            width = min(self.width(), end_x) - x
            if end_x < 0 or start_x > self.width() or width <= 0:
                track_y += self.track_height
                continue

            color = QColor(track.color)
            if not track.animation.enabled:
                color.setAlpha(128)
            painter.fillRect(int(x), track_y, int(width), self.track_height - 10, color)

            painter.setPen(QPen(Qt.GlobalColor.black, 1))
            if track.id == self.selected_track:
                painter.setPen(QPen(Qt.GlobalColor.blue, 2))

            painter.drawRect(int(x), track_y, int(width), self.track_height - 10)
            if width > 40:
                painter.setPen(Qt.GlobalColor.white)
                text_rect = QRect(
                    int(x + 5), track_y + 5, int(width - 10), self.track_height - 20
                )
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                    track.animation.name,
                )

            # Only draw if visible
            remove_x = int(end_x - self.remove_button_size - 5)
            remove_y = track_y + (self.track_height - 10 - self.remove_button_size) // 2
            if start_x < remove_x < self.width():
                icon_color = (
                    QColor(255, 255, 255)
                    if self.hovered_remove_button == track.id
                    else QColor(128, 128, 128)
                )
                icon = qta.icon("fa5s.trash", color=icon_color)
                pixmap = icon.pixmap(self.remove_button_size, self.remove_button_size)
                painter.drawPixmap(remove_x, remove_y, pixmap)

            track_y += self.track_height

        playhead_x = self.frame_to_x(self.current_frame)
        if 0 <= playhead_x <= self.width():
            painter.setPen(QPen(Qt.GlobalColor.red, 1))
            painter.drawLine(int(playhead_x), 0, int(playhead_x), self.height())

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton or not self.tracks:
            return super().mousePressEvent(event)

        track_y = self.ruler_height + 10
        for track in self.tracks:
            start_x = self.frame_to_x(track.animation.global_start_frame)
            end_x = self.frame_to_x(
                track.animation.global_start_frame + track.animation.duration
            )

            # Check if click is on remove button
            remove_x = int(end_x - self.remove_button_size - 5)
            remove_y = track_y + (self.track_height - 10 - self.remove_button_size) // 2

            if (
                remove_x <= event.x() <= remove_x + self.remove_button_size
                and remove_y <= event.y() <= remove_y + self.remove_button_size
                and start_x < remove_x < self.width()
            ):
                self.trackRemoved.emit(track.id)

            if (
                start_x <= event.x() <= end_x
                and track_y <= event.y() <= track_y + self.track_height - 10
            ):
                self.selected_track = track.id
                self.dragging_track = track.id
                self.drag_start_x = event.x()
                self.drag_start_frame = track.animation.global_start_frame
                self.trackSelected.emit(track.id)
                self.update()
                return

            track_y += self.track_height

        frame = self.x_to_frame(event.x())
        self.current_frame = max(0, frame)
        self.frameMoved.emit(self.current_frame)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        # Check if we're hovering over a remove button
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            hovered_button = None
            track_y = self.ruler_height + 10
            for track in self.tracks:
                start_x = self.frame_to_x(track.animation.global_start_frame)
                end_x = self.frame_to_x(
                    track.animation.global_start_frame + track.animation.duration
                )

                remove_x = int(end_x - self.remove_button_size - 5)
                remove_y = (
                    track_y + (self.track_height - 10 - self.remove_button_size) // 2
                )

                if (
                    remove_x <= event.x() <= remove_x + self.remove_button_size
                    and remove_y <= event.y() <= remove_y + self.remove_button_size
                    and start_x < remove_x < self.width()
                ):
                    hovered_button = track.id
                    break

                track_y += self.track_height

            if hovered_button != self.hovered_remove_button:
                self.hovered_remove_button = hovered_button
                self.update()

        draggable = self.dragging_track and self.tracks
        if not draggable or not (event.buttons() & Qt.MouseButton.LeftButton):
            return super().mouseMoveEvent(event)

        frame = self.x_to_frame(event.x())
        frame_shift = frame - self.x_to_frame(self.drag_start_x)
        new_frame = max(0, self.drag_start_frame + frame_shift)

        self.trackMoved.emit(self.dragging_track, new_frame)

        track = next((t for t in self.tracks if t.id == self.dragging_track), None)
        if track is None:
            return None

        track_end = new_frame + track.animation.duration
        if track_end > self.view_end_frame - 10:
            self.view_end_frame = track_end + 20
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.dragging_track = False
        return self.update()

    def wheelEvent(self, event):
        if not self.tracks:
            return super().wheelEvent(event)

        if not (event.modifiers() & Qt.ControlModifier):
            return event.ignore()

        mouse_frame = self.x_to_frame(event.position().x())
        view_range = self.view_end_frame - self.view_start_frame

        zoom_factor = 1.05
        new_range = max(self.min_visible_frames, view_range / zoom_factor)
        if event.angleDelta().y() <= 0:
            new_range = view_range * zoom_factor
            last_frame = 1
            for track in self.tracks:
                track_end = (
                    track.animation.global_start_frame + track.animation.duration
                )
                last_frame = max(last_frame, track_end)
            max_range = max(self.min_visible_frames, last_frame + 40)
            new_range = min(new_range, max_range)

        mouse_ratio = (mouse_frame - self.view_start_frame) / view_range
        self.view_start_frame = mouse_frame - new_range * mouse_ratio
        self.view_end_frame = self.view_start_frame + new_range

        if self.view_start_frame < 0:
            self.view_start_frame = 0
            self.view_end_frame = new_range

        self.update()


class TimelineWidget(QScrollArea):
    trackSelected = Signal(str)
    frameMoved = Signal(int)
    trackMoved = Signal(str, int)
    trackRemoved = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.content = TimelineContent(self)

        self.content.trackSelected.connect(self.trackSelected.emit)
        self.content.frameMoved.connect(self.frameMoved.emit)
        self.content.trackMoved.connect(self.trackMoved.emit)
        self.content.trackRemoved.connect(self.trackRemoved.emit)

        self.setWidget(self.content)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setFrameShape(self.NoFrame)

    def set_tracks(self, tracks):
        self.content.set_tracks(tracks)
        QApplication.processEvents()

    def set_current_frame(self, frame):
        self.content.set_current_frame(frame)
        QApplication.processEvents()

    @property
    def selected_track(self):
        return self.content.selected_track

    @selected_track.setter
    def selected_track(self, value):
        self.content.selected_track = value

    def update(self):
        self.content.update_view_range()
        self.content.update_size()
        self.content.update()
        QApplication.processEvents()
