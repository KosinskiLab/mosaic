import vtk
import numpy as np
from typing import List, Tuple, Literal


class PlaneTrimmer:
    def __init__(self, interactor):
        self.interactor = interactor
        self.vtk_widget = interactor.vtk_widget
        self.renderer = (
            self.vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer()
        )

        self.plane1 = vtk.vtkPlane()
        self.plane2 = vtk.vtkPlane()
        self.plane_widget1 = self._setup_plane_widget((1, 0.8, 0.8))
        self.plane_widget2 = self._setup_plane_widget((1, 0.8, 0.8))

        self.align_to_axis(self.plane_widget1, "-z")
        self.align_to_axis(self.plane_widget2, "z")

        bounds = self._get_scene_bounds()
        self.plane_widget1.SetOrigin(bounds[0], bounds[2], bounds[4])
        self.plane_widget2.SetOrigin(bounds[0], bounds[2], bounds[5])

        self.active = False

    def align_to_axis(
        self, widget: vtk.vtkImplicitPlaneWidget, axis: Literal["x", "y", "z"]
    ):
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

    def _setup_plane_widget(
        self, color: Tuple[float, float, float]
    ) -> vtk.vtkImplicitPlaneWidget:
        """Setup an interactive widget for the plane."""
        widget = vtk.vtkImplicitPlaneWidget()
        widget.SetInteractor(self.vtk_widget.GetRenderWindow().GetInteractor())
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

        for i in range(self.interactor.container.get_cluster_count()):
            if not self.interactor.container.data[i].visible:
                continue

            geom_bounds = self.interactor.container.data[i]._data.GetBounds()
            for i in range(len(geom_bounds)):
                func = min if i % 2 == 0 else max
                bounds[i] = func(bounds[i], geom_bounds[i])

        if any((abs(x) == float("inf")) for x in bounds):
            print("Could not determine bounding box - using default.")
            bounds = [-50.0, 50.0] * 3

        return bounds

    def _update_selection(self):
        """Update point selection based on current plane positions."""
        self.interactor.point_selection.clear()

        for i in range(self.interactor.container.get_cluster_count()):
            if not self.interactor.container.data[i].visible:
                continue

            points = self.interactor.container.data[i].points
            origin1 = np.array(self.plane1.GetOrigin())
            origin2 = np.array(self.plane2.GetOrigin())
            dist1 = np.dot(points - origin1, np.array(self.plane1.GetNormal()))
            dist2 = np.dot(points - origin2, np.array(self.plane2.GetNormal()))
            select = set(np.where((dist1 * dist2) < 0)[0])

            self.interactor.point_selection[i] = select

        self.interactor.highlight_selected_points(color=(0.8, 0.2, 0.2))

    def toggle(self, state=None):
        """Toggle the plane trimmer on/off."""
        if state is None:
            state = not self.active
        self.active = state
        self.plane_widget1.SetEnabled(self.active)
        self.plane_widget2.SetEnabled(self.active)
        self.vtk_widget.GetRenderWindow().Render()

    def cleanup(self):
        """Remove the widgets."""
        self.plane_widget1.SetEnabled(0)
        self.plane_widget2.SetEnabled(0)
