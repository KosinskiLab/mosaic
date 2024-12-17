""" Implemenents DataContainerInteractor and LinkedDataContainerInteractor,
    which mediate interaction between the GUI and underlying DataContainers.
    This includes selection, editing and rendering.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np
from os.path import splitext
from typing import Tuple, List

import vtk
from functools import wraps
from PyQt6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QMenu,
    QFileDialog,
    QMessageBox,
)
from PyQt6.QtCore import (
    Qt,
    QObject,
    QItemSelection,
    QItemSelectionModel,
    pyqtSignal,
    QEvent,
)
from PyQt6.QtGui import QAction, QColor

from .utils import points_to_volume
from .io_utils import OrientationsWriter, write_density
from ._gui.dialog import GeometryPropertiesDialog


def _cluster_modifier(keep_selection: bool = False):
    def decorator(func):
        @wraps(func)
        def func_wrapper(self, **kwargs):
            indices = self._get_selected_indices()
            kwarg_indices = kwargs.pop("indices", ())
            if not isinstance(kwarg_indices, (Tuple, List)):
                kwarg_indices = [kwarg_indices]

            result = func(self, indices=(*indices, *kwarg_indices), **kwargs)
            self.data_changed.emit()
            self.render()

            if not keep_selection:
                return result

            selection = QItemSelection()
            for index in indices:
                index = self.data_list.model().index(index, 0)
                selection.select(index, index)

            selection_model_flag = QItemSelectionModel.SelectionFlag
            self.data_list.selectionModel().select(
                selection, selection_model_flag.Clear | selection_model_flag.Select
            )
            return result

        return func_wrapper

    return decorator


class LinkedDataContainerInteractor(QObject):
    selectionChanged = pyqtSignal()

    def __init__(self, interactor):
        super().__init__()
        self.interactor = interactor

        self.data_list = QListWidget()
        self.data_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        # self.data_list.setEditTriggers(
        #     QListWidget.EditTrigger.DoubleClicked
        #     | QListWidget.EditTrigger.SelectedClicked
        #     | QListWidget.EditTrigger.EditKeyPressed
        # )
        # self.data_list.itemChanged.connect(self.interactor._on_item_renamed)
        self.data_list.itemSelectionChanged.connect(self._on_cluster_selection_changed)

        self._update_list()

        self.interactor.data_changed.connect(self._update_list)
        self.data_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.data_list.customContextMenuRequested.connect(
            self.interactor._show_context_menu
        )

    def _update_list(self):
        self.data_list.clear()
        for i in range(self.interactor.container.get_cluster_count()):
            visible = self.container.data[i].visible

            name = self.container.data[i]._meta.get(
                "name", f"{self.interactor.prefix} {i}"
            )
            item = QListWidgetItem(name)
            if not visible:
                item.setForeground(self.interactor.invisible_color)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.data_list.addItem(item)

    def _on_cluster_selection_changed(self):
        selected_indices = self._get_selected_indices()
        self.interactor.set_selection(selected_indices)
        self.selectionChanged.emit()

    def _get_selected_indices(self):
        return [item.row() for item in self.data_list.selectedIndexes()]

    def deselect(self):
        self.data_list.clearSelection()

    def __getattr__(self, name):
        return getattr(self.interactor, name)


class DataContainerInteractor(QObject):
    data_changed = pyqtSignal()

    def __init__(self, container, vtk_widget, prefix="Cluster"):
        super().__init__()
        self.prefix = prefix
        self.point_selection, self.rendered_actors = {}, set()
        self.vtk_widget, self.container = vtk_widget, container

        # Interaction element for the GUI
        self.data_list = QListWidget()
        self.data_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        # self.data_list.setEditTriggers(
        #     QListWidget.EditTrigger.DoubleClicked
        #     | QListWidget.EditTrigger.SelectedClicked
        #     | QListWidget.EditTrigger.EditKeyPressed
        # )
        self.data_list.itemChanged.connect(self._on_item_renamed)
        self.data_list.itemSelectionChanged.connect(self._on_cluster_selection_changed)

        # We assume its already initialized
        self.interactor = self.vtk_widget.GetRenderWindow().GetInteractor()
        self.area_picker = vtk.vtkAreaPicker()
        style = vtk.vtkInteractorStyleRubberBandPick()

        self.interactor.SetPicker(self.area_picker)
        self.interactor.SetInteractorStyle(style)
        self.area_picker.AddObserver("EndPickEvent", self._on_area_pick)

        self.invisible_color = QColor(128, 128, 128)
        self.data_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.data_list.customContextMenuRequested.connect(self._show_context_menu)

        # Functionality to add points
        self._point_mode, self._active_cluster = False, None
        self.point_picker = vtk.vtkWorldPointPicker()
        self.vtk_widget.installEventFilter(self)

    def eventFilter(self, watched_obj, event):
        # VTK camera also observes left-click, so duplicate calls need to be handled
        if self._point_mode and event.type() in [
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseMove,
        ]:
            if event.buttons() & Qt.MouseButton.LeftButton:
                position = event.pos()

                # Avoid DPI/scaling issue on MacOS Retina displays
                dpr = self.vtk_widget.devicePixelRatio()

                y = (self.vtk_widget.height() - position.y()) * dpr
                r = self.vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer()
                self.point_picker.Pick(position.x() * dpr, y, 0, r)

                world_position = self.point_picker.GetPickPosition()
                self._add_point(world_position)
                return True

        # Let vtk events pass through
        return super().eventFilter(watched_obj, event)

    def _on_item_renamed(self, item):
        index = self.data_list.row(item)
        if self.container._index_ok(index):
            self.container.data[index]._meta["name"] = item.text()
        self.data_changed.emit()
        self.render()

    def _add_point(self, point):
        if not self.container._index_ok(self._active_cluster):
            return -1

        cluster = self.container.data[self._active_cluster]
        cluster.swap_data(np.concatenate((cluster.points, np.asarray(point)[None])))
        self.data_changed.emit()
        self.render()
        return 0

    def deactivate_drawing_mode(self):
        if self._point_mode:
            return self.toggle_drawing_mode()
        return None

    def toggle_drawing_mode(self):
        self._point_mode = not self._point_mode
        self._active_cluster = None
        if self._point_mode:
            active_clusters = list(set(self._get_selected_indices()))
            if len(active_clusters) > 1:
                print("Can only add points if a single cluster is selected.")
                return -1
            elif len(active_clusters) == 0:
                new_cluster = self.container.add(
                    points=np.empty((0, 3), dtype=np.float32)
                )
                active_clusters = [new_cluster]

            self._active_cluster = active_clusters[0]

    def set_selection(self, selected_indices):
        selection = QItemSelection()
        for index in selected_indices:
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
        self.vtk_widget.GetRenderWindow().Render()

    def _on_cutoff_changed(self, cutoff_value):
        cluster_sizes = self.container.get_cluster_size()
        selection = QItemSelection()

        for i in range(self.container.get_cluster_count()):
            if cluster_sizes[i] < cutoff_value:
                index = self.data_list.model().index(i, 0)
                selection.select(index, index)

        self.data_list.selectionModel().select(
            selection, QItemSelectionModel.SelectionFlag.ClearAndSelect
        )

    def _on_area_pick(self, obj, event):
        frustum = obj.GetFrustum()
        self.deselect_points()
        for i, cluster in enumerate(self.container.data):
            extract = vtk.vtkExtractSelectedFrustum()
            extract.SetFrustum(frustum)
            extract.SetInputData(cluster._data)
            extract.Update()
            selected_ids = vtk.vtkIdTypeArray.SafeDownCast(
                extract.GetOutput().GetPointData().GetArray("vtkOriginalPointIds")
            )
            if selected_ids and selected_ids.GetNumberOfTuples() > 0:
                self.point_selection[i] = set(
                    selected_ids.GetValue(j)
                    for j in range(selected_ids.GetNumberOfTuples())
                )
        self.highlight_selected_points(color=(0.8, 0.2, 0.2))

    def _show_context_menu(self, position):
        from ._gui.dialog import make_param

        item = self.data_list.itemAt(position)
        if not item:
            return -1

        context_menu = QMenu(self.data_list)

        show_action = QAction("Show", self.data_list)
        show_action.triggered.connect(lambda: self.change_visibility(visible=True))
        context_menu.addAction(show_action)
        hide_action = QAction("Hide", self.data_list)
        hide_action.triggered.connect(lambda: self.change_visibility(visible=False))
        context_menu.addAction(hide_action)

        duplicate_action = QAction("Duplicate", self.data_list)
        duplicate_action.triggered.connect(self.duplicate)
        context_menu.addAction(duplicate_action)

        formats = [
            "Pointcloud",
            "Normals",
            "Pointcloud with Normals",
            "Mesh",
            "Wireframe",
        ]
        representation_menu = QMenu("Representation", context_menu)
        for format_name in formats:
            action = QAction(format_name, representation_menu)
            action.triggered.connect(
                lambda checked, f=format_name: self.change_representation(f)
            )
            representation_menu.addAction(action)
        context_menu.addMenu(representation_menu)

        context_menu.addSeparator()
        EXPORT_FORMATS = {
            "mrc": {
                "default": [],
                "custom": [
                    make_param("shape_x", 64, 0, "Number of voxels along X"),
                    make_param("shape_y", 64, 0, "Number of voxels along Y"),
                    make_param("shape_z", 64, 0, "Number of voxels along Z"),
                    make_param(
                        "sampling", 1.0, 1e-6, "Distance (typically Å) per voxel."
                    ),
                ],
            },
            "obj": [],
            "tsv": [],
            "star": {
                "default": [],
                "relion 5": [
                    make_param("shape_x", 64, 0, "Number of voxels in x (for center)."),
                    make_param("shape_y", 64, 0, "Number of voxels in y (for center)."),
                    make_param("shape_z", 64, 0, "Number of voxels in z (for center)."),
                ],
            },
            "xyz": [],
        }
        export_menu = QMenu("Export As", context_menu)
        for format_name, parameters in EXPORT_FORMATS.items():
            action = QAction(format_name.lower(), export_menu)
            action.triggered.connect(
                lambda checked, f=format_name, p=parameters: self._export_data(f, p)
            )
            export_menu.addAction(action)

        context_menu.addMenu(export_menu)

        properties_action = QAction("Properties", self.data_list)
        properties_action.triggered.connect(self._show_properties_dialog)
        context_menu.addAction(properties_action)

        context_menu.exec(self.data_list.mapToGlobal(position))

    def _export_data(self, file_format: str, parameters: List[Tuple]):
        from ._gui.dialog import OperationDialog

        kwargs = {}
        if len(parameters):
            dialog = OperationDialog(
                f"Export as {file_format.lower()}", parameters, None
            )
            if dialog.exec() != dialog.DialogCode.Accepted:
                return None
            kwargs = dialog.get_parameters()

        file_dialog = QFileDialog(None)
        file_path, _ = file_dialog.getSaveFileName(
            None, "Save File", "", f"{file_format.upper()} Files (*.{file_format})"
        )

        if not file_path:
            return -1

        success = self.export_data(file_path, file_format, **kwargs)
        if success != -1:
            QMessageBox.information(None, "Success", "Data export successful.")
        return None

    def export_data(self, file_path, file_format, **kwargs):
        indices = self._get_selected_indices()
        if not len(indices):
            return -1

        file_path, _ = splitext(file_path)
        center, shape = 0, self.container.metadata.get("shape", None)
        # Shape and sampling are given if ColabsegData.open_file loaded a volume.
        # For convenience, outputs will be handled w.r.t to the initial volume
        if shape is not None:
            _sampling = self.container.metadata.get("sampling_rate", 1)
            shape = np.rint(np.divide(shape, _sampling)).astype(int)

        if {"shape_x", "shape_y", "shape_z"}.issubset(kwargs):
            shape = tuple(kwargs[x] for x in ["shape_x", "shape_y", "shape_y"])
            if file_format == "star":
                center = np.divide(shape, 2).astype(int)

        export_data, status = {"points": [], "normals": []}, -1
        for index in indices:
            if not self.container._index_ok(index):
                continue

            geometry = self.container.data[index]
            if file_format in ("obj",):
                fit = geometry._meta.get("fit", None)
                if not hasattr(fit, "mesh"):
                    print(f"{index} is not a mesh but format is mesh-specific.")
                    continue
                fit.to_file(f"{file_path}_{index}.{file_format}")
                status = 0
                continue

            points, normals = geometry.points, geometry.normals
            if normals is None:
                normals = np.zeros_like(points)
                if "fit" in geometry._meta:
                    normals = geometry._meta["fit"].compute_normal(points)

            sampling = kwargs.get("sampling", None)
            if sampling is None:
                sampling = np.max(geometry.sampling_rate)

            points = np.subtract(np.divide(points, sampling), center)
            export_data["points"].append(points)
            export_data["normals"].append(normals)

        if file_format in ("obj",):
            return status
        elif len(export_data["points"]) == 0:
            return -1

        if file_format == "mrc":
            if shape is None:
                temp = np.rint(np.concatenate(export_data["points"]))
                shape = temp.astype(int).max(axis=0) + 1

            data = None
            for index, points in enumerate(export_data["points"]):
                data = points_to_volume(
                    points, sampling_rate=1, shape=shape, weight=index + 1, out=data
                )
            return write_density(
                data,
                filename=f"{file_path}.{file_format}",
                sampling_rate=sampling,
            )

        if file_format == "xyz":
            for index, points in enumerate(export_data["points"]):
                fname = f"{file_path}_{index}.{file_format}"
                np.savetxt(fname, points, header="x y z", comments="")

        if file_format not in ("tsv", "star"):
            return -1

        orientations = OrientationsWriter(**export_data)
        orientations.to_file(f"{file_path}.{file_format}", file_format=file_format)

    def _show_properties_dialog(self) -> int:
        indices = self._get_selected_indices()
        indices = [x for x in indices if self.container._index_ok(x)]
        if not len(indices):
            return -1

        base_parameters = self.container.data[indices[0]]._appearance

        dialog = GeometryPropertiesDialog(initial_properties=base_parameters)
        parameters = dialog.exec_()
        if parameters is None:
            return 0

        for index in indices:
            if not self.container._index_ok(index):
                continue
            geometry = self.container.data[index]

            geometry._appearance.update(parameters)
            geometry.set_appearance(**parameters)

        return self.container.highlight(indices)

    def _get_selected_indices(self):
        return [item.row() for item in self.data_list.selectedIndexes()]

    def remove_points(self):
        added_cluster = self.container.add_selection(self.point_selection)
        if added_cluster == -1:
            return -1
        self.deselect_points()
        self.container.remove(added_cluster)
        self.render()

    def cluster_points(self):
        ret = self.container.add_selection(self.point_selection)
        self.render()
        return ret

    def render(self):
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
        for i in range(self.container.get_cluster_count()):
            visible = self.container.data[i].visible
            name = self.container.data[i]._meta.get("name", None)
            if name is None:
                name = f"{self.prefix} {i}"

            item = QListWidgetItem(name)
            if not visible:
                item.setForeground(self.invisible_color)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.data_list.addItem(item)

        return self.render_vtk()

    def render_vtk(self):
        self.vtk_widget.GetRenderWindow().Render()

    def deselect(self):
        self.data_list.clearSelection()
        self.deselect_points()

    def deselect_points(self):
        self.highlight_selected_points(color=(0.7, 0.7, 0.7))
        self.point_selection.clear()

    def highlight_selected_points(self, color):
        for cluster_index, point_ids in self.point_selection.items():
            self.container.highlight_points(cluster_index, point_ids, color)
        self.vtk_widget.GetRenderWindow().Render()

    def change_representation(self, representation: str):
        indices = self._get_selected_indices()
        if not len(indices):
            return -1

        representation = representation.lower()
        representation = representation.replace("with", "_").replace(" ", "")
        for index in indices:
            if not self.container._index_ok(index):
                continue
            geometry = self.container.data[index]

            # BUG: Moving from pointcloud_normals to a different representation and
            # back breaks glyph rendering. This could be due to incorrect cleanup in
            # Geometry.change_representation or an issue of vtk 9.3.1. Creating a copy
            # of the Geometry instance circumvents the issue.
            if representation in ("pointcloud_normals", "normals"):
                self.container.data[index] = geometry[...]
                geometry = self.container.data[index]

            geometry.change_representation(representation)

        self.render()

    @_cluster_modifier()
    def change_visibility(self, **kwargs):
        if len(kwargs["indices"]) == 0:
            kwargs["indices"] = tuple(range(self.container.get_cluster_count()))
        return self.container.change_visibility(**kwargs)

    @_cluster_modifier(keep_selection=True)
    def toggle_visibility(self, **kwargs):
        if len(kwargs["indices"]) == 0:
            kwargs["indices"] = tuple(range(self.container.get_cluster_count()))

        for index in kwargs["indices"]:
            visible = not self.container.data[index].visible
            self.container.change_visibility([index], visible=visible)

        return None

    @_cluster_modifier()
    def cluster(self, method, **kwargs):
        """
        Cluster point cloud using specified clustering method.

        Parameters
        ----------
        point_cloud : ndarray
            Input point cloud coordinates.
        method : str
            Clustering method to use. Options are:
            - 'DBSCAN'
            - 'Connected Components'
        **kwargs
            Additional arguments passed to the chosen clustering method.

        Returns
        -------
        list
            List of point clouds, one for each identified cluster.
        """
        func = self.container.dbscan_cluster
        if method == "Connected Components":
            func = self.container.connected_components
        elif method == "K-Means":
            func = self.container.split

        return func(**kwargs)

    @_cluster_modifier()
    def duplicate(self, **kwargs):
        return self.container.duplicate(**kwargs)

    @_cluster_modifier()
    def decimate(self, **kwargs):
        return self.container.decimate(**kwargs)

    @_cluster_modifier()
    def merge_cluster(self, **kwargs):
        return self.container.merge(**kwargs)

    @_cluster_modifier()
    def remove_cluster(self, **kwargs):
        return self.container.remove(**kwargs)

    @_cluster_modifier()
    def split_cluster(self, **kwargs):
        return self.container.split(**kwargs)

    @_cluster_modifier()
    def sample_cluster(self, **kwargs):
        return self.container.sample(**kwargs)

    @_cluster_modifier()
    def crop_cluster(self, **kwargs):
        return self.container.crop(**kwargs)

    @_cluster_modifier()
    def trim(self, **kwargs):
        return self.container.trim(**kwargs)

    @_cluster_modifier()
    def dbscan_cluster(self, **kwargs):
        return self.container.dbscan_cluster(**kwargs)

    @_cluster_modifier()
    def remove_outliers(self, **kwargs):
        return self.container.remove_outliers(**kwargs)

    def update(self, *args, **kwargs):
        _ = self.container.update(*args, **kwargs)
        self.data_changed.emit()
