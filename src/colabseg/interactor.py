import vtk
from functools import wraps
from PyQt6.QtWidgets import QListWidget, QListWidgetItem
from PyQt6.QtCore import Qt, QObject, QItemSelection, QItemSelectionModel
from PyQt6.QtCore import pyqtSignal


def _cluster_modifier(func):
    @wraps(func)
    def wrapper(self, **kwargs):
        indices = self._get_selected_indices()
        result = func(self, indices=indices, **kwargs)
        self.data_changed.emit()
        self.render()
        return result

    return wrapper


class LinkedDataContainerInteractor(QObject):
    selectionChanged = pyqtSignal()

    def __init__(self, interactor):
        super().__init__()
        self.interactor = interactor

        self.data_list = QListWidget()
        self.data_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.data_list.itemSelectionChanged.connect(self._on_cluster_selection_changed)

        self._update_list()

        self.interactor.data_changed.connect(self._update_list)

    def _update_list(self):
        self.data_list.clear()
        for i in range(self.interactor.data_container.get_cluster_count()):
            self.data_list.addItem(f"{self.interactor.prefix} {i}")

    def _on_cluster_selection_changed(self):
        selected_indices = self._get_selected_indices()
        self.set_selection(selected_indices)
        self.selectionChanged.emit()

    def set_selection(self, selected_indices):
        selection = QItemSelection()
        for index in selected_indices:
            index = self.interactor.data_list.model().index(index, 0)
            selection.select(index, index)

        selection_model_flag = QItemSelectionModel.SelectionFlag
        self.interactor.data_list.selectionModel().select(
            selection, selection_model_flag.Clear | selection_model_flag.Select
        )
        self.interactor.vtk_widget.GetRenderWindow().Render()

    def _get_selected_indices(self):
        return [item.row() for item in self.data_list.selectedIndexes()]

    def deselect(self):
        self.data_list.clearSelection()

    def __getattr__(self, name):
        return getattr(self.interactor, name)


class DataContainerInteractor(QObject):
    data_changed = pyqtSignal()

    def __init__(self, data_container, vtk_widget, prefix="Cluster"):
        super().__init__()
        self.prefix = prefix
        self.point_selection, self.rendered_actors = {}, set()
        self.vtk_widget, self.data_container = vtk_widget, data_container

        # Interaction element for the GUI
        self.data_list = QListWidget()
        self.data_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.data_list.itemSelectionChanged.connect(self._on_cluster_selection_changed)

        # We assume its already initialized
        self.interactor = self.vtk_widget.GetRenderWindow().GetInteractor()
        self.area_picker = vtk.vtkAreaPicker()
        style = vtk.vtkInteractorStyleRubberBandPick()

        self.interactor.SetPicker(self.area_picker)
        self.interactor.SetInteractorStyle(style)
        self.area_picker.AddObserver("EndPickEvent", self._on_area_pick)

    def _on_cluster_selection_changed(self):
        selected_indices = set(self._get_selected_indices())
        self.data_container.highlight(selected_indices)
        self.vtk_widget.GetRenderWindow().Render()

    def _on_cutoff_changed(self, cutoff_value):
        cluster_sizes = self.data_container.get_cluster_size()
        selection = QItemSelection()

        for i in range(self.data_container.get_cluster_count()):
            if cluster_sizes[i] < cutoff_value:
                index = self.data_list.model().index(i, 0)
                selection.select(index, index)

        self.data_list.selectionModel().select(
            selection, QItemSelectionModel.SelectionFlag.ClearAndSelect
        )

    def _on_area_pick(self, obj, event):
        frustum = obj.GetFrustum()
        self.deselect_points()
        for i, cluster in enumerate(self.data_container.data):
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

    def _get_selected_indices(self):
        return [item.row() for item in self.data_list.selectedIndexes()]

    def remove_points(self):
        added_cluster = self.data_container.add_selection(self.point_selection)
        self.deselect_points()
        self.data_container.remove(added_cluster)
        self.render()

    def cluster_points(self):
        ret = self.data_container.add_selection(self.point_selection)
        self.render()
        return ret

    def render(self):
        renderer = self.vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer()

        current_actors = set(self.data_container.get_actors())
        actors_to_remove = self.rendered_actors - current_actors
        for actor in actors_to_remove:
            renderer.RemoveActor(actor)
            self.rendered_actors.remove(actor)

        actors_to_add = current_actors - self.rendered_actors
        for actor in actors_to_add:
            renderer.AddActor(actor)
            self.rendered_actors.add(actor)

        self.data_list.clear()
        for i in range(self.data_container.get_cluster_count()):
            self.data_list.addItem(f"{self.prefix} {i}")

        self.vtk_widget.GetRenderWindow().Render()

    def deselect(self):
        self.data_list.clearSelection()
        self.deselect_points()

    def deselect_points(self):
        self.highlight_selected_points(color=(0.7, 0.7, 0.7))
        self.point_selection.clear()

    def highlight_selected_points(self, color):
        for cluster_index, point_ids in self.point_selection.items():
            self.data_container.highlight_points(cluster_index, point_ids, color)
        self.vtk_widget.GetRenderWindow().Render()

    @_cluster_modifier
    def toggle_visibility(self, **kwargs):
        return self.data_container.toggle_visibility(**kwargs)

    @_cluster_modifier
    def merge_cluster(self, **kwargs):
        return self.data_container.merge(**kwargs)

    @_cluster_modifier
    def remove_cluster(self, **kwargs):
        return self.data_container.remove(**kwargs)

    @_cluster_modifier
    def split_cluster(self, **kwargs):
        return self.data_container.split(**kwargs)

    @_cluster_modifier
    def sample_cluster(self, **kwargs):
        return self.data_container.sample(**kwargs)

    @_cluster_modifier
    def crop_cluster(self, **kwargs):
        return self.data_container.crop(**kwargs)

    @_cluster_modifier
    def trim(self, **kwargs):
        return self.data_container.trim(**kwargs)

    @_cluster_modifier
    def dbscan_cluster(self, **kwargs):
        return self.data_container.dbscan_cluster(**kwargs)

    @_cluster_modifier
    def remove_outliers(self, **kwargs):
        return self.data_container.remove_outliers(**kwargs)

    def update(self, *args, **kwargs):
        _ = self.data_container.update(*args, **kwargs)
        self.data_changed.emit()
