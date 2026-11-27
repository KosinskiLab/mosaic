"""
Cut chosen objects open with the mouse.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from collections.abc import Callable

import numpy as np
import vtk
from qtpy.QtCore import QTimer
from qtpy.QtGui import QColor

from .clipping import ClipCut, bounds, clip_targets
from .stylesheets import Colors

__all__ = ["ClipInteractorStyle", "ClipMode"]


class ClipMode:
    """Move one clipping plane through the chosen objects.

    Event positions are display coordinates with the origin at the lower left.

    Parameters
    ----------
    viewport : ViewportInteractor
        Viewport the mode runs in.
    cut : ClipCut
        Cut to move.
    notify : callable
        Receives status messages for the user.
    """

    def __init__(self, viewport, cut: ClipCut, notify: Callable[[str], None]):
        self._viewport = viewport
        self._cut = cut
        self._notify = notify
        self._targets = []
        self._renderer = None
        self._style = None
        self._press = None
        self._last = None
        self._dragging = False
        self._lod_geometries = []

        self._cube = vtk.vtkCubeSource()
        cutter = vtk.vtkCutter()
        cutter.SetCutFunction(cut.plane)
        cutter.SetInputConnection(self._cube.GetOutputPort())
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(cutter.GetOutputPort())
        self._outline = vtk.vtkActor()
        self._outline.SetMapper(mapper)
        self._outline.SetPickable(False)
        self._outline.SetVisibility(False)

        prop = self._outline.GetProperty()
        prop.SetColor(QColor(Colors.PRIMARY).getRgbF()[:3])
        prop.SetOpacity(0.6)
        prop.SetLineWidth(2)
        prop.LightingOff()

        self._hide_timer = QTimer()
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(500)
        self._hide_timer.timeout.connect(self._hide_outline)

    def activate(self) -> None:
        """Move the cut to the chosen objects and install the interactor style."""
        viewport = self._viewport
        window = viewport.vtk_widget.GetRenderWindow()
        self._renderer = window.GetRenderers().GetFirstRenderer()
        self._renderer.AddActor(self._outline)

        self._targets = clip_targets(viewport.data_pane, viewport.models_pane)
        if self._targets:
            self._cut.set_objects(self._targets)
            self._notify(
                "Right-drag to cut · Shift+right-drag to tilt · F to face · "
                "Right-click to remove"
            )
        else:
            self._cut.clear()
            self._notify("Nothing to cut in the selection")

        interactor = window.GetInteractor()
        if interactor is not None:
            self._style = ClipInteractorStyle(self)
            interactor.SetInteractorStyle(self._style)
        viewport.render_vtk()
        return None

    def deactivate(self) -> None:
        """Remove the outline and restore camera interaction, keeping the cut."""
        if self._dragging:
            self._end_drag()

        self._hide_timer.stop()
        if self._renderer is not None:
            self._renderer.RemoveActor(self._outline)

        if self._style is not None:
            self._style.cleanup()
            self._style = None

        interactor = self._viewport.vtk_widget.GetRenderWindow().GetInteractor()
        if interactor is not None:
            interactor.SetInteractorStyle(vtk.vtkInteractorStyleTrackballCamera())
        return None

    def retain(self, geometries: list) -> None:
        """Drop targets that are not in ``geometries``.

        Parameters
        ----------
        geometries : list of Geometry
            Geometries still in the session.
        """
        alive = set(map(id, geometries))
        self._targets = [g for g in self._targets if id(g) in alive]
        return None

    def right_press(self, x: int, y: int) -> None:
        """Start a right-button gesture at display position ``x``, ``y``."""
        # A release lost outside the window leaves the previous drag running.
        if self._dragging:
            self._end_drag()

        self._press = self._last = (x, y)
        return None

    def right_move(self, x: int, y: int, shift: bool) -> None:
        """Push the cut on a vertical drag, or tilt it with ``shift``."""
        if self._press is None or not self._targets:
            return None

        if not self._dragging:
            if np.hypot(x - self._press[0], y - self._press[1]) <= 4:
                return None
            self._begin_drag()

        if not self._cut.geometries:
            return None

        dx, dy = x - self._last[0], y - self._last[1]
        self._last = (x, y)

        camera = self._renderer.GetActiveCamera()
        direction = np.array(camera.GetDirectionOfProjection())
        if shift:
            right = np.cross(direction, camera.GetViewUp())
            right /= np.linalg.norm(right)
            self._cut.tilt(np.cross(right, direction), 0.5 * dx)
            self._cut.tilt(right, -0.5 * dy)
        else:
            height = self._viewport.vtk_widget.GetRenderWindow().GetSize()[1]
            lower, upper = self._cut.extent()
            self._cut.push(-dy / height * (upper - lower))

        self._show_outline()
        return None

    def right_release(self, x: int, y: int) -> None:
        """Finish a drag, or remove the cut after a click."""
        if self._press is None:
            return None

        self._press = None
        if self._dragging:
            self._end_drag()
            return None

        self._cut.clear()
        self._hide_outline()
        return None

    def key(self, name: str) -> None:
        """Handle key ``name``. ``f`` turns the cut to face the camera."""
        if name.lower() != "f" or not (self._cut.has_pose and self._cut.geometries):
            return None

        camera = self._renderer.GetActiveCamera()
        self._cut.face(camera.GetDirectionOfProjection())
        self._show_outline()
        return None

    def _begin_drag(self):
        self._dragging = True
        if not (self._cut.has_pose and self._cut.geometries):
            self._cut.set_objects(self._targets)

        if not self._cut.has_pose:
            camera = self._renderer.GetActiveCamera()
            self._cut.place_facing(
                camera.GetDirectionOfProjection(), bounds(self._targets)
            )

        self._lod_geometries = self._cut.geometries
        for geometry in self._lod_geometries:
            geometry.lod.begin()
        return None

    def _end_drag(self):
        self._dragging = False
        for geometry in self._lod_geometries:
            geometry.lod.end()
        self._lod_geometries = []
        self._viewport.render_vtk()
        return None

    def _show_outline(self):
        self._cube.SetBounds(bounds(self._cut.geometries))
        self._outline.SetVisibility(True)
        self._hide_timer.start()
        self._viewport.render_vtk()
        return None

    def _hide_outline(self):
        self._hide_timer.stop()
        self._outline.SetVisibility(False)
        self._viewport.render_vtk()
        return None


class ClipInteractorStyle(vtk.vtkInteractorStyleTrackballCamera):
    """Trackball camera that hands right-button drags and ``F`` to a ClipMode.

    Parameters
    ----------
    mode : ClipMode
        Mode receiving the events.
    """

    def __init__(self, mode: ClipMode):
        super().__init__()
        self._mode = mode
        self._right_down = False
        self._observers = [
            self.AddObserver("RightButtonPressEvent", self._on_right_press),
            self.AddObserver("RightButtonReleaseEvent", self._on_right_release),
            self.AddObserver("MouseMoveEvent", self._on_mouse_move),
            self.AddObserver("CharEvent", self._on_char),
        ]

    def cleanup(self) -> None:
        """Remove the event observers."""
        for tag in self._observers:
            self.RemoveObserver(tag)
        self._observers = []
        return None

    def _on_right_press(self, obj, event):
        self._right_down = True
        self._mode.right_press(*self.GetInteractor().GetEventPosition())
        return None

    def _on_right_release(self, obj, event):
        self._right_down = False
        self._mode.right_release(*self.GetInteractor().GetEventPosition())
        return None

    def _on_mouse_move(self, obj, event):
        if not self._right_down:
            self.OnMouseMove()
            return None

        interactor = self.GetInteractor()
        x, y = interactor.GetEventPosition()
        self._mode.right_move(x, y, bool(interactor.GetShiftKey()))
        return None

    def _on_char(self, obj, event):
        key = self.GetInteractor().GetKeySym()
        if key is not None and key.lower() == "f":
            self._mode.key("f")
            return None
        self.OnChar()
        return None
