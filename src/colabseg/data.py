from functools import wraps
from typing import List, Tuple, Union, Dict, Callable

import vtk
import numpy as np
from sklearn.cluster import KMeans
from PyQt6.QtCore import pyqtSignal, QObject

from .io import DataIO, OrientationsIO
from .utils import (
    find_neighbors,
    trim,
    statistical_outlier_removal,
    dbscan_clustering,
    eigenvalue_outlier_removal,
)
from .point_cloud import PointCloud
from .parametrization import PARAMETRIZATION_TYPE
from .selection import DataContainerInteractor

AVAILABLE_PARAMETRIZATIONS = PARAMETRIZATION_TYPE
rbf = PARAMETRIZATION_TYPE.pop("rbf")
PARAMETRIZATION_TYPE["rbf [xy]"] = rbf
PARAMETRIZATION_TYPE["rbf [yz]"] = rbf
PARAMETRIZATION_TYPE["rbf [xz]"] = rbf


def _cluster_modifier(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        result = func(self, *args, **kwargs)
        self.data_changed.emit()
        return result

    return wrapper


def apply_over_indices(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(self, indices: List[int], *args, **kwargs) -> None:
        if isinstance(indices, int):
            indices = [indices]
        for index in indices:
            if not self._index_ok(index):
                continue
            point_cloud = self.data[index]
            new_points = func(self, point_cloud=point_cloud, *args, **kwargs)
            if new_points is not None:
                point_cloud.swap_data(new_points)

    return wrapper


class ColabsegData:
    def __init__(self, vtk_widget):
        # Data containers and GUI interaction elements
        self._data = DataContainer()
        self._models = DataContainer(highlight_color=(0.2, 0.4, 0.8))

        self.models = DataContainerInteractor(self._models, vtk_widget, prefix="Fit")
        # Swapped for now because of exclusive area picker
        self.data = DataContainerInteractor(self._data, vtk_widget)

    def open_file(self, filename):
        data, shape, sampling = DataIO().open_file(filename)

        point_manager = DataContainer(shape=shape)
        for x in data:
            point_manager.add(points=x.astype(np.float32), sampling_rate=sampling)

        self._data.update(point_manager)

        model_manager = DataContainer()
        self._models.update(model_manager)

    def add_fit(self, fit_type: str, fit_args: str = "xz"):
        cluster_indices = self.data._get_selected_indices()
        if fit_type not in PARAMETRIZATION_TYPE:
            return -1

        kwargs = {}
        if fit_type.startswith("rbf") and len(fit_type) == 8:
            kwargs["direction"] = fit_type[5:7]

        fit_object = PARAMETRIZATION_TYPE[fit_type]
        for index in cluster_indices:
            if not self._data._index_ok(index):
                continue
            points = self._data._get_cluster_points(index)
            fit = fit_object.fit(points, **kwargs)
            new_points = fit.sample(n_samples=1000)
            self._models.add(points=new_points, meta={"fit": fit, "points": points})

    def export_fit(self, file_path: str, file_format: str):
        fit_indices = self.models._get_selected_indices()

        center = False
        if file_format == "star (relion 5)":
            center = True

        export_data = {"points": [], "normals": []}
        for index in fit_indices:
            if not self._models._index_ok(index):
                continue
            points = self._models._get_cluster_points(index)

            cloud = self._models.data[index]
            normals = cloud._meta["fit"].compute_normal(points)
            if cloud._sampling_rate is not None:
                points = np.divide(points, cloud._sampling_rate)

            if center and self._data.shape is not None:
                points = np.subtract(points, np.divide(self._data.shape, 2).astype(int))

            export_data["points"].append(points)
            export_data["normals"].append(normals)

        if len(export_data["points"]) == 0:
            return -1

        if file_format.startswith("star"):
            file_format = "star"

        orientations = OrientationsIO(**export_data)
        orientations.to_file(file_path, file_format=file_format)


class DataContainer(QObject):
    data_changed = pyqtSignal()

    def __init__(
        self, shape=None, base_color=(0.7, 0.7, 0.7), highlight_color=(0.8, 0.2, 0.2)
    ):
        super().__init__()
        self.data, self.shape = [], shape
        self.actor_collection = vtk.vtkActorCollection()

        self.base_color = base_color
        self.highlight_color = highlight_color

    def _clear(self):
        self.data.clear()
        self.actor_collection.RemoveAllItems()

    @_cluster_modifier
    def update(self, other):
        self._clear()
        self.shape = other.shape
        for cluster in other.data:
            self.data.append(cluster)
            self.actor_collection.AddItem(cluster.actor)

    @_cluster_modifier
    def add(self, points, color=None, **kwargs):
        if color is None:
            color = self.base_color
        new_cloud = PointCloud(points, color=color, **kwargs)
        self.data.append(new_cloud)
        self.actor_collection.AddItem(new_cloud.actor)
        return len(self.data) - 1

    @_cluster_modifier
    def remove(self, indices: Union[int, List[int]]):
        if isinstance(indices, int):
            indices = [indices]

        # Reverse order to avoid potential shift issue
        for index in sorted(indices, reverse=True):
            if not self._index_ok(index):
                continue
            self.actor_collection.RemoveItem(self.data[index].actor)
            self.data.pop(index)

    def new(self, data: Union[np.ndarray, List[int]], *args, **kwargs) -> int:
        if len(data) == 0:
            return -1
        if not isinstance(data, np.ndarray):
            data = np.concatenate([self._get_cluster_points(i) for i in data])
        return self.add(data, *args, **kwargs)

    def merge(self, indices: List[int]) -> int:
        if len(indices) < 2:
            return -1
        new_index = self.new(indices)
        self.remove(indices)
        return new_index

    def split(self, indices: List[int]) -> Tuple[int, int]:
        if len(indices) != 1:
            return -1

        data = np.concatenate([self._get_cluster_points(i) for i in indices])
        clustering = KMeans(n_clusters=2, n_init="auto").fit(data)

        self.remove(indices)

        new_cluster = []
        new_indices = np.asarray(clustering.labels_)
        for new_clusters in np.unique(new_indices):
            new_cluster.append(self.add(data[np.where(new_indices == new_clusters)]))

        return tuple(new_cluster)

    @apply_over_indices
    def crop(self, point_cloud, distance: float):
        cloud_points = point_cloud._meta.get("points", None)
        if cloud_points is None:
            return None

        points = self._get_cloud_points(point_cloud)
        keep_points = find_neighbors(points, cloud_points, distance)
        return keep_points

    @apply_over_indices
    def sample(self, point_cloud, sampling: float, method: str):
        cloud_fit = point_cloud._meta.get("fit", None)
        if cloud_fit is None:
            return None

        n_samples = sampling
        if method != "N points":
            n_samples = cloud_fit.points_per_sampling(sampling)

        return cloud_fit.sample(int(n_samples))

    @apply_over_indices
    def trim(self, point_cloud, min_value, max_value, axis: str):
        points = self._get_cloud_points(point_cloud)
        new_points = trim(points, min_value, max_value, trim_axis=axis)
        return new_points

    @apply_over_indices
    def dbscan_cluster(self, point_cloud, distance, min_points):
        points = self._get_cloud_points(point_cloud)
        return dbscan_clustering(points, eps=distance, min_points=min_points)

    @apply_over_indices
    def remove_outliers(self, point_cloud, method="statistical", **kwargs):
        points = self._get_cloud_points(point_cloud)
        func = statistical_outlier_removal
        if method == "eigenvalue":
            func = eigenvalue_outlier_removal

        return func(points, **kwargs)

    def swapat(self, index: int, obj: PointCloud):
        self.data[index] = obj
        self.actor_collection.ReplaceItem(index, obj.actor)

    def highlight(self, indices: Tuple[int]):
        _highlighted = getattr(self, "_highlighted_indices", set())
        for index, cluster in enumerate(self.data):
            if not self._index_ok(index):
                continue
            color, opacity = self.base_color, 0.6
            if index in indices:
                color, opacity = self.highlight_color, 1.0
            elif index not in _highlighted:
                continue

            cluster.set_color(color)
            cluster.set_opacity(opacity)

        self._highlighted_indices = set(indices)
        return None

    def highlight_points(self, index: int, point_ids: set, color: Tuple[float]):
        if self._index_ok(index):
            self.data[index].color_points(point_ids, color)

    def get_cluster_count(self) -> int:
        return len(self.data)

    def get_cluster_size(self) -> List[int]:
        return [cluster.get_number_of_points() for cluster in self.data]

    def _index_ok(self, index: int):
        if 0 <= index < len(self.data):
            return True
        return False

    @staticmethod
    def _get_cloud_points(point_cloud):
        return np.asarray(point_cloud._points.GetData())

    def _get_cluster_points(self, index: int) -> np.ndarray:
        if self._index_ok(index):
            return self._get_cloud_points(self.data[index])
        return np.array([])

    def _get_cluster_index(self, actor) -> int:
        for i, cluster in enumerate(self.data):
            if cluster.actor == actor:
                return i
        return None

    def add_selection(self, selected_point_ids: Dict[vtk.vtkActor, set]) -> int:
        new_cluster, remove_cluster = [], []
        for cluster_index, point_ids in selected_point_ids.items():
            if not len(point_ids):
                continue

            points = self._get_cluster_points(cluster_index)
            if points.shape[0] == 0:
                continue
            mask = np.zeros(len(points), dtype=bool)
            try:
                mask[list(point_ids)] = True
            except Exception as e:
                print(e)

            new_cluster.append(points[mask])
            points = points[np.invert(mask)]
            if points.shape[0] != 0:
                self.swapat(cluster_index, PointCloud(points))
            else:
                remove_cluster.append(cluster_index)

        self.remove(remove_cluster)

        if len(new_cluster):
            return self.add(np.concatenate(new_cluster))
        return -1
