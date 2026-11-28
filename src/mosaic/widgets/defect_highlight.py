"""
Highlight a mesh defect on top of the mesh without touching its actor.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np
from qtpy.QtGui import QColor
from vtkmodules.util import numpy_support
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper, vtkRenderer

from ..meshing.check import MeshDefect
from ..stylesheets import Colors

__all__ = ["DefectHighlight"]


class DefectHighlight:
    """Semi-transparent patch over the faces around one mesh defect.

    Parameters
    ----------
    renderer : vtkRenderer
        Renderer the patch is added to.
    """

    def __init__(self, renderer: vtkRenderer):
        self.renderer = renderer
        self.defect: MeshDefect | None = None
        self._actor: vtkActor | None = None

    def show(self, vertices: np.ndarray, faces: np.ndarray, defect: MeshDefect) -> None:
        """Highlight ``defect`` and turn the camera towards it.

        Parameters
        ----------
        vertices : np.ndarray
            Mesh vertex coordinates, shape (N, 3).
        faces : np.ndarray
            Mesh triangles, shape (M, 3).
        defect : MeshDefect
            Defect of this mesh to show.
        """
        self.hide()
        vertices = np.asarray(vertices, dtype=np.float64)
        faces = np.asarray(faces, dtype=np.int64)

        selected = np.isin(faces, defect.vertices).any(axis=1)
        selected = np.isin(faces, np.unique(faces[selected])).any(axis=1)
        patch = faces[selected]

        points = vtkPoints()
        points.SetData(numpy_support.numpy_to_vtk(vertices, deep=True))
        cells = vtkCellArray()
        cells.SetData(
            3, numpy_support.numpy_to_vtkIdTypeArray(patch.ravel(), deep=True)
        )
        polydata = vtkPolyData()
        polydata.SetPoints(points)
        polydata.SetPolys(cells)

        mapper = vtkPolyDataMapper()
        mapper.SetInputData(polydata)
        mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(-2, -2)
        actor = vtkActor()
        actor.SetMapper(mapper)
        prop = actor.GetProperty()
        prop.SetColor(QColor(Colors.WARNING).getRgbF()[:3])
        prop.SetOpacity(0.55)
        prop.SetAmbient(0.5)
        self.renderer.AddActor(actor)
        self._actor, self.defect = actor, defect

        target = vertices[defect.vertices].mean(axis=0)
        direction = target - vertices.mean(axis=0)
        direction /= max(np.linalg.norm(direction), np.finfo(float).eps)
        distance = 2.5 * np.ptp(vertices, axis=0).max()
        camera = self.renderer.GetActiveCamera()
        camera.SetFocalPoint(*target)
        camera.SetPosition(*(target + direction * distance))
        self.renderer.ResetCameraClippingRange()
        return None

    def hide(self) -> None:
        """Remove the patch, if one is shown."""
        if self._actor is not None:
            self.renderer.RemoveActor(self._actor)
        self._actor, self.defect = None, None
        return None
