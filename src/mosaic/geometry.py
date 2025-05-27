""" Atomic Geometry class displayed by the vtk viewer.

    Copyright (c) 2024-2025 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import warnings
from typing import Tuple, List, Dict

import vtk
import numpy as np
from vtk.util import numpy_support

from .utils import find_closest_points, normals_to_rot, apply_quat, NORMAL_REFERENCE

BASE_COLOR = (0.7, 0.7, 0.7)


class Geometry:
    def __init__(
        self,
        points=None,
        quaternions=None,
        color=BASE_COLOR,
        sampling_rate=None,
        meta=None,
        vtk_actor=None,
        **kwargs,
    ):
        self._points = vtk.vtkPoints()
        self._points.SetDataTypeToFloat()

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

        normals = kwargs.get("normals")
        if quaternions is not None:
            _normals = apply_quat(quaternions)
            if normals is not None:
                if not np.allclose(_normals, normals, atol=1e-3):
                    warnings.warn(
                        "Orientation given by quaternions does not match the "
                        "supplied normal vectors. Overwriting normals with "
                        "quaternions for now."
                    )
            normals = _normals

        if normals is None and points is not None:
            normals = np.full_like(points, fill_value=NORMAL_REFERENCE)

        self.points = points
        self.normals = normals
        if quaternions is not None:
            self.quaternions = quaternions

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
        quaternions = self._data.GetPointData().GetArray("OrientationQuaternion")
        if quaternions is not None:
            quaternions = self.quaternions

        return {
            "points": self.points,
            "normals": self.normals,
            "quaternions": quaternions,
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

        quaternions = self._data.GetPointData().GetArray("OrientationQuaternion")
        if quaternions is not None:
            quaternions = self.quaternions
            if np.max(idx) < quaternions.shape[0]:
                quaternions = quaternions[idx].copy()

        ret = Geometry(
            points=self.points[idx].copy(),
            normals=normals,
            quaternions=quaternions,
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

        points, quaternions = [], []
        has_quat = any(geometry.quaternions is not None for geometry in geometries)
        has_normals = any(geometry.normals is not None for geometry in geometries)
        for geometry in geometries:
            points.append(geometry.points)
            if not has_quat and not has_normals:
                continue

            quaternions = geometry.quaternions
            if quaternions is None:
                quaternions = np.full(
                    (geometry.points.shape(0), 4), fill_value=(1, 0, 0, 0)
                )

            normals = geometry.normals
            if normals is None:
                normals = np.full_like(geometry.points, fill_value=NORMAL_REFERENCE)

        quaternions = np.concatenate(quaternions, axis=0) if has_quat else None
        normals = np.concatenate(normals, axis=0) if has_normals else None
        ret = cls(
            points=np.concatenate(points, axis=0),
            normals=normals,
            quaternions=quaternions,
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

    @points.setter
    def points(self, points: np.ndarray):
        points = np.asarray(points, dtype=np.float32)
        if points.shape[1] != 3:
            warnings.warn("Only 3D point clouds are supported.")
            return -1

        if self.points.shape[0] != 0:
            points = np.concatenate((self.points, points))

        # Allow for area picking
        vertex_cells = vtk.vtkCellArray()
        idx = np.arange(points.shape[0], dtype=int)
        cells = np.column_stack((np.ones(idx.size, dtype=int), idx)).flatten()
        vertex_cells.SetCells(idx.size, numpy_support.numpy_to_vtkIdTypeArray(cells))

        # n_points = points.shape[0]
        # vertex_cells = vtk.vtkCellArray()
        # vertex_cells.InsertNextCell(n_points)
        # for i in range(n_points):
        #     vertex_cells.InsertCellPoint(i)

        self._points.SetData(numpy_support.numpy_to_vtk(points, deep=False))
        self._data.SetVerts(vertex_cells)
        self._data.Modified()

    @property
    def normals(self):
        normals = self._data.GetPointData().GetNormals()
        if normals is not None:
            normals = np.asarray(normals)
        return normals

    @normals.setter
    def normals(self, normals: np.ndarray):
        normals = np.asarray(normals, dtype=np.float32)
        if normals.shape != self.points.shape:
            warnings.warn("Number of normals must match number of points.")
            return -1

        normals_vtk = numpy_support.numpy_to_vtk(normals, deep=True)
        normals_vtk.SetName("Normals")
        self._data.GetPointData().SetNormals(normals_vtk)
        self._data.Modified()

    @property
    def quaternions(self):
        quaternions = self._data.GetPointData().GetArray("OrientationQuaternion")
        if quaternions is not None:
            quaternions = np.asarray(quaternions)
        elif self.normals is not None:
            warnings.warn("Computing quaternions from associated normals.")
            quaternions = normals_to_rot(self.normals, scalar_first=True)
            self.quaternions = quaternions
        return quaternions

    @quaternions.setter
    def quaternions(self, quaternions: np.ndarray):
        """
        Add orientation quaternions to the geometry.

        Parameters:
        -----------
        quaternions : array-like
            Quaternion values in scalar-first format (n, (w, x, y, z)).
        """
        quaternions = np.asarray(quaternions, dtype=np.float32)
        if quaternions.shape[0] != self.points.shape[0]:
            warnings.warn("Number of orientations must match number of points.")
            return -1
        if quaternions.shape[1] != 4:
            warnings.warn("Quaternions must have 4 components (w, x, y, z).")
            return -1

        quat_vtk = numpy_support.numpy_to_vtk(quaternions, deep=True)
        quat_vtk.SetName("OrientationQuaternion")
        self._data.GetPointData().AddArray(quat_vtk)
        self._data.Modified()

    def _set_faces(self, faces):
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
        mapper.SetVBOShiftScaleMethod(1)
        mapper.SetResolveCoincidentTopology(False)
        mapper.SetResolveCoincidentTopologyToPolygonOffset()

        if actor is None:
            actor = vtk.vtkLODActor()
            actor.SetNumberOfCloudPoints(100000)

        actor.SetMapper(mapper)
        return actor

    def get_number_of_points(self):
        return self._points.GetNumberOfPoints()

    def set_scalars(self, scalars, color_lut, scalar_range=None, use_point=False):
        scalars = np.asarray(scalars).reshape(-1)
        if scalars.size == 1:
            scalars = np.repeat(scalars, self.points.shape[0])

        if scalars.size != self.points.shape[0]:
            print(f"Needs {self.points.shape[0]} scalars, not {scalars.size}")
            return None

        mapper = self._actor.GetMapper()
        mapper.GetInput().GetPointData().SetScalars(numpy_support.numpy_to_vtk(scalars))
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
        point_ids = np.fromiter(
            (pid for pid in point_ids if pid < n_points), dtype=np.int32
        )

        if not len(point_ids) or n_points == 0:
            return

        current_colors = self._data.GetPointData().GetScalars()
        if (
            current_colors is not None
            and current_colors.GetName() == "Colors"
            and current_colors.GetNumberOfTuples() == n_points
            and current_colors.GetNumberOfComponents() == 3
        ):
            colors_np = vtk.util.numpy_support.vtk_to_numpy(current_colors)
            colors_np = colors_np.reshape(n_points, 3)

            base_color_uint8 = np.array(
                [x * 255 for x in self._appearance["base_color"]], dtype=np.uint8
            )
            highlight_color_unit8 = np.array([x * 255 for x in color], dtype=np.uint8)

            colors_np[:] = base_color_uint8
            colors_np[point_ids] = highlight_color_unit8

            current_colors.Modified()
            return self._data.Modified()

        colors = np.full(
            (n_points, 3),
            fill_value=[x * 255 for x in self._appearance["base_color"]],
            dtype=np.uint8,
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

        _quaternions = self._data.GetPointData().GetArray("OrientationQuaternion")
        if _quaternions is not None:
            _quaternions = subset.quaternions

        kwargs = {
            "points": subset.points,
            "normals": subset.normals,
            "quaternions": _quaternions,
        }

        return self.swap_data(**kwargs)

    def swap_data(
        self, points, normals=None, faces=None, quaternions=None, meta: Dict = None
    ):
        self._points.Reset()
        self._cells.Reset()
        self._normals.Reset()

        # Check whether we have to synchronize quaternion representation
        _quaternions = self._data.GetPointData().GetArray("OrientationQuaternion")
        if quaternions is None and _quaternions is not None and normals is not None:
            quaternions = normals_to_rot(normals)

        self.points = points
        if quaternions is not None:
            normals = apply_quat(quaternions, NORMAL_REFERENCE)
            self.quaternions = quaternions

        if normals is not None:
            self.normals = normals

        if faces is not None:
            self._set_faces(faces)

        if isinstance(meta, dict):
            self._meta.update(meta)

        self.set_color()
        return self.change_representation(self._representation)

    def change_representation(self, representation: str = "pointcloud") -> int:
        supported = [
            "pointcloud",
            "gaussian_density",
            "pointcloud_normals",
            "mesh",
            "wireframe",
            "normals",
            "surface",
            "basis",
        ]
        representation = representation.lower()

        # We dont check representation == self._representation to enable
        # rendering in the same representation after swap_data
        if representation not in supported:
            supported = ", ".join(supported)
            raise ValueError(
                f"Supported representations are {supported} - got {representation}."
            )

        if representation in ["mesh", "wireframe", "surface"]:
            if not hasattr(self._meta.get("fit", None), "mesh"):
                print(
                    "Points and face data required for surface/wireframe representation."
                )
                return -1

        clipping_planes = self._actor.GetMapper().GetClippingPlanes()

        # Consistent normal rendering across representations
        if representation in ("pointcloud_normals", "normals"):
            arrow = vtk.vtkArrowSource()
            arrow.SetTipResolution(6)
            arrow.SetShaftResolution(6)
            arrow.SetTipRadius(0.08)
            arrow.SetShaftRadius(0.02)

            normal_scale = 0.1 * np.max(self.sampling_rate)

            # arrow.SetShaftRadius(0.02 / 5)
            # normal_scale = 0.5 * np.max(self.sampling_rate)

            glyph = vtk.vtkGlyph3D()
            glyph.SetSourceConnection(arrow.GetOutputPort())
            glyph.SetVectorModeToUseNormal()
            glyph.SetScaleFactor(normal_scale)
            glyph.SetColorModeToColorByScalar()
            glyph.OrientOn()

        self._appearance.update({"opacity": 1, "size": 8})

        mapper = vtk.vtkPolyDataMapper()
        if representation == "gaussian_density":
            mapper = vtk.vtkPointGaussianMapper()
            mapper.SetSplatShaderCode("")

        mapper.SetScalarModeToDefault()
        mapper.SetVBOShiftScaleMethod(1)
        mapper.SetResolveCoincidentTopology(False)
        mapper.SetResolveCoincidentTopologyToPolygonOffset()

        self._actor.SetMapper(mapper)
        mapper, prop = self._actor.GetMapper(), self._actor.GetProperty()
        prop.SetOpacity(self._appearance["opacity"])
        prop.SetPointSize(self._appearance["size"])

        if representation == "pointcloud":
            prop.SetRepresentationToPoints()
            mapper.SetInputData(self._data)

        elif representation == "gaussian_density":
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

        elif representation == "basis":
            if self.quaternions is None:
                print("Quaternions are required for basis representation.")
                return -1

            scale = 15 * np.max(self.sampling_rate)
            arrow_x = vtk.vtkArrowSource()
            arrow_y = vtk.vtkArrowSource()
            arrow_z = vtk.vtkArrowSource()

            for arrow in [arrow_x, arrow_y, arrow_z]:
                arrow.SetTipResolution(6)
                arrow.SetShaftResolution(6)
                arrow.SetTipRadius(0.08)
                arrow.SetShaftRadius(0.02)

            transform_x = vtk.vtkTransform()
            transform_x.RotateY(-90)  # Rotate from Z to X
            transform_filter_x = vtk.vtkTransformPolyDataFilter()
            transform_filter_x.SetInputConnection(arrow_x.GetOutputPort())
            transform_filter_x.SetTransform(transform_x)
            transform_filter_x.Update()
            transform_y = vtk.vtkTransform()
            transform_y.RotateZ(90)  # Rotate from Z to Y
            transform_filter_y = vtk.vtkTransformPolyDataFilter()
            transform_filter_y.SetInputConnection(arrow_y.GetOutputPort())
            transform_filter_y.SetTransform(transform_y)
            transform_filter_y.Update()
            transform_scale = vtk.vtkTransform()
            transform_scale.Scale(scale, scale, scale)

            scale_filter_x = vtk.vtkTransformPolyDataFilter()
            scale_filter_x.SetInputConnection(transform_filter_x.GetOutputPort())
            scale_filter_x.SetTransform(transform_scale)
            scale_filter_x.Update()
            scale_filter_y = vtk.vtkTransformPolyDataFilter()
            scale_filter_y.SetInputConnection(transform_filter_y.GetOutputPort())
            scale_filter_y.SetTransform(transform_scale)
            scale_filter_y.Update()
            scale_filter_z = vtk.vtkTransformPolyDataFilter()
            scale_filter_z.SetInputConnection(arrow_z.GetOutputPort())
            scale_filter_z.SetTransform(transform_scale)
            scale_filter_z.Update()
            append_filter = vtk.vtkAppendPolyData()
            append_filter.AddInputConnection(scale_filter_x.GetOutputPort())
            append_filter.AddInputConnection(scale_filter_y.GetOutputPort())
            append_filter.AddInputConnection(scale_filter_z.GetOutputPort())
            append_filter.Update()

            polydata = append_filter.GetOutput()

            mapper = vtk.vtkGlyph3DMapper()
            mapper.SetInputData(self._data)
            mapper.SetSourceData(polydata)
            mapper.SetOrientationArray("OrientationQuaternion")
            mapper.SetOrientationModeToQuaternion()
            mapper.SetScaleModeToNoDataScaling()
            mapper.OrientOn()

            self._actor.SetMapper(mapper)

        elif representation in ("mesh", "wireframe", "surface"):
            self._cells.Reset()
            self._points.Reset()

            mesh = self._meta.get("fit", None)
            if not hasattr(mesh, "vertices"):
                return None
            self.points = mesh.vertices
            self._set_faces(mesh.triangles)
            self.normals = mesh.compute_vertex_normals()

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

        if clipping_planes:
            mapper.SetClippingPlanes(clipping_planes)

        self._representation = representation
        return 0

    def compute_distance(self, query_points: np.ndarray, k: int = 1, **kwargs):
        model = self._meta.get("fit", None)
        if hasattr(model, "compute_distance"):
            return model.compute_distance(query_points)

        return find_closest_points(self.points, query_points, k=k)[0]


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
        self._volume.SetDimensions(volume.shape)
        self._volume.AllocateScalars(vtk.VTK_FLOAT, 1)

        if self.quaternions is None:
            self.quaternions = normals_to_rot(self.normals, scalar_first=True)

        self._raw_volume = volume
        volume_vtk = numpy_support.numpy_to_vtk(
            volume.ravel(order="F"), deep=True, array_type=vtk.VTK_FLOAT
        )
        self._volume.GetPointData().SetScalars(volume_vtk)

        bounds = [0.0] * 6
        self._volume.GetBounds(bounds)
        transform = vtk.vtkTransform()
        transform.Translate(
            [-(b[1] - b[0]) * 0.5 for b in zip(bounds[::2], bounds[1::2])]
        )

        self._volume_sampling_rate = volume_sampling_rate

        # Render volume isosurface as vtk glpyh object
        transformFilter = vtk.vtkTransformFilter()
        transformFilter.SetInputData(self._volume)
        transformFilter.SetTransform(transform)
        transformFilter.Update()
        self._surface = vtk.vtkContourFilter()
        self._surface.SetInputConnection(transformFilter.GetOutputPort())
        self._surface.GenerateValues(1, volume.min(), volume.max())

        mapper = vtk.vtkGlyph3DMapper()
        mapper.SetInputData(self._data)
        mapper.SetSourceConnection(self._surface.GetOutputPort())
        mapper.SetOrientationModeToQuaternion()
        mapper.SetScaleModeToNoDataScaling()
        mapper.SetOrientationArray("OrientationQuaternion")
        mapper.OrientOn()
        self._actor.SetMapper(mapper)

    def __getstate__(self):
        state = super().__getstate__()

        if self._volume is not None:
            state.update(
                {
                    "volume": self._raw_volume,
                    "volume_sampling_rate": self._volume_sampling_rate,
                    "lower_quantile": self._lower_quantile,
                    "upper_quantile": self._upper_quantile,
                }
            )
        return state

    def update_isovalue(self, upper, lower: float = 0):
        return self._surface.SetValue(int(lower), upper)

    def update_isovalue_quantile(
        self, upper_quantile: float, lower_quantile: float = 0.0
    ):
        lower_quantile = max(lower_quantile, 0)
        upper_quantile = min(upper_quantile, 1)

        if lower_quantile >= upper_quantile:
            raise ValueError("Upper quantile must be greater than lower quantile")

        self._lower_quantile = lower_quantile
        self._upper_quantile = upper_quantile
        lower_value = np.quantile(self._raw_volume, self._lower_quantile)
        upper_value = np.quantile(self._raw_volume, self._upper_quantile)
        return self.update_isovalue(upper=upper_value, lower=lower_value)

    def change_representation(self, *args, **kwargs) -> int:
        return -1

    def set_appearance(self, isovalue_percentile=0.99, **kwargs):
        if hasattr(self, "_raw_volume"):
            self._appearance["isovalue_percentile"] = isovalue_percentile
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

    def display_frame(self, frame_idx: int) -> bool:
        if frame_idx < 0 or frame_idx > self.frames:
            return False

        appearance = self._appearance.copy()
        meta = self._trajectory[frame_idx]

        mesh = meta.get("fit", None)
        if not hasattr(mesh, "mesh"):
            return False

        self.swap_data(
            points=mesh.vertices,
            faces=mesh.triangles,
            normals=mesh.compute_vertex_normals(),
            meta=meta,
        )
        self.set_appearance(**appearance)
        return True
