"""
Atomic geometries displayed by the vtk viewer.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import warnings
from uuid import uuid4
from typing import Dict, List, Optional, Tuple

import vtk
import numpy as np
from vtk.util import numpy_support

from .actor import create_actor
from .utils import normals_to_rot, apply_quat, NORMAL_REFERENCE
from .widgets.vtk_widgets import AXIS_COLORS


__all__ = [
    "GeometryData",
    "Geometry",
    "VolumeGeometry",
    "SegmentationGeometry",
    "GeometryTrajectory",
]


BASE_COLOR = (0.7, 0.7, 0.7)


class GeometryData:
    """Canonical store for geometry data.

    Parameters
    ----------
    polydata : vtk.vtkPolyData, optional
        Existing polydata to wrap.  When *None* an empty one is created.
    sampling_rate : array-like, optional
        Voxel spacing along each axis.
    model : object, optional
        Fitted parametrisation model.
    meta : dict, optional
        Metadata dictionary.
    vertex_properties : VertexPropertyContainer, optional
        Additional per-vertex properties.
    """

    def __init__(
        self,
        polydata=None,
        sampling_rate=None,
        model=None,
        meta=None,
        vertex_properties=None,
        points=None,
        normals=None,
        quaternions=None,
    ):
        if polydata is None and points is not None:
            # Legacy construction from numpy arrays
            polydata = vtk.vtkPolyData()

        self.polydata = polydata if polydata is not None else vtk.vtkPolyData()
        self.set_sampling_rate(sampling_rate)
        self.model = model
        self.meta = {} if meta is None else meta

        if vertex_properties is None:
            from .formats.parser import VertexPropertyContainer

            vertex_properties = VertexPropertyContainer()
        self.vertex_properties = vertex_properties

        # Push numpy arrays if provided directly
        if points is not None:
            self.points = points
        if normals is not None:
            self.normals = normals
        if quaternions is not None:
            self.quaternions = quaternions

    @classmethod
    def from_arrays(
        cls,
        points=None,
        normals=None,
        quaternions=None,
        sampling_rate=None,
        model=None,
        meta=None,
        vertex_properties=None,
    ):
        """Create a GeometryData from numpy arrays."""
        pd = vtk.vtkPolyData()
        gd = cls(
            polydata=pd,
            sampling_rate=sampling_rate,
            model=model,
            meta=meta,
            vertex_properties=vertex_properties,
        )
        if points is not None:
            gd.points = points
        if normals is not None:
            gd.normals = normals
        if quaternions is not None:
            gd.quaternions = quaternions
        return gd

    @property
    def points(self) -> np.ndarray:
        pts = self.polydata.GetPoints()
        if pts is None or self.get_number_of_points() == 0:
            return np.empty((0, 3), dtype=np.float32)
        return numpy_support.vtk_to_numpy(pts.GetData())

    @points.setter
    def points(self, value):
        if value is None:
            return self.polydata.SetPoints(None)
        value = np.asarray(value, dtype=np.float32)
        vtk_pts = vtk.vtkPoints()
        vtk_pts.SetDataTypeToFloat()
        vtk_pts.SetData(numpy_support.numpy_to_vtk(value, deep=False))
        self.polydata.SetPoints(vtk_pts)
        self._rebuild_vertex_cells()
        self.polydata.Modified()

    @property
    def normals(self) -> Optional[np.ndarray]:
        n = self.polydata.GetPointData().GetNormals()
        if n is None or n.GetNumberOfTuples() == 0:
            return np.full((self.get_number_of_points(), 3), NORMAL_REFERENCE)
        return numpy_support.vtk_to_numpy(n)

    @normals.setter
    def normals(self, value):
        if value is None:
            return self.polydata.GetPointData().SetNormals(None)
        value = np.asarray(value, dtype=np.float32)
        vtk_arr = numpy_support.numpy_to_vtk(value, deep=False)
        vtk_arr.SetName("Normals")
        self.polydata.GetPointData().SetNormals(vtk_arr)
        self.polydata.Modified()

    @property
    def quaternions(self) -> Optional[np.ndarray]:
        arr = self.polydata.GetPointData().GetArray("OrientationQuaternion")
        if arr is None or arr.GetNumberOfTuples() == 0:
            return None
        return numpy_support.vtk_to_numpy(arr)

    @quaternions.setter
    def quaternions(self, value):
        if value is None:
            return self.polydata.GetPointData().RemoveArray("OrientationQuaternion")
        value = np.asarray(value, dtype=np.float32)
        vtk_arr = numpy_support.numpy_to_vtk(value, deep=False)
        vtk_arr.SetName("OrientationQuaternion")
        self.polydata.GetPointData().AddArray(vtk_arr)
        self.polydata.Modified()

    def set_faces(self, faces):
        """Set triangular face connectivity on the polydata."""
        faces = np.asarray(faces, dtype=int)
        if faces.ndim == 2 and faces.shape[1] == 3:
            faces = np.concatenate(
                (np.full((faces.shape[0], 1), fill_value=3), faces),
                axis=1,
                dtype=int,
            )
        poly_cells = vtk.vtkCellArray()
        poly_cells.SetCells(
            faces.shape[0],
            numpy_support.numpy_to_vtkIdTypeArray(faces.ravel()),
        )
        self.polydata.SetPolys(poly_cells)
        self.polydata.SetVerts(None)
        self.polydata.Modified()

    def set_sampling_rate(self, sampling_rate):
        if sampling_rate is None:
            sampling_rate = np.ones(3, dtype=np.float32)
        sampling_rate = np.asarray(sampling_rate, dtype=np.float32)
        self.sampling_rate = np.repeat(sampling_rate, 3 // sampling_rate.size)

    @property
    def _meta(self):
        return self.meta

    def get_number_of_points(self):
        return self.polydata.GetNumberOfPoints()

    def get_point_data(self):
        return self.points, self.normals, self.quaternions

    def to_dict(self):
        """Return fields as a dict suitable for ``Geometry(**gd.to_dict())``."""
        return {
            "points": self.points,
            "normals": self.normals,
            "quaternions": self.quaternions,
            "sampling_rate": self.sampling_rate,
            "model": self.model,
            "meta": self.meta,
            "vertex_properties": self.vertex_properties,
        }

    def to_geometry(self):
        """Create a :class:`Geometry` that wraps this data's polydata directly."""
        return Geometry(
            polydata=self.polydata,
            sampling_rate=self.sampling_rate,
            model=self.model,
            meta=self.meta,
            vertex_properties=self.vertex_properties,
        )

    def __getitem__(self, idx):
        """Subset points via VTK extraction, return new GeometryData."""
        n_points = self.get_number_of_points()
        if isinstance(idx, (int, np.integer)):
            idx = [idx]
        elif isinstance(idx, slice) or idx is ...:
            idx = np.arange(n_points)[idx]

        idx = np.asarray(idx)
        if idx.dtype == bool:
            idx = np.where(idx)[0]
        idx = idx[idx < n_points]

        sel_node = vtk.vtkSelectionNode()
        sel_node.SetFieldType(vtk.vtkSelectionNode.POINT)
        sel_node.SetContentType(vtk.vtkSelectionNode.INDICES)
        sel_node.SetSelectionList(
            numpy_support.numpy_to_vtkIdTypeArray(idx.astype(np.int64))
        )

        sel = vtk.vtkSelection()
        sel.AddNode(sel_node)

        extract = vtk.vtkExtractSelection()
        extract.SetInputData(0, self.polydata)
        extract.SetInputData(1, sel)
        extract.Update()

        geom_filter = vtk.vtkGeometryFilter()
        geom_filter.SetInputData(extract.GetOutput())
        geom_filter.Update()

        vprops = self.vertex_properties
        if vprops is not None:
            vprops = vprops[idx]

        return GeometryData(
            polydata=geom_filter.GetOutput(),
            sampling_rate=self.sampling_rate.copy(),
            model=self.model,
            meta=self.meta.copy(),
            vertex_properties=vprops,
        )

    def _rebuild_vertex_cells(self):
        """Rebuild vertex cells as a single polyvertex for point cloud rendering.

        Skipped when the polydata already has polygon cells (mesh).
        """
        if self.polydata.GetNumberOfPolys() > 0:
            return
        n = self.polydata.GetNumberOfPoints()
        if n == 0:
            return
        cell_arr = np.empty(n + 1, dtype=np.int64)
        cell_arr[0] = n
        cell_arr[1:] = np.arange(n, dtype=np.int64)
        vertex_cells = vtk.vtkCellArray()
        vertex_cells.SetCells(1, numpy_support.numpy_to_vtkIdTypeArray(cell_arr))
        self.polydata.SetVerts(vertex_cells)


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
        polydata=None,
        **kwargs,
    ):
        self.uuid = str(uuid4())

        if polydata is not None:
            self._geometry_data = GeometryData(
                polydata=polydata,
                sampling_rate=sampling_rate,
                model=model,
                meta=meta,
                vertex_properties=vertex_properties,
            )
        else:
            if quaternions is not None:
                _normals = apply_quat(quaternions)
                if normals is not None:
                    if not np.allclose(_normals, normals, atol=1e-3):
                        warnings.warn(
                            "Orientation given by quaternions does not match "
                            "the supplied normal vectors. Overwriting normals "
                            "with quaternions for now."
                        )
                normals = _normals

            self._geometry_data = GeometryData.from_arrays(
                points=points,
                normals=normals,
                quaternions=quaternions,
                sampling_rate=sampling_rate,
                model=model,
                meta=meta,
                vertex_properties=vertex_properties,
            )

        self._representation = "pointcloud"

        self._actor = self._create_actor(vtk_actor)
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
    def _data(self):
        """The underlying vtkPolyData (owned by GeometryData)."""
        return self._geometry_data.polydata

    @property
    def _meta(self):
        return self._geometry_data.meta

    @property
    def model(self):
        return self._geometry_data.model

    @property
    def geometry_type(self) -> str:
        """Return a descriptive type of the current instance"""
        if self.model is None:
            return "cluster"
        if hasattr(self.model, "mesh"):
            return "trajectory" if hasattr(self, "_trajectory") else "mesh"
        return "parametric"

    @property
    def vertex_properties(self):
        return self._geometry_data.vertex_properties

    @property
    def sampling_rate(self):
        return self._geometry_data.sampling_rate

    @sampling_rate.setter
    def sampling_rate(self, sampling_rate):
        self._geometry_data.set_sampling_rate(sampling_rate)

    def __getstate__(self):
        """
        Get object state for pickling.

        Returns
        -------
        dict
            Serializable state dictionary.
        """
        return self._geometry_data.to_dict() | {
            "visible": self.visible,
            "appearance": self._appearance,
            "representation": self._representation,
            "uuid": self.uuid,
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
        if representation in ("volume", "segmentation"):
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
        return self._geometry_data.points

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

        self._geometry_data.points = points

    @property
    def normals(self):
        """
        Normal vectors at each point.

        Returns
        -------
        np.ndarray or None
            Normal vectors with shape (n_points, 3), or None if not set.
        """
        return self._geometry_data.normals

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

        self._geometry_data.normals = normals

        # Update associated quaternions if available
        if self._geometry_data.quaternions is not None:
            self.quaternions = normals_to_rot(self.normals, scalar_first=True)

    @property
    def quaternions(self):
        """
        Orientation quaternions for each point.

        Returns
        -------
        np.ndarray or None
            Quaternions in scalar-first format (n_points, 4), or None if not set.
        """
        quaternions = self._geometry_data.quaternions
        if quaternions is not None:
            return quaternions
        if self._geometry_data.points is not None:
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

        self._geometry_data.quaternions = quaternions

    def _set_faces(self, faces):
        """Set triangular face connectivity. Delegates to GeometryData."""
        self._geometry_data.set_faces(faces)

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
        base_color: Tuple[float] = None,
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
        base_color : tuple of float, optional
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

        if base_color is None:
            base_color = self._appearance.get("base_color", BASE_COLOR)
        self._appearance["base_color"] = base_color
        self.set_color(base_color)

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
        return self._geometry_data.get_number_of_points()

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
        No-op when in basis representation to preserve per-axis coloring.
        """
        if self._representation == "basis":
            return None

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
        # Check whether we have to synchronize quaternion representation
        if (
            quaternions is None
            and self._geometry_data.quaternions is not None
            and normals is not None
        ):
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

        self._geometry_data.model = model
        if isinstance(meta, dict):
            self._meta.update(meta)

            if "vertex_properties" in meta:
                self._geometry_data.vertex_properties = meta["vertex_properties"]

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

        # Using the uv map will cause distortions in other representations
        if self.actor.GetTexture():
            self.actor.SetTexture(None)

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

            arrow = vtk.vtkArrowSource()
            arrow.SetTipResolution(6)
            arrow.SetShaftResolution(6)
            arrow.SetTipRadius(0.08)
            arrow.SetShaftRadius(0.02)

            # One arrow per axis, oriented by quaternion
            n_pts = self.get_number_of_points()
            directions = np.empty((n_pts * 3, 3), dtype=np.float32)
            for i, axis in enumerate(np.eye(3)):
                directions[i::3] = apply_quat(self.quaternions, axis)

            basis_data = vtk.vtkPolyData()
            vtk_pts = vtk.vtkPoints()
            vtk_pts.SetData(
                numpy_support.numpy_to_vtk(
                    np.repeat(self.points, 3, axis=0).astype(np.float32),
                    deep=True,
                )
            )
            basis_data.SetPoints(vtk_pts)

            vtk_dirs = numpy_support.numpy_to_vtk(directions, deep=True)
            vtk_dirs.SetName("Directions")
            basis_data.GetPointData().AddArray(vtk_dirs)

            axis_idx = np.tile(np.arange(3, dtype=np.float32), n_pts)
            basis_data.GetPointData().SetScalars(
                numpy_support.numpy_to_vtk(axis_idx, deep=True)
            )

            lut = vtk.vtkLookupTable()
            lut.SetNumberOfTableValues(3)
            lut.SetRange(0.0, 2.0)
            for i, color in enumerate(AXIS_COLORS):
                lut.SetTableValue(i, *color, 1.0)
            lut.Build()

            mapper = vtk.vtkGlyph3DMapper()
            mapper.SetInputData(basis_data)
            mapper.SetSourceConnection(arrow.GetOutputPort())
            mapper.SetOrientationArray("Directions")
            mapper.SetOrientationModeToDirection()
            mapper.SetScaleFactor(scale)
            mapper.SetScaleModeToNoDataScaling()
            mapper.OrientOn()
            mapper.SetLookupTable(lut)
            mapper.SetScalarRange(0.0, 2.0)
            mapper.SetScalarVisibility(True)
            mapper.SetColorModeToMapScalars()

            self._actor.SetMapper(mapper)

        elif to_mesh:
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
        d = self._geometry_data
        return d.points, d.normals, d.quaternions


def _geometry_from_polydata(
    polydata,
    sampling_rate=None,
    color=BASE_COLOR,
    representation="surface",
    meta=None,
):
    """Create a :class:`Geometry` from an existing ``vtkPolyData``."""
    g = Geometry(
        polydata=polydata,
        sampling_rate=sampling_rate,
        meta=meta,
    )
    if representation == "surface":
        g.change_representation("surface")
    elif representation == "wireframe":
        g.change_representation("wireframe")
    return g


class SegmentationGeometry(Geometry):
    """
    Binary segmentation rendered as a surface mesh.

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

    # Rebuild mesh when current volume exceeds optimal by this factor
    _COMPACTION_THRESHOLD = 2.0

    def __init__(
        self,
        points=None,
        sampling_rate=None,
        color=BASE_COLOR,
        meta=None,
        volume=None,
        volume_origin=None,
        **kwargs,
    ):
        self.uuid = str(uuid4())
        self._geometry_data = GeometryData(
            points=points,
            sampling_rate=sampling_rate,
            meta=meta,
        )
        self._representation = "segmentation"

        self._appearance = {
            "size": 8,
            "opacity": 1.0,
            "ambient": 0.5,
            "diffuse": 0.7,
            "specular": 0.0,
            "render_spheres": True,
            "base_color": color,
        }

        if self._geometry_data.points is not None:
            from .utils import points_to_volume

            # Use a coarser grid for meshing to limit vertex count
            n_points = self._geometry_data.get_number_of_points()
            mesh_sampling = np.max(self.sampling_rate)
            if n_points > 500_000:
                mesh_sampling *= max(1, int(np.cbrt(n_points / 500_000)))

            vol, offset = points_to_volume(
                self._geometry_data.points,
                sampling_rate=mesh_sampling,
                use_offset=True,
                out_dtype=np.uint8,
            )
            self._volume_shape = vol.shape
            self._origin = (offset * mesh_sampling).astype(np.float32)
            self._mesh_sampling = mesh_sampling
        else:
            self._geometry_data.points = np.empty((0, 3), dtype=np.float32)
            self._volume_shape = (1, 1, 1)
            vol = None
            self._origin = np.zeros(3, dtype=np.float32)
            self._mesh_sampling = np.max(self.sampling_rate)

        self._build_surface(vol)
        self._set_appearance()

    def _build_surface(self, volume_data=None):
        """Extract a surface mesh and create the VTK actor.

        Parameters
        ----------
        volume_data : np.ndarray, optional
            Binary volume data (3D array). If None, an empty mesh is created.
        """
        self._highlighted_point_ids = None
        self._vertex_visible = None
        self._extract_surface_mesh(volume_data)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(self._mesh_polydata)
        mapper.ScalarVisibilityOff()

        self._actor = create_actor()
        self._actor.SetMapper(mapper)
        self._actor.GetProperty().SetColor(
            *self._appearance.get("base_color", BASE_COLOR)
        )

    def _extract_surface_mesh(self, volume_data=None):
        """
        Extract a surface mesh from binary volume data.

        Parameters
        ----------
        volume_data : np.ndarray, optional
            Binary 3D numpy array. If None, creates an empty mesh.
        """
        mesh_sr = getattr(self, "_mesh_sampling", np.max(self.sampling_rate))
        spacing = np.full(3, mesh_sr, dtype=np.float64)
        origin = self._origin.astype(np.float64)

        if volume_data is None:
            self._mesh_polydata = vtk.vtkPolyData()
            self._vertex_to_point_idx = np.array([], dtype=np.intp)
            return

        # Pad volume to ensure closed surface edges
        pad_width = 2
        vol_padded = np.pad(
            (volume_data != 0).astype(np.uint8),
            pad_width,
            mode="constant",
            constant_values=0,
        )
        padded_origin = origin - pad_width * spacing

        padded_volume = vtk.vtkImageData()
        padded_volume.SetDimensions(vol_padded.shape)
        padded_volume.SetSpacing(spacing)
        padded_volume.SetOrigin(padded_origin)
        padded_volume.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 1)
        vtk_arr = numpy_support.numpy_to_vtk(vol_padded.ravel(order="F"), deep=True)
        padded_volume.GetPointData().SetScalars(vtk_arr)

        flying_edges = vtk.vtkFlyingEdges3D()
        flying_edges.SetInputData(padded_volume)
        flying_edges.SetValue(0, 0.5)
        flying_edges.ComputeNormalsOn()
        flying_edges.Update()

        self._mesh_polydata = flying_edges.GetOutput()

        self._ensure_vertex_mapping(spacing)

    def _ensure_vertex_mapping(self, spacing):
        """
        Build the vertex-to-point-index mapping for the current mesh.

        Parameters
        ----------
        spacing : np.ndarray
            Voxel spacing (float64).
        """
        n_vertices = self._mesh_polydata.GetNumberOfPoints()
        n_points = self._geometry_data.get_number_of_points()

        if n_vertices > 0 and n_points > 0:
            vertices = numpy_support.vtk_to_numpy(
                self._mesh_polydata.GetPoints().GetData()
            )
            shape = np.asarray(self._volume_shape)

            # Build sorted sparse mapping: flat voxel index -> point index.
            voxel_coords = self._coord_to_voxel(self._geometry_data.points)
            valid = np.all((voxel_coords >= 0) & (voxel_coords < shape), axis=1)
            vc = voxel_coords[valid]
            flat_pts = np.ravel_multi_index(
                (vc[:, 0], vc[:, 1], vc[:, 2]), self._volume_shape, order="F"
            )
            valid_idx = np.where(valid)[0]

            # Sort and deduplicate; last point per voxel wins
            order = np.argsort(flat_pts, kind="stable")
            sorted_flat = flat_pts[order]
            sorted_point = valid_idx[order]

            # Keep last occurrence per voxel
            unique_mask = np.empty(len(sorted_flat), dtype=bool)
            unique_mask[-1] = True
            unique_mask[:-1] = sorted_flat[:-1] != sorted_flat[1:]
            sparse_flat = sorted_flat[unique_mask]
            sparse_point = sorted_point[unique_mask]

            def _lookup_flat(flat_indices):
                """Map flat voxel indices -> point indices via binary search."""
                idx = np.searchsorted(sparse_flat, flat_indices)
                idx = np.clip(idx, 0, len(sparse_flat) - 1)
                matched = sparse_flat[idx] == flat_indices
                result = np.full(len(flat_indices), -1, dtype=np.intp)
                result[matched] = sparse_point[idx[matched]]
                return result

            # Look up mesh vertex -> point index via voxel grid
            mv = self._coord_to_voxel(vertices)
            mv = np.clip(mv, 0, shape - 1)
            flat_mesh = np.ravel_multi_index(
                (mv[:, 0], mv[:, 1], mv[:, 2]), self._volume_shape, order="F"
            )
            self._vertex_to_point_idx = _lookup_flat(flat_mesh)

            # Fix boundary vertices: after smoothing, ~half the vertices sit
            # just outside the filled region. Shift inward along the mesh
            # normal to land on the correct filled voxel.
            unmapped = self._vertex_to_point_idx == -1
            if np.any(unmapped):
                normals_vtk = self._mesh_polydata.GetPointData().GetNormals()
                if normals_vtk is not None:
                    normals = numpy_support.vtk_to_numpy(normals_vtk)
                    shifted = vertices[unmapped] - 0.7 * normals[unmapped] * spacing
                    sv = self._coord_to_voxel(shifted)
                    sv = np.clip(sv, 0, shape - 1)
                    flat_shifted = np.ravel_multi_index(
                        (sv[:, 0], sv[:, 1], sv[:, 2]),
                        self._volume_shape,
                        order="F",
                    )
                    fixed = _lookup_flat(flat_shifted)
                    umask = np.where(unmapped)[0]
                    got_fix = fixed >= 0
                    self._vertex_to_point_idx[umask[got_fix]] = fixed[got_fix]

            # Use 6-connected neighbors for any remaining unmapped
            unmapped = self._vertex_to_point_idx == -1
            if np.any(unmapped):
                umask = np.where(unmapped)[0]
                uv = mv[unmapped]
                offsets = [
                    (1, 0, 0),
                    (-1, 0, 0),
                    (0, 1, 0),
                    (0, -1, 0),
                    (0, 0, 1),
                    (0, 0, -1),
                ]
                for di, dj, dk in offsets:
                    still_bad = self._vertex_to_point_idx[umask] == -1
                    if not np.any(still_bad):
                        break
                    si = np.where(still_bad)[0]
                    ni = np.clip(uv[si, 0] + di, 0, shape[0] - 1)
                    nj = np.clip(uv[si, 1] + dj, 0, shape[1] - 1)
                    nk = np.clip(uv[si, 2] + dk, 0, shape[2] - 1)
                    flat_nb = np.ravel_multi_index(
                        (ni, nj, nk), self._volume_shape, order="F"
                    )
                    found = _lookup_flat(flat_nb)
                    got = found >= 0
                    self._vertex_to_point_idx[umask[si[got]]] = found[got]

            # Map to nearest valid point index as last resort
            still_unmapped = self._vertex_to_point_idx == -1
            if np.any(still_unmapped):
                self._vertex_to_point_idx[still_unmapped] = 0
        else:
            self._vertex_to_point_idx = np.array([], dtype=np.intp)

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
        sr = getattr(self, "_mesh_sampling", np.max(self.sampling_rate))
        ret = np.rint((np.asarray(coords) - self._origin) / sr)
        return ret.astype(int)

    @property
    def _data(self):
        """Return mesh polydata for GetBounds() compatibility."""
        return self._mesh_polydata

    @property
    def points(self):
        """Original input point coordinates."""
        return self._geometry_data.points

    @points.setter
    def points(self, value):
        value = np.asarray(value, dtype=np.float32)
        self._geometry_data.points = value
        self._rebuild(value)

    @property
    def normals(self):
        return None

    @normals.setter
    def normals(self, value):
        pass

    @property
    def quaternions(self):
        return None

    @quaternions.setter
    def quaternions(self, value):
        pass

    def _set_vertex_scalars(self, vertex_scalars, color_lut, scalar_range):
        """
        Push per-vertex scalars and a LUT to the mapper.

        Parameters
        ----------
        vertex_scalars : np.ndarray or None
            Float32 per-vertex scalar array, or None for uniform color
            (only valid when no visibility mask is active).
        color_lut : vtk.vtkLookupTable
            Lookup table mapping scalar values to RGBA colors.
            NanColor is forced to transparent.
        scalar_range : tuple of float
            (min, max) range for the mapper.
        """
        if vertex_scalars is None:
            self._mesh_polydata.GetPointData().SetScalars(None)
            self._actor.GetMapper().ScalarVisibilityOff()
            return

        if self._vertex_visible is not None:
            vertex_scalars[~self._vertex_visible] = np.nan

        # vtkColorTransferFunction has no per-vertex alpha support in polygon
        # rendering so we sample it into a vtkLookupTable that does.
        if not isinstance(color_lut, vtk.vtkLookupTable):
            n_colors = 256
            lut = vtk.vtkLookupTable()
            lut.SetNumberOfTableValues(n_colors)
            lut.SetTableRange(*scalar_range)
            rgb = [0.0, 0.0, 0.0]
            smin, smax = scalar_range
            for i in range(n_colors):
                t = smin + (smax - smin) * i / max(n_colors - 1, 1)
                color_lut.GetColor(t, rgb)
                lut.SetTableValue(i, *rgb, 1.0)
            lut.Build()
            color_lut = lut

        color_lut.SetNanColor(0, 0, 0, 0)

        vtk_arr = numpy_support.numpy_to_vtk(vertex_scalars, deep=True)
        self._mesh_polydata.GetPointData().SetScalars(vtk_arr)

        mapper = self._actor.GetMapper()
        mapper.SetLookupTable(color_lut)
        mapper.SetScalarRange(*scalar_range)
        mapper.SetScalarModeToUsePointData()
        mapper.SetColorModeToMapScalars()
        mapper.ScalarVisibilityOn()

    def _make_color_lut(self, *colors):
        """
        Build a discrete LUT from one or more RGBA colors.

        Parameters
        ----------
        *colors : tuple of float
            RGB tuples (0-1). Each becomes one table entry.

        Returns
        -------
        vtk.vtkLookupTable
        """
        lut = vtk.vtkLookupTable()
        lut.SetNumberOfTableValues(len(colors))
        lut.SetTableRange(0.0, max(len(colors) - 1, 0.0))
        for i, c in enumerate(colors):
            lut.SetTableValue(i, *c, 1.0)
        lut.Build()
        return lut

    def color_points(self, point_ids, color):
        """
        Highlight specific points on the surface mesh.

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

        if point_ids.size == 0:
            return

        scalars = np.zeros(self.get_number_of_points(), dtype=np.float32)
        scalars[point_ids] = 1.0

        base_color = self._appearance.get("base_color", BASE_COLOR)
        lut = self._make_color_lut(base_color, color)
        self.set_scalars(scalars, lut, (0.0, 1.0))
        self._highlighted_point_ids = point_ids

    def set_scalars(self, scalars, color_lut, scalar_range=None, use_point=False):
        """
        Set scalar data for coloring the surface mesh.

        Parameters
        ----------
        scalars : array-like
            Scalar values for each point.
        color_lut : vtk.vtkLookupTable
            Color lookup table for mapping scalars to colors.
        scalar_range : tuple, optional
            Min and max scalar range for color mapping.
        use_point : bool, optional
            Ignored (kept for API compatibility).
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

        self._highlighted_point_ids = None

        if self._vertex_to_point_idx.size == 0:
            return None

        vertex_scalars = scalars[self._vertex_to_point_idx]
        self._set_vertex_scalars(vertex_scalars, color_lut, scalar_range)

    def set_color(self, color=None):
        """
        Set uniform mesh color, resetting any per-point highlights.

        Parameters
        ----------
        color : tuple of float, optional
            RGB color values (0-1). Uses stored base color if None.
        """
        if color is None:
            color = self._appearance.get("base_color", BASE_COLOR)
        self._highlighted_point_ids = None

        if self._vertex_visible is not None and not self._vertex_visible.all():
            n = self._mesh_polydata.GetNumberOfPoints()
            scalars = np.full(n, 0.0, dtype=np.float32)
            lut = self._make_color_lut(color)
            self._set_vertex_scalars(scalars, lut, (0.0, 0.0))
        else:
            self._set_vertex_scalars(None, None, None)
            self._actor.GetProperty().SetColor(*color)

    def subset(self, idx, copy=False):
        """
        Subset the segmentation, updating the vertex mapping.

        Parameters
        ----------
        idx : int, slice, np.ndarray
            Indices into the point array.
        copy : bool, optional
            If True, return a new geometry; otherwise modify in-place.

        Returns
        -------
        SegmentationGeometry
            The subsetted geometry.

        Notes
        -----
        For in-place subsetting, the mesh geometry is preserved but vertices
        corresponding to removed points are hidden via NaN scalars.
        Full mesh re-extraction only happens on rebuild.
        """
        n_points = self.get_number_of_points()
        if isinstance(idx, (int, np.integer)):
            idx = np.asarray([idx])
        elif isinstance(idx, slice) or idx is ...:
            idx = np.arange(n_points)[idx]
        idx = np.asarray(idx)
        if idx.dtype == bool:
            idx = np.where(idx)[0]
        idx = idx[idx < n_points]

        new_points = self._geometry_data.points[idx]

        if copy:
            state = self.__getstate__()
            state["points"] = new_points
            state.pop("uuid", None)
            ret = self.__class__.__new__(self.__class__)
            ret.__setstate__(state)
            return ret

        # In-place: remap vertex mapping and optionally rebuild
        n_old = n_points
        self._geometry_data.points = new_points

        if new_points.shape[0] == 0:
            self._volume_shape = (1, 1, 1)
            self._origin = np.zeros(3, dtype=np.float32)
            self._build_surface()
            self._set_appearance()
            return self

        if self._should_rebuild(new_points):
            self._rebuild(new_points)
            return self

        # Fast path: remap vertex->point indices
        if self._vertex_to_point_idx.size > 0:
            old_to_new = np.full(n_old, -1, dtype=np.intp)
            old_to_new[idx] = np.arange(idx.size)

            new_mapped = old_to_new[self._vertex_to_point_idx]
            visible = new_mapped >= 0

            if self._vertex_visible is not None:
                visible &= self._vertex_visible

            self._vertex_visible = visible
            self._vertex_to_point_idx = np.where(visible, new_mapped, 0)
            self._highlighted_point_ids = None
            self.set_color()
        return self

    def _should_rebuild(self, current_points):
        """
        Check if the mesh should be rebuilt with a tighter bounding box.

        Parameters
        ----------
        current_points : np.ndarray
            Current active points, shape (n, 3).

        Returns
        -------
        bool
            True if mesh should be rebuilt.
        """
        if current_points.shape[0] == 0:
            return False

        current_volume_size = np.prod(self._volume_shape)

        sampling = np.max(self.sampling_rate)
        positions = np.rint(np.divide(current_points, sampling)).astype(int)
        optimal_shape = positions.max(axis=0) - positions.min(axis=0) + 1
        optimal_size = np.prod(optimal_shape)

        return current_volume_size > self._COMPACTION_THRESHOLD * optimal_size

    def _rebuild(self, current_points):
        """Rebuild the mesh from scratch around current points.

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
        self._build_surface(vol)
        self._set_appearance()

    def change_representation(self, representation=None):
        """Segmentation geometry -- representation changes are not supported."""
        warnings.warn("SegmentationGeometry does not support representation changes.")
        return None

    def is_mesh_representation(self, representation=None):
        return False

    def swap_data(self, *args, **kwargs):
        """Data swapping not supported for segmentation geometry."""
        warnings.warn("swap_data is not supported for SegmentationGeometry.")
        return None

    def __getstate__(self):
        return {
            "points": self._geometry_data.points,
            "sampling_rate": self.sampling_rate,
            "meta": self._meta,
        } | {
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


# For backwards compatibility
class PointCloud(Geometry):
    pass


# TODO: Check whether this breaks backwards compatibility in sessions
class VolumeGeometry(SegmentationGeometry):
    pass
