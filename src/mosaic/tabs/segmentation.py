from typing import List, Tuple, Literal

import vtk
import numpy as np
from qtpy.QtCore import Qt, QEvent
from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QMessageBox,
    QDockWidget,
    QApplication,
    QMainWindow,
)

from ..widgets.ribbon import create_button


class SegmentationTab(QWidget):
    def __init__(self, cdata, ribbon, legend, **kwargs):
        super().__init__()
        self.cdata = cdata
        self.ribbon = ribbon
        self.legend = legend

        self.trimmer = PlaneTrimmer(self.cdata.data)
        self.transfomer = ClusterTransformer(self.cdata.data)
        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ribbon)

        self.cdata.data.vtk_widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Handle Escape key to exit transformer and trimmer mode."""
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()

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
                "mdi.rotate-right",
                self,
                self._toggle_transform,
                "Transform selected cluster",
            ),
            create_button(
                "Crop",
                "mdi.map-marker-distance",
                self,
                self._distance_crop,
                "Crop by distance",
            ),
        ]
        self.ribbon.add_section("Base Operations", cluster_actions)

        point_actions = [
            create_button(
                "Cluster",
                "mdi.sitemap",
                self,
                self.cdata.data.cluster,
                "Cluster points",
                CLUSTER_SETTINGS,
            ),
            create_button(
                "Outlier",
                "mdi.filter",
                self,
                self.cdata.data.remove_outliers,
                "Remove outliers",
                OUTLIER_SETTINGS,
            ),
            create_button(
                "Normals",
                "mdi.arrow-expand-up",
                self,
                self.cdata.data.compute_normals,
                "Assign normals",
                NORMAL_SETTINGS,
            ),
            create_button(
                "Trim",
                "mdi.scissors-cutting",
                self,
                self._toggle_trimmer,
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
            create_button(
                "Downsample",
                "mdi.focus-field-horizontal",
                self,
                self.cdata.data.downsample,
                "Downsample cluster",
                DOWNSAMPLE_SETTINGS,
            ),
        ]
        self.ribbon.add_section("Point Operations", point_actions)

        analysis_actions = [
            create_button(
                "Distances",
                "mdi.graphql",
                self,
                self._show_distance_dialog,
                "Analyse distance distributions",
            ),
            create_button(
                "Properties",
                "mdi.poll",
                self,
                self._show_property_dialog,
                "Analyse object properties",
            ),
        ]
        self.ribbon.add_section("Analysis", analysis_actions)

    def _toggle_trimmer(self):
        if self.trimmer.active:
            return self.trimmer.clean()
        return self.trimmer.show()

    def _toggle_transform(self):
        if self.transfomer.active:
            return self.transfomer.clean()
        return self.transfomer.show()

    def _show_histogram(self):
        from ..dialogs import HistogramDialog

        dialog = HistogramDialog(parent=self)
        dialog.update_histogram(self.cdata._data.get_cluster_size())
        dialog.histogram_widget.cutoff_changed.connect(
            self.cdata.data._on_cutoff_changed
        )
        return dialog.show()

    def _update_histogram(self):
        self.histogram_widget.update_histogram(self.cdata._data.get_cluster_size())

    def _show_distance_dialog(self):
        from ..dialogs import DistanceAnalysisDialog

        fits = self.cdata.format_datalist("models")
        clusters = self.cdata.format_datalist("data")

        dialog = DistanceAnalysisDialog(clusters, fits=fits, parent=self)
        return dialog.show()

    def _show_property_dialog(self):
        from ..dialogs import PropertyAnalysisDialog

        def _exit():
            if self.property_dock:
                self.property_dock.close()
            self.property_dock = None

        # Close dialog if it already exists
        if getattr(self, "property_dock", None) is not None:
            return _exit()

        dialog = PropertyAnalysisDialog(self.cdata, self.legend, parent=self)
        self.cdata.data.render_update.connect(dialog.populate_lists)
        self.cdata.models.render_update.connect(dialog.populate_lists)

        self.property_dock = QDockWidget(self)
        self.property_dock.setFeatures(
            QDockWidget.DockWidgetClosable
            | QDockWidget.DockWidgetFloatable
            | QDockWidget.DockWidgetMovable
        )

        self.property_dock.setWidget(dialog)
        main_window = None
        for widget in QApplication.instance().topLevelWidgets():
            if isinstance(widget, QMainWindow):
                main_window = widget
                break

        if main_window is None:
            QMessageBox.warning(
                self, "Warning", "Could not determine application main window."
            )
            return dialog.show()
        main_window.addDockWidget(Qt.RightDockWidgetArea, self.property_dock)

        dialog.accepted.connect(_exit)
        dialog.rejected.connect(_exit)

        self.property_dock.show()
        self.property_dock.raise_()

    def _distance_crop(self):
        from ..dialogs import DistanceCropDialog
        from ..properties import GeometryProperties

        fits = self.cdata.format_datalist("models")
        clusters = self.cdata.format_datalist("data")

        dialog = DistanceCropDialog(clusters=clusters, fits=fits, parent=self)
        self.cdata.data.render_update.connect(dialog.populate_lists)
        self.cdata.models.render_update.connect(dialog.populate_lists)

        sources, targets, distance, keep_smaller = dialog.get_results()
        if sources is None:
            return -1

        for source in sources:
            dist = GeometryProperties.compute(
                geometry=source,
                property_name="distance",
                queries=targets,
                include_self=True,
            )
            mask = dist >= distance
            if keep_smaller:
                mask = dist < distance

            if mask.sum() == 0:
                QMessageBox.warning(self, "Warning", "No points satisfy cutoff.")

                continue
            self.cdata.data.add(source[mask])

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

        geometry = self.data.get_geometry(self.selected_cluster)

        points = geometry.points
        mins = np.min(points, axis=0)
        maxs = np.max(points, axis=0)

        bounds = []
        padding = np.maximum(
            np.multiply(maxs - mins, 0.55), 20 * geometry.sampling_rate
        )
        for min_val, max_val, pad in zip(mins, maxs, padding):
            bounds.extend([min_val - pad, max_val + pad])

        # Transforms are w.r.t baseline orientation
        self.points = points.copy()
        self.normals = geometry.normals.copy()
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

        new_points = self.points.copy()
        new_normals = self.normals.copy()
        if not only_translate:
            new_points = np.matmul(new_points, rotation.T, out=new_points)
            new_normals = np.matmul(new_normals, rotation.T, out=new_normals)

        new_points = np.add(new_points, translation, out=new_points)
        self.data.container.data[self.selected_cluster].swap_data(
            new_points, normals=new_normals
        )
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

        for i in range(len(self.data.container)):
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

        for i in range(len(self.data.container)):
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
            "description": "Retrieve outer/inner hull or core points.",
        },
    ],
    "method_settings": {
        "core": [
            {
                "label": "Radius",
                "parameter": "cutoff",
                "type": "float",
                "description": "Radius of sphere used for thinning.",
                "default": 50,
                "min": 0,
                "max": 1e32,
                "notes": "Larger radius yields coarser structures.",
            },
        ],
    },
}

NORMAL_SETTINGS = {
    "title": "Normal Settings",
    "settings": [
        {
            "label": "Method",
            "type": "select",
            "options": ["Compute", "Flip"],
            "default": "Compute",
            "description": "Compute new or flip direction of existing normals.",
        },
    ],
    "method_settings": {
        "Compute": [
            {
                "label": "Neighbors",
                "parameter": "k",
                "type": "number",
                "description": "Number of neighboring points to consider for normal estimation",
                "min": 3,
                "max": 100,
                "default": 15,
            },
        ],
        "Flip": [],
    },
}

DOWNSAMPLE_SETTINGS = {
    "title": "Downsample Settings",
    "settings": [
        {
            "label": "Method",
            "type": "select",
            "options": ["Radius", "Number"],
            "default": "Radius",
        },
    ],
    "method_settings": {
        "Radius": [
            {
                "label": "Radius",
                "parameter": "voxel_size",
                "type": "float",
                "default": 40.0,
            },
        ],
        "Number": [
            {
                "label": "Number",
                "parameter": "size",
                "type": "number",
                "min": 1,
                "default": 1000,
            },
        ],
    },
}

CLUSTER_SETTINGS = {
    "title": "Cluster Settings",
    "settings": [
        {
            "label": "Method",
            "type": "select",
            "options": [
                "Connected Components",
                "Envelope",
                "Leiden",
                "DBSCAN",
                "K-Means",
                "Birch",
            ],
            "default": "Connected Components",
        },
        {
            "label": "Use Points",
            "parameter": "use_points",
            "type": "boolean",
            "description": "Use spatial coordinates for clustering",
            "default": True,
        },
        {
            "label": "Use Normals",
            "parameter": "use_normals",
            "type": "boolean",
            "description": "Use normal vectors for clustering",
            "default": False,
        },
        {
            "label": "Drop Noise",
            "parameter": "drop_noise",
            "type": "boolean",
            "description": "Drop noise cluster if available.",
            "default": True,
        },
        {
            "label": "Radius",
            "parameter": "downsampling_radius",
            "type": "float",
            "description": "Consider points within radius as one for clustering.",
            "default": -1.0,
            "min": -1.0,
            "max": 1e32,
            "notes": "Defaults to no downsampling.",
        },
    ],
    "method_settings": {
        "Connected Components": [
            {
                "label": "Distance",
                "parameter": "distance",
                "type": "float",
                "description": "Distance between points to be considered connected.",
                "default": -1.0,
                "min": -1.0,
                "max": 1e32,
                "notes": "Defaults to the associated sampling rate of the cluster.",
            },
        ],
        "Envelope": [
            {
                "label": "Distance",
                "parameter": "distance",
                "type": "float",
                "description": "Distance between points to be considered connected.",
                "default": -1.0,
                "min": -1.0,
                "max": 1e32,
                "notes": "Defaults to the associated sampling rate of the cluster.",
            },
        ],
        "Leiden": [
            {
                "label": "Distance",
                "parameter": "distance",
                "type": "float",
                "description": "Distance between points to be considered connected.",
                "default": -1.0,
                "min": -1.0,
                "max": 1e32,
                "notes": "Defaults to the associated sampling rate of the cluster.",
            },
            {
                "label": "Resolution (log10)",
                "parameter": "resolution_parameter",
                "type": "float",
                "description": "Log10 of resolution parameter for graph clustering.",
                "default": -7.3,
                "min": -1e32,
                "max": 1e32,
                "decimals": 8,
                "notes": "Smaller values yield larger clusters. Range: -8 to -2 for membranes.",
            },
        ],
        "DBSCAN": [
            {
                "label": "Distance",
                "parameter": "distance",
                "type": "float",
                "description": "Distance between neighbors in a cluster.",
                "default": 100.0,
            },
            {
                "label": "Min Points",
                "parameter": "min_points",
                "type": "number",
                "description": "Minimum cluster size.",
                "min": 1,
                "default": 500,
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
        "Birch": [
            {
                "label": "Clusters",
                "parameter": "n_clusters",
                "type": "number",
                "description": "Number of clusters to form.",
                "min": 1,
                "default": 3,
            },
            {
                "label": "Threshold",
                "parameter": "threshold",
                "type": "float",
                "description": "Radius for merging subclusters. Lower values create more clusters.",
                "default": 50.0,
            },
            {
                "label": "Branching Factor",
                "parameter": "branching_factor",
                "type": "number",
                "description": "Max subclusters per node. Higher values use more memory.",
                "min": 1,
                "default": 50,
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
