""" Variety of widgets used throughout the GUI.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import Tuple

import vtk


class BoundingBoxWidget:
    def __init__(self, renderer, interactor):
        self.renderer = renderer
        self.interactor = interactor
        self.box_actor = None
        self.setup()

    def setup(self, shape: Tuple[int] = None, offset: Tuple[int] = None):
        box_mapper = vtk.vtkPolyDataMapper()
        if shape is not None:
            offset = (
                [
                    0,
                ]
                * len(shape)
                if offset is None
                else offset
            )

            # TODO: Fix odd even box offset
            shape = tuple(x - 1 for x in shape)
            box_source = vtk.vtkCubeSource()
            box_source.SetXLength(shape[0])
            box_source.SetYLength(shape[1])
            box_source.SetZLength(shape[2])
            box_source.SetCenter(*(y + x / 2 for x, y in zip(shape, offset)))
            box_mapper.SetInputConnection(box_source.GetOutputPort())

        self.box_actor = vtk.vtkActor()
        self.box_actor.SetMapper(box_mapper)
        self.box_actor.GetProperty().SetColor(0.5, 0.5, 0.5)

        # Perhaps expose this settings and this actor in general
        # self.box_actor.GetProperty().SetOpacity(0.3)
        self.box_actor.GetProperty().SetOpacity(1)
        self.box_actor.GetProperty().SetRepresentationToWireframe()
        self.box_actor.PickableOff()
        self.renderer.AddActor(self.box_actor)


class AxesWidget:
    def __init__(self, renderer, interactor):
        self.axes_actor = vtk.vtkAxesActor()
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
        self.orientation_marker = vtk.vtkOrientationMarkerWidget()
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
