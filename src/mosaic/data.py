"""
Implements ColabsegData, which is reponsible for tracking overall
application state and mediating interaction between segmentations
and parametrizations.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import pickle

import numpy as np
import multiprocessing as mp

from qtpy.QtCore import QObject

__all__ = ["MosaicData"]


class MosaicData(QObject):

    def __init__(self, vtk_widget):
        """Initialize MosaicData instance for managing application state.

        Parameters
        ----------
        vtk_widget : VTKWidget
            VTK widget instance for 3D visualization
        """
        super().__init__()
        from .container import DataContainer
        from .interactor import DataContainerInteractor

        # Data containers and GUI interaction elements
        self.shape = None
        self._data = DataContainer()
        self._models = DataContainer(highlight_color=(0.2, 0.4, 0.8))

        self.data = DataContainerInteractor(self._data, vtk_widget)
        self.models = DataContainerInteractor(self._models, vtk_widget, prefix="Fit")

        self.data.attach_area_picker()
        self.active_picker = "data"

    def to_file(self, filename: str):
        """Save current application state to file.

        Parameters
        ----------
        filename : str
            Path to save the application state.
        """
        state = {"shape": self.shape, "_data": self._data, "_models": self._models}
        with open(filename, "wb") as ofile:
            pickle.dump(state, ofile)

    def load_session(self, filename: str):
        """
        Load application state from file.

        Parameters
        ----------
        filename : str
            Path to the saved session file (.pickle).
        """
        from .container import DataContainer
        from .formats import open_file, open_session

        sampling = 1
        if filename.endswith("pickle"):
            data = open_session(filename)
            shape = data["shape"]
            point_manager, model_manager = data["_data"], data["_models"]

        else:
            container = open_file(filename)

            shape = container.shape
            sampling = container.sampling
            point_manager, model_manager = DataContainer(), DataContainer()
            for data in container:
                point_manager.add(
                    points=data.vertices, normals=data.normals, sampling_rate=sampling
                )

        metadata = {"shape": self.shape, "sampling_rate": sampling}

        point_manager.metadata = metadata.copy()
        model_manager.metadata = metadata.copy()

        self.shape = shape
        self.data.update(point_manager)
        self.models.update(model_manager)

    def reset(self):
        """
        Reset the state of the class instance.
        """
        from .container import DataContainer

        self.shape = None
        self.data.update(DataContainer())
        self.models.update(DataContainer())

    def refresh_actors(self):
        """
        Reinitialize all vtk actors to accomodate render setting changes.
        """
        self.data.refresh_actors()
        self.models.refresh_actors()

    def set_coloring_mode(self, mode: str):
        self.data.set_coloring_mode(mode)
        self.models.set_coloring_mode(mode)

    def _get_active_container(self):
        if self.active_picker == "data":
            return self.data
        return self.models

    def swap_area_picker(self):
        """Toggle area picker between data and models containers."""
        self.active_picker = "data" if self.active_picker != "data" else "models"
        self.data.activate_viewing_mode()
        self.models.activate_viewing_mode()
        container = self._get_active_container()
        return container.attach_area_picker()

    def activate_viewing_mode(self):
        """Activate viewing mode for all contaienrs."""
        self.data.activate_viewing_mode()
        self.models.activate_viewing_mode()

    def highlight_clusters_from_selected_points(self):
        """Highlight clusters containing currently selected points.

        Returns
        -------
        bool
            Success status of highlighting operation
        """
        obj = self._get_active_container()
        return obj.highlight_clusters_from_selected_points()

    def activate_picking_mode(self):
        obj = self._get_active_container()
        return obj.activate_picking_mode()

    def _add_fit(self, fit, sampling_rate=None, **kwargs):
        if hasattr(fit, "mesh"):
            new_points = fit.vertices
            normals = fit.compute_vertex_normals()
        else:
            new_points = fit.sample(n_samples=1000)
            normals = fit.compute_normal(new_points)

        index = self.models.add(
            points=new_points,
            normals=normals,
            sampling_rate=sampling_rate,
            meta={"fit": fit, "fit_kwargs": kwargs},
        )
        if hasattr(fit, "mesh"):
            self._models.data[index].change_representation("surface")
        self.models.data_changed.emit()

        return index

    def add_fit(self, method: str, **kwargs):
        """Add parametric fit to selected data points.

        Parameters
        ----------
        method : str
            Name of the fitting method to use
        **kwargs
            Additional parameters for the fitting method
        """
        from .parametrization import PARAMETRIZATION_TYPE

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
            kwargs["voxel_size"] = np.max(cloud.sampling_rate)

            n = cloud.points.shape[0]
            if n < 50 and method not in ["convexhull", "spline"]:
                raise ValueError(
                    f"Cluster {index} contains insufficient points for fit ({n}<50)."
                )

            try:
                fit = fit_object.fit(cloud.points, **kwargs)
                if fit is None:
                    continue

                self._add_fit(fit=fit, sampling_rate=cloud._sampling_rate)

            except Exception as e:
                raise type(e)(f"Object {index}: {str(e)}") from e

    def format_datalist(self, type="data", mesh_only: bool = False):
        """Format data list for dialog display.

        Parameters
        ----------
        type : str, optional
            Type of data to format ('data' or 'models'), by default 'data'
        mesh_only : bool, optional
            Whether to return only TriangularMesh instances for type 'models'.

        Returns
        -------
        list
            List of tuples containing (item_text, data_object) pairs
        """
        from .parametrization import TriangularMesh

        if mesh_only and type != "models":
            mesh_only = False

        interactor, container = self.data, self._data
        if type == "models":
            interactor, container = self.models, self._models

        ret = []
        for i in range(interactor.data_list.count()):
            list_item = interactor.data_list.item(i)

            geometry = container.get(i)
            if geometry is None:
                continue

            if mesh_only:
                is_mesh = isinstance(geometry._meta.get("fit"), TriangularMesh)
                if not is_mesh:
                    continue

            ret.append((list_item.text(), geometry))
        return ret

    def sample_fit(self, sampling, sampling_method, normal_offset=0.0, **kwargs):
        from .operations import GeometryOperations

        tasks = []
        fit_indices = self.models._get_selected_indices()
        for index in fit_indices:
            geometry = self._models.get(index)
            if geometry is None:
                continue
            tasks.append((geometry, sampling, sampling_method, normal_offset))

        # TODO: Handle processes in the Qt backend to avoid initialization overhead
        with mp.Pool(1) as pool:
            results = pool.starmap(GeometryOperations.sample, tasks)

        for geometry in results:
            if geometry is None:
                continue
            self.data.add(geometry)

        return self.data.data_changed.emit()
