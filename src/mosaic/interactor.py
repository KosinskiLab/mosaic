"""
Implemenents DataContainerInteractor and LinkedDataContainerInteractor,
which mediate interaction between the GUI and underlying DataContainers.
This includes selection, editing and rendering.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np
from os.path import splitext
from typing import Tuple, List, Dict

import vtk
from functools import wraps
from qtpy.QtGui import QAction
from qtpy.QtWidgets import (
    QListWidget,
    QMenu,
    QFileDialog,
    QMessageBox,
    QDialog,
)
from qtpy.QtCore import (
    Qt,
    QObject,
    QItemSelection,
    QItemSelectionModel,
    Signal,
    QEvent,
)
from .parallel import run_in_background

__all__ = ["DataContainerInteractor"]


def on_run_complete(self, *args, **kwargs):
    self.data_changed.emit()
    self.render()


def _cluster_modifier(
    operation_name: str,
    keep_selection: bool = False,
    render: bool = True,
    remove_original: bool = False,
):
    def decorator(func):
        @wraps(func)
        def func_wrapper(self, **kwargs):
            from .operations import GeometryOperations

            indices = self._get_selected_indices()
            kwarg_indices = kwargs.pop("indices", ())
            if not isinstance(kwarg_indices, (Tuple, List)):
                kwarg_indices = [kwarg_indices]

            indices = (*indices, *kwarg_indices)
            for index in indices:
                geometry = self.container.get(index)
                if geometry is None:
                    continue

                func = getattr(GeometryOperations, operation_name)

                geometry = func(geometry, **kwargs)

                if geometry is None:
                    continue
                elif isinstance(geometry, (List, Tuple)):
                    _ = [self.add(x) for x in geometry]
                else:
                    self.add(geometry)

            if remove_original:
                self.container.remove(indices)

            self.data_changed.emit()
            if render:
                self.render()

            if not keep_selection:
                return None

            selection = QItemSelection()
            for index in indices:
                index = self.data_list.model().index(index, 0)
                selection.select(index, index)

            selection_model_flag = QItemSelectionModel.SelectionFlag
            self.data_list.selectionModel().select(
                selection, selection_model_flag.Clear | selection_model_flag.Select
            )

        return func_wrapper

    return decorator


class DataContainerInteractor(QObject):
    """Handle interaction between GUI and DataContainer"""

    data_changed = Signal()
    render_update = Signal()

    def __init__(self, container, vtk_widget, prefix="Cluster"):
        from .widgets import ContainerListWidget

        super().__init__()
        self.prefix = prefix
        self.point_selection, self.rendered_actors = {}, set()
        self.vtk_widget, self.container = vtk_widget, container

        # Interaction element for the GUI
        self.data_list = ContainerListWidget()
        self.data_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.data_list.itemChanged.connect(self._on_item_renamed)
        self.data_list.itemSelectionChanged.connect(self._on_cluster_selection_changed)

        self.data_list.list_widget.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.data_list.list_widget.customContextMenuRequested.connect(
            self._show_context_menu
        )

        # Functionality to add points
        self._interaction_mode, self._active_cluster = False, None
        self.point_picker = vtk.vtkWorldPointPicker()
        self.vtk_widget.installEventFilter(self)

        self.set_coloring_mode("default")

    def _get_selected_indices(self):
        return sorted([item.row() for item in self.data_list.selectedIndexes()])

    def attach_area_picker(self):
        self.interactor = self.vtk_widget.GetRenderWindow().GetInteractor()
        if self.interactor is None:
            print("Initialize an Interactor first.")
            return None
        self.area_picker = vtk.vtkAreaPicker()
        style = vtk.vtkInteractorStyleRubberBandPick()

        self.interactor.SetPicker(self.area_picker)
        self.interactor.SetInteractorStyle(style)
        self.area_picker.AddObserver("EndPickEvent", self._on_area_pick)

    def get_event_position(self, event, return_event_position: bool = True):
        pos = event.pos()
        return self._get_event_position(
            (pos.x(), pos.y(), 0), return_event_position=return_event_position
        )

    def _get_event_position(self, position, return_event_position: bool = True):
        # Avoid DPI/scaling issue on MacOS Retina displays
        dpr = self.vtk_widget.devicePixelRatio()

        y = (self.vtk_widget.height() - position[1]) * dpr
        event_position = (position[0] * dpr, y, 0)
        r = self.vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer()
        self.point_picker.Pick(*event_position, r)
        world_position = self.point_picker.GetPickPosition()

        # Projection onto current camera plane
        camera = r.GetActiveCamera()
        camera_plane = vtk.vtkPlane()
        camera_plane.SetNormal(camera.GetDirectionOfProjection())
        camera_plane.SetOrigin(world_position)

        t = vtk.mutable(0.0)
        x = [0, 0, 0]
        camera_plane.IntersectWithLine(camera.GetPosition(), world_position, t, x)
        if return_event_position:
            return x, event_position
        return x

    def eventFilter(self, watched_obj, event):
        # VTK camera also observes left-click, so duplicate calls need to be handled
        if self._interaction_mode in ("draw", "pick") and event.type() in [
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseMove,
        ]:
            if event.buttons() & Qt.MouseButton.LeftButton:
                world_position, event_position = self.get_event_position(event, True)
                if self._interaction_mode == "draw":
                    self._add_point(world_position)
                elif self._interaction_mode == "pick":
                    self._pick_prop(event_position)
                return True

        # Let vtk events pass through
        return super().eventFilter(watched_obj, event)

    def _on_item_renamed(self, item):
        index = self.data_list.row(item)
        if self.container._index_ok(index):
            self.container.data[index]._meta["name"] = item.text()
        self.data_changed.emit()
        self.render()

    def next_color(self):
        if not hasattr(self, "colors"):
            return self.container.base_color

        color = self.colors.pop(0)
        self.colors.append(color)
        return color

    def get_geometry(self, index):
        return self.container.get(index)

    def set_coloring_mode(self, mode: str):
        from .utils import get_cmap

        if mode not in ("default", "entity"):
            raise ValueError("Only mode 'default' and 'entity' are supported.")

        self.colors = [self.container.base_color]
        if mode == "entity":
            cmap = get_cmap("Set2")
            self.colors = [cmap(i)[:3] for i in range(cmap.N)]

        for i in range(len(self.container)):
            self.container.update_appearance([i], {"base_color": self.next_color()})
        self.container.highlight([])
        return self.render_vtk()

    def add(self, *args, **kwargs):
        if kwargs.get("color", None) is None:
            kwargs["color"] = self.next_color()
        return self.container.add(*args, **kwargs)

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

            geometry = self.container.get(index)
            if geometry is None:
                return None

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

        self.container.remove(remove_cluster)

        if len(new_cluster):
            points = np.concatenate([x[0] for x in new_cluster])
            normals = np.concatenate([x[1] for x in new_cluster])
            return self.add(points, normals=normals, sampling_rate=sampling)
        return -1

    def _add_point(self, point):
        geometry = self.container.get(self._active_cluster)
        if geometry is None:
            return -1

        geometry.swap_data(np.concatenate((geometry.points, np.asarray(point)[None])))
        self.data_changed.emit()
        self.render()
        return 0

    def activate_viewing_mode(self):
        self._interaction_mode = None
        self._active_cluster = None

    def activate_drawing_mode(self):
        self._active_cluster = None
        self._interaction_mode = "draw"

        active_clusters = list(set(self._get_selected_indices()))
        if len(active_clusters) > 1:
            print("Can only add points if a single cluster is selected.")
            return -1
        elif len(active_clusters) == 0:
            new_cluster = self.add(points=np.empty((0, 3), dtype=np.float32))
            active_clusters = [new_cluster]

        self._active_cluster = active_clusters[0]

    def activate_picking_mode(self):
        self._interaction_mode = "pick"

    def set_selection(self, selected_indices):
        selection = QItemSelection()
        for index in set(selected_indices):
            index = self.data_list.model().index(index, 0)
            selection.select(index, index)

        selection_model_flag = QItemSelectionModel.SelectionFlag
        self.data_list.selectionModel().select(
            selection, selection_model_flag.Clear | selection_model_flag.Select
        )
        self._on_cluster_selection_changed()

    def _on_cluster_selection_changed(self):
        selected_indices = set(self._get_selected_indices())
        self.container.highlight(selected_indices)
        self.render_vtk()

    def _on_cutoff_changed(self, lower_cutoff, upper_cutoff=None):
        cluster_sizes = self.container.get_cluster_size()
        selection = QItemSelection()

        if upper_cutoff is None:
            upper_cutoff = max(cluster_sizes) + 1

        for i in range(len(self.container)):
            if (cluster_sizes[i] > lower_cutoff) & (cluster_sizes[i] < upper_cutoff):
                index = self.data_list.model().index(i, 0)
                selection.select(index, index)

        self.data_list.selectionModel().select(
            selection, QItemSelectionModel.SelectionFlag.ClearAndSelect
        )

    def _on_area_pick(self, obj, event):
        frustum = obj.GetFrustum()

        extractor = vtk.vtkExtractSelectedFrustum()
        extractor.SetFrustum(frustum)

        interactor = self.vtk_widget.GetRenderWindow().GetInteractor()
        if not interactor.GetShiftKey():
            self.deselect_points()

        for i, cluster in enumerate(self.container.data):
            extractor.SetInputData(cluster._data)
            extractor.Update()

            output = extractor.GetOutput()
            n_selected = output.GetNumberOfPoints()
            if n_selected == 0:
                continue

            selected_ids = output.GetPointData().GetArray("vtkOriginalPointIds")
            if selected_ids and selected_ids.GetNumberOfTuples() > 0:
                ids_numpy = vtk.util.numpy_support.vtk_to_numpy(selected_ids)
                if i not in self.point_selection:
                    self.point_selection[i] = set()
                self.point_selection[i].update(set(ids_numpy))

        self.highlight_selected_points(color=None)

    def _pick_prop(self, event_pos):
        picker = vtk.vtkPropPicker()
        r = self.vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer()
        picker.Pick(*event_pos, r)

        picked_actor = picker.GetActor()
        actors = self.container.get_actors()
        if picked_actor in actors:
            index = actors.index(picked_actor)
            selected_indices = self._get_selected_indices()
            self.set_selection([index, *selected_indices])
        return None

    def _show_context_menu(self, position):
        item = self.data_list.itemAt(position)
        if not item:
            return -1

        context_menu = QMenu(self.data_list)

        show_action = QAction("Show", self.data_list)
        show_action.triggered.connect(lambda: self.visibility(visible=True))
        context_menu.addAction(show_action)
        hide_action = QAction("Hide", self.data_list)
        hide_action.triggered.connect(lambda: self.visibility(visible=False))
        context_menu.addAction(hide_action)

        duplicate_action = QAction("Duplicate", self.data_list)
        duplicate_action.triggered.connect(self.duplicate)
        context_menu.addAction(duplicate_action)
        remove_action = QAction("Remove", self.data_list)
        remove_action.triggered.connect(self.remove)
        context_menu.addAction(remove_action)

        formats = [
            "Points",
            "Gaussian Density",
            "Normals",
            "Basis",
            "Points with Normals",
            None,
            "Mesh",
            "Surface",
            "Wireframe",
        ]
        representation_menu = QMenu("Representation", context_menu)
        for format_name in formats:
            if format_name is None:
                representation_menu.addSeparator()
                continue
            action = QAction(format_name, representation_menu)
            action.triggered.connect(
                lambda checked, f=format_name: self.change_representation(f)
            )
            representation_menu.addAction(action)
        context_menu.addMenu(representation_menu)

        context_menu.addSeparator()
        export_menu = QAction("Export As", self.data_list)
        export_menu.triggered.connect(lambda: self._handle_export())
        context_menu.addAction(export_menu)

        properties_action = QAction("Properties", self.data_list)
        properties_action.triggered.connect(self._show_properties_dialog)
        context_menu.addAction(properties_action)

        context_menu.exec(self.data_list.mapToGlobal(position))

    def _handle_export(self, *args, **kwargs):
        from .dialogs import ExportDialog

        # Shape and sampling are given if MosaicData.open_file loaded a volume.
        # For convenience, outputs will be handled w.r.t to the initial volume
        sampling, shape = 1, self.container.metadata.get("shape")
        dialog = ExportDialog(parent=None, parameters={"shape": shape})

        if shape is not None:
            sampling = self.container.metadata.get("sampling_rate", 1)
            shape = np.rint(np.divide(shape, sampling)).astype(int)
        else:
            shape = (64, 64, 64)

        dialog.set_shape(shape)
        dialog.export_requested.connect(self._wrap_export)

        return dialog.exec()

    def _wrap_export(self, export_data):
        file_format = export_data.get("format")

        file_dialog = QFileDialog(None)
        file_path, _ = file_dialog.getSaveFileName(
            None, "Save File", "", f"{file_format.upper()} Files (*.{file_format})"
        )
        if not file_path:
            return -1

        try:
            self._export_data(file_path, export_data)
        except Exception as e:
            QMessageBox.warning(None, "Error", str(e))
        return None

    def _export_data(self, file_path: str, export_data: Dict):
        from .utils import points_to_volume
        from .formats import OrientationsWriter, write_density

        mesh_formats = ("obj", "stl", "ply")
        volume_formats = ("mrc", "em", "h5")
        point_formats = ("tsv", "star", "xyz")

        file_format = export_data.get("format")
        indices = self._get_selected_indices()
        if not len(indices):
            raise ValueError("Select at least one object.")

        file_path, _ = splitext(file_path)

        shape = self.container.metadata.get("shape", None)
        if shape is not None:
            _sampling = self.container.metadata.get("sampling_rate", 1)
            shape = np.rint(np.divide(shape, _sampling)).astype(int)

        center = 0
        if {"shape_x", "shape_y", "shape_z"}.issubset(export_data):
            shape = tuple(export_data[x] for x in ["shape_x", "shape_y", "shape_z"])

        orientation_kwargs = {}
        data = {"points": [], "quaternions": []}
        for index in indices:
            geometry = self.container.get(index)
            if geometry is None:
                continue

            if file_format in mesh_formats:
                fit = geometry._meta.get("fit", None)
                if not hasattr(fit, "mesh"):
                    raise ValueError(f"Selected geometry {index} is not a mesh.")
                fit.to_file(f"{file_path}_{index}.{file_format}")
                continue

            points, quaternions = geometry.points, None
            if file_format in point_formats:
                points, quaternions = geometry.points, geometry.quaternions

            if quaternions is None:
                quaternions = np.full((points.shape[0], 4), fill_value=(1, 0, 0, 0))

            sampling = export_data.get("sampling", -1)
            if sampling < 0:
                sampling = geometry.sampling_rate

            if export_data.get("relion_5_format", False):
                center = np.divide(shape, 2).astype(int) if shape is not None else 0
                center = np.multiply(center, sampling)
                orientation_kwargs["version"] = "# version 50001"
                sampling = 1

            points = np.subtract(np.divide(points, sampling), center)
            data["points"].append(points)
            data["quaternions"].append(quaternions)

        if file_format in mesh_formats:
            return None

        if len(data["points"]) == 0:
            raise ValueError("No elements suitable for export")

        if file_format in volume_formats:
            if shape is None:
                temp = np.rint(np.concatenate(data["points"]))
                shape = temp.astype(int).max(axis=0) + 1

            volume = None
            for index, points in enumerate(data["points"]):
                volume = points_to_volume(
                    points, sampling_rate=1, shape=shape, weight=index + 1, out=volume
                )

            # Try saving some memory on write. uint8 would be padded to 16 hence int8
            dtype = np.float32
            if index < np.iinfo(np.int8).max:
                dtype = np.int8
            elif index < np.iinfo(np.uint16).max:
                dtype = np.uint16

            return write_density(
                volume.astype(dtype),
                filename=f"{file_path}.{file_format}",
                sampling_rate=sampling,
            )

        if file_format not in point_formats:
            return None

        data["entities"] = [
            np.full(x.shape[0], fill_value=i) for i, x in enumerate(data["points"])
        ]
        if single_file := export_data.get("single_file", True):
            data = {k: [np.concatenate(v)] for k, v in data.items()}

        if file_format == "xyz":
            for index, points in enumerate(data["points"]):
                fname = f"{file_path}_{index}.{file_format}"
                if single_file:
                    fname = f"{file_path}.{file_format}"

                header = ""
                if export_data.get("header", True):
                    header = ",".join(["x", "y", "z"])

                np.savetxt(fname, points, delimiter=",", header=header, comments="")
            return 1

        for index in range(len(data["points"])):
            orientations = OrientationsWriter(**{k: v[index] for k, v in data.items()})
            fname = f"{file_path}_{index}.{file_format}"
            if single_file:
                fname = f"{file_path}.{file_format}"
            orientations.to_file(fname, file_format=file_format, **orientation_kwargs)

    def _show_properties_dialog(self) -> int:
        from .dialogs import GeometryPropertiesDialog

        indices = self._get_selected_indices()
        indices = [x for x in indices if self.container._index_ok(x)]
        if not len(indices):
            return -1

        base_container = self.container.data[indices[0]]
        base_parameters = base_container._appearance.copy()
        base_parameters["sampling_rate"] = base_container.sampling_rate

        dialog = GeometryPropertiesDialog(initial_properties=base_parameters)

        def on_parameters_changed(parameters):
            sampling_rate = parameters.pop("sampling_rate")
            full_render = self.container.update_appearance(indices, parameters)
            for index in indices:
                self.container.data[index]._sampling_rate = sampling_rate

            if full_render:
                return self.render()
            return self.render_vtk()

        dialog.parametersChanged.connect(on_parameters_changed)

        if dialog.exec() == QDialog.DialogCode.Rejected:
            on_parameters_changed(base_parameters)
        return 1

    def remove_points(self):
        added_cluster = self.add_selection(self.point_selection)
        if added_cluster == -1:
            return -1

        self.deselect_points()
        self.container.remove(added_cluster)

    def cluster_points(self):
        ret = self.add_selection(self.point_selection)
        self.deselect_points()
        return ret

    def render(self):
        from .widgets import StyledListWidgetItem

        renderer = self.vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer()

        current_actors = set(self.container.get_actors())

        actors_to_remove = self.rendered_actors - current_actors
        for actor in actors_to_remove:
            renderer.RemoveActor(actor)
            self.rendered_actors.remove(actor)

        actors_to_add = current_actors - self.rendered_actors
        for actor in actors_to_add:
            renderer.AddActor(actor)
            self.rendered_actors.add(actor)

        self.data_list.clear()
        for i in range(len(self.container)):
            name = self.container.data[i]._meta.get("name", None)
            if name is None:
                name = f"{self.prefix} {i}"

            visible = self.container.data[i].visible
            text = self.container.data[i]._meta.get("metadata_text", None)
            if text is None:
                text = _format_point_label(self.container.data[i].points.shape[0])

            type = "cluster"
            geometry = self.container.data[i]
            fit = geometry._meta.get("fit", None)
            if fit is not None:
                text = "mesh" if hasattr(fit, "mesh") else "parametric"
                if text == "mesh" and hasattr(geometry, "_trajectory"):
                    text = "trajectory"
                type = text

            meta_info = geometry._meta.pop("info", {})
            meta_info.update({"metadata_text": text, "item_type": type, "name": name})

            geometry._meta["info"] = meta_info
            item = StyledListWidgetItem(name, visible, meta_info, editable=True)
            self.data_list.addItem(item)

        self.render_vtk()
        return self.render_update.emit()

    def render_vtk(self):
        self.vtk_widget.GetRenderWindow().Render()

    def deselect(self):
        self.data_list.clearSelection()
        self.deselect_points()

    def deselect_points(self):
        for cluster_index, point_ids in self.point_selection.items():
            if not self.container._index_ok(cluster_index):
                continue
            geometry = self.container.data[cluster_index]
            color = geometry._appearance.get("base_color", (0.7, 0.7, 0.7))
            self.container.highlight_points(cluster_index, point_ids, color)

        self.point_selection.clear()

    def highlight_selected_points(self, color):
        for cluster_index, point_ids in self.point_selection.items():
            self.container.highlight_points(cluster_index, point_ids, color)

        self.vtk_widget.GetRenderWindow().Render()

    def highlight_clusters_from_selected_points(self):
        return self.set_selection(list(self.point_selection.keys()))

    def change_representation(self, representation: str):
        indices = self._get_selected_indices()
        if not len(indices):
            return -1

        representation = representation.lower().replace(" ", "_")

        if representation == "points":
            representation = "pointcloud"
        elif representation == "points_with_normals":
            representation = "pointcloud_normals"

        for index in indices:
            geometry = self.container.get(index)
            if geometry is None:
                continue

            # BUG: Moving from pointcloud_normals to a different representation and
            # back breaks glyph rendering. This could be due to incorrect cleanup in
            # Geometry.change_representation or an issue of vtk 9.3.1. Creating a copy
            # of the Geometry instance circumvents the issue.
            if representation in (
                "pointcloud_normals",
                "normals",
                "basis",
                "gaussian_density",
            ):
                self.container.data[index] = geometry[...]
                geometry = self.container.data[index]

            geometry.change_representation(representation)
        self.render()

    def _backup(self):
        # Save clusters and points that are modified by the operation
        self._merge_index = None
        try:
            self._geometry_backup = {
                i: self.container.get(i)[...] for i in self._get_selected_indices()
            }
            self._point_backup = {
                i: self.container.get(i)[list(ix)]
                for i, ix in self.point_selection.items()
            }
        except Exception:
            self._geometry_backup = None
            self._point_backup = None

    def undo(self):
        if getattr(self, "_geometry_backup", None) is None:
            return None

        if getattr(self, "_merge_index", None) is not None:
            self.container.remove(self._merge_index)

        for i, geometry in self._geometry_backup.items():
            self.add(geometry)

        for i, geometry in self._point_backup.items():
            if not self.container._index_ok(i):
                self.add(geometry)
                continue
            self.container.data[i] = geometry.merge((geometry, self.container.data[i]))

        self._geometry_backup = None
        self._point_backup = None
        self._merge_index = None
        self.render()

    def merge(self):
        self._backup()
        point_cluster = self.cluster_points()
        new_cluster = self.merge_cluster()
        self.merge_cluster(indices=(new_cluster, point_cluster))
        self._merge_index = len(self.container.data) - 1

    def remove(self):
        self._backup()
        self.remove_points()
        self.remove_cluster()

    def refresh_actors(self):
        for index in range(len(self.container)):
            self.container.data[index] = self.container.data[index][...]
        return self.render()

    def remove_cluster(self, **kwargs):
        self.container.remove(self._get_selected_indices())
        return self.render()

    def merge_cluster(self, **kwargs):
        from .geometry import Geometry

        indices = self._get_selected_indices()
        kwarg_indices = kwargs.pop("indices", ())
        if not isinstance(kwarg_indices, (Tuple, List)):
            kwarg_indices = [kwarg_indices]

        indices = (*indices, *kwarg_indices)
        geometries = [self.container.get(i) for i in (*indices, *kwarg_indices)]
        geometries = [x for x in geometries if x is not None]
        if len(geometries) == 0:
            return None

        geometry = Geometry.merge(geometries)

        self.container.remove(indices)
        self.add(geometry)
        self.render()

    def update(self, other):
        if not isinstance(other, type(self.container)):
            raise ValueError(
                f"Can not update {type(self.container)} using {type(other)}."
            )

        self.container.clear()
        self.container.metadata.update(other.metadata)
        for index in range(len(other)):
            geometry = other.get(index)
            if geometry is None:
                continue
            self.add(geometry)
        self.data_changed.emit()


_GEOMETRY_OPERATIONS = {
    "decimate": {"remove_original": False},
    "downsample": {"remove_original": False},
    "remove_outliers": {"remove_original": False},
    "compute_normals": {"remove_original": False},
    "cluster": {"remove_original": True, "render": False, "background": True},
    "duplicate": {"remove_original": False},
    "visibility": {"remove_original": False},
}

for operation_name, config in _GEOMETRY_OPERATIONS.items():
    method_name = config.get("method_name", operation_name)
    remove_original = config.get("remove_original", False)
    render = config.get("render", True)
    background = config.get("background", False)

    def create_method(op_name, remove_orig, render_flag, bg_task):
        @_cluster_modifier(op_name, remove_original=remove_orig, render=render_flag)
        def method(self, **kwargs):
            f"""Apply {op_name} operation to selected geometries."""
            pass

        if bg_task:
            method = run_in_background(op_name.title(), callback=on_run_complete)(
                method
            )

        method.__name__ = method_name
        method.__doc__ = f"Apply {op_name} operation using GeometryOperations."
        return method

    setattr(
        DataContainerInteractor,
        method_name,
        create_method(operation_name, remove_original, render, background),
    )


def _format_point_label(count):
    if count <= 9999:
        return f"{count} pts"
    elif count < 1000000:
        return f"{count/1000:.3g}k pts"
    else:
        return f"{count/1000000:.3g}M pts"
