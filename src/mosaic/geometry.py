"""
Atomic Geometry class displayed by the vtk viewer.

Copyright (c) 2024-2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import warnings
from uuid import uuid4
from typing import Tuple, List, Dict

import vtk
import numpy as np
from vtk.util import numpy_support

from .actor import create_actor
from .utils import normals_to_rot, apply_quat, NORMAL_REFERENCE


__all__ = ["Geometry", "VolumeGeometry", "SegmentationGeometry", "GeometryTrajectory"]


BASE_COLOR = (0.7, 0.7, 0.7)


class Geometry:
    """
    VTK-based geometry representation for 3D point clouds and meshes.

    Parameters
    ----------
    points : np.ndarray, optional
        3D point coordinates.
    quaternions : np.ndarray, optional
        Normal vectors for each point (x,y,z).
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
    model : :py:class:`mosaic.parametrization.Parametrization`
        Model fitted to geometry data.
    **kwargs
        Additional keyword arguments including normals.
    """

    def __init__(
        self,
        points=None,
        normals=None,
        quaternions=None,
        color=BASE_COLOR,
        sampling_rate=None,
        meta=None,
        vtk_actor=None,
        vertex_properties=None,
        model=None,
        **kwargs,
    ):
        self.uuid = str(uuid4())

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

        if points is not None:
            self.points = points

        if normals is not None:
            self.normals = normals

        if quaternions is not None:
            self.quaternions = quaternions

        self._model = model
        self._meta = {} if meta is None else meta
        self._representation = "pointcloud"

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
    def model(self):
        return self._model

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
        sampling_rate = np.asarray(sampling_rate, dtype=np.float32).copy()
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
        points, normals, quaternions = self.get_point_data()

        return {
            "points": points,
            "normals": normals,
            "quaternions": quaternions,
            "sampling_rate": self.sampling_rate,
            "meta": self._meta,
            "visible": self.visible,
            "appearance": self._appearance,
            "representation": self._representation,
            "vertex_properties": self.vertex_properties,
            "uuid": self.uuid,
            "model": self.model,
        }

    def __setstate__(self, state):
        """
        Restore object state from unpickling.

        Parameters
        ----------
        state : dict
            State dictionary to restore from.
        """
        uuid = state.pop("uuid", None)
        visible = state.pop("visible", True)
        appearance = state.pop("appearance", {})

        # Compatibility with pre 1.0.12
        if "fit" in state.get("meta", {}):
            state["model"] = state["meta"].pop("fit")

        self.__init__(**state)
        self.set_visibility(visible)

        if uuid is not None:
            self.uuid = uuid

        # Required to support loading VolumeGeometries
        if state.get("representation") != self._representation:
            self.change_representation(state.get("representation"))
        self.set_appearance(**appearance)

    def subset(self, idx, copy: bool = False):
        n_points = self.get_number_of_points()
        if isinstance(idx, (int, np.integer)):
            idx = [idx]
        elif isinstance(idx, slice) or idx is ...:
            idx = np.arange(n_points)[idx]

        idx = np.asarray(idx)
        if idx.dtype == bool:
            idx = np.where(idx)[0]
        idx = idx[idx < n_points]

        state = self.__getstate__()
        if "meta" in state and copy:
            state["meta"] = state["meta"].copy()

        data_array = ("points", "normals", "quaternions")
        if (vertex_properties := state.get("vertex_properties")) is not None:
            state["vertex_properties"] = vertex_properties[idx]

        for key in data_array:
            if (value := state.get(key)) is not None:
                state[key] = np.asarray(value)[idx]
                if copy:
                    state[key] = state[key].copy()

        ret = self
        if copy:
            _ = state.pop("uuid", None)
            ret = self.__class__.__new__(self.__class__)
        else:
            state["vtk_actor"] = self.actor
        ret.__setstate__(state)
        return ret

    def __getitem__(self, idx):
        """Array-like indexing using int/bool numpy arrays, slices or ellipsis."""
        return self.subset(idx, copy=True)

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
        geometries = [x for x in geometries if isinstance(x, Geometry)]
        if not len(geometries):
            raise ValueError("No geometries provided for merging")
        elif len(geometries) == 1:
            return geometries[0]

        data = {
            "points": [],
            "quaternions": [],
            "normals": [],
            "models": [],
        }

        for geometry in geometries:
            _points, _normals, _quaternions = geometry.get_point_data()

            data["points"].append(_points)
            if _normals is not None:
                data["normals"].append(_normals)

            if _quaternions is not None:
                data["quaternions"].append(_quaternions)

            if (model := geometry.model) is not None:
                data["models"].append(model)

        # Merging Geometries with different sampling rate is an underdetermined
        # problem without user intervention. Computing the maximum of geometries
        # makes the problem symmetric. In most workflows this should suffice, but
        # we might need to show a warning moving forward.
        sampling_rate = np.max(np.array([x.sampling_rate for x in geometries]), axis=0)

        # Use majority representation for new class
        representation = [x._representation for x in geometries]
        representation = max(set(representation), key=representation.count)
        appearance = [
            x._appearance for x in geometries if x._representation == representation
        ][0]

        model = None
        if len(data["models"]):
            from .parametrization import merge

            model = merge(data.pop("models"))

        # TODO: We can handle merging of VolumeGeometries propertly, but
        # need to make sure they contain the same volume. For now we just
        # render them as point cloud
        if representation == "volume":
            representation = "pointcloud"
            _ = appearance.pop("volume_path", None)
            _ = appearance.pop("isovalue_percentile", None)

        state = {
            "sampling_rate": sampling_rate,
            "visible": any(x.visible for x in geometries),
            "representation": representation,
            "appearance": appearance,
            "model": model,
        }

        state |= {
            k: np.concatenate(data[k]) if len(data[k]) else None
            for k in ("points", "quaternions", "normals")
        }

        ret = cls.__new__(cls)
        ret.__setstate__(state)
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

        vertex_cells = vtk.vtkCellArray()
        idx = np.arange(points.shape[0], dtype=int)
        cells = np.column_stack((np.ones(idx.size, dtype=int), idx)).flatten()
        vertex_cells.SetCells(idx.size, numpy_support.numpy_to_vtkIdTypeArray(cells))

        self._points.SetData(numpy_support.numpy_to_vtk(points, deep=False))
        if getattr(self, "_representation", None) in ("surface", "wireframe"):
            vertex_cells = None

        self._data.SetVerts(vertex_cells)
        return self._data.Modified()

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
        if normals is None:
            normals = np.full_like(self.points, fill_value=NORMAL_REFERENCE)
        elif normals is not None:
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
        self.color_points(
            np.arange(self.get_number_of_points(), dtype=np.int32), color=color
        )

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

        Notes
        -----
        Data in scalars can be invalidated during this operation.
        """
        scalars = np.asarray(scalars).ravel()
        if scalars.size == 1:
            scalars = np.full(
                (self.get_number_of_points()), fill_value=scalars, dtype=scalars.dtype
            )

        if scalars.size != self.get_number_of_points():
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
        if scalars_np.shape[0] != self.get_number_of_points():
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
        point_ids : np.ndarray
            Set of point indices to color
        color : tuple of float
            RGB color values (0-1) to apply to selected points
        """
        n_points = self.get_number_of_points()
        if not isinstance(point_ids, np.ndarray):
            point_ids = np.asarray(point_ids, dtype=np.int32)

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

    def swap_data(
        self,
        points,
        normals=None,
        faces=None,
        quaternions=None,
        model=None,
        meta: Dict = None,
        **kwargs,
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
        model : :py:class:`mosaic.parametrization.Parametrization`
            Model fitted to geometry data.
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

        self._model = model
        if isinstance(meta, dict):
            self._meta.update(meta)

            if "vertex_properties" in meta:
                self._vertex_properties = meta["vertex_properties"]

        self.set_color()
        appearance = self._appearance.copy()
        self.change_representation(self._representation)
        self.set_appearance(**appearance)

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
        clipping_planes = self._actor.GetMapper().GetClippingPlanes()

        # Use fitted mesh representation
        to_mesh = self.is_mesh_representation(representation)
        if to_mesh:
            mesh = self.model
            if not hasattr(mesh, "mesh"):
                warnings.warn(
                    "Surface/mesh/wireframe requires a fitted mesh model. "
                    "Fit a mesh parametrization first."
                )
                return None

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

        self._representation = representation
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

            # Geometries without normals are treated as having a normal (0,0,1)
            # We dont want to save this uninformative normal, because this can
            # get fairly expensive for large point clouds. Hence we just make the
            # arrow point in this default direction instead
            if self._data.GetPointData().GetNormals() is None:
                transform = vtk.vtkTransform()
                transform.RotateY(-90)
                transformFilter = vtk.vtkTransformPolyDataFilter()
                transformFilter.SetInputConnection(arrow.GetOutputPort())
                transformFilter.SetTransform(transform)
                transformFilter.Update()
                mapper.SetSourceConnection(transformFilter.GetOutputPort())

            mapper.SetScaleFactor(scale)
            mapper.SetOrientationArray("Normals")
            mapper.SetOrientationModeToDirection()
            mapper.SetScaleModeToNoDataScaling()
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

        elif to_mesh:
            self._cells.Reset()
            self._points.Reset()

            self.points = mesh.vertices
            self._set_faces(mesh.triangles)
            self.normals = mesh.compute_vertex_normals()

            mapper.SetInputData(self._data)
            if representation == "wireframe":
                prop.SetRepresentationToWireframe()
            else:
                prop.SetRepresentationToSurface()
                prop.SetEdgeVisibility(representation == "mesh")
                self._appearance["size"] = 2 if representation == "mesh" else 0

            if representation in ("surface", "wireframe"):
                prop.SetVertexVisibility(False)

        if clipping_planes:
            mapper.SetClippingPlanes(clipping_planes)
        return self.set_appearance()

    def is_mesh_representation(self, representation: str = None) -> bool:
        if representation is None:
            representation = self._representation
        return representation in ("mesh", "surface", "wireframe")

    def get_point_data(self):
        normals = self._data.GetPointData().GetNormals()
        if normals is not None:
            normals = np.asarray(normals)

        quaternions = self._data.GetPointData().GetArray("OrientationQuaternion")
        if quaternions is not None:
            quaternions = np.asarray(quaternions)

        return self.points, normals, quaternions


# For backwards compatibility
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
    target_resolution : float, optional
        Target physical resolution for lowpass filtering. Set to 0
        to disable filtering. By default 10.0 (Angstroms).
    **kwargs
        Additional keyword arguments passed to parent Geometry class.
    """

    def __init__(
        self,
        volume: np.ndarray = None,
        volume_sampling_rate=np.ones(3),
        target_resolution: float = 10.0,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._volume = None
        self._target_resolution = target_resolution
        self._lower_quantile = 0.0
        self._upper_quantile = 0.995

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

        # Gaussian smoothing to normalize volume to target physical resolution
        # sigma_voxels = target_resolution / (2 * sampling_rate)
        pipeline_input = None
        self._smoother = vtk.vtkImageGaussianSmooth()
        self._smoother.SetInputData(self._volume)
        max_sampling_rate = np.max(volume_sampling_rate)
        self._applies_smoothing = (
            target_resolution > 0 and target_resolution > max_sampling_rate
        )
        if self._applies_smoothing:
            sigma = target_resolution / (2.0 * max_sampling_rate)
            self._smoother.SetStandardDeviation(sigma)
            self._smoother.SetRadiusFactor(2.0)
            self._smoother.Update()
            pipeline_input = self._smoother.GetOutputPort()

            smoothed_data = self._smoother.GetOutput()
            scalars = smoothed_data.GetPointData().GetScalars()
            volume = numpy_support.vtk_to_numpy(scalars)

        isovalue = np.quantile(volume, self._upper_quantile)
        self._surface = vtk.vtkFlyingEdges3D()
        if pipeline_input is not None:
            self._surface.SetInputConnection(pipeline_input)
        else:
            self._surface.SetInputData(self._volume)
        self._surface.SetValue(0, isovalue)
        self._surface.ComputeNormalsOn()

        # Center the isosurface mesh (transform works on polydata output)
        transformFilter = vtk.vtkTransformPolyDataFilter()
        transformFilter.SetInputConnection(self._surface.GetOutputPort())
        transformFilter.SetTransform(transform)

        mapper = vtk.vtkGlyph3DMapper()
        mapper.SetInputData(self._data)
        mapper.SetSourceConnection(transformFilter.GetOutputPort())
        mapper.SetOrientationModeToQuaternion()
        mapper.SetScaleModeToNoDataScaling()
        mapper.SetOrientationArray("OrientationQuaternion")
        mapper.OrientOn()
        self._actor.SetMapper(mapper)

        if "upper_quantile" in kwargs and "lower_quantile" in kwargs:
            self.update_isovalue_quantile(
                upper_quantile=kwargs.get("upper_quantile"),
                lower_quantile=kwargs.get("lower_quantile"),
            )
        self._representation = "volume"

    def __getstate__(self):
        state = super().__getstate__()

        if self._volume is not None:
            state.update(
                {
                    "volume": self._raw_volume,
                    "volume_sampling_rate": self._volume_sampling_rate,
                    "lower_quantile": self._lower_quantile,
                    "upper_quantile": self._upper_quantile,
                    "target_resolution": self._target_resolution,
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

    def set_appearance(self, isovalue_percentile=99.5, **kwargs):
        if hasattr(self, "_raw_volume"):
            self._appearance["isovalue_percentile"] = isovalue_percentile
            self.update_isovalue_quantile(upper_quantile=isovalue_percentile / 100)
        super().set_appearance(**kwargs)

    def update_target_resolution(self, resolution: float):
        """
        Update the target physical resolution for lowpass filtering.

        Parameters
        ----------
        resolution : float
            Target resolution in physical units (e.g., Angstroms).
            Set to 0 to disable filtering.
        """
        self._target_resolution = max(0.0, resolution)
        max_sampling_rate = np.max(self._volume_sampling_rate)
        if resolution > 0 and resolution > max_sampling_rate:
            sigma = resolution / (2.0 * max_sampling_rate)
            self._smoother.SetStandardDeviation(sigma)
        else:
            self._smoother.SetStandardDeviation(0.0)
        self._smoother.Modified()


class SegmentationGeometry(Geometry):
    """
    Geometry class for binary segmentation volumes rendered via GPU ray casting.

    Parameters
    ----------
    points : np.ndarray, optional
        3D point coordinates with shape (n, 3).
    sampling_rate : np.ndarray, optional
        Voxel spacing along each axis.
    color : tuple, optional
        Base RGB color, by default (0.7, 0.7, 0.7).
    meta : dict, optional
        Metadata dictionary.
    **kwargs
        Additional keyword arguments (ignored).
    """

    # Rebuild volume when current size exceeds optimal by this factor
    _COMPACTION_THRESHOLD = 2.0

    def __init__(
        self,
        points=None,
        sampling_rate=None,
        color=BASE_COLOR,
        meta=None,
        **kwargs,
    ):
        from .utils import points_to_volume

        self.uuid = str(uuid4())
        self._cache = {}
        self._meta = {} if meta is None else meta
        self._model = None
        self._representation = "segmentation"
        self._vertex_properties = None

        self.sampling_rate = sampling_rate

        self._appearance = {
            "size": 8,
            "opacity": 1.0,
            "ambient": 0.5,
            "diffuse": 0.7,
            "specular": 0.0,
            "render_spheres": True,
            "base_color": color,
        }

        if points is not None:
            points = np.asarray(points, dtype=np.float32)
            self._input_points = points
            vol, offset = points_to_volume(
                points,
                sampling_rate=np.max(self.sampling_rate),
                use_offset=True,
                out_dtype=np.uint8,
            )
            self._volume_shape = vol.shape
            self._origin = (offset * self.sampling_rate).astype(np.float32)
        else:
            self._input_points = np.empty((0, 3), dtype=np.float32)
            self._volume_shape = (1, 1, 1)
            vol = None
            self._origin = np.zeros(3, dtype=np.float32)

        self._build_volume_pipeline(vol)
        self._set_appearance()

    def _build_volume_pipeline(self, initial_data=None):
        """Create vtkImageData, mapper, volume property, and vtkVolume.

        Parameters
        ----------
        initial_data : np.ndarray, optional
            Initial volume data (3D array). If None, volume is zero-filled.
        """
        spacing = self.sampling_rate.astype(np.float64)

        self._volume = vtk.vtkImageData()
        self._volume.SetDimensions(self._volume_shape)
        self._volume.SetSpacing(spacing)
        self._volume.SetOrigin(self._origin.astype(np.float64))
        self._volume.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 1)

        # Initialize from data if provided, otherwise leave zero-filled
        if initial_data is not None:
            np.copyto(self._vtk_scalars, initial_data.ravel(order="F"))

        self._vtk_mapper = vtk.vtkGPUVolumeRayCastMapper()
        self._vtk_mapper.SetInputData(self._volume)
        self._vtk_mapper.SetBlendModeToComposite()
        self._vtk_mapper.SetAutoAdjustSampleDistances(False)
        self._vtk_mapper.SetSampleDistance(float(min(spacing)))
        self._vtk_mapper.SetUseJittering(True)

        color_tf = vtk.vtkColorTransferFunction()
        self._update_color_tf(color_tf, self._appearance["base_color"])

        opacity_tf = vtk.vtkPiecewiseFunction()
        opacity = self._appearance.get("opacity", 1.0)
        opacity_tf.AddPoint(0, 0.0)
        opacity_tf.AddPoint(1, opacity)
        opacity_tf.AddPoint(255, opacity)

        self._vtk_property = vtk.vtkVolumeProperty()
        self._vtk_property.SetColor(color_tf)
        self._vtk_property.SetScalarOpacity(opacity_tf)
        self._vtk_property.SetInterpolationTypeToNearest()
        self._vtk_property.ShadeOn()
        self._vtk_property.SetAmbient(self._appearance.get("ambient", 0.5))
        self._vtk_property.SetDiffuse(self._appearance.get("diffuse", 0.7))
        self._vtk_property.SetSpecular(self._appearance.get("specular", 0.0))

        self._vtk_volume = vtk.vtkVolume()
        self._vtk_volume.SetMapper(self._vtk_mapper)
        self._vtk_volume.SetProperty(self._vtk_property)

        # Alias so parents set_visibility work unchanged
        self._actor = self._vtk_volume
        self._highlighted_flat = None

    @property
    def _vtk_scalars(self):
        """Numpy view of VTK scalar array (flat, Fortran order)."""
        return numpy_support.vtk_to_numpy(self._volume.GetPointData().GetScalars())

    def _coords_to_flat_indices(self, coords):
        """Convert world coordinates to flat volume indices.

        Parameters
        ----------
        coords : np.ndarray
            World coordinates, shape (n, 3).

        Returns
        -------
        np.ndarray
            Flat indices into the volume array (Fortran order).
            Only valid coordinates are returned.
        """
        voxel_coords = self._coord_to_voxel(coords)
        shape = np.asarray(self._volume_shape)

        # Filter to valid voxel indices
        mask = np.all((voxel_coords >= 0) & (voxel_coords < shape), axis=1)
        valid_coords = voxel_coords[mask]

        if valid_coords.shape[0] == 0:
            return np.array([], dtype=np.intp)

        return np.ravel_multi_index(
            (valid_coords[:, 0], valid_coords[:, 1], valid_coords[:, 2]),
            self._volume_shape,
            order="F",
        )

    @staticmethod
    def _update_color_tf(color_tf, base_color, highlight_color=None):
        """Update the color transfer function.

        Parameters
        ----------
        color_tf : vtk.vtkColorTransferFunction
            Color transfer function to populate.
        base_color : tuple
            RGB base color (0-1).
        highlight_color : tuple, optional
            RGB highlight color (0-1). Defaults to base_color.
        """
        if highlight_color is None:
            highlight_color = base_color

        color_tf.RemoveAllPoints()
        color_tf.AddRGBPoint(0, 0, 0, 0)
        color_tf.AddRGBPoint(1, *base_color)
        color_tf.AddRGBPoint(2, *highlight_color)

    @property
    def _data(self):
        """Return vtkImageData for GetBounds() compatibility."""
        return self._volume

    @property
    def points(self):
        """Original input point coordinates.

        Returns
        -------
        np.ndarray
            Point coordinates with shape (n_points, 3).
        """
        return self._input_points

    @points.setter
    def points(self, value):
        # Points are set via __init__ — ignore explicit sets
        pass

    def _coord_to_voxel(self, coords):
        """Convert world coordinates to voxel indices.

        Parameters
        ----------
        coords : np.ndarray
            World coordinates, shape (..., 3).

        Returns
        -------
        np.ndarray
            Integer voxel indices.
        """
        return np.rint((np.asarray(coords) - self._origin) / self.sampling_rate).astype(
            int
        )

    def get_number_of_points(self):
        """Number of points in the segmentation.

        Returns
        -------
        int
            Number of input points.
        """
        return self._input_points.shape[0]

    def subset(self, idx, copy=False):
        """
        Subset the segmentation to keep only selected points.

        Uses deferred volume compaction: removed voxels are masked to 0 (transparent)
        rather than immediately rebuilding the volume. The volume is only rebuilt
        when its size exceeds the optimal bounding box by _COMPACTION_THRESHOLD.

        Parameters
        ----------
        idx : int, slice, np.ndarray
            Indices into the point array (same order as ``.points``).
        copy : bool, optional
            If True, return a new SegmentationGeometry; otherwise modify in-place.

        Returns
        -------
        SegmentationGeometry
            The subsetted geometry.
        """
        n_points = self.get_number_of_points()
        if isinstance(idx, (int, np.integer)):
            idx = [idx]
        elif isinstance(idx, slice) or idx is ...:
            idx = np.arange(n_points)[idx]

        idx = np.asarray(idx)
        if idx.dtype == bool:
            idx = np.where(idx)[0]
        idx = idx[idx < n_points]

        new_points = self._input_points[idx]

        if copy:
            state = self.__getstate__()
            state["points"] = new_points
            state.pop("uuid", None)
            ret = self.__class__.__new__(self.__class__)
            ret.__setstate__(state)
            return ret

        removed_mask = np.ones(n_points, dtype=bool)
        removed_mask[idx] = False
        removed_points = self._input_points[removed_mask]

        self._input_points = new_points
        self._cache.clear()

        if new_points.shape[0] == 0:
            self._volume_shape = (1, 1, 1)
            self._origin = np.zeros(3, dtype=np.float32)
            self._build_volume_pipeline()
            self._set_appearance()
            return self

        if removed_points.shape[0] > 0:
            self._mask_voxels(removed_points)

        if self._should_compact(new_points):
            self._compact_volume(new_points)
        return self

    def _mask_voxels(self, points_to_mask):
        """Set voxels corresponding to given points to 0 (transparent).

        Parameters
        ----------
        points_to_mask : np.ndarray
            World coordinates of points to mask out, shape (n, 3).
        """
        flat_idx = self._coords_to_flat_indices(points_to_mask)
        if flat_idx.size == 0:
            return

        self._vtk_scalars[flat_idx] = 0

        # Clear highlights to prevent _reset_highlights from restoring masked voxels
        self._highlighted_flat = None
        self._volume.GetPointData().GetScalars().Modified()
        self._volume.Modified()

    def _should_compact(self, current_points):
        """Check if the volume should be rebuilt with a tighter bounding box.

        Parameters
        ----------
        current_points : np.ndarray
            Current active points, shape (n, 3).

        Returns
        -------
        bool
            True if volume should be compacted.
        """
        if current_points.shape[0] == 0:
            return False

        current_volume_size = np.prod(self._volume_shape)

        # Compute optimal bounding box for current points
        sampling = np.max(self.sampling_rate)
        positions = np.rint(np.divide(current_points, sampling)).astype(int)
        optimal_shape = positions.max(axis=0) - positions.min(axis=0) + 1
        optimal_size = np.prod(optimal_shape)

        return current_volume_size > self._COMPACTION_THRESHOLD * optimal_size

    def _compact_volume(self, current_points):
        """Rebuild the volume with a tight bounding box around current points.

        Parameters
        ----------
        current_points : np.ndarray
            Current active points, shape (n, 3).
        """
        from .utils import points_to_volume

        vol, offset = points_to_volume(
            current_points,
            sampling_rate=np.max(self.sampling_rate),
            use_offset=True,
            out_dtype=np.uint8,
        )
        self._volume_shape = vol.shape
        self._origin = (offset * self.sampling_rate).astype(np.float32)
        self._build_volume_pipeline(vol)
        self._set_appearance()

    def __getitem__(self, idx):
        """Array-like indexing returning a copy."""
        return self.subset(idx, copy=True)

    def _reset_highlights(self):
        """Reset previously highlighted voxels back to label 1. O(n_highlighted)."""
        if self._highlighted_flat is None:
            return
        self._vtk_scalars[self._highlighted_flat] = 1
        self._highlighted_flat = None
        self._volume.GetPointData().GetScalars().Modified()
        self._volume.Modified()

    def color_points(self, point_ids, color):
        """Highlight specific points via transfer function labeling.

        Parameters
        ----------
        point_ids : np.ndarray
            Indices into the point array to highlight.
        color : tuple of float
            RGB highlight color (0-1).
        """
        if not isinstance(point_ids, np.ndarray):
            point_ids = np.asarray(point_ids, dtype=np.int32)
        point_ids = point_ids[point_ids < self.get_number_of_points()]

        self._reset_highlights()
        flat_idx = self._coords_to_flat_indices(self._input_points[point_ids])
        if flat_idx.size > 0:
            self._vtk_scalars[flat_idx] = 2
            self._highlighted_flat = flat_idx
            self._volume.GetPointData().GetScalars().Modified()
            self._volume.Modified()

        color_tf = self._vtk_property.GetRGBTransferFunction()
        self._update_color_tf(color_tf, self._appearance["base_color"], color)
        self._vtk_property.Modified()

    def set_color(self, color=None):
        """Set the displayed color, resetting any per-point highlights.

        Parameters
        ----------
        color : tuple of float, optional
            RGB color values (0-1). Uses stored base color if None.
        """
        if color is None:
            color = self._appearance["base_color"]

        self._reset_highlights()

        color_tf = self._vtk_property.GetRGBTransferFunction()
        self._update_color_tf(color_tf, color)
        self._vtk_property.Modified()

    def set_appearance(
        self,
        size=None,
        opacity=None,
        render_spheres=None,
        ambient=None,
        diffuse=None,
        specular=None,
        color=None,
        **kwargs,
    ):
        """Set visual appearance, ignoring point-specific parameters.

        Parameters
        ----------
        size : ignored
        opacity : float, optional
        render_spheres : ignored
        ambient : float, optional
        diffuse : float, optional
        specular : float, optional
        color : tuple of float, optional
        **kwargs
            Additional parameters (e.g. base_color, highlight_color)
            stored in appearance dict for compatibility with base class.
        """
        params = {
            "opacity": opacity,
            "ambient": ambient,
            "diffuse": diffuse,
            "specular": specular,
            **kwargs,
        }
        self._appearance.update({k: v for k, v in params.items() if v is not None})
        self._set_appearance()

        if color is None:
            color = self._appearance.get("base_color", BASE_COLOR)
        self._appearance["base_color"] = color
        self.set_color(color)

    def _set_appearance(self):
        """Propagate appearance settings to vtkVolumeProperty."""
        if not hasattr(self, "_vtk_property"):
            return None

        self._vtk_property.SetAmbient(self._appearance.get("ambient", 0.5))
        self._vtk_property.SetDiffuse(self._appearance.get("diffuse", 0.7))
        self._vtk_property.SetSpecular(self._appearance.get("specular", 0.0))

        opacity = self._appearance.get("opacity", 1.0)
        opacity_tf = self._vtk_property.GetScalarOpacity()
        opacity_tf.RemoveAllPoints()
        opacity_tf.AddPoint(0, 0.0)
        opacity_tf.AddPoint(1, opacity)
        opacity_tf.AddPoint(255, opacity)

    def __getstate__(self):
        return {
            "points": self._input_points,
            "sampling_rate": self.sampling_rate,
            "meta": self._meta,
            "visible": self.visible,
            "appearance": self._appearance,
            "uuid": self.uuid,
        }

    def __setstate__(self, state):
        uuid = state.pop("uuid", None)
        visible = state.pop("visible", True)
        appearance = state.pop("appearance", {})

        self.__init__(**state)
        self.set_visibility(visible)

        if uuid is not None:
            self.uuid = uuid
        self.set_appearance(**appearance)

    @property
    def normals(self):
        return super().normals

    @normals.setter
    def normals(self, value):
        pass

    @property
    def quaternions(self):
        return super().quaternions

    @quaternions.setter
    def quaternions(self, value):
        pass

    def change_representation(self, representation=None):
        """Volume-only geometry — representation changes are not supported."""
        warnings.warn("SegmentationGeometry does not support representation changes.")
        return None

    def is_mesh_representation(self, representation=None):
        return False

    def set_scalars(self, scalars, color_lut, scalar_range=None, use_point=False):
        """Set scalar data for coloring points via the volume transfer function.

        Quantizes scalars to uint8 [1, 255] (0 = transparent background),
        writes them into voxels in-place, and builds a color transfer function
        by sampling the lookup table.

        Parameters
        ----------
        scalars : array-like
            Scalar values for each point.
        color_lut : vtk.vtkLookupTable
            Color lookup table for mapping scalars to colors.
        scalar_range : tuple, optional
            Min and max scalar range for color mapping.
        use_point : bool, optional
            Ignored (kept for API compatibility with base class).
        """
        scalars = np.asarray(scalars, dtype=np.float32).ravel()
        if scalars.size == 1:
            scalars = np.full(
                self.get_number_of_points(), fill_value=scalars, dtype=np.float32
            )
        if scalars.size != self.get_number_of_points():
            return None

        if scalar_range is None:
            scalar_range = (float(scalars.min()), float(scalars.max()))
        smin, smax = scalar_range

        # Quantize to [1, 255], 0 is reserved for transparent background
        if smax > smin:
            normalized = (scalars - smin) / (smax - smin)
        else:
            normalized = np.full_like(scalars, 0.5)
        quantized = np.clip(np.rint(normalized * 254 + 1), 1, 255).astype(np.uint8)

        self._reset_highlights()

        # Get flat indices and corresponding quantized values for valid coords
        voxel_coords = self._coord_to_voxel(self._input_points)
        shape = np.asarray(self._volume_shape)
        mask = np.all((voxel_coords >= 0) & (voxel_coords < shape), axis=1)
        valid_coords = voxel_coords[mask]
        valid_quantized = quantized[mask]

        if valid_coords.shape[0] == 0:
            return None

        flat_idx = np.ravel_multi_index(
            (valid_coords[:, 0], valid_coords[:, 1], valid_coords[:, 2]),
            self._volume_shape,
            order="F",
        )

        self._vtk_scalars[flat_idx] = valid_quantized
        self._highlighted_flat = flat_idx
        self._volume.GetPointData().GetScalars().Modified()
        self._volume.Modified()

        # Build color TF by sampling the LUT across the quantized range
        color_tf = self._vtk_property.GetRGBTransferFunction()
        color_tf.RemoveAllPoints()
        color_tf.AddRGBPoint(0, 0, 0, 0)
        rgb = [0.0, 0.0, 0.0]
        for q in range(1, 256):
            t = (q - 1) / 254.0
            color_lut.GetColor(smin + t * (smax - smin), rgb)
            color_tf.AddRGBPoint(q, *rgb)
        self._vtk_property.Modified()

    def swap_data(self, *args, **kwargs):
        """Data swapping not supported for volume geometry."""
        warnings.warn("swap_data is not supported for SegmentationGeometry.")
        return None


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

        meta = self._trajectory[frame_idx]
        model = meta.get("fit")
        if not hasattr(model, "mesh"):
            return False

        meta = {k: v for k, v in meta.items() if k != "fit"}
        self.swap_data(
            points=model.vertices,
            faces=model.triangles,
            normals=model.compute_vertex_normals(),
            meta=meta,
            model=model,
        )
        return True
