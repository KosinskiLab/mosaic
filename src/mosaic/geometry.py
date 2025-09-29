"""
Atomic Geometry class displayed by the vtk viewer.

Copyright (c) 2024-2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import warnings
from typing import Tuple, List, Dict

import vtk
import numpy as np
from vtk.util import numpy_support

from .actor import create_actor
from .utils import find_closest_points, normals_to_rot, apply_quat, NORMAL_REFERENCE

__all__ = ["Geometry", "VolumeGeometry", "GeometryTrajectory"]


BASE_COLOR = (0.7, 0.7, 0.7)


class Geometry:
    """
    VTK-based geometry representation for 3D point clouds and meshes.

    Parameters
    ----------
    points : np.ndarray, optional
        3D point coordinates.
    quaternions : np.ndarray, optional
        Orientation quaternions for each point (scalar first w,x,y,z).
    color : tuple, optional
        Base RGB color values, by default (0.7, 0.7, 0.7).
    sampling_rate : np.ndarray, optional
        Sampling rates along each axis.
    meta : dict, optional
        Metadata dictionary.
    vtk_actor : vtk.vtkActor, optional
        Custom VTK actor object.
    vertex_properties : VertexPropertyContainer, optional
        Additional vertex properties.
    **kwargs
        Additional keyword arguments including normals.
    """

    def __init__(
        self,
        points=None,
        quaternions=None,
        color=BASE_COLOR,
        sampling_rate=None,
        meta=None,
        vtk_actor=None,
        vertex_properties=None,
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

        if points is not None:
            self.points = points

        if normals is not None:
            self.normals = normals

        if quaternions is not None:
            self.quaternions = quaternions

        self._actor = self._create_actor(vtk_actor)
        self._vertex_properties = vertex_properties
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
    def vertex_properties(self):
        return self._vertex_properties

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
        """
        Get object state for pickling.

        Returns
        -------
        dict
            Serializable state dictionary.
        """
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
            "vertex_properties": self.vertex_properties,
        }

    def __setstate__(self, state):
        """
        Restore object state from unpickling.

        Parameters
        ----------
        state : dict
            State dictionary to restore from.
        """
        visible = state.pop("visible", True)
        appearance = state.pop("appearance", {})
        self.__init__(**state)
        self.set_visibility(visible)

        representation = state.get("representation", False)
        if representation:
            self.change_representation(representation)

        self.set_appearance(**appearance)

    def __getitem__(self, idx):
        """Array-like indexing using int/bool numpy arrays, slices or ellipses."""
        if isinstance(idx, (int, np.integer)):
            idx = [idx]
        elif isinstance(idx, slice) or idx is ...:
            idx = np.arange(self.get_number_of_points())[idx]

        idx = np.asarray(idx)
        if idx.dtype == bool:
            idx = np.where(idx)[0]

        normals = None
        if isinstance(self.normals, np.ndarray):
            normals = self.normals.copy()
            if np.max(idx) < normals.shape[0]:
                normals = normals[idx].copy()

        quaternions = self._data.GetPointData().GetArray("OrientationQuaternion")
        if quaternions is not None:
            quaternions = self.quaternions.copy()
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
        ret.set_visibility(self.visible)

        # Avoid clashes from properties of classes inheriting from Geometry
        ret._appearance.update(
            {k: v for k, v in self._appearance.items() if k in ret._appearance}
        )
        return ret

    @classmethod
    def merge(cls, geometries):
        """
        Merge multiple geometry objects into a single geometry.

        Parameters
        ----------
        geometries : list of Geometry
            List of geometry objects to merge.

        Returns
        -------
        Geometry
            New geometry object containing merged data.

        Raises
        ------
        ValueError
            If no geometries provided for merging.
        """
        if not len(geometries):
            raise ValueError("No geometries provided for merging")

        points, quaternions, normals = [], [], []

        has_quat = any(
            x._data.GetPointData().GetArray("OrientationQuaternion") is not None
            for x in geometries
        )
        has_normals = any(geometry.normals is not None for geometry in geometries)
        for geometry in geometries:
            points.append(geometry.points)

            if has_quat:
                quaternions.append(geometry.quaternions)

            if has_normals:
                normals.append(geometry.normals)

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
        ret.set_visibility(any(x.visible for x in geometries))
        ret._appearance.update(geometries[0]._appearance)
        return ret

    @property
    def actor(self):
        """
        VTK actor object for rendering.

        Returns
        -------
        vtk.vtkActor
            VTK actor used for visualization.
        """
        return self._actor

    @property
    def visible(self):
        """
        Visibility state of the geometry.

        Returns
        -------
        bool
            True if geometry is visible, False otherwise.
        """
        return self.actor.GetVisibility()

    @property
    def points(self):
        """
        3D point coordinates of the geometry.

        Returns
        -------
        np.ndarray
            Point coordinates with shape (n_points, 3).
        """
        return numpy_support.vtk_to_numpy(self._data.GetPoints().GetData())

    @points.setter
    def points(self, points: np.ndarray):
        """
        Set 3D point coordinates.

        Parameters
        ----------
        points : np.ndarray
            Point coordinates with shape (n_points, 3).
        """
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

        self._points.SetData(numpy_support.numpy_to_vtk(points, deep=False))
        self._data.SetVerts(vertex_cells)
        self._data.Modified()

    @property
    def normals(self):
        """
        Normal vectors at each point.

        Returns
        -------
        np.ndarray or None
            Normal vectors with shape (n_points, 3), or None if not set.
        """
        normals = self._data.GetPointData().GetNormals()
        if normals is not None:
            normals = np.asarray(normals)
        return normals

    @normals.setter
    def normals(self, normals: np.ndarray):
        """
        Set normal vectors.

        Parameters
        ----------
        normals : np.ndarray
            Normal vectors with shape (n_points, 3).
        """
        normals = np.asarray(normals, dtype=np.float32)
        if normals.shape != self.points.shape:
            warnings.warn("Number of normals must match number of points.")
            return -1

        normals_vtk = numpy_support.numpy_to_vtk(normals, deep=True)
        normals_vtk.SetName("Normals")
        self._data.GetPointData().SetNormals(normals_vtk)

        # Update associated quaternions if available
        quaternions = self._data.GetPointData().GetArray("OrientationQuaternion")
        if quaternions is not None:
            self.quaternions = normals_to_rot(self.normals, scalar_first=True)
        self._data.Modified()

    @property
    def quaternions(self):
        """
        Orientation quaternions for each point.

        Returns
        -------
        np.ndarray or None
            Quaternions in scalar-first format (n_points, 4), or None if not set.
        """
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
        """
        Set uniform color for all points in the geometry.

        Parameters
        ----------
        color : tuple of int, optional
            RGB color values. Uses base color if None.
        """
        if color is None:
            color = self._appearance["base_color"]
        self.color_points(range(self._points.GetNumberOfPoints()), color=color)

    def set_visibility(self, visibility: bool = True):
        """
        Set geometry visibility in the scene.

        Parameters
        ----------
        visibility : bool, optional
            Whether geometry should be visible, by default True.
        """
        return self.actor.SetVisibility(visibility)

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
        """
        Set visual appearance properties of the geometry.

        Parameters
        ----------
        size : int, optional
            Point size for rendering.
        opacity : float, optional
            Transparency level (0.0 to 1.0).
        render_spheres : bool, optional
            Whether to render points as spheres.
        ambient : float, optional
            Ambient lighting coefficient.
        diffuse : float, optional
            Diffuse lighting coefficient.
        specular : float, optional
            Specular lighting coefficient.
        color : tuple of float, optional
            RGB color values.
        **kwargs
            Additional appearance parameters.
        """
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
        """Propagate appearance settings to VTK actor properties."""
        prop = self._actor.GetProperty()

        prop.SetRenderPointsAsSpheres(True)
        if not self._appearance.get("render_spheres", True):
            prop.SetRenderPointsAsSpheres(False)

        prop.SetPointSize(self._appearance.get("size", 8))
        prop.SetOpacity(self._appearance.get("opacity", 1.0))
        prop.SetAmbient(self._appearance.get("ambient", 0.3))
        prop.SetDiffuse(self._appearance.get("diffuse", 0.7))
        prop.SetSpecular(self._appearance.get("specular", 0.2))

    def _create_actor(
        self, actor=None, lod_points: int = 5e6, lod_points_size: int = 3
    ):
        """
        Create VTK actor with appropriate mapper configuration.

        Parameters
        ----------
        actor : vtk.vtkActor, optional
            Existing actor to use.
        lod_points : int, optional
            Level of detail threshold for points, by default 5e6.
        lod_points_size : int, optional
            Point size for level of detail, by default 3.

        Returns
        -------
        vtk.vtkActor
            Configured VTK actor.
        """
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(self._data)

        mapper.SetScalarModeToDefault()
        mapper.SetVBOShiftScaleMethod(1)
        mapper.SetResolveCoincidentTopology(False)
        mapper.SetResolveCoincidentTopologyToPolygonOffset()

        if actor is None:
            actor = create_actor()
        actor.SetMapper(mapper)
        return actor

    def get_number_of_points(self):
        """
        Get total number of points in the geometry.

        Returns
        -------
        int
            Number of points.
        """
        return self._points.GetNumberOfPoints()

    def set_scalars(self, scalars, color_lut, scalar_range=None, use_point=False):
        """
        Set scalar data for coloring points.

        Parameters
        ----------
        scalars : array-like
            Scalar values for each point.
        color_lut : vtk.vtkLookupTable
            Color lookup table for mapping scalars to colors.
        scalar_range : tuple, optional
            Min and max scalar range for color mapping.
        use_point : bool, optional
            Whether to use point data for scalar mode, by default False.
        """
        scalars = np.asarray(scalars).reshape(-1)
        if scalars.size == 1:
            scalars = np.repeat(scalars, self.points.shape[0])

        if scalars.size != self.points.shape[0]:
            return None

        mapper = self._actor.GetMapper()
        mapper.GetInput().GetPointData().SetScalars(
            numpy_support.numpy_to_vtk(scalars, deep=False)
        )

        self._configure_scalar_mapper(mapper, color_lut, scalar_range, use_point)
        self._actor.Modified()

    def _update_scalars_from_ids(
        self, point_ids, color_lut, scalar_range=None, use_point=False
    ) -> bool:
        """
        Try to update existing scalar array in place for better performance.

        Parameters
        ----------
        point_ids : array-like
            Point indices to set to 1.0, all others set to 0.0
        color_lut : vtk.vtkLookupTable
            Color lookup table for mapping scalars to colors.
        scalar_range : tuple, optional
            Min and max scalar range for color mapping.
        use_point : bool, optional
            Whether to use point data for scalar mode, by default False.

        Returns
        -------
        bool
            True if successful, False if scalar array couldn't be reused.
        """
        mapper = self._actor.GetMapper()
        cur_scalars = mapper.GetInput().GetPointData().GetScalars()

        if not (cur_scalars is not None and cur_scalars.GetNumberOfComponents() == 1):
            return False

        scalars_np = vtk.util.numpy_support.vtk_to_numpy(cur_scalars)
        if scalars_np.shape[0] != self._points.GetNumberOfPoints():
            return False

        scalars_np.fill(0.0)
        scalars_np[point_ids] = 1.0
        cur_scalars.Modified()

        self._configure_scalar_mapper(mapper, color_lut, scalar_range, use_point)
        self._actor.Modified()
        return True

    def _configure_scalar_mapper(
        self, mapper, color_lut, scalar_range=None, use_point=False
    ):
        """
        Configure mapper for scalar coloring with common settings.

        Parameters
        ----------
        mapper : vtk.vtkMapper
            The mapper to configure
        color_lut : vtk.vtkLookupTable
            Color lookup table for mapping scalars to colors.
        scalar_range : tuple, optional
            Min and max scalar range for color mapping.
        use_point : bool, optional
            Whether to use point data for scalar mode, by default False.
        """
        if color_lut is not None:
            mapper.SetLookupTable(color_lut)
        if scalar_range is not None:
            mapper.SetScalarRange(*scalar_range)
        mapper.ScalarVisibilityOn()
        if use_point:
            mapper.SetScalarModeToUsePointData()

    def color_points(self, point_ids: set, color: Tuple[float]):
        """
        Color specific points in the geometry using set_scalars backend.

        Parameters
        ----------
        point_ids : set
            Set of point indices to color
        color : tuple of float
            RGB color values (0-1) to apply to selected points
        """
        n_points = self._points.GetNumberOfPoints()
        if not isinstance(point_ids, np.ndarray):
            point_ids = np.array(list(point_ids), dtype=np.int32)

        point_ids = point_ids.astype(np.int32, copy=False)
        point_ids = point_ids[point_ids < n_points]

        lut = vtk.vtkLookupTable()
        lut.SetNumberOfTableValues(2)
        lut.SetRange(0.0, 1.0)
        lut.SetTableValue(0, *self._appearance["base_color"], 1.0)
        lut.SetTableValue(1, *color, 1.0)
        lut.Build()

        kw = {"color_lut": lut, "scalar_range": (0.0, 1.0), "use_point": True}

        success = self._update_scalars_from_ids(point_ids, **kw)
        if not success:
            scalars = np.zeros(n_points, dtype=np.float32)
            scalars[point_ids] = 1.0
            return self.set_scalars(scalars, **kw)

    def subset(self, indices):
        """
        Create a subset geometry from specified indices.

        Parameters
        ----------
        indices : array-like
            Indices of points to include in subset.

        Returns
        -------
        Geometry
            New geometry with swapped data from subset.
        """
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
        """
        Replace geometry data with new point cloud or mesh data.

        Parameters
        ----------
        points : np.ndarray
            New 3D point coordinates.
        normals : np.ndarray, optional
            New normal vectors.
        faces : np.ndarray, optional
            New face connectivity indices.
        quaternions : np.ndarray, optional
            New orientation quaternions.
        meta : dict, optional
            New metadata dictionary.

        Returns
        -------
        int
            Result of representation change.
        """
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

        if normals is None and points is not None:
            normals = np.full_like(points, fill_value=NORMAL_REFERENCE)

        if normals is not None:
            self.normals = normals

        if faces is not None:
            self._set_faces(faces)

        if isinstance(meta, dict):
            self._meta.update(meta)

            if "vertex_properties" in meta:
                self._vertex_properties = meta["vertex_properties"]

        self.set_color()
        return self.change_representation(self._representation)

    def change_representation(self, representation: str = "pointcloud") -> int:
        """
        Change the visual representation mode of the geometry.

        Parameters
        ----------
        representation : str, optional
            Representation mode, by default "pointcloud".
            Supported: "pointcloud", "gaussian_density", "pointcloud_normals",
            "mesh", "wireframe", "normals", "surface", "basis".

        Returns
        -------
        int
            Success status (0 for success, -1 for failure).

        Raises
        ------
        ValueError
            If representation mode is not supported.
        """
        supported = [
            "pointcloud",
            "gaussian_density",
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

        mapper = vtk.vtkPolyDataMapper()
        if representation == "gaussian_density":
            mapper = vtk.vtkPointGaussianMapper()
            mapper.SetSplatShaderCode("")

        mapper.SetScalarModeToDefault()
        mapper.SetVBOShiftScaleMethod(1)
        mapper.SetResolveCoincidentTopology(False)
        mapper.SetResolveCoincidentTopologyToPolygonOffset()

        self._actor.SetMapper(mapper)
        self._appearance.update({"opacity": 1, "size": 8, "render_spheres": True})
        if representation == "gaussian_density":
            self._appearance["render_spheres"] = False

        scale = 15 * np.max(self.sampling_rate)
        mapper, prop = self._actor.GetMapper(), self._actor.GetProperty()
        prop.SetOpacity(self._appearance["opacity"])
        prop.SetPointSize(self._appearance["size"])
        prop.SetRenderPointsAsSpheres(self._appearance["render_spheres"])
        if representation == "pointcloud":
            prop.SetRepresentationToPoints()
            mapper.SetInputData(self._data)

        elif representation == "gaussian_density":
            mapper.SetSplatShaderCode("")
            mapper.SetScaleFactor(self._appearance["size"] * 0.25)
            mapper.SetScalarVisibility(True)
            mapper.SetInputData(self._data)

        elif representation == "normals":
            arrow = vtk.vtkArrowSource()
            arrow.SetTipResolution(6)
            arrow.SetShaftResolution(6)
            arrow.SetTipRadius(0.08)
            arrow.SetShaftRadius(0.02)

            mapper = vtk.vtkGlyph3DMapper()
            mapper.SetInputData(self._data)
            mapper.SetSourceConnection(arrow.GetOutputPort())
            mapper.SetOrientationArray("Normals")
            mapper.SetOrientationModeToDirection()
            mapper.SetScaleModeToNoDataScaling()
            mapper.SetScaleFactor(scale)
            mapper.OrientOn()

            self._actor.SetMapper(mapper)

        elif representation == "basis":
            if self.quaternions is None:
                print("Quaternions are required for basis representation.")
                return -1

            arrow_x = vtk.vtkArrowSource()
            arrow_y = vtk.vtkArrowSource()
            arrow_z = vtk.vtkArrowSource()
            for arrow in [arrow_x, arrow_y, arrow_z]:
                arrow.SetTipResolution(6)
                arrow.SetShaftResolution(6)
                arrow.SetTipRadius(0.08)
                arrow.SetShaftRadius(0.02)

            transform_x = vtk.vtkTransform()
            transform_x.RotateY(-90)
            transform_filter_x = vtk.vtkTransformPolyDataFilter()
            transform_filter_x.SetInputConnection(arrow_x.GetOutputPort())
            transform_filter_x.SetTransform(transform_x)
            transform_filter_x.Update()

            transform_y = vtk.vtkTransform()
            transform_y.RotateZ(90)
            transform_filter_y = vtk.vtkTransformPolyDataFilter()
            transform_filter_y.SetInputConnection(arrow_y.GetOutputPort())
            transform_filter_y.SetTransform(transform_y)
            transform_filter_y.Update()

            append_filter = vtk.vtkAppendPolyData()
            append_filter.AddInputConnection(transform_filter_x.GetOutputPort())
            append_filter.AddInputConnection(transform_filter_y.GetOutputPort())
            append_filter.AddInputConnection(arrow_z.GetOutputPort())
            append_filter.Update()

            mapper = vtk.vtkGlyph3DMapper()
            mapper.SetInputData(self._data)
            mapper.SetSourceData(append_filter.GetOutput())
            mapper.SetOrientationArray("OrientationQuaternion")
            mapper.SetOrientationModeToQuaternion()
            mapper.SetScaleFactor(scale)
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
        return self.set_appearance()

    def compute_distance(self, query_points: np.ndarray, k: int = 1, **kwargs):
        model = self._meta.get("fit", None)
        if hasattr(model, "compute_distance"):
            return model.compute_distance(query_points)

        return find_closest_points(self.points, query_points, k=k)[0]


class PointCloud(Geometry):
    pass


class VolumeGeometry(Geometry):
    """
    Geometry class specialized for 3D volume rendering with isosurfaces.

    Parameters
    ----------
    volume : np.ndarray, optional
        3D volume data array.
    volume_sampling_rate : np.ndarray, optional
        Sampling rates for volume data, by default ones(3).
    **kwargs
        Additional keyword arguments passed to parent Geometry class.
    """

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
        """
        Update the isovalue for volume surface rendering.

        Parameters
        ----------
        upper : float
            Upper isovalue threshold.
        lower : float, optional
            Lower isovalue threshold, by default 0.
        """
        return self._surface.SetValue(int(lower), upper)

    def update_isovalue_quantile(
        self, upper_quantile: float, lower_quantile: float = 0.0
    ):
        """
        Update isovalue using quantile-based thresholds.

        Parameters
        ----------
        upper_quantile : float
            Upper quantile threshold (0.0 to 1.0).
        lower_quantile : float, optional
            Lower quantile threshold (0.0 to 1.0), by default 0.0.

        Raises
        ------
        ValueError
            If upper quantile is not greater than lower quantile.
        """
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
    """
    Geometry class for displaying animated trajectory sequences.

    Parameters
    ----------
    trajectory : list of dict
        List of trajectory frames containing geometry data.
    **kwargs
        Additional keyword arguments passed to parent Geometry class.
    """

    def __init__(self, trajectory: List[Dict], **kwargs):
        super().__init__(**kwargs)
        self._trajectory = trajectory

    def __getstate__(self):
        state = super().__getstate__()
        state.update({"trajectory": self._trajectory})
        return state

    @property
    def frames(self):
        """
        Number of frames in the trajectory.

        Returns
        -------
        int
            Total number of trajectory frames.
        """
        return len(self._trajectory)

    def display_frame(self, frame_idx: int) -> bool:
        """
        Display specific trajectory frame.

        Parameters
        ----------
        frame_idx : int
            Index of frame to display.

        Returns
        -------
        bool
            True if frame was successfully displayed, False otherwise.
        """
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
