import numpy as np
import vtk
from typing import Dict, List

from .parametrization import Parametrization, PARAMETRIZATION_TYPE

PARAMETRIZATION_TYPE = PARAMETRIZATION_TYPE


class ParametrizationManager:
    def __init__(self):
        self.fits: Dict[int, Parametrization] = {}
        self.mesh_actors: Dict[int, vtk.vtkActor] = {}
        self.original_points: Dict[int, np.ndarray] = {}
        self.next_id = 0

    def add_fit(self, parametrization: Parametrization, points: np.ndarray):
        fit_id = self.next_id
        self.next_id += 1

        self.fits[fit_id] = parametrization
        self.original_points[fit_id] = points

        mesh = self.create_mesh_from_parametrization(parametrization)
        actor = vtk.vtkActor()
        actor.SetMapper(vtk.vtkPolyDataMapper())
        actor.GetMapper().SetInputData(mesh)
        self.mesh_actors[fit_id] = actor

        return fit_id

    def remove_fit(self, fit_id: int):
        if fit_id in self.fits:
            del self.fits[fit_id]
            del self.original_points[fit_id]
            del self.mesh_actors[fit_id]

    def get_actor(self, fit_id: int) -> vtk.vtkActor:
        return self.mesh_actors.get(fit_id)

    def get_all_actors(self) -> List[vtk.vtkActor]:
        return list(self.mesh_actors.values())

    def create_mesh_from_parametrization(
        self, parametrization: Parametrization
    ) -> vtk.vtkPolyData:
        points = parametrization.sample(1000)

        vtk_points = vtk.vtkPoints()
        for point in points:
            vtk_points.InsertNextPoint(point)

        poly_data = vtk.vtkPolyData()
        poly_data.SetPoints(vtk_points)

        delaunay = vtk.vtkDelaunay3D()
        delaunay.SetInputData(poly_data)
        delaunay.Update()

        surface_filter = vtk.vtkGeometryFilter()
        surface_filter.SetInputConnection(delaunay.GetOutputPort())
        surface_filter.Update()

        return surface_filter.GetOutput()
