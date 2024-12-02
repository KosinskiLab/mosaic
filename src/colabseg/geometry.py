""" Atomic Geometry class displayed by the vtk viewer.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""
from typing import Tuple

import vtk
from vtk.util import numpy_support
import numpy as np

BASE_COLOR = (0.7, 0.7, 0.7)


class Geometry:
    def __init__(
        self,
        points=None,
        normals=None,
        color=BASE_COLOR,
        sampling_rate=np.ones(3),
        meta={},
    ):
        self._points = vtk.vtkPoints()
        self._cells = vtk.vtkCellArray()
        self._normals = vtk.vtkFloatArray()
        self._normals.SetNumberOfComponents(3)
        self._normals.SetName("Normals")

        self._data = vtk.vtkPolyData()
        self._data.SetPoints(self._points)
        self._data.SetVerts(self._cells)

        self._actor = self.create_actor()
        self._sampling_rate = sampling_rate

        self._meta = meta
        self._default_color = color
        self._representation = "pointcloud"

        if points is not None:
            self.add_points(points)

        if normals is not None:
            self.add_normals(normals)

        # self.change_representation("pointcloud_normals")
        self.set_appearance(size=8)
        self.set_color(color)

    def __getstate__(self):
        return {
            "points": self.points,
            "normals": self.normals,
            "sampling_rate": self.sampling_rate,
            "meta": self._meta,
        }

    def __getitem__(self, idx):
        """
        Array-like indexing of geometry using integer, slice or boolean/interger
        numpy array.
        """
        if isinstance(idx, (int, np.integer)):
            idx = [idx]
        elif isinstance(idx, slice) or idx is ...:
            idx = np.arange(self.get_number_of_points())[idx]

        idx = np.asarray(idx)
        if idx.dtype == bool:
            idx = np.where(idx)[0]

        normals = None
        if self.normals is not None:
            normals = self.normals[idx]

        return Geometry(
            points=self.points[idx],
            normals=normals,
            color=self._default_color,
            sampling_rate=self._sampling_rate,
            meta=self._meta.copy(),
        )

    @classmethod
    def merge(cls, clouds):
        if not len(clouds):
            raise ValueError("No point clouds provided for merging")

        points, normals = [], []
        has_normals = any(cloud.normals is not None for cloud in clouds)
        for cloud in clouds:
            points.append(cloud.points)
            if not has_normals:
                continue
            normals = cloud.normals
            if normals is None:
                normals = np.zeros_like(cloud.points)

        normals = np.concatenate(normals, axis=0) if has_normals else None
        return cls(
            points=np.concatenate(points, axis=0),
            normals=normals,
            sampling_rate=clouds[0]._sampling_rate,
        )

    def __setstate__(self, state):
        self.__init__(**state)

    @property
    def actor(self):
        return self._actor

    @property
    def visible(self):
        return self.actor.GetVisibility()

    @property
    def sampling_rate(self):
        return self._sampling_rate

    @property
    def points(self):
        return numpy_support.vtk_to_numpy(self._data.GetPoints().GetData())

    @property
    def normals(self):
        normals = self._data.GetPointData().GetNormals()
        if normals is not None:
            normals = np.asarray(normals)
        return normals

    def add_points(self, points):
        points = np.asarray(points, dtype=np.float32)
        for i in range(points.shape[0]):
            point_id = self._points.InsertNextPoint(points[i])
            self._cells.InsertNextCell(1)
            self._cells.InsertCellPoint(point_id)
        self._data.Modified()

    def add_normals(self, normals):
        normals = np.asarray(normals, dtype=np.float32)
        if normals.shape != self.points.shape:
            raise ValueError("Number of normals must match number of points.")

        self._normals.Reset()
        for normal in normals:
            self._normals.InsertNextTuple3(*normal)

        self._data.GetPointData().SetNormals(self._normals)
        self._data.Modified()

    def set_color(self, color: Tuple[int] = None):
        if color is None:
            color = self._default_color
        self.color_points(range(self._points.GetNumberOfPoints()), color=color)

    def set_visibility(self, visibility: bool = True):
        return self.actor.SetVisibility(visibility)

    def toggle_visibility(self):
        return self.set_visibility(not self.visible)

    def set_appearance(
        self,
        size=8,
        opacity=1.0,
        render_spheres=True,
        ambient=0.3,
        diffuse=0.7,
        specular=0.2,
    ):
        prop = self._actor.GetProperty()

        if render_spheres:
            prop.SetRenderPointsAsSpheres(True)

        if getattr(self, "_representation", None) in ("mesh", "mesh_edges"):
            opacity = 0.3

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

    def subset(self, indices):
        subset = self[indices]
        return self.swap_data(subset.points, normals=subset.normals)

    def swap_data(self, new_points, normals=None):
        target_representation = self._representation
        if self._representation != "pointcloud":
            self.change_representation("pointcloud")

        self._points.Reset()
        self._cells.Reset()
        self._normals.Reset()

        self.add_points(new_points)
        if normals is not None:
            self.add_normals(normals)

        self._data.SetPoints(self._points)
        self._data.SetVerts(self._cells)
        self._data.Modified()

        self.set_color()
        self.change_representation(target_representation)

    def change_representation(self, representation: str = "pointcloud") -> int:
        supported = ["pointcloud", "pointcloud_normals", "mesh", "wireframe"]
        representation = representation.lower()

        if representation not in supported:
            raise ValueError(f"Supported representations are {', '.join(supported)}.")

        if representation == self._representation:
            return 0

        if representation in ["mesh", "wireframe"]:
            faces = self._meta.get("faces", None)
            if faces is None or "points" not in self._meta:
                print(
                    "Points and face data required for surface/wireframe representation."
                )
                return -1

        # Gymnastics, because fits are currently still allowed to own samples
        _save = ["pointcloud", "pointcloud_normals"]
        if self._representation in _save and representation not in _save:
            self._original_data = vtk.vtkPolyData()
            self._original_data.DeepCopy(self._data)

        if representation in _save and hasattr(self, "_original_data"):
            self._data.Reset()
            normals = self._original_data.GetPointData().GetNormals()
            if normals is not None:
                self._normals = normals
            self._points = self._original_data.GetPoints()
            self._cells = self._original_data.GetVerts()
            self._data.SetPoints(self._points)
            self._data.SetVerts(self._cells)
            self._data.GetPointData().SetNormals(self._normals)
            delattr(self, "_original_data")

        mapper = self.actor.GetMapper()
        mapper.SetInputConnection(None)
        mapper.SetInputData(None)

        self._actor.SetMapper(vtk.vtkPolyDataMapper())
        mapper, prop = self.actor.GetMapper(), self._actor.GetProperty()
        if representation == "pointcloud":
            if hasattr(self, "_glyph_mapper"):
                delattr(self, "_glyph_mapper")
            prop.SetRepresentationToPoints()
            mapper.SetInputData(self._data)

        elif representation == "pointcloud_normals":
            arrow = vtk.vtkArrowSource()
            arrow.SetTipResolution(16)
            arrow.SetShaftResolution(16)
            arrow.SetTipLength(0.3)
            arrow.SetTipRadius(0.1)

            points = self.points
            scale = np.multiply(np.max(points.max(axis=0) - points.min(axis=0)), 0.0005)

            glyph = vtk.vtkGlyph3D()
            glyph.SetInputData(self._data)
            glyph.SetSourceConnection(arrow.GetOutputPort())
            glyph.SetVectorModeToUseNormal()
            glyph.SetScaleFactor(scale)
            glyph.OrientOn()
            mapper.SetInputConnection(glyph.GetOutputPort())

        elif representation in ("mesh", "wireframe"):
            self._cells.Reset()
            self._points.Reset()
            self.add_points(self._meta["points"])
            self.add_faces(self._meta["faces"])
            if "normals" in self._meta:
                self.add_normals(self._meta["normals"])

            self._data.SetPolys(self._cells)
            mapper.SetInputData(self._data)

            if representation == "wireframe":
                prop.SetRepresentationToWireframe()
            else:
                prop.SetRepresentationToSurface()
                prop.SetEdgeVisibility(True)
                prop.SetOpacity(0.3)

        self._representation = representation
        mapper.Update()
        return 0

    def add_faces(self, faces):
        if faces.shape[1] != 3:
            raise ValueError("Only triangular faces are supported")

        for face in faces:
            self._cells.InsertNextCell(3)
            for vertex_idx in face:
                self._cells.InsertCellPoint(vertex_idx)
        self._data.Modified()
