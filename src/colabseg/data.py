""" Implements ColabsegData, which is reponsible for tracking overall
    application state and mediating interaction between segmentations
    and parametrizations.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import pickle
import numpy as np
from functools import wraps
from typing import Callable
from PyQt6.QtCore import pyqtSignal, QObject

from .io_utils import VertexDataLoader
from .container import DataContainer
from .interactor import DataContainerInteractor
from .parametrization import PARAMETRIZATION_TYPE


def _progress_decorator(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(self, *args, **kwargs) -> None:
        ret = None
        try:
            ret = func(self, *args, **kwargs)
        except Exception as e:
            print(e)
        finally:
            # Termination signal for listeners
            self.progress.emit(1)
        return ret

    return wrapper


class ColabsegData(QObject):
    progress = pyqtSignal(float)

    def __init__(self, vtk_widget):
        super().__init__()
        # Data containers and GUI interaction elements
        self.shape = None
        self._data = DataContainer()
        self._models = DataContainer(highlight_color=(0.2, 0.4, 0.8))

        self.models = DataContainerInteractor(self._models, vtk_widget, prefix="Fit")
        # Swapped for now because of exclusive area picker
        self.data = DataContainerInteractor(self._data, vtk_widget)

    def to_file(self, filename: str):
        state = {"shape": self.shape, "_data": self._data, "_models": self._models}
        with open(filename, "wb") as ofile:
            pickle.dump(state, ofile)

    def open_file(self, filename):
        sampling = 1
        if filename.endswith("pickle"):
            with open(filename, "rb") as ifile:
                data = pickle.load(ifile)

            shape = data["shape"]
            point_manager, model_manager = data["_data"], data["_models"]

        else:
            ret = VertexDataLoader().open_file(filename)

            if ret is None:
                return -1

            data, normals, (shape, offset), sampling = ret
            point_manager, model_manager = DataContainer(), DataContainer()
            for x, y in zip(data, normals):
                point_manager.add(points=x, normals=y, sampling_rate=sampling)

        metadata = {"shape": self.shape, "sampling_rate": sampling}

        point_manager.metadata = metadata.copy()
        model_manager.metadata = metadata.copy()

        self.shape = shape
        self.data.update(point_manager)
        self.models.update(model_manager)

    @_progress_decorator
    def add_fit(self, method: str, **kwargs):
        method = method.lower()
        cluster_indices = self.data._get_selected_indices()
        if method not in PARAMETRIZATION_TYPE:
            return -1

        fit_object = PARAMETRIZATION_TYPE[method]
        for index in cluster_indices:
            if not self._data._index_ok(index):
                continue

            cloud = self._data.data[index]
            if cloud._sampling_rate is None:
                cloud._sampling_rate = 10
            kwargs["voxel_size"] = np.max(cloud._sampling_rate)

            n = cloud.points.shape[0]
            if n < 50 and method != "convexhull":
                print(f"Cluster {index} contains insufficient points for fit ({n}<50).")
                continue

            try:
                fit = fit_object.fit(cloud.points, **kwargs)
                if fit is None:
                    continue

                meta = {"fit": fit, "points": cloud.points, "faces": None}
                if hasattr(fit, "mesh"):
                    meta["points"] = np.asarray(fit.mesh.vertices)
                    meta["faces"] = np.asarray(fit.mesh.triangles)
                    meta["normals"] = fit.compute_normal(meta["points"])

                new_points = fit.sample(n_samples=1000)
                self._models.add(
                    points=new_points,
                    normals=fit.compute_normal(new_points),
                    sampling_rate=cloud._sampling_rate,
                    meta=meta,
                )
            except Exception as e:
                print(e)
                continue

            self.progress.emit((index + 1) / len(cluster_indices))

    def sample_fit(self, sampling, sampling_method, normal_offset=0, **kwargs):
        fit_indices = self.models._get_selected_indices()
        for index in fit_indices:
            if not self._models._index_ok(index):
                continue

            geometry = self._models.data[index]
            fit = geometry._meta.get("fit", None)
            if fit is None:
                return None

            n_samples, kwargs = sampling, {}
            if sampling_method != "N points" and sampling_method != "Points":
                n_samples = fit.points_per_sampling(sampling)
                kwargs["mesh_init_factor"] = 5

            points = fit.sample(int(n_samples), **kwargs)
            normals = fit.compute_normal(points)
            points = np.add(points, np.multiply(normals, normal_offset))

            self._data.add(
                points=points,
                normals=normals,
                sampling_rate=geometry._sampling_rate,
            )

        self.data.data_changed.emit()
        self.data.render()

    def format_datalist(self, type="data"):
        interactor, container = self.data, self._data
        if type == "models":
            interactor, container = self.models, self._models

        ret = []
        for i in range(interactor.data_list.count()):
            list_item = interactor.data_list.item(i)
            ret.append((list_item.text(), container.data[i]))
        return ret
