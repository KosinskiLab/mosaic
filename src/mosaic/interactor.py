"""
Implemenents DataContainerInteractor to mediate interaction between
the viewport/GUI and DataContainers.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np
from dataclasses import dataclass
from typing import Dict, Optional

from qtpy.QtGui import QAction
from qtpy.QtWidgets import QListWidget, QMenu, QDialog
from qtpy.QtCore import Qt, QObject, Signal

from .widgets import MosaicMessageBox
from .formats.writer import write_geometries
from .widgets.container_list import StyledTreeWidgetItem

__all__ = ["DataContainerInteractor"]


_VOLUME_GEOMETRY_KEYS = (
    "volume",
    "volume_sampling_rate",
    "lower_quantile",
    "upper_quantile",
    "target_resolution",
)


@dataclass
class _GeometrySwap:
    """Restore a uuid to an exact geometry (or absence) in either direction."""

    uuid: str
    before: Optional["Geometry"]
    after: Optional["Geometry"]


@dataclass
class _GeometrySubset:
    """Point subset removed from a surviving geometry; undo re-appends the slice."""

    uuid: str
    removed: "Geometry"
    n_kept: int


def _has_mesh_model(geometry) -> bool:
    """Whether ``geometry`` carries triangular-mesh connectivity in its model."""
    return geometry is not None and hasattr(getattr(geometry, "model", None), "mesh")


def _convert_geometry(geometry, target_cls):
    """Rebuild *geometry* as an instance of *target_cls* preserving shared state.

    Why: VTK subclasses (Volume/Segmentation) own type-specific attributes that
    do not survive a hand-rolled field copy. Round-tripping through __getstate__
    keeps vertex_properties, model, and meta intact across representation swaps.
    """
    from .geometry import VolumeGeometry

    state = geometry.__getstate__()
    appearance = state.pop("appearance", {})
    for key in ("visible", "representation", "uuid"):
        state.pop(key, None)
    if target_cls is not VolumeGeometry:
        for key in _VOLUME_GEOMETRY_KEYS:
            state.pop(key, None)
    state["color"] = appearance.get("base_color", (0.7, 0.7, 0.7))

    new_geom = target_cls(**state)
    new_geom._appearance.update(appearance)
    return new_geom


class DataContainerInteractor(QObject):
    """Handle interaction between GUI and DataContainer"""

    data_changed = Signal()

    def __init__(self, session, role, prefix="Cluster"):
        from .widgets import ContainerListWidget

        super().__init__()
        self.prefix = prefix
        self.point_selection = {}
        self.session = session

        # "data" or "models", names the container on session
        self.role = role

        # Wired in via attach_viewport once the ViewportInteractor exists.
        self.viewport = None

        # Interaction element for the GUI
        self.data_list = ContainerListWidget()
        self.data_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.data_list.itemChanged.connect(self._on_item_renamed)
        self.data_list.itemSelectionChanged.connect(self._on_cluster_selection_changed)

        self.data_list.tree_widget.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.data_list.tree_widget.customContextMenuRequested.connect(
            self._show_context_menu
        )

        self._active_cluster = None
        self.set_coloring_mode("default")

    def attach_viewport(self, viewport):
        """Wire this pane to its ViewportInteractor."""
        self.viewport = viewport

    def set_active_cluster(self, uuid):
        """Set the UUID of the cluster receiving drawn points (``None`` to clear)."""
        self._active_cluster = uuid

    @property
    def container(self):
        """The DataContainer this pane operates on."""
        return getattr(self.session, f"_{self.role}")

    def _get_selected_uuids(self):
        """Get UUIDs of selected items."""
        uuids = []
        for item in self.data_list.selected_items():
            if uuid := item.metadata.get("uuid"):
                uuids.append(uuid)
        return uuids

    def clear(self):
        self.point_selection.clear()
        self.container.clear()
        self.render(defer_render=True)

    def get_selected_geometries(self):
        ret = [self.container.get(uuid) for uuid in self._get_selected_uuids()]
        return [x for x in ret if x is not None]

    def _on_item_renamed(self, item):
        if item.metadata.get("uuid") is None:
            return None

        # setData already wrote the new name to geometry._meta;
        # detect whether the stored metadata name diverged (i.e. a rename)
        current_name = item.text(0)
        if current_name != item.metadata.get("name"):
            item.metadata["name"] = current_name
            self.data_changed.emit()
            self.render()

    def next_color(self):
        if not hasattr(self, "colors"):
            return self.container.base_color

        color = self.colors.pop(0)
        self.colors.append(color)
        return color

    def set_coloring_mode(self, mode: str):
        from .stylesheets import Colors

        if mode not in ("default", "entity"):
            raise ValueError("Only mode 'default' and 'entity' are supported.")

        self.colors = [self.container.base_color]
        if mode == "entity":
            self.colors = list(Colors.ENTITY)

        for i in range(len(self.container)):
            if (geometry := self.container.get(i)) is None:
                continue
            self.container.update_appearance(
                [i], geometry._appearance | {"base_color": self.next_color()}
            )
        self.container.highlight([])

    def add(self, *args, **kwargs):
        if kwargs.get("color", None) is None:
            if hasattr(self, "colors") and len(self.colors) > 1:
                kwargs["color"] = self.next_color()
        ret = self.container.add(*args, **kwargs)
        self.data_changed.emit()
        return ret

    def add_selection(
        self, selected_point_ids: Dict[str, np.ndarray], add: bool = True
    ) -> int:
        """Add new cloud from selected points.

        Parameters
        ----------
        selected_point_ids : dict
            Mapping of geometry UUID to selected point IDs.
        add : bool
            Whether to add the Geometry defined by selected points.

        Returns
        -------
        int
            Index of new cloud, -1 if creation failed.
        """
        from .geometry import Geometry

        new_cluster, remove_cluster = [], []
        for uuid, point_ids in selected_point_ids.items():
            if (geometry := self.container.get(uuid)) is None:
                continue

            n_points = geometry.get_number_of_points()
            if not geometry.visible or n_points == 0 or point_ids.size == 0:
                continue

            inverse = np.ones(n_points, dtype=bool)
            inverse[point_ids] = False

            if add:
                new_cluster.append(geometry[point_ids])

            if inverse.sum() != 0:
                self.container.update(uuid, geometry.subset(inverse))
            else:
                # All points were selected, mark for removal
                remove_cluster.append(geometry)

        self.remove(remove_cluster)
        if len(new_cluster) and add:
            return self.add(Geometry.merge(new_cluster))
        return -1

    def add_point(self, point):
        """Append a point to the active drawing cluster."""
        if (geometry := self.container.get(self._active_cluster)) is None:
            return -1

        # We call swap data to automatically handle other Geometry attributes
        geometry.swap_data(np.concatenate((geometry.points, np.asarray(point)[None])))
        self.data_changed.emit()
        return self.render()

    def set_selection_by_uuid(self, uuids):
        """
        Set selection by UUIDs.

        Parameters
        ----------
        uuids : list of str
            UUIDs to select
        """
        self.data_list.set_selection(uuids)
        self._highlight_selection()

    def _on_cluster_selection_changed(self):
        # This is of course not ideal but prevents unhighlight/highlight
        # when clicking on groups due to itemClicked behaviour. So we
        # handle actual deselect all using _highlight_selection
        if not len(self._get_selected_uuids()):
            return None

        self._highlight_selection()

    def deselect(self):
        """Deselect on right-click"""
        self.data_list.clearSelection()
        self._highlight_selection()
        self.deselect_points()

    def _highlight_selection(self):
        self.container.highlight(self._get_selected_uuids())
        self.render_vtk()

    def pick_prop(self, picked_prop):
        """Select the geometry whose actor was picked by the viewport, if any."""
        actors = self.container.get_actors()
        if picked_prop in actors:
            index = actors.index(picked_prop)
            uuid = self.container.get(index).uuid
            self.set_selection_by_uuid([uuid, *self._get_selected_uuids()])
        return None

    def _show_context_menu(self, position):
        item = self.data_list.itemAt(position)
        if not item:
            return -1

        # Make sure right click also selects group members
        self.data_list._select_group_children(item)
        context_menu = QMenu(self.data_list.window())
        context_menu.setWindowFlags(
            context_menu.windowFlags()
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        context_menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        show_action = QAction("Show", self.data_list)
        show_action.triggered.connect(
            lambda: self.visibility(self.get_selected_geometries(), visible=True)
        )
        context_menu.addAction(show_action)

        hide_action = QAction("Hide", self.data_list)
        hide_action.triggered.connect(
            lambda: self.visibility(self.get_selected_geometries(), visible=False)
        )
        context_menu.addAction(hide_action)

        duplicate_action = QAction("Duplicate", self.data_list)
        duplicate_action.triggered.connect(
            lambda: self.duplicate(self.get_selected_geometries())
        )
        context_menu.addAction(duplicate_action)
        remove_action = QAction("Remove", self.data_list)
        remove_action.triggered.connect(self.remove_selection)
        context_menu.addAction(remove_action)

        selected_items = self.data_list.selected_items()
        rename_action = QAction("Rename", self.data_list)
        rename_action.triggered.connect(self._show_batch_rename_dialog)
        rename_action.setEnabled(len(selected_items) >= 1)
        context_menu.addAction(rename_action)

        formats = [
            "Points",
            "Gaussian Density",
            "Normals",
            "Basis",
        ]
        mesh_formats = [
            None,
            "Surface",
            "Mesh",
            "Wireframe",
        ]

        selected = self.get_selected_geometries()
        if any(_has_mesh_model(x) for x in selected):
            formats.extend(mesh_formats)

        # We might need a more reliable check for assessing whether
        # this is the Cluster interactor. This safeguard prevents converting
        # meshes to Segmentation volumes, which will cause out of memory
        # issues on the majority of systems
        if all(x.model is None for x in selected):
            formats.extend([None, "Segmentation"])

        _formap_map = {k: k.lower().replace(" ", "_") for k in formats if k is not None}
        _formap_map["Points"] = "pointcloud"

        # Only show checkbox if there is a majority representation
        _representation = {x._representation for x in selected}
        if len(_representation) == 1:
            _inverse_map = {v: k for k, v in _formap_map.items()}
            _representation = _inverse_map.get(_representation.pop())
            if _representation is not None:
                _representation = _representation.title()
        else:
            _representation = None

        representation_menu = QMenu("Representation", context_menu)
        representation_menu.setWindowFlags(
            representation_menu.windowFlags()
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        representation_menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        for format_name in formats:
            if format_name is None:
                representation_menu.addSeparator()
                continue
            action = QAction(format_name, representation_menu)
            action.setCheckable(True)
            if format_name == _representation:
                action.setChecked(True)

            action.triggered.connect(
                lambda checked, f=format_name: self.change_representation(
                    _formap_map[f]
                )
            )
            representation_menu.addAction(action)

        context_menu.addSeparator()

        group_action = QAction("Group", self.data_list)
        group_action.triggered.connect(
            lambda: self.data_list.group_selected("New Group")
        )
        context_menu.addAction(group_action)

        ungroup_action = QAction("Ungroup", self.data_list)
        ungroup_action.triggered.connect(
            lambda: (self.data_list.ungroup_selected(), self.render())
        )
        context_menu.addAction(ungroup_action)
        context_menu.addMenu(representation_menu)

        context_menu.addSeparator()

        from .geometry import GeometryTrajectory

        trajectories = [g for g in selected if isinstance(g, GeometryTrajectory)]
        if len(trajectories) == 1:
            extract_action = QAction("Extract Frame", self.data_list)
            extract_action.triggered.connect(
                lambda: self._extract_trajectory_frame(trajectories[0])
            )
            context_menu.addAction(extract_action)

        export_menu = QAction("Export As", self.data_list)
        export_menu.triggered.connect(lambda: self._handle_export())
        context_menu.addAction(export_menu)

        properties_action = QAction("Properties", self.data_list)
        properties_action.triggered.connect(self._show_properties_dialog)
        context_menu.addAction(properties_action)

        context_menu.exec(self.data_list.mapToGlobal(position))

    def _extract_trajectory_frame(self, trajectory):
        from .geometry import Geometry

        model = trajectory.model
        geometry = Geometry(model=model, sampling_rate=trajectory.sampling_rate)
        geometry.change_representation("mesh")
        self.add(geometry)
        self.render()

    def _handle_export(self, *args, **kwargs):
        from .dialogs import ExportDialog
        from qtpy.QtWidgets import QApplication

        geometries = self.get_selected_geometries()

        enabled_categories = ["pointcloud", "volume"]
        if any(_has_mesh_model(g) for g in geometries):
            enabled_categories.append("mesh")

        names = [g._meta.get("name", f"Geometry {i}") for i, g in enumerate(geometries)]
        dialog = ExportDialog(
            parent=QApplication.activeWindow(),
            enabled_categories=enabled_categories,
            parameters={"shape": self.session.metadata.get("shape", None)},
            names=names,
        )

        dialog.export_requested.connect(self._wrap_export)
        return dialog.exec()

    def _wrap_export(self, export_data):
        from os.path import splitext
        from .geometry import Geometry, GeometryTrajectory

        file_path = export_data.pop("file_path", None)
        if not file_path:
            return -1

        export_data.pop("category", None)
        export_data.pop("tsi_format", None)

        geometries = self.get_selected_geometries()
        has_trajectory = any(isinstance(g, GeometryTrajectory) for g in geometries)

        if has_trajectory:
            ref = file_path if isinstance(file_path, str) else file_path[0]
            base, ext = splitext(ref)
            expanded = []
            for geom in geometries:
                if not isinstance(geom, GeometryTrajectory):
                    expanded.append(geom)
                    continue

                for frame in geom._trajectory:
                    if (model := frame.get("fit")) is None:
                        continue
                    g = Geometry(
                        points=model.vertices,
                        normals=model.compute_vertex_normals(),
                        model=model,
                        sampling_rate=geom.sampling_rate,
                    )
                    expanded.append(g)
            file_path = [f"{base}_{i:d}{ext}" for i in range(len(expanded))]
            geometries = expanded

        try:
            write_geometries(geometries, file_path, **export_data)
        except Exception as e:
            MosaicMessageBox.warning(None, "Error during writing geometries", str(e))
        return None

    def _show_properties_dialog(self) -> int:
        from .dialogs import GeometryPropertiesDialog

        uuids = self._get_selected_uuids()
        if not len(uuids):
            return -1

        snapshots, property_list = {}, []
        for uuid in uuids:
            geometry = self.container.get(uuid)
            if geometry is None:
                continue

            appearance = geometry._appearance.copy()
            appearance["sampling_rate"] = geometry.sampling_rate
            appearance.setdefault("highlight_color", self.container.highlight_color)

            # volume_scale and volume_path live on geometry._meta, not _appearance;
            # surface them so the dialog can detect Native/Invert mixing.
            if "volume_scale" in geometry._meta:
                appearance["volume_scale"] = geometry._meta["volume_scale"]
            if "volume_path" in geometry._meta:
                appearance["volume_path"] = geometry._meta["volume_path"]

            snapshots[uuid] = appearance
            property_list.append(appearance)

        if not snapshots:
            return -1

        dialog = GeometryPropertiesDialog(property_list, anchor=self.data_list)

        def on_parameters_changed(parameters):
            sampling_rate = parameters.pop("sampling_rate", None)
            full_render = False
            if parameters:
                full_render = self.container.update_appearance(uuids, parameters)
            if sampling_rate is not None:
                for uuid in uuids:
                    if (geometry := self.container.get(uuid)) is None:
                        continue
                    geometry.sampling_rate = sampling_rate

            if full_render:
                self.render()

            self.set_selection_by_uuid(uuids)

        dialog.parametersChanged.connect(on_parameters_changed)

        result = dialog.exec()
        if result == QDialog.DialogCode.Rejected:
            full_render = False
            for uuid, snap in snapshots.items():
                snap = snap.copy()
                sampling_rate = snap.pop("sampling_rate", None)

                # volume_path / volume_scale belong to _meta; strip them so the
                # cancel-restore doesn't trigger a spurious volume reload.
                snap.pop("volume_path", None)
                snap.pop("volume_scale", None)
                if self.container.update_appearance([uuid], snap):
                    full_render = True
                if (
                    sampling_rate is not None
                    and (geom := self.container.get(uuid)) is not None
                ):
                    geom.sampling_rate = sampling_rate
            if full_render:
                self.render()
            self.set_selection_by_uuid(uuids)
        return 1

    def _show_batch_rename_dialog(self) -> int:
        from qtpy.QtWidgets import QApplication
        from .dialogs import BatchRenameDialog

        items = self.data_list.selected_items()
        if len(items) < 1:
            return -1

        uuids = [item.metadata.get("uuid") for item in items]
        current_names = [item.text() for item in items]

        dialog = BatchRenameDialog(
            names=current_names, parent=QApplication.activeWindow()
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return -1

        self.data_list.tree_widget.blockSignals(True)
        for item, uuid, new_name in zip(items, uuids, dialog.result_names):
            if (geometry := self.container.get(uuid)) is not None:
                geometry._meta["name"] = new_name
            item.setText(0, new_name)
        self.data_list.tree_widget.blockSignals(False)

        self.data_changed.emit()
        self.render()
        return 1

    def _uuid_to_items(self):
        uuid_to_items = {}
        for i in range(len(self.container)):
            if (geometry := self.container.get(i)) is None:
                continue

            name = geometry._meta.get("name", None)
            if name is None:
                name = f"{self.prefix} {i}"

            geometry._meta["name"] = name

            item = StyledTreeWidgetItem(
                geometry=geometry, visible=geometry.visible, editable=True
            )
            uuid_to_items[geometry.uuid] = item
        return uuid_to_items

    def render(self, defer_render: bool = False):
        return self.viewport.render(defer_render=defer_render)

    def render_vtk(self):
        return self.viewport.render_vtk()

    def deselect_points(self):
        if len(self.point_selection) == 0:
            return None

        for uuid, point_ids in self.point_selection.items():
            if (geometry := self.container.get(uuid)) is None:
                continue

            color = geometry._appearance.get("base_color", (0.7, 0.7, 0.7))
            self.container.highlight_points(uuid, point_ids, color)

        self.point_selection.clear()

    def highlight_selected_points(self, color):
        for uuid, point_ids in self.point_selection.items():
            self.container.highlight_points(uuid, point_ids, color)

    def highlight_clusters_from_selected_points(self):
        return self.set_selection_by_uuid(list(self.point_selection.keys()))

    def change_representation(self, representation: str):
        from .geometry import Geometry, VolumeGeometry, SegmentationGeometry

        if not len(geometries := self.get_selected_geometries()):
            return -1

        for geometry in geometries:

            if representation == "segmentation":
                if isinstance(geometry, SegmentationGeometry):
                    continue

                seg = _convert_geometry(geometry, SegmentationGeometry)
                self.container.update(geometry.uuid, seg)
                continue

            if isinstance(geometry, SegmentationGeometry):
                new_geom = _convert_geometry(geometry, Geometry)
                self.container.update(geometry.uuid, new_geom)
                geometry = self.container.get(geometry.uuid)

            # Its less of a headache to handle this here, because normals and basis
            # representation rely on similar glyph rendering mechanisms as the volume
            elif isinstance(geometry, VolumeGeometry) and representation != "volume":
                new_geom = _convert_geometry(geometry, Geometry)
                self.container.update(geometry.uuid, new_geom)
                geometry = self.container.get(geometry.uuid)

            # BUG: Moving from pointcloud_normals to a different representation and
            # back breaks glyph rendering. This could be due to incorrect cleanup in
            # Geometry.change_representation or an issue of vtk 9.3.1. Creating a copy
            # of the Geometry instance circumvents the issue.
            if representation in ("normals", "basis", "gaussian_density"):
                self.container.update(geometry.uuid, geometry[...])
                geometry = self.container.get(geometry.uuid)

            geometry.change_representation(representation)

        self._highlight_selection()
        self.render()

    def _restore_geometry(self, uuid, geom) -> None:
        """Set ``uuid`` to ``geom`` exactly, or remove it when ``geom`` is None."""
        prev = self.container.get(uuid)
        if geom is None:
            if prev is not None:
                self.container.remove(uuid)
        elif prev is None:
            geom.uuid = uuid
            self.add(geom)
        else:
            self.container.update(uuid, geom)
        return None

    def _undo_subset_removal(self, record) -> None:
        """Re-append a removed point slice to its surviving geometry."""
        from .geometry import merge_geometries

        slice_copy = record.removed[...]
        slice_copy.uuid = record.uuid
        current = self.container.get(record.uuid)
        if current is None:
            self.add(slice_copy)
            return None
        # merge_geometries keeps the surviving geometry's representation (e.g. a
        # segmentation stays a segmentation instead of collapsing to a point cloud).
        merged = merge_geometries((current, slice_copy))
        merged.uuid = record.uuid
        self.container.update(record.uuid, merged)
        return None

    def _redo_subset_removal(self, record) -> None:
        """Re-remove the slice by keeping only the first ``n_kept`` points.

        Undo appends the slice at the tail, so the first ``n_kept`` points are the
        surviving set; redo only runs on that post-undo state (the UndoStack clears
        redo on push and a redo can only follow its matching undo).
        """
        current = self.container.get(record.uuid)
        if current is None:
            return None
        keep = np.zeros(current.get_number_of_points(), dtype=bool)
        keep[: record.n_kept] = True
        self.container.update(record.uuid, current.subset(keep, copy=True))
        return None

    def _apply_changes(self, changes, *, undo: bool) -> None:
        """Apply each change in the given direction, then refresh once."""
        for change in changes:
            if isinstance(change, _GeometrySubset):
                if undo:
                    self._undo_subset_removal(change)
                else:
                    self._redo_subset_removal(change)
            else:
                self._restore_geometry(
                    change.uuid, change.before if undo else change.after
                )
        self.data_changed.emit()
        self.render()
        return None

    def _capture_selection(self, selected):
        """Snapshot the pre-op state shared by ``merge`` and ``remove_selection``."""
        whole_uuids = {g.uuid for g in selected}
        point_uuids = [u for u in self.point_selection if u not in whole_uuids]
        swaps = {
            u: _GeometrySwap(u, before=self.container.get(u)[...], after=None)
            for u in whole_uuids
        }
        slices, originals = {}, {}
        for u in point_uuids:
            source = self.container.get(u)
            slices[u] = source[self.point_selection[u]]
            # Subsetting a mesh drops triangles straddling the cut, and the
            # subset/merge undo path cannot rebuild that severed connectivity.
            # Snapshot the pristine mesh so undo restores it exactly instead.
            if _has_mesh_model(source):
                originals[u] = source[...]
        return swaps, slices, originals

    def _subset_changes(self, slices, originals):
        """Build one change per point source from its post-op survival state."""
        changes = []
        for uuid, removed in slices.items():
            survivor = self.container.get(uuid)
            if survivor is None:
                changes.append(_GeometrySwap(uuid, before=removed, after=None))
            elif uuid in originals:
                changes.append(
                    _GeometrySwap(uuid, before=originals[uuid], after=survivor[...])
                )
            else:
                changes.append(
                    _GeometrySubset(
                        uuid, removed=removed, n_kept=survivor.get_number_of_points()
                    )
                )
        return changes

    def _push_swap(self, label: str, changes) -> None:
        from .undo import STACK

        STACK.push_pair(
            label,
            undo=lambda: self._apply_changes(changes, undo=True),
            redo=lambda: self._apply_changes(changes, undo=False),
        )
        return None

    def merge(self):
        from .geometry import Geometry, merge_geometries

        selected = self.get_selected_geometries()
        swaps, slices, originals = self._capture_selection(selected)

        point_cluster = self.add_selection(self.point_selection, add=True)
        self.deselect_points()

        merge_list = [
            *self.get_selected_geometries(),
            self.container.get(point_cluster),
        ]
        merge_list = [g for g in merge_list if isinstance(g, Geometry)]
        if not merge_list:
            self.render()
            return None

        merged = merge_geometries(merge_list)
        self.remove(merge_list)
        new_index = self.add(merged)
        merged_uuid = self.container.get(new_index).uuid

        if merged_uuid in swaps:
            swaps[merged_uuid].after = merged[...]
        else:
            swaps[merged_uuid] = _GeometrySwap(
                merged_uuid, before=None, after=merged[...]
            )

        changes = list(swaps.values()) + self._subset_changes(slices, originals)
        self._push_swap("Merge", changes)
        self.render()
        return None

    def remove(self, uuids_or_geometries):
        """Remove the given geometries from the container and notify listeners."""
        self.container.remove(uuids_or_geometries)
        self.data_changed.emit()

    def remove_selection(self):
        """Drop selected points (or whole geometries when fully selected)."""
        selected = self.get_selected_geometries()
        if not self.point_selection and not selected:
            return None

        swaps, slices, originals = self._capture_selection(selected)

        self.add_selection(self.point_selection, add=False)
        self.point_selection.clear()
        self.remove(selected)

        changes = list(swaps.values()) + self._subset_changes(slices, originals)
        self._push_swap("Remove", changes)
        self.render()
        return None

    def visibility(self, geometries, visible: bool = True):
        for geometry in geometries:
            if geometry is None:
                continue
            geometry.set_visibility(visible)
        self.render()

    def duplicate(self, geometries):
        for geometry in geometries:
            if geometry is None:
                continue
            self.add(geometry[...])
        self.render()

    def update(self, tree_state=None):
        """Resync the tree widget after the session swapped containers.

        Parameters
        ----------
        tree_state : TreeState, optional
            Tree structure to restore. If None, items are added to root.
        """
        self.viewport.rendered_actors.clear()

        if tree_state is not None:
            self.data_list.apply_state(tree_state, self._uuid_to_items())
        else:
            self.data_list.update(self._uuid_to_items())

        self.data_changed.emit()
