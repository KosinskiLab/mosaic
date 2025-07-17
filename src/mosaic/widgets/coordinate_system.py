"""
Variety of widgets used throughout the GUI.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtWidgets import QMessageBox
from vtk import (
    vtkCubeSource,
    vtkPolyDataMapper,
    vtkActor,
    vtkAxesActor,
    vtkOrientationMarkerWidget,
)


def create_bounding_box_actor(
    bounds_or_shape, offset=None, color=(0.5, 0.5, 0.5), opacity=1.0
):
    """
    Create a bounding box actor from bounds or shape.

    Parameters
    ----------
    bounds_or_shape : array-like
        Either VTK bounds [xmin, xmax, ymin, ymax, zmin, zmax]
        or shape tuple (width, height, depth).
    offset : array-like, optional
        Offset for shape-based boxes (ignored for bounds), by default None.
    color : tuple of float, optional
        RGB color tuple with values between 0 and 1, by default (0.5, 0.5, 0.5).
    opacity : float, optional
        Opacity value between 0 and 1, by default 0.6.
    line_width : int, optional
        Line width for wireframe representation, by default 1.

    Returns
    -------
    vtk.vtkActor
        A VTK actor representing the bounding box in wireframe mode.
    """
    if len(bounds_or_shape) == 6:
        xmin, xmax, ymin, ymax, zmin, zmax = bounds_or_shape
        center = [(xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2]
        size = [xmax - xmin, ymax - ymin, zmax - zmin]
    else:
        shape = bounds_or_shape
        offset = offset or [0] * len(shape)

        # TODO: Fix odd even box offset
        shape = tuple(x - 1 for x in shape)
        center = [y + x / 2 for x, y in zip(shape, offset)]
        size = list(shape)

    box_source = vtkCubeSource()
    box_source.SetCenter(*center)
    box_source.SetXLength(size[0])
    box_source.SetYLength(size[1])
    box_source.SetZLength(size[2])

    box_mapper = vtkPolyDataMapper()
    box_mapper.SetInputConnection(box_source.GetOutputPort())

    box_actor = vtkActor()
    box_actor.SetMapper(box_mapper)
    box_actor.GetProperty().SetColor(*color)
    box_actor.GetProperty().SetOpacity(opacity)
    box_actor.GetProperty().SetRepresentationToWireframe()
    box_actor.PickableOff()

    return box_actor


class BoundingBoxManager:
    """Manager for showing bounding boxes"""

    def __init__(self, renderer, interactor, cdata):
        self.renderer = renderer
        self.interactor = interactor
        self.cdata = cdata
        self.object_box_actors = []
        self.dataset_box_actor = None
        self.session_box_actor = None

    def show_all_object_boxes(self):
        """Show bounding boxes for all visible objects"""

        data_indices = [
            i
            for i in range(len(self.cdata.data.container))
            if self.cdata.data.get_geometry(i).visible
        ]
        model_indices = [
            i
            for i in range(len(self.cdata.models.container))
            if self.cdata.models.get_geometry(i).visible
        ]
        return self.show_selected_boxes(
            data_indices=data_indices, model_indices=model_indices
        )

    def show_selected_boxes(self, *args, data_indices=None, model_indices=None):
        """Show bounding boxes for selected objects only"""
        self.clear_object_boxes()

        if data_indices is None:
            data_indices = self.cdata.data._get_selected_indices()

        if model_indices is None:
            model_indices = self.cdata.models._get_selected_indices()

        for index in data_indices:
            geometry = self.cdata.data.get_geometry(index)
            self._create_object_box(geometry)

        for index in model_indices:
            geometry = self.cdata.models.get_geometry(index)
            self._create_object_box(geometry)

        self.renderer.GetRenderWindow().Render()

    def _create_object_box(self, geometry):
        """Create a bounding box actor for a specific geometry object"""
        bounds = geometry._actor.GetBounds()

        actor = create_bounding_box_actor(bounds_or_shape=bounds)
        self.object_box_actors.append(actor)
        return self.renderer.AddActor(actor)

    def clear_object_boxes(self):
        """Remove all object bounding boxes"""
        for actor in self.object_box_actors:
            self.renderer.RemoveActor(actor)
        self.object_box_actors.clear()
        self.renderer.GetRenderWindow().Render()

    def show_dataset_bounds(self, visible):
        """Toggle bounding box computed from all loaded data"""
        if visible:
            if not self.dataset_box_actor:
                self._create_dataset_bounds()
        else:
            if self.dataset_box_actor:
                self.renderer.RemoveActor(self.dataset_box_actor)
                self.dataset_box_actor = None
        self.renderer.GetRenderWindow().Render()

    def show_session_bounds(self, visible):
        """Toggle session bounding box from cdata.shape"""
        if visible:
            if not self.session_box_actor:
                self._create_session_bounds()
        else:
            if self.session_box_actor:
                self.renderer.RemoveActor(self.session_box_actor)
                self.session_box_actor = None
        self.renderer.GetRenderWindow().Render()

    def _create_session_bounds(self):
        """Create session bounds from cdata.shape"""
        if not hasattr(self.cdata, "shape") or self.cdata.shape is None:
            QMessageBox.warning(
                None,
                "Session Bound Unavailable",
                "No session bounding box is available.\n\n"
                "To use this feature, open a file using 'File > Load Session', "
                "or a session saved after opening a file using Load Session. "
                "This will provide the original volume boundaries, useful for instance "
                "for volume segmentations.",
            )
            return

        self.session_box_actor = create_bounding_box_actor(self.cdata.shape)
        self.renderer.AddActor(self.session_box_actor)

    def _create_dataset_bounds(self):
        """Create dataset bounds from all visible data"""
        all_bounds = []

        # Collect bounds from all visible data
        for i in range(len(self.cdata.data.container)):
            if self.cdata.data.container.data[i].visible:
                geometry = self.cdata.data.get_geometry(i)
                bounds = geometry._data.GetBounds()
                all_bounds.append(bounds)

        for i in range(len(self.cdata.models.container)):
            if self.cdata.models.container.data[i].visible:
                geometry = self.cdata.models.get_geometry(i)
                bounds = geometry._data.GetBounds()
                all_bounds.append(bounds)

        if not all_bounds:
            return

        # Calculate overall bounds
        xmin = min(b[0] for b in all_bounds)
        xmax = max(b[1] for b in all_bounds)
        ymin = min(b[2] for b in all_bounds)
        ymax = max(b[3] for b in all_bounds)
        zmin = min(b[4] for b in all_bounds)
        zmax = max(b[5] for b in all_bounds)

        bounds = [xmin, xmax, ymin, ymax, zmin, zmax]
        self.dataset_box_actor = create_bounding_box_actor(bounds)
        self.renderer.AddActor(self.dataset_box_actor)


class AxesWidget:
    def __init__(self, renderer, interactor):
        self.axes_actor = vtkAxesActor()
        self.axes_actor.SetTotalLength(20, 20, 20)
        self.axes_actor.SetShaftType(0)
        self.axes_actor.SetAxisLabels(1)
        self.axes_actor.SetCylinderRadius(0.02)
        self.axes_actor.SetPosition(0, 0, 0)

        for axis in ["X", "Y", "Z"]:
            caption_actor = getattr(self.axes_actor, f"Get{axis}AxisCaptionActor2D")()
            text_actor = caption_actor.GetTextActor()
            text_actor.SetTextScaleModeToNone()
            text_actor.GetTextProperty().SetFontSize(12)
            actor = getattr(self.axes_actor, f"Get{axis}AxisShaftProperty")()
            actor.SetColor(0.5, 0.5, 0.5)

        # Create orientation marker widget
        self.orientation_marker = vtkOrientationMarkerWidget()
        self.orientation_marker.SetOrientationMarker(self.axes_actor)
        self.orientation_marker.SetInteractor(interactor)
        self.orientation_marker.SetViewport(0.0, 0.0, 0.2, 0.2)
        self.orientation_marker.SetEnabled(1)
        self.orientation_marker.InteractiveOff()
        self.orientation_marker.SetOutlineColor(0.93, 0.57, 0.13)

        self.visible = True
        self.set_colored(True)
        self.set_labels_visible(False)
        self.arrow_heads_visible = True

    def set_visibility(self, visible: bool):
        self.visible = visible
        self.orientation_marker.SetEnabled(1 if visible else 0)

    def set_colored(self, colored: bool):
        self.colored = colored

        colors = [(0.5, 0.5, 0.5)] * 3
        if self.colored:
            colors = [(0.8, 0.2, 0.2), (0.26, 0.65, 0.44), (0.2, 0.4, 0.8)]

        for index, axis in enumerate(["X", "Y", "Z"]):
            actor = getattr(self.axes_actor, f"Get{axis}AxisTipProperty")()
            actor.SetColor(*colors[index])

    def set_arrow_heads_visible(self, visible: bool):
        self.arrow_heads_visible = visible
        self.axes_actor.SetConeRadius(0.4 if visible else 0.0)
        self.set_colored(self.colored)

    def set_labels_visible(self, visible: bool):
        self.labels_visible = visible
        self.axes_actor.SetAxisLabels(1 if visible else 0)
