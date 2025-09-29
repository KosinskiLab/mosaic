"""
Implements ColabsegData, which is reponsible for tracking overall
application state and mediating interaction between segmentations
and parametrizations.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import pickle

import multiprocessing as mp

from qtpy.QtCore import QObject

__all__ = ["MosaicData"]


class MosaicData(QObject):
    """
    Initialize MosaicData instance for managing application state.

    Parameters
    ----------
    vtk_widget : VTKWidget
        VTK widget instance for 3D visualization
    """

    def __init__(self, vtk_widget):
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

    def visibility_unselected(self, visible: bool = True):
        """Hide clusters and models that are not selected."""
        cluster = list(self.data.point_selection.keys())
        cluster.extend(self.data._get_selected_indices())
        cluster = set(cluster)

        unselected = set(range(self.data.data_list.count())) - cluster
        self.data.visibility(geometry_indices=list(unselected), visible=visible)

        models = set(self.models._get_selected_indices())
        unselected = set(range(self.models.data_list.count())) - models
        self.models.visibility(geometry_indices=list(unselected), visible=visible)

    def activate_picking_mode(self):
        obj = self._get_active_container()
        return obj.activate_picking_mode()

    def _add_fit(self, fit, sampling_rate=None, vertex_properties=None, **kwargs):
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
            vertex_properties=vertex_properties,
            meta={"fit": fit, "fit_kwargs": kwargs},
        )
        if hasattr(fit, "mesh"):
            self._models.data[index].change_representation("surface")
        self.models.data_changed.emit()

        return index

    def format_datalist(
        self, type="data", mesh_only: bool = False, selected: bool = False
    ):
        """Format data list for dialog display.

        Parameters
        ----------
        type : str, optional
            Type of data to format ('data' or 'models'), by default 'data'
        mesh_only : bool, optional
            Whether to return only TriangularMesh instances for type 'models'.
        selected : bool, optional
            Whether to return only selected objects

        Returns
        -------
        list
            List of tuples containing (item_text, data_object) pairs
        """
        if mesh_only and type != "models":
            mesh_only = False

        interactor, container = self.data, self._data
        if type == "models":
            interactor, container = self.models, self._models

        selection = range(interactor.data_list.count())
        if selected:
            selection = interactor._get_selected_indices()

        ret = []
        for i in selection:
            list_item = interactor.data_list.item(i)

            geometry = container.get(i)
            if geometry is None:
                continue

            if mesh_only:
                from .parametrization import TriangularMesh

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
