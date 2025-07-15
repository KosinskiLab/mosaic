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
        self.legend = kwargs.get("legend", None)

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
            create_button(
                "Outer",
                "mdi.hexagon",
                self,
                self.get_outer,
                "Merge selected clusters",
            ),
            create_button(
                "Ward",
                "mdi.hexagon",
                self,
                self.ward,
                "Merge selected clusters",
            ),
        ]
        self.ribbon.add_section("Base Operations", cluster_actions)

    def add_cloud(self, *args):
        num_points = 50000
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

    def get_outer(self):
        cluster_indices = self.cdata.data._get_selected_indices()
        if len(cluster_indices) == 0:
            return None
        geometry = self.cdata._data.data[cluster_indices[0]]

        points = np.divide(geometry.points, geometry.sampling_rate)

        from scipy.sparse import coo_matrix
        from scipy.spatial import KDTree
        from ..utils import connected_components

        tree = KDTree(
            points,
            leafsize=16,
            compact_nodes=False,
            balanced_tree=False,
            copy_data=False,
        )
        pairs = tree.query_pairs(r=np.sqrt(3), eps=0.1, output_type="ndarray")

        n_points = points.shape[0]
        adjacency = coo_matrix(
            (np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])),
            shape=(n_points, n_points),
            dtype=np.int8,
        )

        adjacency = adjacency + adjacency.T
        n0 = np.asarray(adjacency.sum(axis=0)).reshape(-1)

        print(points.shape[1] ** 3 - 4)
        rel_points = points[(n0 < 23) * (n0 > 9)]
        points = connected_components(rel_points)
        for point in points:
            point = np.multiply(point, geometry.sampling_rate)
            self.cdata._data.add(points=point, sampling_rate=geometry.sampling_rate)
        self.cdata.data.render()

    def ward(self):
        cluster_indices = self.cdata.data._get_selected_indices()
        if len(cluster_indices) == 0:
            return None
        geometry = self.cdata._data.data[cluster_indices[0]]

        points = np.divide(geometry.points, geometry.sampling_rate)
        from ..utils import _get_adjacency_matrix

        adjacency = _get_adjacency_matrix(points, eps=0.1)
        import igraph as ig
        import leidenalg

        sources, targets = adjacency.nonzero()
        edges = list(zip(sources, targets))
        g = ig.Graph(n=len(points), edges=edges)
        partition = leidenalg.find_partition(
            g, leidenalg.CPMVertexPartition, resolution_parameter=0.00000005
        )
        for community in partition:
            print(community)
            point = points[community]
            point = np.multiply(point, geometry.sampling_rate)
            self.cdata._data.add(points=point, sampling_rate=geometry.sampling_rate)
        self.cdata.data.render()
