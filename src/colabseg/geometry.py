""" Atomic Geometry class displayed by the vtk viewer.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import warnings
from typing import Tuple, List, Dict

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
        self._sampling_rate = sampling_rate
        if self._sampling_rate is None:
            self._sampling_rate = np.ones(3)

        self._meta = {} if meta is None else meta
        self._representation = "pointcloud"

        if points is not None:
            self.add_points(np.asarray(points, dtype=np.float32))

        if normals is not None:
            self.add_normals(np.asarray(normals, dtype=np.float32))

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

    def __getstate__(self):
        return {
            "points": self.points,
            "normals": self.normals,
            "sampling_rate": self.sampling_rate,
            "meta": self._meta,
            "visible": self.visible,
            "appearance": self._appearance,
        }

    def __setstate__(self, state):
        visible = state.pop("visible", True)
        appearance = state.pop("appearance", {})
        self.__init__(**state)
        self.set_visibility(visible)
        self.set_appearance(**appearance)
        self._appearance.update(appearance)

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
        if isinstance(self.normals, np.ndarray):
            if np.max(idx) < self.normals.shape[0]:
                normals = self.normals[idx].copy()

        # ret = self.__class__(
        ret = Geometry(
            points=self.points[idx],
            normals=normals,
            color=self._appearance["base_color"],
            sampling_rate=self._sampling_rate,
            meta=self._meta.copy(),
        )
        ret._appearance.update(self._appearance)
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
            warnings.warn("Number of normals must match number of points.")
            return -1

        self._normals.Reset()
        for normal in normals:
            self._normals.InsertNextTuple3(*normal)

        self._data.GetPointData().SetNormals(self._normals)
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

    def color_points(self, point_ids: set, color: Tuple[float]):
        colors = vtk.vtkUnsignedCharArray()
        colors.SetNumberOfComponents(3)
        colors.SetName("Colors")

        color = tuple(int(c * 255) for c in color)
        default_color = tuple(int(c * 255) for c in self._appearance["base_color"])

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
            faces = self._meta.get("faces", None)
            if faces is None or "points" not in self._meta:
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

            # max_pos, min_pos = self.points.max(axis=0), self.points.min(axis=0)
            # bbox_diagonal = np.sqrt(np.sum((max_pos - min_pos) ** 2))

            # TODO: When importing files, make sure to use the actual sampling
            # rate not 1/scale; The same applies for importing meshes
            bbox_diagonal = 1000 * np.max(self._sampling_rate)

            glyph = vtk.vtkGlyph3D()
            glyph.SetSourceConnection(arrow.GetOutputPort())
            glyph.SetVectorModeToUseNormal()
            glyph.SetScaleFactor(bbox_diagonal * 0.0001)
            glyph.SetColorModeToColorByScalar()
            glyph.OrientOn()

        self._appearance["opacity"] = 1
        self._actor.SetMapper(vtk.vtkPolyDataMapper())
        mapper, prop = self._actor.GetMapper(), self._actor.GetProperty()
        prop.SetOpacity(self._appearance["opacity"])
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
            self.add_points(self._meta["points"])
            self.add_faces(self._meta["faces"])
            if "normals" in self._meta:
                self.add_normals(self._meta["normals"])

            self._data.SetPolys(self._cells)

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
                prop.SetOpacity(self._appearance["opacity"])

            # self._representation = "surface"
            # self.compute_curvature(curvature_type="gaussian")

        self._representation = representation
        return 0

    def compute_curvature(self, curvature_type="gaussian", color_map=None):
        """
        Compute and visualize curvature of the polydata surface.

        Parameters:
        -----------
        curvature_type : str
            Type of curvature to compute. Options are:
            - 'gaussian': Gaussian curvature
            - 'mean': Mean curvature
            - 'maximum': Maximum curvature
            - 'minimum': Minimum curvature
        color_map : tuple
            Optional color map range (min, max) for curvature visualization.
            If None, automatically computed from data range.

        Returns:
        --------
        int
            0 if successful, -1 if failed
        """
        if self._representation not in ["mesh", "surface"]:
            print("Curvature computation requires mesh or surface representation")
            return -1

        triangulate = vtk.vtkTriangleFilter()
        triangulate.SetInputData(self._data)
        triangulate.Update()

        normals = vtk.vtkPolyDataNormals()
        normals.SetInputData(triangulate.GetOutput())
        normals.ComputePointNormalsOn()
        normals.ComputeCellNormalsOn()
        normals.SplittingOff()
        normals.ConsistencyOn()
        normals.Update()

        curv_filter = vtk.vtkCurvatures()
        if curvature_type.lower() == "gaussian":
            curv_filter = vtk.vtkCurvatures()
            curv_filter.SetCurvatureTypeToGaussian()
        elif curvature_type.lower() == "mean":
            curv_filter = vtk.vtkCurvatures()
            curv_filter.SetCurvatureTypeToMean()
        elif curvature_type.lower() == "maximum":
            curv_filter = vtk.vtkCurvatures()
            curv_filter.SetCurvatureTypeToMaximum()
        elif curvature_type.lower() == "minimum":
            curv_filter = vtk.vtkCurvatures()
            curv_filter.SetCurvatureTypeToMinimum()
        else:
            print(f"Unsupported curvature type: {curvature_type}")
            return -1

        curv_filter.SetInputConnection(normals.GetOutputPort())
        curv_filter.Update()
        output = curv_filter.GetOutput()

        scalars = output.GetPointData().GetScalars()
        if scalars is None:
            print("No scalar data computed. Curvature calculation failed.")
            return -1

        print(f"Curvature range: {scalars.GetRange()}")

        mapper = self._actor.GetMapper()
        mapper.SetInputData(output)

        if color_map is None:
            curv_range = scalars.GetRange()
        else:
            curv_range = color_map

        # Blue to Red
        lut = vtk.vtkLookupTable()
        lut.SetHueRange(0.667, 0.0)
        lut.SetSaturationRange(1.0, 1.0)
        lut.SetValueRange(1.0, 1.0)
        lut.SetNumberOfColors(256)
        lut.Build()

        mapper.SetLookupTable(lut)
        mapper.SetScalarRange(curv_range)
        mapper.SetScalarModeToUsePointData()
        mapper.ScalarVisibilityOn()

        self._actor.GetProperty().SetColor(1.0, 1.0, 1.0)
        self._data.DeepCopy(output)
        self._data.Modified()

        return 0

    def reset_curvature_coloring(self):
        """
        Reset the coloring back to the original appearance settings.
        """
        mapper = self._actor.GetMapper()
        mapper.ScalarVisibilityOff()
        self._actor.GetProperty().SetColor(*self._appearance["base_color"])
        self._data.Modified()
        return 0

    def add_faces(self, faces):
        if faces.shape[1] != 3:
            raise ValueError("Only triangular faces are supported")

        for face in faces:
            self._cells.InsertNextCell(3)
            for vertex_idx in face:
                self._cells.InsertCellPoint(vertex_idx)
        self._data.Modified()


class PointCloud(Geometry):
    pass


class VolumeGeometry(Geometry):
    def __init__(
        self, volume: np.ndarray = None, volume_sampling_rate=np.ones(3), **kwargs
    ):
        super().__init__(**kwargs)
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

    @property
    def frames(self):
        return len(self._trajectory)

    def display_frame(self, frame_idx: int):
        target_representation = self._representation

        if frame_idx < 0 or frame_idx > self.frames:
            return None

        meta = self._trajectory[frame_idx]

        self.swap_data(meta["points"])
        self._meta.update(meta)

        if target_representation != "pointcloud":
            self.change_representation(target_representation)
        return None
