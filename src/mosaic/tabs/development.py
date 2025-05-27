import time

import numpy as np
from qtpy.QtWidgets import QWidget, QVBoxLayout

from ..widgets.ribbon import create_button


def noop(*args, **kwargs):
    return None


class PerformanceMonitor:
    """Monitor VTK rendering performance"""

    def __init__(self, render_window):
        self.render_window = render_window
        self.frame_times = []
        self.start_time = None

    def start_monitoring(self):
        """Start performance monitoring"""
        self.frame_times = []
        self.start_time = time.time()

    def record_frame(self):
        """Record a frame render time"""
        if self.start_time:
            frame_time = time.time() - self.start_time
            self.frame_times.append(frame_time)
            self.start_time = time.time()

    def get_stats(self):
        """Get performance statistics"""
        if not self.frame_times:
            return {}

        frame_times = np.array(self.frame_times)
        fps = 1.0 / np.mean(frame_times) if np.mean(frame_times) > 0 else 0

        return {
            "avg_fps": fps,
            "min_fps": 1.0 / np.max(frame_times) if np.max(frame_times) > 0 else 0,
            "max_fps": 1.0 / np.min(frame_times) if np.min(frame_times) > 0 else 0,
            "avg_frame_time_ms": np.mean(frame_times) * 1000,
            "frame_count": len(frame_times),
        }

    def print_stats(self, label="Performance"):
        """Print performance statistics"""
        stats = self.get_stats()
        if stats:
            print(f"\n=== {label} ===")
            print(f"Average FPS: {stats['avg_fps']:.1f}")
            print(f"Frame time: {stats['avg_frame_time_ms']:.1f}ms")
            print(f"FPS range: {stats['min_fps']:.1f} - {stats['max_fps']:.1f}")
            print(f"Frames measured: {stats['frame_count']}")


class DevelopmentTab(QWidget):
    def __init__(self, cdata, ribbon, **kwargs):
        super().__init__()
        self.cdata = cdata
        self.ribbon = ribbon

        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ribbon)

    def show_ribbon(self):
        self.ribbon.clear()
        cluster_actions = [
            create_button(
                "Add", "mdi.plus", self, self.add_cloud, "Merge selected clusters"
            ),
            create_button(
                "Test Render",
                "mdi.test-tube",
                self,
                self.test_point_rendering_performance,
                "Merge selected clusters",
            ),
        ]
        self.ribbon.add_section("Base Operations", cluster_actions)

    def add_cloud(self, *args):
        num_points = 1000
        points = np.random.rand(num_points, 3) * 100
        self.cdata._data.add(points=points, sampling_rate=1)
        self.cdata.data.data_changed.emit()
        self.cdata.data.render()

    def test_point_rendering_performance(self, *args, **kwargs):
        """
        Test rendering performance by spinning the camera
        """
        test_duration = 5.0
        vtk_widget = self.cdata.data.vtk_widget
        render_window = vtk_widget.GetRenderWindow()
        renderer = render_window.GetRenderers().GetFirstRenderer()
        camera = renderer.GetActiveCamera()

        monitor = PerformanceMonitor(render_window)
        monitor.start_monitoring()
        start_time = time.time()
        frame_count = 0

        while (time.time() - start_time) < test_duration:
            camera.Azimuth(1.0)

            monitor.start_time = time.time()
            render_window.Render()
            monitor.record_frame()

            frame_count += 1

            vtk_widget.GetRenderWindow().GetInteractor().ProcessEvents()

        print(monitor.get_stats())
        return monitor
