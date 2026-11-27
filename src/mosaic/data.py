"""
Implements MosaicData, which is responsible for tracking overall
application state and mediating interaction between segmentations
and parametrizations.

Wraps :class:`~mosaic.commands.session.Session` with Qt interactors
for GUI-driven workflows.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import json
from collections.abc import Callable
from typing import TYPE_CHECKING

from .undo import STACK

if TYPE_CHECKING:
    from numpy.typing import ArrayLike
    from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

__all__ = ["MosaicData"]


class MosaicData:
    """GUI application state backed by a headless :class:`Session`.

    Parameters
    ----------
    vtk_widget : VTKWidget
        VTK widget instance for 3D visualization.
    """

    def __init__(self, vtk_widget: "QVTKRenderWindowInteractor"):
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

    def open_file(
        self,
        filename: str,
        offset: "ArrayLike" = 0,
        scale: "ArrayLike" = 1,
        sampling_rate: "ArrayLike" = 1,
        segmentation: bool = False,
    ):
        """Open a file and register new geometries with the GUI."""
        data_container = self.data.container
        models_container = self.models.container
        n_data = len(data_container.data)
        n_models = len(models_container.data)

        self._session.open(
            filename,
            offset=offset,
            scale=scale,
            sampling_rate=sampling_rate,
            segmentation=segmentation,
        )

        for geom in data_container.data[n_data:]:
            geom.set_appearance(
                base_color=self.data.next_color(),
                highlight_color=data_container.highlight_color,
            )
        for geom in models_container.data[n_models:]:
            geom.set_appearance(
                base_color=self.models.next_color(),
                highlight_color=models_container.highlight_color,
            )

    @property
    def shape(self):
        return self._session.metadata.get("shape")

    @shape.setter
    def shape(self, value: "ArrayLike | None"):
        if value is None:
            self._session.metadata.pop("shape", None)
        else:
            self._session.metadata["shape"] = value

    @property
    def physical_shape(self):
        return self._session.metadata.get("physical_shape")

    def register_session_hook(
        self, collect: Callable[[], dict], restore: Callable[[dict], object]
    ):
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

    def to_file(self, filename: str, sections: dict | None = None) -> str:
        """Save current application state to file and return the path written."""
        self._session._data_tree = self.data.data_list.to_state()
        self._session._models_tree = self.models.data_list.to_state()

        if sections is None:
            sections = {}

        if self.thumbnail_provider is not None:
            try:
                thumb = self.thumbnail_provider()
                if thumb is not None:
                    sections["thumbnail"] = ("png", thumb)
            except Exception:
                pass

        file_sections = self._session._file_sections
        base = file_sections.get("meta")
        meta = json.loads(base[1]) if base is not None else {}
        for collect, _ in self._session_hooks:
            try:
                meta.update(collect() or {})
            except Exception:
                pass

        meta = {k: v for k, v in meta.items() if v is not None}
        if meta:
            sections["meta"] = (
                "json",
                json.dumps(meta, separators=(",", ":")).encode("utf-8"),
            )
        else:
            file_sections.pop("meta", None)

        return self._session.save_session(filename, sections=sections)

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
            meta = json.loads(meta_entry[1])

        for _, restore in self._session_hooks:
            try:
                restore(meta)
            except Exception:
                pass

        self.refresh_lod()

    def reset(self):
        """Reset the state of the class instance."""
        self.viewport._lod_restore_timer.stop()
        self.shape = None

        self.data.clear()
        self.models.clear()
        STACK.clear()
        self._session._file_sections = {}

    def refresh_lod(self):
        """Shortcut for :meth:`ViewportInteractor.refresh_lod`."""
        return self.viewport.refresh_lod()

    def format_datalist(
        self, type: str = "data", mesh_only: bool = False, selected: bool = False
    ):
        """Format data list for dialog display."""
        if mesh_only and type != "models":
            mesh_only = False

        interactor = self.data
        if type == "models":
            interactor = self.models
        container = interactor.container

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

    def get_tree_state(self, type: str = "data"):
        """Get the tree state (group structure) for a container."""
        if type == "models":
            return self.models.data_list.to_state()
        return self.data.data_list.to_state()
