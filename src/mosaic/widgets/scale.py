""" VTK Scale Bar widget for adding distance indicators to the vtk viewer.

    Copyright (c) 2025 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import vtk


class ScaleBarWidget:
    def __init__(
        self, renderer: vtk.vtkRenderer, interactor: vtk.vtkRenderWindowInteractor
    ):
        self.renderer = renderer
        self.interactor = interactor
        self.visible = False

        self.scale_actor = vtk.vtkLegendScaleActor()
        self.scale_actor.AllAxesOff()

        # self.scale_actor.BottomAxisVisibilityOn()
        self.scale_actor.LegendVisibilityOn()

        color = (0.41, 0.42, 0.435)
        self.scale_actor.GetLegendLabelProperty().SetColor(*color)
        self.scale_actor.GetLegendLabelProperty().SetFontSize(0)
        self.scale_actor.GetLegendLabelProperty().SetShadow(0)

        self.scale_actor.GetLegendTitleProperty().SetColor(*color)
        self.scale_actor.GetLegendTitleProperty().SetFontSize(14)
        self.scale_actor.GetLegendTitleProperty().SetShadow(0)

    def show(self):
        if self.visible:
            return None

        self.renderer.AddActor(self.scale_actor)
        self.visible = True
        return self.interactor.GetRenderWindow().Render()

    def hide(self):
        if not self.visible:
            return None

        self.renderer.RemoveActor(self.scale_actor)
        self.visible = False
        return self.interactor.GetRenderWindow().Render()

    def set_label_format(self, format_string: str):
        """Set the format string for the scale labels.

        Args:
            format_string: Format string (e.g., "%.1f mm" or "%.2f µm")
        """
        self.scale_actor.SetLabelFormat(format_string)
        self.interactor.GetRenderWindow().Render()

    def set_units(self, units: str):
        """Set the units for the scale bar.

        Args:
            units: Unit string (e.g., "mm", "µm", "nm")
        """
        format_string = f"%.1f {units}"
        self.set_label_format(format_string)
