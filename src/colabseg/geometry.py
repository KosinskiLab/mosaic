from typing import Tuple

import vtk
import numpy as np

BASE_COLOR = (0.7, 0.7, 0.7)


class PointCloud:
    def __init__(self, points=None, color=BASE_COLOR, sampling_rate=None, meta={}):
        self._points = vtk.vtkPoints()
        self._verts = vtk.vtkCellArray()

        self._data = vtk.vtkPolyData()
        self._data.SetPoints(self._points)
        self._data.SetVerts(self._verts)

        self._actor = self.create_actor()
        self._sampling_rate = sampling_rate

        self._meta = meta
        self._default_color = color

        if points is not None:
            self.add_points(points)

        self.set_size(4)
        self.set_color(color)

    def __getstate__(self):
        return {
            "points": self.points,
            "sampling_rate": self._sampling_rate,
            "meta": self._meta,
        }

    def __setstate__(self, state):
        self.__init__(**state)

    @property
    def actor(self):
        return self._actor

    @property
    def points(self):
        return np.asarray(self._points.GetData())

    def add_points(self, points):
        for point in points:
            point_id = self._points.InsertNextPoint(point)
            self._verts.InsertNextCell(1)
            self._verts.InsertCellPoint(point_id)
        self._data.Modified()

    def set_color(self, color: Tuple[int] = None):
        if color is None:
            color = self._default_color
        self.color_points(range(self._points.GetNumberOfPoints()), color=color)

    def set_size(self, size: int = 4):
        self._actor.GetProperty().SetPointSize(size)

    def set_opacity(self, opacity: float = 0.6):
        self._actor.GetProperty().SetOpacity(opacity)

    def create_actor(self):
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(self._data)

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        return actor

    def get_number_of_points(self):
        return self._points.GetNumberOfPoints()

    def _update_colors(self):
        for i in range(self._points.GetNumberOfPoints()):
            if i in self._highlighted_points:
                self._colors.SetTuple3(i, *self._color_to_rgb(self._highlight_color))
            else:
                self._colors.SetTuple3(i, *self._color_to_rgb(self._global_color))
        self._data.GetPointData().SetScalars(self._colors)
        self._data.Modified()

    def color_points(self, point_ids: set, color: Tuple[float]):
        colors = vtk.vtkUnsignedCharArray()
        colors.SetNumberOfComponents(3)
        colors.SetName("Colors")

        default_color = self.actor.GetProperty().GetColor()

        color = tuple(int(c * 255) for c in color)
        default_color = tuple(int(c * 255) for c in self._default_color)

        for i in range(self._points.GetNumberOfPoints()):
            if i in point_ids:
                colors.InsertNextTuple3(*color)
            else:
                colors.InsertNextTuple3(*default_color)

        self._data.GetPointData().SetScalars(colors)
        self._data.Modified()

    def swap_data(self, new_points):
        self._points.Reset()
        self._verts.Reset()

        self.add_points(new_points)

        self._data.SetPoints(self._points)
        self._data.SetVerts(self._verts)
        self._data.Modified()

        self.set_color()


class TriangularMesh(PointCloud):
    def __init__(self, points=None, faces=None, **kwargs):
        super().__init__(**kwargs)
        self._data.SetPolys(self._verts)

    def set_color(self, color: Tuple[int] = None):
        if color is None:
            color = self._default_color
        self.actor.GetProperty().SetColor(color)

    def add_faces(self, faces):
        if faces.shape[1] != 3:
            raise ValueError("Only triangular faces are supported")

        for face in faces:
            self._polys.InsertNextCell(3)
            for vertex_idx in face:
                self._polys.InsertCellPoint(vertex_idx)
        self._data.Modified()

    def swap_data(self, new_points, new_faces):
        self._points.Reset()
        self._verts.Reset()

        self.add_points(new_points)
        self.add_faces(new_faces)
        self._data.SetPolys(self._verts)

        self._data.Modified()
        self.set_color()
