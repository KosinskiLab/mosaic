import vtk
import numpy as np

from .parametrization import TriangularMesh
from .meshing import to_open3d, merge_meshes


class MeshEditInteractorStyle(vtk.vtkInteractorStyleTrackballCamera):
    def __init__(self, parent, cdata):
        super().__init__()
        self.parent = parent
        self.cdata = cdata
        self.cell_picker = vtk.vtkCellPicker()
        self.point_picker = vtk.vtkPointPicker()

        self.selected_mapper = vtk.vtkDataSetMapper()
        self.selected_actor = vtk.vtkActor()
        self.current_selection = None

        self.add_face_mode = False
        self.selected_points = []

        self.AddObserver("LeftButtonPressEvent", self.on_left_button_down)
        self.AddObserver("KeyPressEvent", self.on_key_press)

    def toggle_add_face_mode(self):
        self.add_face_mode = not self.add_face_mode
        if not self.add_face_mode:
            self.clear_point_selection()

    def on_left_button_down(self, obj, event):
        if self.add_face_mode:
            self.handle_point_selection()
        else:
            self.handle_face_selection()

        self.OnLeftButtonDown()

    def _get_actor_index(self, actor, container="cluster"):
        # We use this order to promote extending existing meshes
        data = self.cdata._models
        if container == "cluster":
            data = self.cdata._data

        try:
            index = data.get_actors().index(actor)
        except Exception:
            index = None
        finally:
            return index

    def _get_data_from_actor(self, actor):
        index = self._get_actor_index(actor, "model")
        if index is not None:
            return self.cdata._models.data[index], index
        index = self._get_actor_index(actor, "cluster")
        if index is not None:
            return self.cdata._data.data[index], index
        return None

    def _selection_to_geometry(self):
        unique_geometries = {}
        for geometry, point_id in self.selected_points:
            _, index = self._get_data_from_actor(geometry._actor)
            if index not in unique_geometries:
                unique_geometries[index] = [geometry, []]
            unique_geometries[index][1].append(point_id)
        return unique_geometries

    def _highlight_selected_points(self):
        if len(self.selected_points) == 0:
            return None

        unique_geometries = self._selection_to_geometry()
        for geometry, point_ids in unique_geometries.values():
            geometry.color_points(
                point_ids, geometry._appearance.get("highlight_color", (0.7, 0.7, 0.7))
            )
        return None

    def handle_point_selection(self):
        click_pos = self.GetInteractor().GetEventPosition()
        self.point_picker.Pick(click_pos[0], click_pos[1], 0, self.parent.renderer)

        point_id = self.point_picker.GetPointId()
        if point_id == -1:
            return None

        picked_actor = self.point_picker.GetActor()
        geometry, _ = self._get_data_from_actor(picked_actor)
        if geometry is None:
            return None

        self.selected_points.append((geometry, point_id))
        self._highlight_selected_points()

        if len(self.selected_points) == 3:
            self.create_new_face()
            self.clear_point_selection()

    def handle_face_selection(self):
        click_pos = self.GetInteractor().GetEventPosition()

        self.cell_picker.Pick(click_pos[0], click_pos[1], 0, self.parent.renderer)
        cell_id = self.cell_picker.GetCellId()
        if cell_id == -1:
            return None

        picked_actor = self.cell_picker.GetActor()
        geometry, _ = self._get_data_from_actor(picked_actor)
        if geometry is None:
            return None

        self.current_selection = {"geometry": geometry, "cell_id": cell_id}
        self.highlight_selected_face(geometry, cell_id)

    def clear_point_selection(self):
        return self.selected_points.clear()

    def create_new_face(self):
        unique_geometries = self._selection_to_geometry()

        points, meshes = [], []
        for index, (geometry, point_ids) in unique_geometries.items():
            geometry.color_points(
                point_ids, geometry._appearance.get("base_color", (0.7, 0.7, 0.7))
            )
            points.append(geometry.points[point_ids])
            fit = geometry._meta.get("fit", None)
            if hasattr(fit, "mesh"):
                meshes.append((fit.mesh, index))

        vertices = np.concatenate(points).reshape(-1, 3)
        faces = np.arange(vertices.size).reshape(-1, 3)
        meshes.append((to_open3d(vertices, faces), None))

        vertices, faces = merge_meshes(
            vertices=[np.asarray(x.vertices) for (x, _) in meshes],
            faces=[np.asarray(x.triangles) for (x, _) in meshes],
        )
        fit = TriangularMesh(to_open3d(vertices, faces))

        self.cdata._add_fit(
            fit=fit,
            points=np.asarray(fit.mesh.vertices),
            sampling_rate=1,
        )
        self.cdata._models.remove([index for (_, index) in meshes])
        self.cdata.models.data_changed.emit()

        self.cdata.models.render()

    def highlight_selected_face(self, geometry, cell_id):
        ids = vtk.vtkIdTypeArray()
        ids.SetNumberOfComponents(1)
        ids.InsertNextValue(cell_id)

        selection_node = vtk.vtkSelectionNode()
        selection_node.SetFieldType(vtk.vtkSelectionNode.CELL)
        selection_node.SetContentType(vtk.vtkSelectionNode.INDICES)
        selection_node.SetSelectionList(ids)

        selection = vtk.vtkSelection()
        selection.AddNode(selection_node)

        extract_selection = vtk.vtkExtractSelection()
        extract_selection.SetInputData(0, geometry._data)
        extract_selection.SetInputData(1, selection)
        extract_selection.Update()

        selected = vtk.vtkUnstructuredGrid()
        selected.ShallowCopy(extract_selection.GetOutput())

        self.selected_mapper.SetInputData(selected)
        self.selected_actor.SetMapper(self.selected_mapper)
        self.selected_actor.GetProperty().EdgeVisibilityOn()
        self.selected_actor.GetProperty().SetColor(1.0, 0.0, 0.0)
        self.selected_actor.GetProperty().SetLineWidth(3)

        self.parent.renderer.AddActor(self.selected_actor)
        self.parent.vtk_widget.GetRenderWindow().Render()

    def delete_selected_face(self):
        if not self.current_selection:
            return

        geometry = self.current_selection["geometry"]
        cell_id = self.current_selection["cell_id"]

        cells = geometry._data.GetPolys()
        new_cells = vtk.vtkCellArray()

        cells.InitTraversal()
        idList = vtk.vtkIdList()
        current_id = 0
        while cells.GetNextCell(idList):
            if current_id != cell_id:
                new_cells.InsertNextCell(idList)
            current_id += 1

        geometry._data.SetPolys(new_cells)
        geometry._data.Modified()

        self.parent.renderer.RemoveActor(self.selected_actor)
        self.current_selection = None
        self.parent.vtk_widget.GetRenderWindow().Render()
        self.cdata.models.render_vtk()

    def on_key_press(self, obj, event):
        key = self.GetInteractor().GetKeySym()
        if key == "Delete" or key == "BackSpace":
            self.delete_selected_face()
        elif key == "a":
            self.toggle_add_face_mode()
        elif key == "Escape":
            self.clear_point_selection()
