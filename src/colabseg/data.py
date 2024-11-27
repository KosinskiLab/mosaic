import pickle
import numpy as np
from functools import wraps
from typing import Callable
from PyQt6.QtCore import pyqtSignal, QObject

from .utils import points_to_volume
from .container import DataContainer
from .io import DataIO, OrientationsIO, write_density
from .interactor import DataContainerInteractor
from .parametrization import PARAMETRIZATION_TYPE, TriangularMesh

AVAILABLE_PARAMETRIZATIONS = PARAMETRIZATION_TYPE
rbf = PARAMETRIZATION_TYPE.pop("rbf")
PARAMETRIZATION_TYPE["rbf [xy]"] = rbf
PARAMETRIZATION_TYPE["rbf [xz]"] = rbf
PARAMETRIZATION_TYPE["rbf [yz]"] = rbf


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
        if filename.endswith("pickle"):
            with open(filename, "rb") as ifile:
                data = pickle.load(ifile)

            shape = data["shape"]
            point_manager, model_manager = data["_data"], data["_models"]

        else:
            ret = DataIO().open_file(filename)

            if ret is None:
                return -1

            data, shape, sampling = ret
            point_manager, model_manager = DataContainer(), DataContainer()
            for x in data:
                point_manager.add(points=x.astype(np.float32), sampling_rate=sampling)

        self.shape = shape
        self.data.update(point_manager)
        self.models.update(model_manager)

    @_progress_decorator
    def add_fit(self, method: str, **kwargs):
        method = method.lower()
        cluster_indices = self.data._get_selected_indices()
        if method not in PARAMETRIZATION_TYPE:
            return -1

        if method.startswith("rbf") and len(method) == 8 and "direction" in kwargs:
            kwargs["direction"] = method[5:7]

        fit_object = PARAMETRIZATION_TYPE[method]
        for index in cluster_indices:
            if not self._data._index_ok(index):
                continue

            cloud = self._data.data[index]
            if cloud._sampling_rate is None:
                cloud._sampling_rate = 10
            kwargs["voxel_size"] = np.max(cloud._sampling_rate)

            n = cloud.points.shape[0]
            if n < 50:
                print(f"Cluster {index} contains insufficient points for fit ({n}<50).")
                continue

            try:
                fit = fit_object.fit(cloud.points, **kwargs)
                if fit is None:
                    continue

                new_points = fit.sample(n_samples=1000)
                self._models.add(
                    points=new_points,
                    # points=np.asarray(fit.mesh.vertices),
                    # faces=np.asarray(fit.mesh.triangles),
                    sampling_rate=cloud._sampling_rate,
                    meta={"fit": fit, "points": cloud.points},
                )
            except Exception as e:
                print(e)
                continue

            self.progress.emit((index + 1) / len(cluster_indices))

    def export_fit(self, file_path: str, file_format: str, **kwargs):
        if file_format in ("mrc", "xyz"):
            self._export_fit(
                indices=self.data._get_selected_indices(),
                container=self._data,
                file_path=f"{file_path}_cluster",
                file_format=file_format,
                **kwargs,
            )
        self._export_fit(
            indices=self.models._get_selected_indices(),
            container=self._models,
            file_path=f"{file_path}_fit",
            file_format=file_format,
            **kwargs,
        )

    def _export_fit(self, indices, container, file_path, file_format, **kwargs):
        if not len(indices):
            return -1

        center = False
        if file_format == "star":
            center = kwargs.get("center", False)

        sampling = 10
        export_data = {"points": [], "normals": []}
        for index in indices:
            if not container._index_ok(index):
                continue

            points = container._get_cluster_points(index)
            cloud = container.data[index]

            if file_format in ("stl", "obj"):
                fit = cloud._meta["fit"]
                if not hasattr(fit, "mesh"):
                    print(f"{index} is not a mesh. Creating a new one.")
                    fit = TriangularMesh.fit(
                        points, voxel_size=np.max(cloud._sampling_rate), repair=False
                    )

                fit.to_file(f"{file_path}_{index}.{file_format}")

            normals = None
            if "fit" in cloud._meta:
                normals = cloud._meta["fit"].compute_normal(points)

            if cloud._sampling_rate is not None:
                sampling = np.max(cloud._sampling_rate)
                points = np.divide(points, cloud._sampling_rate)

            if center and self._data.shape is not None:
                points = np.subtract(points, np.divide(self._data.shape, 2).astype(int))

            export_data["points"].append(points)
            export_data["normals"].append(normals)

        if len(export_data["points"]) == 0:
            return -1

        if file_format == "mrc":
            shape = self.shape
            if shape is None:
                temp = np.concatenate(export_data["points"])
                temp = np.rint(temp).astype(int)
                shape = temp.max(axis=0) + 1
            else:
                shape = np.rint(np.divide(shape, sampling)).astype(int)

            data = None
            for index, points in enumerate(export_data["points"]):
                data = points_to_volume(
                    points, sampling_rate=1, shape=shape, weight=index + 1, out=data
                )
            if data is None:
                return -1

            return write_density(
                data,
                filename=f"{file_path}.{file_format}",
                sampling_rate=sampling,
            )

        if file_format == "xyz":
            for index, points in enumerate(export_data["points"]):
                fname = f"{file_path}_{index}.{file_format}"
                np.savetxt(fname, points, header="x y z", comments="")

        if file_format not in ("txt", "star"):
            return -1

        print(export_data)

        orientations = OrientationsIO(**export_data)
        orientations.to_file(file_path, file_format=file_format)
