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

    def cleanup(self):
        if self.selected_actor is None:
            return None

        self.parent.renderer.RemoveActor(self.selected_actor)
        return self.cdata.models.render_vtk()

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

    def _get_actor_index(self, actor, container="model"):
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

        if point_id > geometry.points.shape[0]:
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

        sampling, appearance, points, meshes = 1, {}, [], []
        for index, (geometry, point_ids) in unique_geometries.items():
            geometry.color_points(
                point_ids, geometry._appearance.get("base_color", (0.7, 0.7, 0.7))
            )
            points.append(geometry.points[point_ids].copy())
            fit = geometry._meta.get("fit", None)
            if hasattr(fit, "mesh"):
                meshes.append((fit.mesh, index))
                sampling = geometry._sampling_rate
                appearance.update(geometry._appearance)

        shape = (-1, 3)
        vertices = np.concatenate(points).reshape(*shape)
        faces = np.arange(vertices.size // shape[1]).reshape(*shape)
        meshes.append((to_open3d(vertices, faces), None))

        vertices, faces = merge_meshes(
            vertices=[np.asarray(x.vertices) for (x, _) in meshes],
            faces=[np.asarray(x.triangles) for (x, _) in meshes],
        )

        fit = TriangularMesh(to_open3d(vertices, faces))
        index = self.cdata._add_fit(fit=fit, points=vertices, sampling_rate=sampling)
        if self.cdata._models._index_ok(index):
            geometry = self.cdata._models.data[index]
            geometry.change_representation("mesh")
            geometry.set_appearance(**appearance)

        self.cdata._models.remove([index for (_, index) in meshes])
        self.cdata.models.data_changed.emit()
        return self.cdata.models.render()

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
        self.selected_mapper.SetScalarVisibility(False)
        self.selected_mapper.SetResolveCoincidentTopology(True)
        self.selected_mapper.SetRelativeCoincidentTopologyLineOffsetParameters(0, -1)
        self.selected_mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(0, -1)
        self.selected_mapper.SetRelativeCoincidentTopologyPointOffsetParameter(0)

        self.selected_actor.SetMapper(self.selected_mapper)
        self.selected_actor.ForceOpaqueOn()
        self.selected_actor.SetPickable(False)

        prop = self.selected_actor.GetProperty()
        prop.SetOpacity(0.3)
        prop.SetAmbient(1.0)
        prop.SetDiffuse(0.0)
        prop.SetLineWidth(2)
        prop.EdgeVisibilityOn()
        prop.SetColor(0.388, 0.400, 0.945)

        self.parent.renderer.AddActor(self.selected_actor)
        self.parent.vtk_widget.GetRenderWindow().Render()

    def delete_selected_face(self):
        if not self.current_selection:
            return

        geometry = self.current_selection["geometry"]
        cell_id = self.current_selection["cell_id"]
        cell_id = cell_id - geometry._data.GetVerts().GetNumberOfCells()

        if cell_id < 0:
            return None

        new_cells = vtk.vtkCellArray()
        cells = geometry._data.GetPolys()

        cells.InitTraversal()
        current_id, id_list = 0, vtk.vtkIdList()
        while cells.GetNextCell(id_list):
            if current_id != cell_id:
                new_cells.InsertNextCell(id_list)
            current_id += 1

        geometry._data.SetPolys(new_cells)
        geometry._data.Modified()

        faces = vtk.util.numpy_support.vtk_to_numpy(new_cells.GetConnectivityArray())
        geometry._meta["faces"] = faces.reshape(-1, 3)
        geometry._meta["fit"] = TriangularMesh(
            to_open3d(geometry._meta["points"], geometry._meta["faces"])
        )

        self.current_selection = None
        self.parent.renderer.RemoveActor(self.selected_actor)
        self.cdata.models.render_vtk()

    def on_key_press(self, obj, event):
        key = self.GetInteractor().GetKeySym()
        if key == "Delete" or key == "BackSpace":
            self.delete_selected_face()
        elif key == "a":
            self.toggle_add_face_mode()
        elif key == "Escape":
            self.clear_point_selection()


class CurveBuilderInteractorStyle(vtk.vtkInteractorStyleTrackballCamera):
    def __init__(self, parent, cdata):
        super().__init__()
        self.parent = parent
        self.cdata = cdata

        # Picking tools
        self.point_picker = vtk.vtkPointPicker()
        self.prop_picker = vtk.vtkPropPicker()

        # State management
        self.points = []
        self.point_actors = []
        self.selected_point_actor = None
        self.spline_actor = None
        self._base_size = 8

        # Add observers
        self.AddObserver("LeftButtonPressEvent", self.on_left_button_down)
        self.AddObserver("MouseMoveEvent", self.on_mouse_move)
        self.AddObserver("LeftButtonReleaseEvent", self.on_left_button_up)

    def cleanup(self):
        """Remove all temporary visualization actors"""
        for actor in self.point_actors:
            self.parent.renderer.RemoveActor(actor)
        if self.spline_actor:
            self.parent.renderer.RemoveActor(self.spline_actor)
        self.reset()
        self.parent.vtk_widget.GetRenderWindow().Render()

    def reset(self):
        """Reset the spline state"""
        self.points = []
        self.point_actors = []
        self.selected_point_actor = None
        self.spline_actor = None

    def _create_point_actor(self, position):
        """Create a VTK actor for a control point"""
        point_data = vtk.vtkPoints()
        point_data.InsertNextPoint(position)

        vertices = vtk.vtkCellArray()
        vertices.InsertNextCell(1)
        vertices.InsertCellPoint(0)

        poly_data = vtk.vtkPolyData()
        poly_data.SetPoints(point_data)
        poly_data.SetVerts(vertices)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(poly_data)
        mapper.SetResolveCoincidentTopologyToPolygonOffset()

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(0, 1, 1)
        actor.GetProperty().SetPointSize(self._base_size)
        actor.GetProperty().SetRenderPointsAsSpheres(True)

        return actor

    def add_point(self, position, is_boundary=False):
        """Add a control point to the spline"""
        position = np.array(position)
        self.points.append(position)

        actor = self._create_point_actor(position)
        self.point_actors.append(actor)
        self.parent.renderer.AddActor(actor)
        self._update_spline_visualization()

    def update_point_position(self, actor, new_position):
        """Update the position of a control point"""
        try:
            index = self.point_actors.index(actor)
        except ValueError:
            return None

        self.points[index] = np.array(new_position)
        point_data = actor.GetMapper().GetInput().GetPoints()
        point_data.SetPoint(0, new_position)
        point_data.Modified()
        self._update_spline_visualization()

    def _update_spline_visualization(self):
        """Update the spline visualization"""
        if len(self.points) < 2:
            if self.spline_actor:
                self.parent.renderer.RemoveActor(self.spline_actor)
                self.spline_actor = None
            return

        if self.spline_actor:
            self.parent.renderer.RemoveActor(self.spline_actor)

        vtkPoints = vtk.vtkPoints()
        for point in self.points:
            vtkPoints.InsertNextPoint(point)

        spline = vtk.vtkParametricSpline()
        spline.SetPoints(vtkPoints)
        spline.SetParameterizeByLength(1)
        spline.SetClosed(0)

        curve_source = vtk.vtkParametricFunctionSource()
        curve_source.SetParametricFunction(spline)
        curve_source.SetUResolution(200)
        curve_source.Update()

        tube_filter = vtk.vtkTubeFilter()
        tube_filter.SetInputConnection(curve_source.GetOutputPort())
        tube_filter.SetRadius(self._base_size * 0.05)
        tube_filter.SetNumberOfSides(8)
        tube_filter.SetVaryRadiusToVaryRadiusOff()
        tube_filter.Update()

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(tube_filter.GetOutputPort())
        mapper.SetResolveCoincidentTopologyToPolygonOffset()
        mapper.SetScalarVisibility(False)

        self.spline_actor = vtk.vtkActor()
        self.spline_actor.SetMapper(mapper)
        self.spline_actor.GetProperty().SetColor(1, 1, 0)
        self.parent.renderer.AddActor(self.spline_actor)
        self.parent.vtk_widget.GetRenderWindow().Render()

    def on_left_button_down(self, obj, event):
        """Handle left button click events"""
        click_pos = self.GetInteractor().GetEventPosition()

        self.prop_picker.Pick(click_pos[0], click_pos[1], 0, self.parent.renderer)
        picked_actor = self.prop_picker.GetActor()

        if picked_actor in self.point_actors:
            self.selected_point_actor = picked_actor
            return

        self.point_picker.Pick(click_pos[0], click_pos[1], 0, self.parent.renderer)
        position = self.point_picker.GetPickPosition()

        picked_actor = self.point_picker.GetActor()
        if picked_actor:
            index = self.cdata.data.container._get_cluster_index(picked_actor)
            if index is not None:
                point_locator = vtk.vtkPointLocator()
                point_locator.SetDataSet(picked_actor.GetMapper().GetInput())
                point_locator.BuildLocator()

                closest_point_id = point_locator.FindClosestPoint(position)
                position = (
                    picked_actor.GetMapper()
                    .GetInput()
                    .GetPoints()
                    .GetPoint(closest_point_id)
                )

        self.add_point(position, index is not None)
        self.OnLeftButtonDown()

    def on_mouse_move(self, obj, event):
        """Handle mouse movement for dragging points"""
        if not self.selected_point_actor:
            return self.OnMouseMove()

        # When dragging a point, don't allow camera movement
        button = self.GetInteractor().GetEventPosition()
        self.point_picker.Pick(button[0], button[1], 0, self.parent.renderer)
        position = self.point_picker.GetPickPosition()

        self.update_point_position(self.selected_point_actor, position)

    def on_left_button_up(self, obj, event):
        """Handle left button release"""
        self.selected_point_actor = None
        self.OnLeftButtonUp()

    def create_spline_parametrization(self):
        """Create the final spline parametrization"""
        if len(self.points) < 2:
            return

        from ..parametrization import SplineCurve

        spline_param = SplineCurve(self.points)
        meta = {
            "fit": spline_param,
            "points": self.points,
            "normals": spline_param.compute_normal(self.points),
        }

        self.cdata._models.add(
            points=meta["points"],
            normals=meta["normals"],
            meta=meta,
            sampling_rate=1.0,
        )

        self.cdata.models.data_changed.emit()
        self.cleanup()
        self.cdata.models.render()
