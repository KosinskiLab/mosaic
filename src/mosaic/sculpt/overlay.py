"""VTK actors that visualize the sculpt cursor in the viewport.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import Sequence

import numpy as np
import vtk


__all__ = ["SculptOverlay"]


def _make_cursor_ring():
    src = vtk.vtkRegularPolygonSource()
    src.GeneratePolygonOff()
    src.SetNumberOfSides(48)
    src.SetRadius(24)
    src.SetCenter(0, 0, 0)
    mapper = vtk.vtkPolyDataMapper2D()
    mapper.SetInputConnection(src.GetOutputPort())
    actor = vtk.vtkActor2D()
    actor.SetMapper(mapper)
    actor.GetProperty().SetLineWidth(1.5)
    actor.GetProperty().SetColor(1.0, 0.7, 0.2)
    return actor, src


def _make_drag_vector():
    src = vtk.vtkLineSource()
    src.SetPoint1(0.0, 0.0, 0.0)
    src.SetPoint2(0.0, 0.0, 0.0)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(src.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetLineWidth(2.0)
    prop.SetColor(1.0, 0.7, 0.2)
    prop.SetOpacity(0.0)
    try:
        prop.SetLineStipplePattern(0x00FF)
        prop.SetLineStippleRepeatFactor(1)
    except AttributeError:
        pass
    actor.SetVisibility(False)
    return actor, src


class SculptOverlay:
    def __init__(self):
        self.cursor_ring, self._ring_source = _make_cursor_ring()
        self.drag_vector, self._drag_source = _make_drag_vector()
        self._color = (1.0, 0.7, 0.2)

    def set_tool_color(self, rgb: Sequence[float]) -> None:
        self._color = tuple(float(c) for c in rgb)
        for actor in (self.cursor_ring, self.drag_vector):
            actor.GetProperty().SetColor(*self._color)

    def set_cursor_screen_position(self, x: int, y: int, on_mesh: bool) -> None:
        self.cursor_ring.SetPosition(x, y)
        self.cursor_ring.GetProperty().SetOpacity(1.0 if on_mesh else 0.35)

    def set_cursor_radius(self, pixels: float) -> None:
        self._ring_source.SetRadius(max(2.0, float(pixels)))
        self._ring_source.Modified()

    def set_drag_vector(
        self, anchor_world: np.ndarray, current_world: np.ndarray
    ) -> None:
        a = np.asarray(anchor_world, dtype=np.float64).reshape(3)
        c = np.asarray(current_world, dtype=np.float64).reshape(3)
        self._drag_source.SetPoint1(float(a[0]), float(a[1]), float(a[2]))
        self._drag_source.SetPoint2(float(c[0]), float(c[1]), float(c[2]))
        self.drag_vector.GetProperty().SetOpacity(1.0)
        self.drag_vector.SetVisibility(True)

    def clear_drag_vector(self) -> None:
        self.drag_vector.SetVisibility(False)
        self.drag_vector.GetProperty().SetOpacity(0.0)

    def attach(self, renderer) -> None:
        renderer.AddActor2D(self.cursor_ring)
        renderer.AddActor(self.drag_vector)

    def detach(self, renderer) -> None:
        renderer.RemoveActor2D(self.cursor_ring)
        renderer.RemoveActor(self.drag_vector)
