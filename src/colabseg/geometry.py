from typing import Tuple

import vtk
import numpy as np

BASE_COLOR = (0.7, 0.7, 0.7)


class PointCloud:
    def __init__(self, points=None, color=BASE_COLOR, sampling_rate=None, meta={}):
        self._points = vtk.vtkPoints()
        self._cells = vtk.vtkCellArray()

        self._data = vtk.vtkPolyData()
        self._data.SetPoints(self._points)
        self._data.SetVerts(self._cells)

        self._actor = self.create_actor()
        self._sampling_rate = sampling_rate

        self._meta = meta
        self._default_color = color

        if points is not None:
            self.add_points(points)

        self.set_appearance(size=8)
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
    def visible(self):
        return self._actor.GetVisibility()

    @property
    def points(self):
        return np.asarray(self._points.GetData())

    def add_points(self, points):
        points = np.asarray(points, dtype=np.float32)
        for i in range(points.shape[0]):
            point_id = self._points.InsertNextPoint(points[i])
            self._cells.InsertNextCell(1)
            self._cells.InsertCellPoint(point_id)
        self._data.Modified()

    def set_color(self, color: Tuple[int] = None):
        if color is None:
            color = self._default_color
        self.color_points(range(self._points.GetNumberOfPoints()), color=color)

    def set_visibility(self, visibility: bool = True):
        return self._actor.SetVisibility(visibility)

    def toggle_visibility(self):
        return self.set_visibility(not self.visible)

    def set_appearance(
        self,
        size=8,
        opacity=0.8,
        render_spheres=True,
        ambient=0.3,
        diffuse=0.7,
        specular=0.2,
    ):
        prop = self._actor.GetProperty()

        if render_spheres:
            prop.SetRenderPointsAsSpheres(True)

        prop.SetPointSize(size)
        prop.SetOpacity(opacity)
        prop.SetAmbient(ambient)
        prop.SetDiffuse(diffuse)
        prop.SetSpecular(specular)

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
        self._cells.Reset()

        self.add_points(new_points)

        self._data.SetPoints(self._points)
        self._data.SetVerts(self._cells)
        self._data.Modified()

        self.set_color()


class TriangularMesh(PointCloud):
    def __init__(self, points=None, faces=None, **kwargs):
        super().__init__(**kwargs)
        self._data.SetPolys(self._cells)

        if points is not None:
            self.add_points(points)
        if faces is not None:
            self.add_faces(faces)

        self.set_color(kwargs.get("color", BASE_COLOR))

    def __getstate__(self):
        state = super().__getstate__()
        state.update({"faces": self.faces})
        return state

    def __setstate__(self, state):
        faces = state.pop("faces", None)
        super().__init__(**state)
        if faces is not None:
            self.add_faces(faces)

    @property
    def faces(self):
        cells = []
        idList = vtk.vtkIdList()
        for i in range(self._cells.GetNumberOfCells()):
            self._cells.GetCell(i, idList)
            cells.append([idList.GetId(j) for j in range(idList.GetNumberOfIds())])
        return np.array(cells)

    def set_color(self, color: Tuple[int] = None):
        if color is None:
            color = self._default_color
        self.actor.GetProperty().SetColor(color)
        self.actor.GetProperty().SetRepresentationToSurface()

    def color_faces(self, face_ids: set, color: Tuple[float]):
        colors = vtk.vtkUnsignedCharArray()
        colors.SetNumberOfComponents(3)
        colors.SetName("Colors")

        default_color = self.actor.GetProperty().GetColor()
        color = tuple(int(c * 255) for c in color)
        default_color = tuple(int(c * 255) for c in self._default_color)

        num_faces = self._cells.GetNumberOfCells()
        for i in range(num_faces):
            if i in face_ids:
                colors.InsertNextTuple3(*color)
            else:
                colors.InsertNextTuple3(*default_color)

        self._data.GetCellData().SetScalars(colors)
        self._data.Modified()

    def add_faces(self, faces):
        if faces.shape[1] != 3:
            raise ValueError("Only triangular faces are supported")

        for face in faces:
            self._cells.InsertNextCell(3)
            for vertex_idx in face:
                self._cells.InsertCellPoint(vertex_idx)
        self._data.Modified()

    def swap_data(self, new_points, new_faces):
        self._points.Reset()
        self._cells.Reset()

        self.add_points(new_points)
        self.add_faces(new_faces)

        self._data.SetPolys(self._cells)
        self._data.Modified()
        self.set_color()
