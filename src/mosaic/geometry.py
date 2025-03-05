""" Atomic Geometry class displayed by the vtk viewer.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import warnings
from typing import Tuple, List, Dict

import vtk
import numpy as np
from vtk.util import numpy_support

from .utils import find_closest_points, find_closest_points_cutoff, NORMAL_REFERENCE

BASE_COLOR = (0.7, 0.7, 0.7)


class Geometry:
    def __init__(
        self,
        points=None,
        normals=None,
        color=BASE_COLOR,
        sampling_rate=None,
        meta=None,
        vtk_actor=None,
        **kwargs,
    ):
        self._points = vtk.vtkPoints()
        self._cells = vtk.vtkCellArray()
        self._normals = vtk.vtkFloatArray()
        self._normals.SetNumberOfComponents(3)
        self._normals.SetName("Normals")

        self._data = vtk.vtkPolyData()
        self._data.SetPoints(self._points)
        self._data.SetVerts(self._cells)

        self._actor = self.create_actor(vtk_actor)

        self.sampling_rate = sampling_rate
        self._meta = {} if meta is None else meta
        self._representation = "pointcloud"

        if points is not None:
            self.add_points(points)

        if normals is None and points is not None:
            normals = np.full_like(points, fill_value=NORMAL_REFERENCE)

        if normals is not None:
            self.add_normals(normals)

        self._appearance = {
            "size": 8,
            "opacity": 1.0,
            "ambient": 0.3,
            "diffuse": 0.7,
            "specular": 0.2,
            "render_spheres": True,
            "base_color": color,
        }
        self.set_appearance(**self._appearance)

    @property
    def sampling_rate(self):
        return np.asarray(self._sampling_rate).astype(np.float32)

    @sampling_rate.setter
    def sampling_rate(self, sampling_rate):
        if sampling_rate is None:
            sampling_rate = np.ones(3, dtype=np.float32)
        sampling_rate = np.asarray(sampling_rate, dtype=np.float32)
        sampling_rate = np.repeat(sampling_rate, 3 // sampling_rate.size)
        self._sampling_rate = sampling_rate

    def __getstate__(self):
        return {
            "points": self.points,
            "normals": self.normals,
            "sampling_rate": self.sampling_rate,
            "meta": self._meta,
            "visible": self.visible,
            "appearance": self._appearance,
            "representation": self._representation,
        }

    def __setstate__(self, state):
        visible = state.pop("visible", True)
        appearance = state.pop("appearance", {})
        self.__init__(**state)
        self.set_visibility(visible)

        representation = state.get("representation", False)
        if representation:
            self.change_representation(representation)

        self.set_appearance(**appearance)

    def __getitem__(self, idx):
        """
        Array-like indexing of geometry using int/bool numpy arrays, slices or ellipses
        """
        if isinstance(idx, (int, np.integer)):
            idx = [idx]
        elif isinstance(idx, slice) or idx is ...:
            idx = np.arange(self.get_number_of_points())[idx]

        idx = np.asarray(idx)
        if idx.dtype == bool:
            idx = np.where(idx)[0]

        normals = None
        if isinstance(self.normals, np.ndarray):
            if np.max(idx) < self.normals.shape[0]:
                normals = self.normals[idx].copy()

        ret = Geometry(
            points=self.points[idx].copy(),
            normals=normals,
            color=self._appearance["base_color"],
            sampling_rate=self._sampling_rate,
            meta=self._meta.copy(),
        )

        # Avoid clashes from properties of classes inheriting from Geometry
        ret._appearance.update(
            {k: v for k, v in self._appearance.items() if k in ret._appearance}
        )
        return ret

    @classmethod
    def merge(cls, geometries):
        if not len(geometries):
            raise ValueError("No geometries provided for merging")

        points, normals = [], []
        has_normals = any(geometry.normals is not None for geometry in geometries)
        for geometry in geometries:
            points.append(geometry.points)
            if not has_normals:
                continue
            normals = geometry.normals
            if normals is None:
                normals = np.zeros_like(geometry.points)

        normals = np.concatenate(normals, axis=0) if has_normals else None
        ret = cls(
            points=np.concatenate(points, axis=0),
            normals=normals,
            sampling_rate=geometries[0]._sampling_rate,
            color=geometries[0]._appearance["base_color"],
            meta=geometries[0]._meta.copy(),
        )
        ret._appearance.update(geometries[0]._appearance)
        return ret

    @property
    def actor(self):
        return self._actor

    @property
    def visible(self):
        return self.actor.GetVisibility()

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
        if points.shape[1] != 3:
            warnings.warn("Only 3D point clouds are supported.")
            return -1

        if self.points.shape[0] != 0:
            points = np.concatenate((self.points, points))

        vertex_cells = vtk.vtkCellArray()
        idx = np.arange(points.shape[0], dtype=int)
        cells = np.column_stack((np.ones(idx.size, dtype=int), idx)).flatten()
        vertex_cells.SetCells(idx.size, numpy_support.numpy_to_vtkIdTypeArray(cells))

        self._points.SetData(numpy_support.numpy_to_vtk(points, deep=True))
        self._data.SetVerts(vertex_cells)
        self._data.SetPoints(self._points)
        self._data.Modified()

    def add_normals(self, normals):
        normals = np.asarray(normals, dtype=np.float32)
        if normals.shape != self.points.shape:
            warnings.warn("Number of normals must match number of points.")
            return -1

        normals_vtk = numpy_support.numpy_to_vtk(normals, deep=True)
        normals_vtk.SetName("Normals")
        self._data.GetPointData().SetNormals(normals_vtk)
        self._data.Modified()

    def add_faces(self, faces):
        faces = np.asarray(faces, dtype=int)
        if faces.shape[1] != 3:
            warnings.warn("Only triangular faces are supported.")
            return -1

        faces = np.concatenate(
            (np.full((faces.shape[0], 1), fill_value=3), faces), axis=1, dtype=int
        )
        poly_cells = vtk.vtkCellArray()
        poly_cells.SetCells(
            faces.shape[0], numpy_support.numpy_to_vtkIdTypeArray(faces.ravel())
        )
        self._data.SetPolys(poly_cells)
        self._data.Modified()

    def set_color(self, color: Tuple[int] = None):
        if color is None:
            color = self._appearance["base_color"]
        self.color_points(range(self._points.GetNumberOfPoints()), color=color)

    def set_visibility(self, visibility: bool = True):
        return self.actor.SetVisibility(visibility)

    def toggle_visibility(self):
        return self.set_visibility(not self.visible)

    def set_appearance(
        self,
        size: int = None,
        opacity: float = None,
        render_spheres: bool = None,
        ambient: float = None,
        diffuse: float = None,
        specular: float = None,
        color: Tuple[float] = None,
        **kwargs,
    ):
        params = {
            "size": size,
            "opacity": opacity,
            "render_spheres": render_spheres,
            "ambient": ambient,
            "diffuse": diffuse,
            "specular": specular,
            **kwargs,
        }
        self._appearance.update({k: v for k, v in params.items() if v is not None})
        self._set_appearance()

        if color is None:
            color = self._appearance.get("base_color", (0.7, 0.7, 0.7))
        self.set_color(color)

    def _set_appearance(self):
        prop = self._actor.GetProperty()

        prop.SetRenderPointsAsSpheres(True)
        if not self._appearance.get("render_spheres", True):
            prop.SetRenderPointsAsSpheres(False)

        prop.SetPointSize(self._appearance.get("size", 8))
        prop.SetOpacity(self._appearance.get("opacity", 1.0))
        prop.SetAmbient(self._appearance.get("ambient", 0.3))
        prop.SetDiffuse(self._appearance.get("diffuse", 0.7))
        prop.SetSpecular(self._appearance.get("specular", 0.2))

    def create_actor(self, actor=None):
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(self._data)

        mapper.SetScalarModeToDefault()
        mapper.SetResolveCoincidentTopologyToPolygonOffset()

        if actor is None:
            actor = vtk.vtkActor()

        actor.SetMapper(mapper)
        return actor

    def get_number_of_points(self):
        return self._points.GetNumberOfPoints()

    def set_scalars(self, scalars, color_lut, scalar_range=None, use_point=False):
        if isinstance(scalars, np.ndarray):
            scalars = numpy_support.numpy_to_vtk(scalars)

        mapper = self._actor.GetMapper()
        mapper.GetInput().GetPointData().SetScalars(scalars)
        mapper.SetLookupTable(color_lut)
        if scalar_range is not None:
            mapper.SetScalarRange(*scalar_range)
        mapper.ScalarVisibilityOn()
        if use_point:
            mapper.SetScalarModeToUsePointData()

        return self._actor.Modified()

    def color_points(self, point_ids: set, color: Tuple[float]):
        """
        Color specific points in the geometry.

        Parameters:
        -----------
        point_ids : set
            Set of point indices to color
        color : tuple of float
            RGB color values (0-1) to apply to selected points
        """
        mapper = self._actor.GetMapper()
        prop = self._actor.GetProperty()
        if self._representation in ("normals", "pointcloud_normals"):
            mapper.ScalarVisibilityOff()
            return prop.SetColor(*color)

        # Remove highlight_color hue when switching back from modes above
        prop.SetColor(*self._appearance["base_color"])
        n_points = self._points.GetNumberOfPoints()
        point_ids = [x for x in point_ids if x < n_points]
        colors = np.full(
            (n_points, 3),
            fill_value=[x * 255 for x in self._appearance["base_color"]],
            dtype=np.float32,
        )
        colors[point_ids] = [x * 255 for x in color]
        return self.set_point_colors(colors)

    def set_point_colors(self, colors):
        """
        Set individual colors for each point in the geometry.

        Parameters:
        -----------
        colors : array-like
            RGB colors for each point. Shape should be (n_points, 3) with values 0-255
        """
        if len(colors) != self._points.GetNumberOfPoints():
            raise ValueError("Number of colors must match number of points")

        colors_vtk = vtk.util.numpy_support.numpy_to_vtk(
            colors,
            deep=False,
            array_type=vtk.VTK_UNSIGNED_CHAR,
        )

        colors_vtk.SetName("Colors")
        colors_vtk.SetNumberOfComponents(3)

        self._data.GetPointData().SetScalars(colors_vtk)
        self._data.Modified()

    def subset(self, indices):
        subset = self[indices]
        return self.swap_data(subset.points, normals=subset.normals)

    def swap_data(self, points, normals=None, faces=None):
        self._points.Reset()
        self._cells.Reset()
        self._normals.Reset()

        self.add_points(points)
        if normals is not None:
            self.add_normals(normals)

        if faces is not None:
            self.add_faces(faces)

        self.set_color()
        return self.change_representation(self._representation)

    def change_representation(self, representation: str = "pointcloud") -> int:
        supported = [
            "pointcloud",
            "pointcloud_normals",
            "mesh",
            "wireframe",
            "normals",
            "surface",
        ]
        representation = representation.lower()

        if representation not in supported:
            raise ValueError(f"Supported representations are {', '.join(supported)}.")

        if representation == self._representation:
            return 0

        if representation in ["mesh", "wireframe", "surface"]:
            is_mesh = hasattr(self._meta.get("fit", None), "mesh")
            is_surface = self._meta.get("faces") is None or "points" not in self._meta
            if not is_mesh and not is_surface:
                print(
                    "Points and face data required for surface/wireframe representation."
                )
                return -1

        # Gymnastics, because fits are currently still allowed to own samples
        _save = ["pointcloud", "pointcloud_normals", "normals"]
        if self._representation in _save and representation not in _save:
            self._original_data = vtk.vtkPolyData()
            self._original_data.DeepCopy(self._data)

        if self._representation == "surface" and representation != "surface":
            self._data.SetVerts(self._original_verts)
            self._original_verts = None

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
            self._original_data = None
            delattr(self, "_original_data")

        # Consistent normal rendering across representations
        if representation in ("pointcloud_normals", "normals"):
            arrow = vtk.vtkArrowSource()
            arrow.SetTipResolution(6)
            arrow.SetShaftResolution(6)
            arrow.SetTipRadius(0.08)
            arrow.SetShaftRadius(0.02)

            normal_scale = 0.1 * np.max(self.sampling_rate)

            glyph = vtk.vtkGlyph3D()
            glyph.SetSourceConnection(arrow.GetOutputPort())
            glyph.SetVectorModeToUseNormal()
            glyph.SetScaleFactor(normal_scale)
            glyph.SetColorModeToColorByScalar()
            glyph.OrientOn()

        self._appearance.update({"opacity": 1, "size": 8})
        self._actor.SetMapper(vtk.vtkPolyDataMapper())
        mapper, prop = self._actor.GetMapper(), self._actor.GetProperty()
        prop.SetOpacity(self._appearance["opacity"])
        prop.SetPointSize(self._appearance["size"])
        if representation == "pointcloud":
            prop.SetRepresentationToPoints()
            mapper.SetInputData(self._data)

        elif representation == "pointcloud_normals":
            vertex_glyph = vtk.vtkVertexGlyphFilter()
            vertex_glyph.SetInputData(self._data)
            vertex_glyph.Update()

            glyph.SetInputConnection(vertex_glyph.GetOutputPort())
            append = vtk.vtkAppendPolyData()
            append.AddInputData(vertex_glyph.GetOutput())
            append.AddInputConnection(glyph.GetOutputPort())
            append.Update()
            mapper.SetInputConnection(append.GetOutputPort())

        elif representation == "normals":
            glyph.SetInputData(self._data)
            mapper.SetInputConnection(glyph.GetOutputPort())

        elif representation in ("mesh", "wireframe", "surface"):
            self._cells.Reset()
            self._points.Reset()

            mesh = self._meta.get("fit", None)
            if not hasattr(mesh, "vertices"):
                return None
            self.add_points(mesh.vertices)
            self.add_faces(mesh.triangles)
            self.add_normals(mesh.compute_vertex_normals())

            if representation == "surface":
                self._original_verts = self._data.GetVerts()
                self._data.SetVerts(None)
            mapper.SetInputData(self._data)

            if representation == "wireframe":
                self._data.SetVerts(None)
                prop.SetRepresentationToWireframe()
            else:
                prop.SetRepresentationToSurface()
                prop.SetEdgeVisibility(representation == "mesh")

                self._appearance["size"] = 2
                prop.SetPointSize(self._appearance["size"])

        self._representation = representation
        return 0

    def compute_distance(self, query_points: np.ndarray, cutoff: float = None):
        model = self._meta.get("fit", None)
        if hasattr(model, "compute_distance"):
            return model.compute_distance(query_points)

        if cutoff is not None:
            indices = find_closest_points_cutoff(self.points, query_points, cutoff)
            distances = np.full(indices.size, fill_value=cutoff + 1)
            distances[indices] = 0
            return distances
        return find_closest_points(self.points, query_points, k=1)[1]


class PointCloud(Geometry):
    pass


class VolumeGeometry(Geometry):
    def __init__(
        self, volume: np.ndarray = None, volume_sampling_rate=np.ones(3), **kwargs
    ):
        super().__init__(**kwargs)
        self._volume = None
        if volume is None:
            return None

        self._volume = vtk.vtkImageData()
        self._volume.SetSpacing(volume_sampling_rate)
        self._volume.SetDimensions(volume.shape[::-1])
        self._volume.AllocateScalars(vtk.VTK_FLOAT, 1)
        self._raw_volume = volume
        volume_vtk = numpy_support.numpy_to_vtk(volume.ravel(), deep=True)
        self._volume.GetPointData().SetScalars(volume_vtk)

        bounds = [0.0] * 6
        self._volume.GetBounds(bounds)
        transform = vtk.vtkTransform()
        transform.Translate(
            [-(b[1] - b[0]) * 0.5 for b in zip(bounds[::2], bounds[1::2])]
        )

        self._volume_sampling_rate = volume_sampling_rate
        transformFilter = vtk.vtkTransformFilter()
        transformFilter.SetInputData(self._volume)
        transformFilter.SetTransform(transform)
        transformFilter.Update()

        # Render volume isosurface as vtk glpyh object
        self._surface = vtk.vtkContourFilter()
        self._surface.SetInputConnection(transformFilter.GetOutputPort())
        self._surface.GenerateValues(1, volume.min(), volume.max())

        # Per glyph orientation and coloring
        self._glyph = vtk.vtkGlyph3D()
        self._glyph.SetInputData(self._data)
        self._glyph.SetSourceConnection(self._surface.GetOutputPort())
        self._glyph.SetVectorModeToUseNormal()
        self._glyph.SetScaleModeToDataScalingOff()
        self._glyph.SetColorModeToColorByScalar()
        self._glyph.OrientOn()

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(self._glyph.GetOutputPort())
        self._actor.SetMapper(mapper)

    def __getstate__(self):
        state = super().__getstate__()

        if self._volume is not None:
            state.update(
                {
                    "volume": self._raw_volume,
                    "volume_sampling_rate": self._volume_sampling_rate,
                }
            )
        return state

    def update_isovalue(self, upper, lower: float = 0):
        return self._surface.SetValue(int(lower), upper)

    def update_isovalue_quantile(
        self, upper_quantile: float, lower_quantile: float = 0.0
    ):
        if not (0 <= lower_quantile <= 1 and 0 <= upper_quantile <= 1):
            raise ValueError("Quantiles must be between 0 and 1")

        if lower_quantile >= upper_quantile:
            raise ValueError("Upper quantile must be greater than lower quantile")

        lower_value = np.quantile(self._raw_volume, lower_quantile)
        upper_value = np.quantile(self._raw_volume, upper_quantile)
        return self.update_isovalue(upper_value, lower_value)

    def change_representation(self, *args, **kwargs) -> int:
        return -1

    def set_appearance(self, isovalue_percentile=0.99, **kwargs):
        if hasattr(self, "_raw_volume"):
            self.update_isovalue_quantile(upper_quantile=isovalue_percentile)
        super().set_appearance(**kwargs)


class GeometryTrajectory(Geometry):
    def __init__(self, trajectory: List[Dict], **kwargs):
        super().__init__(**kwargs)
        self._trajectory = trajectory

    def __getstate__(self):
        state = super().__getstate__()
        state.update({"trajectory": self._trajectory})
        return state

    @property
    def frames(self):
        return len(self._trajectory)

    def display_frame(self, frame_idx: int):
        if frame_idx < 0 or frame_idx > self.frames:
            return None

        appearance = self._appearance.copy()
        meta = self._trajectory[frame_idx]

        mesh = meta.get("fit", None)
        if not hasattr(mesh, "mesh"):
            return None

        self.swap_data(
            mesh.vertices, faces=mesh.triangles, normals=mesh.compute_vertex_normals()
        )
        self._meta.update(meta)
        return self.set_appearance(**appearance)

    def change_representation(self, *args, **kwargs):
        # This avoid a but in change_representation when saving previous datasets
        # TODO: Adjust Geometry.change_representation when parametriations can
        # no longer own samples from the underlying parametrization object
        if self._representation == "surface":
            self._representation = None
        return super().change_representation(*args, **kwargs)
