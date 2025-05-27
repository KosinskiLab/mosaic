""" Implements DataContainer as handler of Geometry object collections.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from functools import wraps
from typing import List, Tuple, Union, Dict, Callable

import vtk
import numpy as np
from sklearn.cluster import KMeans

from .utils import (
    statistical_outlier_removal,
    dbscan_clustering,
    eigenvalue_outlier_removal,
    connected_components,
    com_cluster_points,
    find_closest_points,
    birch_clustering,
)


def apply_over_indices(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(self, indices: List[int], *args, **kwargs) -> None:
        if isinstance(indices, int):
            indices = [indices]
        for index in indices:
            if not self._index_ok(index):
                continue
            geometry = self.data[index]
            new_points = func(self, geometry=geometry, *args, **kwargs)
            if isinstance(new_points, np.ndarray):
                geometry.swap_data(new_points)
            elif new_points == 101:
                self.remove(index)

    return wrapper


class DataContainer:
    """
    Container for managing and manipulating point cloud data collections.

    Parameters
    ----------
    base_color : tuple of float, optional
        Default color for points in RGB format in range 0-1.
        Default is (0.7, 0.7, 0.7).
    highlight_color : tuple of float, optional
        Highlight color for points in RGB format in range 0-1.
        Default is (0.8, 0.2, 0.2).
    """

    def __init__(self, base_color=(0.7, 0.7, 0.7), highlight_color=(0.8, 0.2, 0.2)):
        self.data = []
        self.metadata = {}
        self.base_color = base_color
        self.highlight_color = highlight_color

    def __getitem__(self, idx):
        """
        Get a subset of the DataContainer.

        Parameters
        ----------
        idx : int, slice, or list-like
            Index, slice, or list of indices to retrieve.

        Returns
        -------
        DataContainer
            A new DataContainer containing the specified geometries.
        """
        indices = []
        if isinstance(idx, int):
            indices = [idx]
        elif isinstance(idx, slice) or idx is ...:
            indices = np.arange(len(self.data))[idx]
        elif hasattr(idx, "__iter__"):
            indices = list(idx)
        elif isinstance(idx, np.ndarray):
            if idx.dtype == bool:
                indices = np.where(idx)
        else:
            raise TypeError(f"Invalid index type: {type(idx)}")

        result = DataContainer(
            base_color=self.base_color, highlight_color=self.highlight_color
        )
        result.metadata = self.metadata.copy()
        result.data = [self.data[i] for i in indices if self._index_ok(i)]
        return result

    def update(self, other: "DataContainer"):
        """Update current class instance with data from another container.

        Parameters
        ----------
        other : DataContainer
            Container whose data will be copied.
        """
        self.data.clear()
        self.data.extend(other.data)
        self.metadata.clear()
        self.metadata.update(other.metadata)

    def get_actors(self):
        """Get VTK actors from all geometries.

        Returns
        -------
        list
            List of VTK actors.
        """
        return [x.actor for x in self.data]

    def add(self, points, color=None, **kwargs):
        """Add a new geometry object to the container.

        Parameters
        ----------
        points : np.ndarray or Geometry
            Points to add to the container.
        color : tuple of float, optional
            RGB color values for the point cloud.

        Returns
        -------
        int
            Index of the new point cloud.
        """
        from .geometry import Geometry

        if color is None:
            color = self.base_color

        if issubclass(type(points), Geometry):
            new_geometry = points
        else:
            new_geometry = Geometry(points, color=color, **kwargs)

        new_geometry._appearance["highlight_color"] = self.highlight_color
        self.data.append(new_geometry)
        return len(self.data) - 1

    def remove(self, indices: Union[int, List[int]]):
        """Remove geometries at specified indices.

        Parameters
        ----------
        indices : int or list of int
            Indices of geometries to remove.
        """
        if isinstance(indices, int):
            indices = [indices]

        indices = [x for x in indices if self._index_ok(x)]

        # Reverse order to avoid potential shift issue
        for index in sorted(indices, reverse=True):
            self.data.pop(index)

    def new(self, data: Union[np.ndarray, List[int]], *args, **kwargs) -> int:
        """Create new point cloud from existing data.

        Parameters
        ----------
        data : np.ndarray or list of int
            Points or indices of existing clouds to use.

        Returns
        -------
        int
            Index of new point cloud, -1 if creation failed.
        """
        if len(data) == 0:
            return -1
        if not isinstance(data, np.ndarray):
            if "sampling_rate" not in kwargs:
                kwargs["sampling_rate"] = self.data[data[0]]._sampling_rate

            geometries = [self.data[i] for i in data]
            data = np.concatenate([x.points for x in geometries])
            kwargs["normals"] = np.concatenate([x.normals for x in geometries])

        return self.add(data, *args, **kwargs)

    def merge(self, indices: List[int]) -> int:
        """Merge multiple geometries into one.

        Parameters
        ----------
        indices : list of int
            Indices of geometries to merge.

        Returns
        -------
        int
            Index of merged cloud, negative value if merge failed.
        """
        if len(indices) < 2:
            return -1
        indices = [x for x in indices if self._index_ok(x)]
        new_index = self.new(indices)
        self.remove(indices)
        return new_index - len(indices)

    def duplicate(self, indices: List[int]) -> int:
        """Duplicate different geometries

        Parameters
        ----------
        indices : list of int
            Indices of geometries to merge.

        Returns
        -------
        int
            Number of added geometries.
        """
        for index in indices:
            self.add(self.data[index][...])
        return len(indices)

    def split(self, indices: List[int], k=2) -> Tuple[int, int]:
        """Split point cloud into k using K-means.

        Parameters
        ----------
        indices : list of int
            Single-element list with index of cloud to split.
        k : int
            Number of clusteres.

        Returns
        -------
        tuple of int
            Indices of resulting clouds, -1 if split failed.
        """
        if len(indices) != 1:
            return -1

        data = np.concatenate([self._get_cluster_points(i) for i in indices])
        sampling_rate = self.data[indices[0]]._sampling_rate
        clustering = KMeans(n_clusters=k, n_init="auto").fit(data)

        self.remove(indices)

        new_cluster = []
        new_indices = np.asarray(clustering.labels_)
        for new_clusters in np.unique(new_indices):
            new_cluster.append(
                self.add(
                    data[np.where(new_indices == new_clusters)],
                    sampling_rate=sampling_rate,
                )
            )

        return tuple(new_cluster)

    @apply_over_indices
    def decimate(self, geometry, method: str = "core", **kwargs) -> int:
        """
        Decimate point cloud using specified method

        Parameters
        ----------
        geometry : :py:class:`mosaic.geometry.Geometry`
            Cloud to decimate.
        method : str
            Method to use. Options are:
            - 'outer' : Keep outer hull
            - 'core' : Keep core
            - 'inner' : Keep inner hull
        **kwargs
            Additional arguments passed to the chosen method.

        Returns
        -------
        int
            Index of newly added point cloud.
        """
        from .parametrization import ConvexHull

        points = geometry.points
        cutoff = 4 * np.max(geometry._sampling_rate)
        if method == "core":
            points = com_cluster_points(points, cutoff)
        elif method == "outer":
            hull = ConvexHull.fit(
                points,
                elastic_weight=0,
                curvature_weight=0,
                volume_weight=0,
                voxel_size=geometry._sampling_rate,
            )
            hull_points = hull.sample(int(0.5 * points.shape[0]))
            _, indices = find_closest_points(points, hull_points)
            points = points[np.unique(indices)]
        elif method == "inner":
            # Budget ray-casting using spherical coordinates
            centroid = np.mean(points, axis=0)
            centered_points = points - centroid

            r = np.linalg.norm(centered_points, axis=1)
            theta = np.arccos(centered_points[:, 2] / r)
            phi = np.arctan2(centered_points[:, 1], centered_points[:, 0])

            n_phi_bins = 360
            theta_idx = np.digitize(theta, np.linspace(0, np.pi, n_phi_bins // 2))
            phi_idx = np.digitize(phi, np.linspace(-np.pi, np.pi, n_phi_bins))
            bin_id = theta_idx * n_phi_bins + phi_idx

            inner_indices = []
            for b in np.unique(bin_id):
                mask = np.where(bin_id == b)[0]
                inner_indices.append(mask[np.argmin(r[mask])])

            points = points[inner_indices]
        else:
            print("Supported methods are 'inner', 'core' and 'outer.")

        return self.add(points, sampling_rate=geometry._sampling_rate)

    @apply_over_indices
    def downsample(self, geometry, method: str = "radius", **kwargs) -> int:
        """
        Downsample point cloud using specified method

        Parameters
        ----------
        geometry : :py:class:`mosaic.geometry.Geometry`
            Cloud to decimate.
        method : str
            Method to use. Options are:
            - 'radius' : Remove points that fall within radius of each other.
            - 'number' : Randomly subsample points to number.
        **kwargs
            Additional arguments passed to the chosen method.

        Returns
        -------
        int
            Index of newly added point cloud.
        """
        points, normals = geometry.points, geometry.normals
        if method.lower() == "radius":
            import open3d as o3d

            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points)
            pcd.normals = o3d.utility.Vector3dVector(normals)
            pcd = pcd.voxel_down_sample(**kwargs)
            points = np.asarray(pcd.points)
            normals = np.asarray(pcd.normals)
        else:
            size = kwargs.get("size", 1000)
            size = min(size, points.shape[0])
            keep = np.random.choice(range(points.shape[0]), replace=False, size=size)
            points, normals = points[keep], normals[keep]

        return self.add(points, normals=normals, sampling_rate=geometry._sampling_rate)

    @apply_over_indices
    def crop(
        self, geometry, distance: float, query: np.ndarray, keep_smaller: bool = True
    ):
        """Crop geometry based on distance to query points.

        Parameters
        ----------
        geometry : :py:class:`mosaic.geometry.Geometry`
            Cloud to crop.
        query : np.ndarray
            Points to compute distances to.
        distance : float
            Distance threshold for cropping.

        Returns
        -------
        ndarray
            Remaining points after cropping.
        """
        dist = geometry.compute_distance(query_points=query, cutoff=distance)
        if keep_smaller:
            return geometry.points[dist < distance]
        return geometry.points[dist >= distance]

    @apply_over_indices
    def sample(self, geometry, sampling: float, method: str):
        """Sample points from cloud.

        Parameters
        ----------
        geometry : :py:class:`mosaic.geometry.Geometry`
            Cloud to sample from.
        sampling : float
            Sampling rate or number of points.
        method : str
            Sampling method to use.

        Returns
        -------
        ndarray
            Sampled points.
        """
        cloud_fit = geometry._meta.get("fit", None)
        if cloud_fit is None:
            return geometry.points

        n_samples, kwargs = sampling, {}
        if method != "N points":
            n_samples = cloud_fit.points_per_sampling(sampling)
            kwargs["mesh_init_factor"] = 5

        return cloud_fit.sample(int(n_samples), **kwargs)

    @apply_over_indices
    def trim(self, geometry, min_value, max_value, axis: str = "z"):
        """Trim points based on axis-aligned bounds.

        Parameters
        ----------
        geometry : :py:class:`mosaic.geometry.Geometry`
            Cloud to trim.
        min_value : float
            Minimum bound value.
        max_value : float
            Maximum bound value.
        axis : str, optional
            Axis along which to trim, z by default.

        Returns
        -------
        ndarray
            Remaining points after trimming.

        Raises
        ------
        ValueError
            If an invalid trim_axis is provided.
        """
        _axis_map = {"x": 0, "y": 1, "z": 2}

        trim_column = _axis_map.get(axis)
        if trim_column is None:
            raise ValueError(f"Value for trim axis must be in {_axis_map.keys()}.")

        points = geometry.points

        coordinate_colum = points[:, trim_column]
        mask = np.logical_and(
            coordinate_colum > min_value,
            coordinate_colum < max_value,
        )
        return points[mask]

    @apply_over_indices
    def connected_components(self, geometry, **kwargs):
        """Identify connected components in a point cloud.

        Parameters
        ----------
        geometry : :py:class:`mosaic.geometry.Geometry`
            Cloud to cluster.
        """
        sampling = geometry.sampling_rate
        components = connected_components(geometry.points, sampling_rate=sampling)
        for component in components:
            self.add(component, sampling_rate=sampling)
        return 101

    @apply_over_indices
    def dbscan_cluster(self, geometry, **kwargs):
        """Perform DBSCAN clustering.

        Parameters
        ----------
        geometry : :py:class:`mosaic.geometry.Geometry`
            Cloud to cluster.
        kwargs : dict
            Keyword arguments passed to py:meth:`mosaic.utils.birch_clustering`

        Returns
        -------
        ndarray
            Clustered points.
        """
        ret = dbscan_clustering(geometry.points, **kwargs)
        for component in ret:
            self.add(component, sampling_rate=geometry._sampling_rate)
        return None

    @apply_over_indices
    def birch_cluster(self, geometry, **kwargs):
        """
        Perform Birch clustering on the input points using skimage.

        Parameters
        ----------
        geometry : ndarray
            Input point cloud.
        kwargs : dict
            Keyword arguments passed to py:meth:`mosaic.utils.birch_clustering`

        Returns
        -------
        list
            List of clusters, where each cluster is an array of points.
        """
        ret = birch_clustering(geometry.points, **kwargs)
        for component in ret:
            self.add(component, sampling_rate=geometry._sampling_rate)
        return None

    @apply_over_indices
    def remove_outliers(self, geometry, method="statistical", **kwargs):
        """Remove outliers from point cloud.

        Parameters
        ----------
        geometry : :py:class:`mosaic.geometry.Geometry`
            Cloud to process.
        method : str, optional
            'statistical' or 'eigenvalue', default 'statistical'.
        **kwargs
            Additional parameters for outlier removal.

        Returns
        -------
        int
            Index of newly added point cloud.
        """
        func = statistical_outlier_removal
        if method == "eigenvalue":
            func = eigenvalue_outlier_removal

        mask = func(geometry.points, **kwargs)
        if mask.sum() == 0:
            return None

        return self.add(geometry[mask])

    def highlight(self, indices: Tuple[int]):
        """Highlight specified geometries.

        Parameters
        ----------
        indices : tuple of int
            Indices of clouds to highlight.
        """
        _highlighted = getattr(self, "_highlighted_indices", set())
        for index, geometry in enumerate(self.data):
            if not self._index_ok(index):
                continue

            appearance = geometry._appearance
            color = appearance.get("base_color", self.base_color)
            if index in indices:
                color = appearance.get("highlight_color", self.highlight_color)
            elif index not in _highlighted:
                continue

            if not geometry.visible:
                continue

            geometry.set_color(color=color)

        self._highlighted_indices = set(indices)
        return None

    def highlight_points(self, index: int, point_ids: set, color: Tuple[float]):
        """Highlight specific points in a cloud.

        Parameters
        ----------
        index : int
            Index of target cloud.
        point_ids : set
            IDs of points to highlight.
        color : tuple of float
            RGB color for highlighting.
        """
        if self._index_ok(index):
            geometry = self.data[index]
            if color is None:
                color = geometry._appearance.get("highlight_color", (0.8, 0.2, 0.2))
            geometry.color_points(point_ids, color)

    def change_visibility(self, indices: Tuple[int], visible, **kwargs):
        """Change visibility of specified geometries.

        Parameters
        ----------
        indices : tuple of int
            Indices of geometries to apply operation to.
        """
        for index in indices:
            if not self._index_ok(index):
                continue
            self.data[index].set_visibility(visible)
        return None

    def update_appearance(self, indices: list, parameters: dict) -> None:
        from .formats.parser import load_density
        from .geometry import VolumeGeometry

        volume = parameters.get("volume", None)
        volume_path = parameters.get("volume_path", None)
        if volume_path is not None:
            volume = load_density(volume_path)

        if volume is not None:
            sampling = volume.sampling_rate
            volume = volume.data * parameters.get("scale", 1.0)

        parameters["isovalue_percentile"] = (
            parameters.get("isovalue_percentile", 99) / 100
        )
        for index in indices:
            if not self._index_ok(index):
                continue

            geometry = self.data[index]
            if volume is not None:
                state = geometry.__getstate__()

                try:
                    data_recent = np.allclose(state["volume"], volume)
                except Exception:
                    data_recent = False

                if not data_recent:
                    state["volume"] = volume
                    state["volume_sampling_rate"] = sampling
                    geometry = VolumeGeometry(vtk_actor=geometry._actor, **state)
                    self.data[index] = geometry

            geometry.set_appearance(**parameters)

        self.highlight(indices)

    def get_cluster_count(self) -> int:
        """Get number of geometries in container.

        Returns
        -------
        int
            Number of geometries.
        """
        return len(self.data)

    def get_cluster_size(self) -> List[int]:
        """Get number of points in each cloud.

        Returns
        -------
        list of int
            Point count for each cloud.
        """
        return [cluster.get_number_of_points() for cluster in self.data]

    def _index_ok(self, index: int):
        """Check if index is valid.

        Parameters
        ----------
        index : int
            Index to check.

        Returns
        -------
        bool
            True if index is valid.
        """
        try:
            index = int(index)
        except Exception:
            return False

        if 0 <= index < len(self.data):
            return True
        return False

    def _get_cluster_points(self, index: int) -> np.ndarray:
        """Get points from specified cloud.

        Parameters
        ----------
        index : int
            Index of target cloud.

        Returns
        -------
        ndarray
            Points from cloud, empty array if invalid index.
        """
        if self._index_ok(index):
            return self.data[index].points
        return np.array([])

    def _get_cluster_index(self, actor) -> int:
        """Get index of cloud containing actor.

        Parameters
        ----------
        actor : vtkActor
            Actor to search for.

        Returns
        -------
        int or None
            Index of cloud containing actor, None if not found.
        """
        for i, cluster in enumerate(self.data):
            if cluster.actor == actor:
                return i
        return None

    def add_selection(self, selected_point_ids: Dict[vtk.vtkActor, set]) -> int:
        """Add new cloud from selected points.

        Parameters
        ----------
        selected_point_ids : dict
            Mapping of vtkActor to selected point IDs.

        Returns
        -------
        int
            Index of new cloud, -1 if creation failed.
        """
        new_cluster, remove_cluster, sampling = [], [], 1
        for index, point_ids in selected_point_ids.items():
            if not len(point_ids):
                continue

            if not self._index_ok(index):
                continue

            # Ignore selected points from invisible geometries
            geometry = self.data[index]
            if not geometry.visible:
                continue

            if geometry.points.shape[0] == 0:
                continue

            sampling = geometry.sampling_rate
            mask = np.zeros(len(geometry.points), dtype=bool)
            try:
                mask[list(point_ids)] = True
            except Exception as e:
                print(e)
                return -1

            new_cluster.append((geometry.points[mask], geometry.normals[mask]))
            inverse_mask = np.invert(mask)
            if inverse_mask.sum() != 0:
                geometry.subset(inverse_mask)
            else:
                remove_cluster.append(index)

        self.remove(remove_cluster)

        if len(new_cluster):
            points = np.concatenate([x[0] for x in new_cluster])
            normals = np.concatenate([x[1] for x in new_cluster])
            return self.add(points, normals=normals, sampling_rate=sampling)
        return -1
