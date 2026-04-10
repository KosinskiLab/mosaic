"""
Implements MosaicData, which is responsible for tracking overall
application state and mediating interaction between segmentations
and parametrizations.

Wraps :class:`~mosaic.commands.session.Session` with Qt interactors
for GUI-driven workflows.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

__all__ = ["MosaicData"]


class MosaicData:
    """GUI application state backed by a headless :class:`Session`.

    Parameters
    ----------
    vtk_widget : VTKWidget
        VTK widget instance for 3D visualization.
    """

    def __init__(self, vtk_widget):
        super().__init__()
        from .commands.session import Session
        from .interactor import DataContainerInteractor

        self._session = Session(quiet=True)
        self.thumbnail_provider = None
        self._session_hooks = []

        self._data = self._session._data
        self._models = self._session._models

        # GUI interaction layer on top of session containers
        self.data = DataContainerInteractor(self._data, vtk_widget)
        self.models = DataContainerInteractor(self._models, vtk_widget, prefix="Fit")

        self.data.attach_area_picker()
        self.active_picker = "data"

    def open_file(
        self, filename, offset=0, scale=1, sampling_rate=1, segmentation=False
    ):
        """Open a file and register new geometries with the GUI."""
        n_data = len(self._data.data)
        n_models = len(self._models.data)

        self._session.open(
            filename,
            offset=offset,
            scale=scale,
            sampling_rate=sampling_rate,
            segmentation=segmentation,
        )

        # Assign colours and highlight color to newly added geometries
        for geom in self._data.data[n_data:]:
            geom.set_appearance(
                base_color=self.data.next_color(),
                highlight_color=self._data.highlight_color,
            )
        for geom in self._models.data[n_models:]:
            geom.set_appearance(
                base_color=self.models.next_color(),
                highlight_color=self._models.highlight_color,
            )

    @property
    def shape(self):
        return self._data.metadata.get("shape")

    @shape.setter
    def shape(self, value):
        self._data.metadata["shape"] = value

    def register_session_hook(self, collect, restore):
        """Register callbacks for session save/load.

        Parameters
        ----------
        collect : callable
            Called on save. Returns a dict of key-value pairs merged into
            the session's ``meta`` section.
        restore : callable
            Called on load with the full meta dict. Picks out relevant
            keys to restore widget state.
        """
        self._session_hooks.append((collect, restore))

    def to_file(self, filename: str, sections: dict = None):
        """Save current application state to file."""
        self._session._data_tree = self.data.data_list.to_state()
        self._session._models_tree = self.models.data_list.to_state()

        if not filename.endswith(".pickle"):
            if sections is None:
                sections = {}

            if self.thumbnail_provider is not None:
                try:
                    thumb = self.thumbnail_provider()
                    if thumb is not None:
                        sections["thumbnail"] = ("png", thumb)
                except Exception:
                    pass

            meta = {}
            for collect, _ in self._session_hooks:
                try:
                    result = collect()
                    if result:
                        meta.update(result)
                except Exception:
                    pass
            if meta:
                import json

                sections["meta"] = (
                    "json",
                    json.dumps(meta, separators=(",", ":")).encode("utf-8"),
                )

        self._session.save_session(filename, sections=sections)

    def load_session(self, filename: str):
        """Load application state from file."""
        self._session.load_session(filename)

        self._data = self._session._data
        self._models = self._session._models

        self.data.update(self._data, tree_state=self._session._data_tree)
        self.models.update(self._models, tree_state=self._session._models_tree)

        meta_entry = self._session._metadata.get("meta")
        meta = {}
        if meta_entry is not None:
            import json

            meta = json.loads(meta_entry[1])

        for _, restore in self._session_hooks:
            try:
                restore(meta)
            except Exception:
                pass

    def reset(self):
        """Reset the state of the class instance."""
        from .container import DataContainer

        self.shape = None
        self.data.update(DataContainer())
        self.models.update(DataContainer(highlight_color=(0.2, 0.4, 0.8)))

        self._session._data = self._data = self.data.container
        self._session._models = self._models = self.models.container

    def refresh_actors(self):
        """Reinitialize all VTK actors to accommodate render setting changes."""
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
        """Activate viewing mode for all containers."""
        self.data.activate_viewing_mode()
        self.models.activate_viewing_mode()

    def highlight_clusters_from_selected_points(self):
        obj = self._get_active_container()
        return obj.highlight_clusters_from_selected_points()

    def visibility_unselected(self, visible: bool = True):
        """Hide clusters and models that are not selected."""
        cluster = list(self.data.point_selection.keys())
        cluster.extend(self.data._get_selected_uuids())
        cluster = set(cluster)

        unselected = self.data.data_list.to_state().get_all_uuids() - cluster
        self.data.visibility(
            geometries=[self._data.get(x) for x in unselected], visible=visible
        )

        models = set(self.models._get_selected_uuids())
        unselected = self.models.data_list.to_state().get_all_uuids() - models
        self.models.visibility(
            geometries=[self._models.get(x) for x in unselected], visible=visible
        )

    def activate_picking_mode(self):
        obj = self._get_active_container()
        return obj.activate_picking_mode()

    def format_datalist(
        self, type="data", mesh_only: bool = False, selected: bool = False
    ):
        """Format data list for dialog display."""
        if mesh_only and type != "models":
            mesh_only = False

        interactor, container = self.data, self._data
        if type == "models":
            interactor, container = self.models, self._models

        selection = [x.uuid for x in container.data]
        if selected:
            selection = interactor._get_selected_uuids()

        ret = []
        for i in selection:
            if (geometry := container.get(i)) is None:
                continue

            if mesh_only:
                from .parametrization import TriangularMesh

                if not isinstance(geometry.model, TriangularMesh):
                    continue

            ret.append((geometry._meta.get("name", ""), geometry))
        return ret

    def get_tree_state(self, type="data"):
        """Get the tree state (group structure) for a container."""
        if type == "models":
            return self.models.data_list.to_state()
        return self.data.data_list.to_state()
