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
        from .viewport import ViewportInteractor

        self._session = Session(quiet=True)
        self.thumbnail_provider = None
        self._session_hooks = []

        # GUI interaction layer on top of session containers
        self.data = DataContainerInteractor(self._session, "data")
        self.models = DataContainerInteractor(self._session, "models", prefix="Fit")

        self.viewport = ViewportInteractor(vtk_widget, [self.data, self.models])

        self._last_lod_budget = None
        self._setup_interaction_lod(vtk_widget)

    @property
    def _data(self):
        return self._session._data

    @property
    def _models(self):
        return self._session._models

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
        return self._session.metadata.get("shape")

    @shape.setter
    def shape(self, value):
        if value is None:
            self._session.metadata.pop("shape", None)
        else:
            self._session.metadata["shape"] = value

    @property
    def physical_shape(self):
        return self._session.metadata.get("physical_shape")

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

        # Containers are now resolved live from the session via property,
        # so we only refresh the trees from the restored state.
        self.data.update(tree_state=self._session._data_tree)
        self.models.update(tree_state=self._session._models_tree)

        meta_entry = self._session._file_sections.get("meta")
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
        self._lod_restore_timer.stop()
        self.shape = None

        self.data.clear()
        self.models.clear()

    def _setup_interaction_lod(self, vtk_widget):
        """Register VTK interaction observers for point-budget LOD."""
        from qtpy.QtCore import QTimer

        self._vtk_widget = vtk_widget
        self._lod_restore_timer = QTimer(vtk_widget)
        self._lod_restore_timer.setSingleShot(True)
        self._lod_restore_timer.setInterval(200)
        self._lod_restore_timer.timeout.connect(self._restore_full_data)

        if (interactor := vtk_widget.GetRenderWindow().GetInteractor()) is None:
            return None

        interactor.AddObserver("StartInteractionEvent", self._on_interaction_start)
        interactor.AddObserver("EndInteractionEvent", self._on_interaction_end)

    def _on_interaction_start(self, obj, event):
        self._lod_restore_timer.stop()
        for geom in self._data.data:
            geom.begin_interaction()
        for geom in self._models.data:
            geom.begin_interaction()

    def _on_interaction_end(self, obj, event):
        self._lod_restore_timer.start()

    def _restore_full_data(self):
        for geom in self._data.data:
            geom.end_interaction()
        for geom in self._models.data:
            geom.end_interaction()
        self._vtk_widget.GetRenderWindow().Render()

    def refresh_lod(self):
        """Recompute interaction-LOD budgets from current settings.

        Returns
        -------
        bool
            True when any LOD actors changed (renderer sync needed).
        """
        from . import lod

        budget = lod.get_point_budget()
        force = budget != self._last_lod_budget
        self._last_lod_budget = budget

        changed = self._data.refresh_lod(budget=budget, force=force)
        changed |= self._models.refresh_lod(budget=budget, force=force)
        if changed:
            self.viewport.render()
        return changed

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
