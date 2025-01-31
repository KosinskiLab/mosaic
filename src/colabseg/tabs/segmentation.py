from typing import List, Tuple, Literal

import vtk
import numpy as np
from matplotlib.pyplot import get_cmap
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QDialog

from ..utils import find_closest_points
from ..dialogs import (
    DistanceAnalysisDialog,
    DistanceStatsDialog,
    DistanceCropDialog,
    LocalizationDialog,
)
from ..dialogs.paywall import PaywallDialog
from ..widgets import HistogramWidget
from ..widgets.ribbon import create_button


class SegmentationTab(QWidget):
    def __init__(self, cdata, ribbon):
        super().__init__()
        self.cdata = cdata
        self.ribbon = ribbon

        self.trimmer = PlaneTrimmer(self.cdata.data)
        self.transfomer = ClusterTransformer(self.cdata.data)
        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ribbon)

        self.histogram_widget = HistogramWidget()
        self.histogram_window = QWidget()
        self.histogram_window.setWindowTitle("Select Clusters by Size")
        self.histogram_window.setFixedSize(600, 300)

        layout = QVBoxLayout(self.histogram_window)
        layout.addWidget(self.histogram_widget)

        self.cdata.data.data_changed.connect(self._update_histogram)
        self.histogram_widget.cutoff_changed.connect(self.cdata.data._on_cutoff_changed)

        self.cdata.data.vtk_widget.installEventFilter(self)
        self.histogram_window.move(self.mapToGlobal(self.rect().center()))

    def eventFilter(self, obj, event):
        """Handle Escape key to exit transformer and trimmer mode."""
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.trimmer.clean()
                self.transfomer.clean()
                return True

            if not self.trimmer.active:
                return super().eventFilter(obj, event)

            if key in (Qt.Key.Key_X, Qt.Key.Key_C, Qt.Key.Key_Z):
                axis = {Qt.Key.Key_X: "x", Qt.Key.Key_C: "y", Qt.Key.Key_Z: "z"}[key]

                self.trimmer.align_to_axis(self.trimmer.plane_widget1, f"-{axis}")
                self.trimmer.align_to_axis(self.trimmer.plane_widget2, f"{axis}")
                return True

        return super().eventFilter(obj, event)

    def show_ribbon(self):
        self.ribbon.clear()
        cluster_actions = [
            create_button(
                "Merge",
                "mdi.merge",
                self,
                self.cdata.data.merge,
                "Merge selected clusters",
            ),
            create_button(
                "Remove",
                "fa5s.trash",
                self,
                self.cdata.data.remove,
                "Remove selected clusters",
            ),
            create_button(
                "Select",
                "mdi.chart-histogram",
                self,
                self._show_histogram,
                "Select clusters by size",
            ),
            create_button(
                "Transform",
                "mdi.rotate-3d",
                self,
                self.transfomer.show,
                "Transform selected cluster",
            ),
        ]
        self.ribbon.add_section("Base Operations", cluster_actions)

        point_actions = [
            create_button(
                "Cluster",
                "mdi.sitemap",
                self,
                self.cdata.data.cluster,
                "Cluster Points",
                CLUSTER_SETTINGS,
            ),
            create_button(
                "Crop",
                "mdi.map-marker-distance",
                self,
                self._distance_crop,
                "Crop by Distance",
            ),
            create_button(
                "Outlier",
                "mdi.filter",
                self,
                self.cdata.data.remove_outliers,
                "Remove Outliers",
                OUTLIER_SETTINGS,
            ),
            create_button(
                "Trim",
                "mdi.scissors-cutting",
                self,
                self.trimmer.show,
                "Trim points using planes",
            ),
            create_button(
                "Thin",
                "mdi.dots-horizontal",
                self,
                self.cdata.data.decimate,
                "Reduce cluster to outer, core or inner points.",
                THINNING_SETTINGS,
            ),
        ]
        self.ribbon.add_section("Point Operations", point_actions)

        analysis_actions = [
            create_button(
                "Distances",
                "mdi.graphql",
                self,
                self._show_distance_dialog,
                "Analyse Distance Distributions",
            ),
            create_button(
                "Localization",
                "mdi.format-color-fill",
                self,
                self._show_localization_dialog,
                "Color Points By Localization",
            ),
            create_button(
                "Statistics",
                "fa5s.calculator",
                self,
                self._show_stats_dialog,
                "Compute Cluster Statistics",
            ),
        ]
        self.ribbon.add_section("Analysis", analysis_actions)

        upgrade_actions = [
            create_button(
                "Upgrade", "mdi.star", self, PaywallDialog.show_dialog, "Thin Cluster"
            ),
        ]
        self.ribbon.add_section("Upgrade", upgrade_actions)

    def _show_histogram(self):
        self._update_histogram()
        self.histogram_window.show()

    def _update_histogram(self):
        self.histogram_widget.update_histogram(self.cdata._data.get_cluster_size())

    def _show_distance_dialog(self):
        fits = self.cdata.format_datalist("models")
        clusters = self.cdata.format_datalist("data")

        dialog = DistanceAnalysisDialog(clusters, fits=fits, parent=self)
        return dialog.show()

    def _show_localization_dialog(self):
        fits = self.cdata.format_datalist("models")
        clusters = self.cdata.format_datalist("data")

        dialog = LocalizationDialog(clusters, fits=fits, parent=self)

        vtk_widget = self.cdata.data.vtk_widget
        renderer = vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer()
        camera_pos = np.array(renderer.GetActiveCamera().GetPosition())

        def _handle_selection(parameters):
            geometries = parameters.get("objects", [])
            if len(geometries) == 0:
                return None

            if (colormap := parameters.get("color_map", None)) is None:
                return None

            colormap = colormap.lower()
            if parameters.get("reverse", False):
                colormap = f"{colormap}_r"

            colormap = get_cmap(colormap)
            target = parameters.get("target", None)
            distances, color_by = [], parameters.get("color_by", "Identity")

            if target is None and color_by not in ("Camera Distance", "Identity"):
                return None

            identity = np.linspace(0, 255, len(geometries))
            for index, geometry in enumerate(geometries):
                points = geometry.points
                if color_by == "Camera Distance":
                    dist = np.linalg.norm(points - camera_pos, axis=1)
                elif color_by == "Cluster Distance":
                    dist = find_closest_points(target.points, points, k=1)[0]
                elif color_by == "Fit Distance":
                    model = target._meta["fit"]
                    if hasattr(model, "compute_distance"):
                        dist = model.compute_distance(points)
                    else:
                        dist = find_closest_points(target.points, points, k=1)[0]
                else:
                    dist = np.full(points.shape[0], fill_value=identity[index])

                distances.append(dist)

            if parameters.get("normalize_per_object", False):
                for index in range(len(distances)):
                    x_min, x_max = distances[index].min(), distances[index].max()
                    if (x_max - x_min) < 1e-6:
                        continue
                    distances[index] = (distances[index] - x_min) / (x_max - x_min)

            max_value = np.max([x.max() for x in distances]) + 1e-8
            min_value = np.min([x.min() for x in distances]) - 1e-8
            value_range = max_value - min_value

            # Extend color map beyond data range to avoid wrapping
            offset = value_range / 255.0
            min_value -= offset
            max_value += offset

            color_transfer_function = vtk.vtkColorTransferFunction()
            for i in range(256):
                if color_by == "Identity":
                    color_transfer_function.AddRGBPoint(i, *colormap(i / 255)[0:3])
                    continue

                data_value = min_value + i * offset
                x = (data_value - min_value) / (max_value - min_value)
                x = max(0, min(1, x))

                color_transfer_function.AddRGBPoint(data_value, *colormap(x)[0:3])

            from vtkmodules.util import numpy_support

            for index, geometry in enumerate(geometries):
                vtk_scalars = numpy_support.numpy_to_vtk(distances[index])
                geometry.actor.GetMapper().GetInput().GetPointData().SetScalars(
                    vtk_scalars
                )
                geometry.actor.GetMapper().SetLookupTable(color_transfer_function)
                geometry.actor.GetMapper().SetScalarRange(min_value, max_value)
                geometry.actor.GetMapper().ScalarVisibilityOn()
                geometry.actor.Modified()

            self.cdata.data.render_vtk()

        dialog.previewRequested.connect(_handle_selection)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return _handle_selection(dialog.get_settings())

        return None

    def _show_stats_dialog(self):
        clusters = self.cdata.format_datalist(type="data")
        dialog = DistanceStatsDialog(clusters, parent=self)
        return dialog.show()

    def _distance_crop(self):
        clusters = self.cdata.format_datalist(type="data")
        dialog = DistanceCropDialog(clusters, self)
        sources, targets, distance, keep_smaller = dialog.get_results()
        if sources is None:
            return -1

        # Build points attribute first to avoid synchronization issues
        for source in sources:
            temp_targets = [x for x in targets if x != source]
            if len(temp_targets) == 0:
                continue
            target_points = np.concatenate(
                [self.cdata._data._get_cluster_points(x) for x in temp_targets]
            )
            self.cdata._data.data[source]._meta["points"] = target_points

        for source in sources:
            self.cdata._data.crop(
                indices=[source], distance=distance, keep_smaller=keep_smaller
            )
            _ = self.cdata._data.data[source]._meta.pop("points")
        self.cdata.data.render()


class ClusterTransformer:
    def __init__(self, data):
        self.data = data
        self.original_points = None
        self.transform_widget = None
        self.selected_cluster = None

    @property
    def active(self):
        return self.transform_widget is not None

    def clean(self):
        """Remove the transform widget and clean up resources."""
        if not self.active:
            return None

        self.transform_widget.Off()
        self.transform_widget.SetEnabled(0)

        self.original_points = None
        self.transform_widget = None
        self.selected_cluster = None
        self.data.vtk_widget.GetRenderWindow().Render()

    def show(self):
        selected_items = self.data.data_list.selectedItems()
        if not selected_items:
            return

        self.setup()
        self.selected_cluster = self.data.data_list.row(selected_items[0])

        points = self.data.container._get_cluster_points(self.selected_cluster)
        mins = np.min(points, axis=0)
        maxs = np.max(points, axis=0)

        bounds = []
        padding = np.multiply(maxs - mins, 0.55)
        for min_val, max_val, pad in zip(mins, maxs, padding):
            bounds.extend([min_val - pad, max_val + pad])

        # Transforms are w.r.t baseline orientation
        self.original_points = points.copy()
        self.transform_widget.PlaceWidget(bounds)
        self.transform_widget.On()
        self.data.vtk_widget.GetRenderWindow().Render()

    def setup(self):
        """Create and configure the 3D widget for transformations."""
        if self.active:
            return None

        self.transform_widget = vtk.vtkBoxWidget()
        self.transform_widget.SetInteractor(
            self.data.vtk_widget.GetRenderWindow().GetInteractor()
        )
        self.transform_widget.SetRotationEnabled(True)
        self.transform_widget.SetTranslationEnabled(True)
        self.transform_widget.SetScalingEnabled(False)

        self.transform_widget.AddObserver("InteractionEvent", self.on_transform)

    def on_transform(self, widget, event):
        """Handle transformation updates."""
        if not self.active:
            return None

        t = vtk.vtkTransform()
        widget.GetTransform(t)
        vmatrix = t.GetMatrix()
        matrix = np.eye(4)
        vmatrix.DeepCopy(matrix.ravel(), vmatrix)

        rotation, translation = matrix[:3, :3], matrix[:3, 3]
        only_translate = np.allclose(rotation, np.eye(3), rtol=1e-10)

        new_points = self.original_points.copy()
        if not only_translate:
            new_points = np.matmul(new_points, rotation.T, out=new_points)

        new_points = np.add(new_points, translation, out=new_points)
        self.data.container.data[self.selected_cluster].swap_data(new_points=new_points)
        self.data.render()


class PlaneTrimmer:
    def __init__(self, data):
        self.data = data
        self.plane1, self.plane2 = None, None

    @property
    def active(self):
        return self.plane1 is not None and self.plane2 is not None

    def clean(self):
        """Remove the widgets."""
        if self.active:
            self.plane_widget1.Off()
            self.plane_widget1.SetEnabled(0)
            self.plane_widget2.Off()
            self.plane_widget2.SetEnabled(0)

        self.plane_widget1, self.plane_widget2 = None, None
        self.plane1, self.plane2 = None, None

    def show(self, state=None):
        if len(self.data.container.data) == 0:
            print("Load cluster data before launching trimmer widget.")
            return None

        self._setup()
        self.plane_widget1.SetEnabled(self.active)
        self.plane_widget2.SetEnabled(self.active)
        self.data.render_vtk()

    def _setup(self):
        self.plane1 = vtk.vtkPlane()
        self.plane2 = vtk.vtkPlane()
        self.plane_widget1 = self._setup_plane_widget((1, 0.8, 0.8))
        self.plane_widget2 = self._setup_plane_widget((1, 0.8, 0.8))

        self.align_to_axis(self.plane_widget1, "-z")
        self.align_to_axis(self.plane_widget2, "z")

        bounds = self._get_scene_bounds()
        self.plane_widget1.SetOrigin(bounds[0], bounds[2], bounds[4])
        self.plane_widget2.SetOrigin(bounds[0], bounds[2], bounds[5])

    def align_to_axis(self, widget, axis: Literal["x", "y", "z"]):
        """Align plane normal to specified axis."""
        _normal_mapping = {
            "x": (1, 0, 0),
            "y": (0, 1, 0),
            "z": (0, 0, 1),
            "-x": (-1, 0, 0),
            "-y": (0, -1, 0),
            "-z": (0, 0, -1),
        }
        _axis_mapping = {"x": 0, "y": 1, "z": 2}

        axis = axis.lower()
        normal = _normal_mapping.get(axis, None)
        if normal is None:
            return -1

        plane = self.plane1
        bounds = self._get_scene_bounds()
        origin = [bounds[0], bounds[2], bounds[4]]
        if widget == self.plane_widget2:
            plane = self.plane2
            index = _axis_mapping.get(axis, 0)
            origin[index] = bounds[index * 2 + 1]

        plane.SetNormal(normal)
        plane.SetOrigin(origin)
        widget.SetNormal(*normal)
        widget.SetOrigin(origin)
        self._update_selection()

    def _setup_plane_widget(self, color: Tuple[float, float, float]):
        """Setup an interactive widget for the plane."""
        widget = vtk.vtkImplicitPlaneWidget()
        widget.SetInteractor(self.data.vtk_widget.GetRenderWindow().GetInteractor())
        widget.SetPlaceFactor(1.0)

        bounds = self._get_scene_bounds()
        padding = [(b[1] - b[0]) * 0.1 for b in zip(bounds[::2], bounds[1::2])]
        padding = [
            -padding[i // 2] if i % 2 == 0 else padding[i // 2]
            for i in range(len(bounds))
        ]
        widget.PlaceWidget([sum(x) for x in zip(bounds, padding)])

        widget.GetPlaneProperty().SetColor(*color)
        widget.GetPlaneProperty().SetOpacity(0.4)

        widget.GetNormalProperty().SetColor(0.9, 0.9, 0.9)
        widget.GetNormalProperty().SetLineWidth(1)

        widget.GetEdgesProperty().SetColor(0.9, 0.9, 0.9)
        widget.GetEdgesProperty().SetLineWidth(1)

        widget.TubingOff()
        widget.ScaleEnabledOff()
        widget.OutlineTranslationOff()

        def callback(obj, event):
            origin = [0, 0, 0]
            normal = [0, 0, 0]
            obj.GetNormal(normal)
            obj.GetOrigin(origin)

            plane = self.plane2
            if obj == self.plane_widget1:
                plane = self.plane1

            plane.SetNormal(normal)
            plane.SetOrigin(origin)
            self._update_selection()

        widget.AddObserver("InteractionEvent", callback)
        return widget

    def _get_scene_bounds(self) -> List[float]:
        """Get the bounds of all visible geometry in the scene."""
        bounds = [float("inf"), float("-inf")] * 3

        for i in range(self.data.container.get_cluster_count()):
            if not self.data.container.data[i].visible:
                continue

            geom_bounds = self.data.container.data[i]._data.GetBounds()
            for i in range(len(geom_bounds)):
                func = min if i % 2 == 0 else max
                bounds[i] = func(bounds[i], geom_bounds[i])

        if any((abs(x) == float("inf")) for x in bounds):
            print("Could not determine bounding box - using default.")
            bounds = [-50.0, 50.0] * 3

        return bounds

    def _update_selection(self):
        """Update point selection based on current plane positions."""
        self.data.point_selection.clear()

        for i in range(self.data.container.get_cluster_count()):
            if not self.data.container.data[i].visible:
                continue

            points = self.data.container.data[i].points
            origin1 = np.array(self.plane1.GetOrigin())
            origin2 = np.array(self.plane2.GetOrigin())
            dist1 = np.dot(points - origin1, np.array(self.plane1.GetNormal()))
            dist2 = np.dot(points - origin2, np.array(self.plane2.GetNormal()))
            select = set(np.where((dist1 * dist2) < 0)[0])

            self.data.point_selection[i] = select

        self.data.highlight_selected_points(color=(0.8, 0.2, 0.2))


THINNING_SETTINGS = {
    "title": "Thinning Settings",
    "settings": [
        {
            "label": "Method",
            "type": "select",
            "options": ["outer", "core", "inner"],
            "default": "core",
        },
    ],
}

CLUSTER_SETTINGS = {
    "title": "Cluster Settings",
    "settings": [
        {
            "label": "Method",
            "type": "select",
            "options": ["Connected Components", "DBSCAN", "K-Means"],
            "default": "Connected Components",
        },
    ],
    "method_settings": {
        "DBSCAN": [
            {
                "label": "Distance",
                "parameter": "distance",
                "type": "float",
                "default": 40.0,
            },
            {
                "label": "Min Points",
                "parameter": "min_points",
                "type": "number",
                "min": 1,
                "default": 5,
            },
        ],
        "K-Means": [
            {
                "label": "Clusters",
                "parameter": "k",
                "type": "number",
                "min": 1,
                "default": 2,
            },
        ],
    },
}

OUTLIER_SETTINGS = {
    "title": "Remove Outlier",
    "settings": [
        {
            "label": "Method",
            "type": "select",
            "options": ["statistical", "eigenvalue"],
            "default": "statistical",
            "description": "Statistical - General outliers. Eigenvalue - Noisy Edges",
        },
        {
            "label": "Neighbors",
            "parameter": "k_neighbors",
            "type": "number",
            "min": 1,
            "default": 10,
            "description": "k-neigbors for estimating local densities.",
        },
        {
            "label": "Threshold",
            "parameter": "thresh",
            "type": "float",
            "default": 0.02,
            "description": "Threshold is sdev for statistical, eigenvalue ratio otherwise.",
        },
    ],
}
