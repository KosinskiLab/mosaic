from typing import List, Tuple, Literal

import vtk
import numpy as np
from qtpy.QtCore import Qt, QEvent
from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QMessageBox,
)

from ..registry import MethodRegistry
from ..utils import Throttle
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
                "ph.git-merge",
                self,
                lambda: (self.cdata.data.merge(), self.cdata.models.merge()),
                "Merge selected objects",
            ),
            create_button(
                "Remove",
                "ph.trash",
                self,
                lambda: (self.cdata.data.remove(), self.cdata.models.remove()),
                "Remove selected objects",
            ),
            create_button(
                "Select",
                "ph.chart-bar",
                self,
                self._show_histogram,
                "Filter objects by size",
            ),
            create_button(
                "Transform",
                "ph.arrows-out-cardinal",
                self,
                self._toggle_transform,
                "Transform selected cluster",
            ),
            create_button(
                "Crop",
                "ph.crop",
                self,
                self._distance_crop,
                "Crop by distance",
            ),
        ]
        self.ribbon.add_section("Base Operations", cluster_actions)

        point_actions = [
            create_button(
                "Cluster",
                "ph.arrows-out-line-horizontal",
                self,
                self.cdata.data.cluster,
                "Extract distinct components",
                MethodRegistry.settings_dict("cluster"),
            ),
            create_button(
                "Outlier",
                "ph.funnel",
                self,
                self.cdata.data.remove_outliers,
                "Remove isolated points",
                MethodRegistry.settings_dict("remove_outliers"),
            ),
            create_button(
                "Normals",
                "ph.arrows-out",
                self,
                self.cdata.data.compute_normals,
                "Assign normals",
                MethodRegistry.settings_dict("compute_normals"),
            ),
            create_button(
                "Trim",
                "ph.scissors",
                self,
                self._toggle_trimmer,
                "Trim points using planes",
            ),
            create_button(
                "Skeletonize",
                "ph.line-segments",
                self,
                self.cdata.data.skeletonize,
                "Extract boundary or core points",
                MethodRegistry.settings_dict("skeletonize"),
            ),
            create_button(
                "Downsample",
                "ph.arrows-in",
                self,
                self.cdata.data.downsample,
                "Reduce point density",
                MethodRegistry.settings_dict("downsample"),
            ),
        ]
        self.ribbon.add_section("Point Operations", point_actions)

        analysis_actions = [
            create_button(
                "Properties",
                "ph.chart-bar-horizontal",
                self,
                self._show_property_dialog,
                "Analyze cluster properties",
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
        from ..widgets.dock import create_or_toggle_dock

        dialog = None
        if getattr(self, "histogram_dock", None) is None:
            dialog = HistogramDialog(self.cdata, parent=self)
        create_or_toggle_dock(self, "histogram_dock", dialog)

    def _show_property_dialog(self):
        from ..dialogs import PropertyAnalysisDialog
        from ..widgets.dock import create_or_toggle_dock

        dialog = PropertyAnalysisDialog(self.cdata, self.legend, parent=self)
        create_or_toggle_dock(self, "property_dock", dialog)

    def _distance_crop(self):
        from ..dialogs import DistanceCropDialog
        from ..widgets.dock import create_or_toggle_dock

        dialog = None
        if getattr(self, "distance_crop_dock", None) is None:
            dialog = DistanceCropDialog(cdata=self.cdata, parent=self)
            self.cdata.data.render_update.connect(dialog.populate_lists)
            self.cdata.models.render_update.connect(dialog.populate_lists)
            dialog.cropApplied.connect(self._apply_distance_crop)

        create_or_toggle_dock(self, "distance_crop_dock", dialog)

    def _apply_distance_crop(self, crop_data):
        """Apply the distance crop operation.

        Parameters
        ----------
        crop_data : dict
            Dictionary with sources, targets, distance, keep_smaller keys.
        """
        from ..properties import GeometryProperties

        sources = crop_data["sources"]
        targets = crop_data["targets"]
        distance = crop_data["distance"]
        keep_smaller = crop_data["keep_smaller"]

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
        self.geometry = None
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

        self.geometry = None
        self.points = None
        self.normals = None

        self.transform_widget = None
        self.selected_cluster = None
        self.data.vtk_widget.GetRenderWindow().Render()

    def show(self):
        geometries = self.data.get_selected_geometries()
        if not geometries:
            return None

        self.setup()

        self.geometry = geometries[0]

        points = self.geometry.points
        mins = np.min(points, axis=0)
        maxs = np.max(points, axis=0)

        bounds = []
        padding = np.maximum(
            np.multiply(maxs - mins, 0.55), 20 * self.geometry.sampling_rate
        )
        for min_val, max_val, pad in zip(mins, maxs, padding):
            bounds.extend([min_val - pad, max_val + pad])

        # Transforms are w.r.t baseline orientation
        self.points = points.copy()
        self.normals = self.geometry.normals.copy()
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

        self._transform_throttle = Throttle(self.on_transform, interval_ms=50)
        self.transform_widget.AddObserver("InteractionEvent", self._transform_throttle)

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
        self.geometry.swap_data(new_points, normals=new_normals)
        self.data.render()


class PlaneTrimmer:
    def __init__(self, data):
        self.data = data
        self.plane1, self.plane2 = None, None
        self._update_throttle = Throttle(self._update_selection, interval_ms=100)

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
        if len(self.data.container) == 0:
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
            self._update_throttle()

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
        from ..interactor import (
            _bounds_in_frustum,
            _points_in_frustum,
        )

        self.data.point_selection.clear()
        plane_norm = np.empty((2, 3), dtype=np.float32)
        plane_orig = np.empty((2, 3), dtype=np.float32)

        plane_norm[0] = self.plane1.GetNormal()
        plane_norm[1] = self.plane2.GetNormal()
        plane_orig[0] = self.plane1.GetOrigin()
        plane_orig[1] = self.plane2.GetOrigin()

        for geometry in self.data.container.data:
            if not geometry.visible:
                continue

            bounds = geometry._data.GetBounds()
            if not _bounds_in_frustum(bounds, plane_norm, plane_orig):
                continue

            points = geometry.points
            ids = np.where(
                np.invert(_points_in_frustum(points, plane_norm, plane_orig))
            )[0]
            if len(ids) == 0:
                continue

            self.data.point_selection[geometry.uuid] = ids
        self.data.highlight_selected_points(color=None)
