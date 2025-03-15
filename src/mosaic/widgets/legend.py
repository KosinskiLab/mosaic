""" LegendWidget widget for visualization of scalar mappings.

    Copyright (c) 2025 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import vtk


class LegendWidget:
    def __init__(self, renderer, interactor):
        self.renderer = renderer
        self.interactor = interactor

        self.scalar_bar = vtk.vtkScalarBarActor()
        self.scalar_bar.SetBarRatio(0.07)

        self.scalar_bar.SetDrawFrame(False)
        self.scalar_bar.SetLabelFormat("%.3g")
        self.scalar_bar.SetDrawBackground(False)
        self.scalar_bar.UnconstrainedFontSizeOn()
        self.scalar_bar.SetMaximumNumberOfColors(256)

        color = (0.41, 0.42, 0.435)
        label_property = self.scalar_bar.GetLabelTextProperty()
        label_property.SetColor(*color)
        label_property.SetShadow(0)

        title_property = self.scalar_bar.GetTitleTextProperty()
        title_property.SetColor(*color)
        title_property.SetShadow(0)

        self.widget = vtk.vtkScalarBarWidget()
        self.widget.SetInteractor(self.interactor)
        self.widget.SetScalarBarActor(self.scalar_bar)

        self.widget.GetScalarBarRepresentation().SetShowBorder(False)
        self.widget.ProcessEventsOff()

        self.title = None
        self.visible = False
        self.orientation = "vertical"
        self.set_orientation(self.orientation)

        default_lut = vtk.vtkLookupTable()
        default_lut.SetHueRange(0.667, 0.0)
        default_lut.SetSaturationRange(1.0, 1.0)
        default_lut.SetValueRange(1.0, 1.0)
        default_lut.SetNumberOfColors(256)
        default_lut.Build()
        self.set_lookup_table(default_lut)

    def set_lookup_table(self, lut, title=""):
        self.title = title
        self.scalar_bar.SetLookupTable(lut)
        self.scalar_bar.SetTitle(title)

        return self.interactor.Render()

    def set_orientation(self, orientation):
        is_vertical = orientation.lower() == "vertical"

        self.orientation = "vertical"
        if is_vertical:
            self.scalar_bar.SetOrientationToVertical()
            self.scalar_bar.SetTextPositionToPrecedeScalarBar()
            self.scalar_bar.SetTextPad(-4)
        else:
            self.orientation = "horizontal"
            self.scalar_bar.SetOrientationToHorizontal()
            self.scalar_bar.SetTextPositionToSucceedScalarBar()
            self.scalar_bar.SetTextPad(0)

        self.interactor.Render()

    def show(self):
        if self.visible:
            return None

        self.widget.On()
        self.visible = True
        return self.interactor.Render()

    def hide(self):
        if not self.visible:
            return None

        self.widget.Off()
        self.visible = False
        return self.interactor.Render()
