from typing import Tuple

import vtk


class BoundingBoxWidget:
    def __init__(self, renderer, interactor):
        self.renderer = renderer
        self.interactor = interactor
        self.box_actor = None
        self.axes_actor = None
        self.orientation_marker = None
        self.setup()

    def setup(self, shape: Tuple[int] = None):
        box_mapper = vtk.vtkPolyDataMapper()
        if shape is not None:
            box_source = vtk.vtkCubeSource()
            box_source.SetXLength(shape[0])
            box_source.SetYLength(shape[1])
            box_source.SetZLength(shape[2])
            box_source.SetCenter(*(x // 2 for x in shape))
            box_mapper.SetInputConnection(box_source.GetOutputPort())

        self.box_actor = vtk.vtkActor()
        self.box_actor.SetMapper(box_mapper)
        self.box_actor.GetProperty().SetColor(0.5, 0.5, 0.5)
        self.box_actor.GetProperty().SetOpacity(0.3)
        self.box_actor.GetProperty().SetRepresentationToWireframe()

        # Create axes actor
        self.axes_actor = vtk.vtkAxesActor()
        self.axes_actor.SetTotalLength(20, 20, 20)
        self.axes_actor.SetShaftType(0)
        self.axes_actor.SetAxisLabels(1)
        self.axes_actor.SetCylinderRadius(0.01)
        self.axes_actor.SetPosition(0, 0, 0)

        # Adjust text properties for axis labels
        for axis in ["X", "Y", "Z"]:
            caption_actor = getattr(self.axes_actor, f"Get{axis}AxisCaptionActor2D")()
            text_actor = caption_actor.GetTextActor()
            text_actor.SetTextScaleModeToNone()
            text_actor.GetTextProperty().SetFontSize(12)

        # Create orientation marker widget
        self.orientation_marker = vtk.vtkOrientationMarkerWidget()
        self.orientation_marker.SetOrientationMarker(self.axes_actor)
        self.orientation_marker.SetInteractor(self.interactor)
        self.orientation_marker.SetViewport(0.0, 0.0, 0.2, 0.2)
        self.orientation_marker.SetEnabled(1)
        self.orientation_marker.InteractiveOff()
        self.orientation_marker.SetOutlineColor(0.93, 0.57, 0.13)

        self.renderer.AddActor(self.box_actor)
