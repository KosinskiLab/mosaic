""" Style classes facilitating unique interactions with the vtk viewer.

    Copyright (c) 2025 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import vtk
import numpy as np

from .parametrization import TriangularMesh
from .meshing import to_open3d, merge_meshes


class MeshEditInteractorStyle(vtk.vtkInteractorStyleTrackballCamera):
    def __init__(self, parent, cdata):
        super().__init__()
        self.parent = parent
        self.cdata = cdata

        self.selected_actor = vtk.vtkActor()
        self.cell_picker = vtk.vtkCellPicker()
        self.point_picker = vtk.vtkPointPicker()
        self.selected_mapper = vtk.vtkDataSetMapper()

        self.is_dragging = False
        self.selected_faces = []
        self.selected_points = []
        self.add_face_mode = False
        self.current_selection = None
        self.last_picked_actor = None

        self.AddObserver("KeyPressEvent", self.on_key_press)
        self.AddObserver("MouseMoveEvent", self.on_mouse_move)
        self.AddObserver("LeftButtonPressEvent", self.on_left_button_down)
        self.AddObserver("LeftButtonReleaseEvent", self.on_left_button_up)

    def cleanup(self):
        self.is_dragging = False
        self.clear_point_selection()
        self.clear_face_selection()

        if self.selected_actor is not None:
            self.parent.renderer.RemoveActor(self.selected_actor)
        return self.cdata.models.render_vtk()

    def clear_face_selection(self):
        self.selected_faces = []
        self.current_selection = None
        self.last_picked_actor = None

    def clear_point_selection(self):
        return self.selected_points.clear()

    def toggle_add_face_mode(self):
        self.add_face_mode = not self.add_face_mode
        if not self.add_face_mode:
            self.clear_point_selection()

    def on_left_button_down(self, obj, event):
        if self.add_face_mode:
            self.handle_point_selection()
        else:
            self.clear_face_selection()
            self.handle_face_selection()
            self.is_dragging = True

        if not self.is_dragging:
            self.OnLeftButtonDown()

    def on_left_button_up(self, obj, event):
        self.is_dragging = False
        self.OnLeftButtonUp()

    def on_mouse_move(self, obj, event):
        if self.is_dragging:
            return self.handle_face_selection()
        self.OnMouseMove()

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
        return None, None

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

        selection = {"geometry": geometry, "cell_id": cell_id}
        if self.last_picked_actor != picked_actor:
            self.last_picked_actor = picked_actor
        if selection not in self.selected_faces:
            self.selected_faces.append(selection)
            self.current_selection = selection

        self.highlight_selected_faces()

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

    def highlight_selected_faces(self):
        if not self.selected_faces:
            return

        ids = vtk.vtkIdTypeArray()
        ids.SetNumberOfComponents(1)

        for selection in self.selected_faces:
            ids.InsertNextValue(selection["cell_id"])

        selection_node = vtk.vtkSelectionNode()
        selection_node.SetFieldType(vtk.vtkSelectionNode.CELL)
        selection_node.SetContentType(vtk.vtkSelectionNode.INDICES)
        selection_node.SetSelectionList(ids)

        selection = vtk.vtkSelection()
        selection.AddNode(selection_node)

        # Use the geometry from the last selected face
        geometry = self.selected_faces[-1]["geometry"]

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

    def delete_selected_faces(self):
        if not self.selected_faces:
            return

        geometry = self.selected_faces[0]["geometry"]

        cell_ids_to_delete = set()
        for selection in self.selected_faces:
            cell_id = (
                selection["cell_id"] - geometry._data.GetVerts().GetNumberOfCells()
            )
            if cell_id >= 0:
                cell_ids_to_delete.add(cell_id)

        new_cells = vtk.vtkCellArray()
        cells = geometry._data.GetPolys()

        cells.InitTraversal()
        current_id, id_list = 0, vtk.vtkIdList()
        while cells.GetNextCell(id_list):
            if current_id not in cell_ids_to_delete:
                new_cells.InsertNextCell(id_list)
            current_id += 1

        geometry._data.SetPolys(new_cells)
        geometry._data.Modified()

        faces = vtk.util.numpy_support.vtk_to_numpy(new_cells.GetConnectivityArray())
        mesh = to_open3d(geometry.points, faces.reshape(-1, 3))
        geometry._meta.update({"fit": TriangularMesh(mesh)})

        return self.cleanup()

    def on_key_press(self, obj, event):
        key = self.GetInteractor().GetKeySym().lower()
        if key in ["return", "enter", "delete", "backspace"]:
            self.delete_selected_faces()
        return self.OnKeyPress()


class CurveBuilderInteractorStyle(vtk.vtkInteractorStyleRubberBandPick):
    """VTK interactor style for building spline curves."""

    def __init__(self, parent, cdata):
        """Initialize the interactor style.

        Args:
            parent: Parent widget containing the VTK widget
            cdata: Data container object
        """
        super().__init__()
        self.parent = parent
        self.cdata = cdata

        self.points = []
        self.actors = []
        self.selected_actor = None
        self.current_connection = None
        self._base_size = 8

        self.prop_picker = vtk.vtkPropPicker()
        self.world_picker = vtk.vtkWorldPointPicker()

        self.renderer = self.parent.renderer
        self.AddObserver("LeftButtonPressEvent", self.on_left_button_down)
        self.AddObserver("MouseMoveEvent", self.on_mouse_move)
        self.AddObserver("LeftButtonReleaseEvent", self.on_left_button_release)
        self.AddObserver("KeyPressEvent", self.on_key_press)

    def _event_to_worldposition(self, position):
        event_position = (position[0], position[1], 0)
        r = self.parent.vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer()
        self.world_picker.Pick(*event_position, r)
        world_position = self.world_picker.GetPickPosition()

        camera = r.GetActiveCamera()
        camera_plane = vtk.vtkPlane()
        camera_plane.SetNormal(camera.GetDirectionOfProjection())
        camera_plane.SetOrigin(world_position)

        t = vtk.mutable(0.0)
        x = [0, 0, 0]
        camera_plane.IntersectWithLine(camera.GetPosition(), world_position, t, x)
        return x

    def on_left_button_down(self, obj, event):
        """Handle left button press events"""
        event_position = [*self.GetInteractor().GetEventPosition(), 0]

        self.prop_picker.Pick(*event_position, self.renderer)
        picked_actor = self.prop_picker.GetActor()

        world_position = self._event_to_worldposition(event_position)

        func = self._handle_spline_interaction
        if picked_actor in self.actors:
            self.selected_actor = picked_actor
            func = self._update_point_position

        func(position=world_position, actor=picked_actor)
        return self.OnLeftButtonDown()

    def on_left_button_release(self, obj, event):
        self.selected_actor = None
        return self.OnLeftButtonUp()

    def on_mouse_move(self, obj, event):
        """Handle mouse move events"""
        if self.selected_actor is None:
            return self.OnMouseMove()

        click_pos = [*self.GetInteractor().GetEventPosition(), 0]
        world_position = self._event_to_worldposition(click_pos)
        return self._update_point_position(position=world_position)

    def cleanup(self):
        """Remove all temporary visualization actors"""
        for actor in self.actors:
            self.renderer.RemoveActor(actor)
        if self.current_connection:
            self.renderer.RemoveActor(self.current_connection)

        self.points.clear()
        self.actors.clear()
        self.selected_actor = None
        self.current_connection = None
        self.parent.vtk_widget.GetRenderWindow().Render()

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

    def _handle_spline_interaction(self, position, actor):
        """Handle spline interaction events"""
        try:
            index = self.cdata.data.container._get_cluster_index(actor)
        except Exception:
            index = None

        if index is not None:
            point_locator = vtk.vtkPointLocator()
            point_locator.SetDataSet(actor.GetMapper().GetInput())
            point_locator.BuildLocator()

            closest_point_id = point_locator.FindClosestPoint(position)
            closest_point = (
                actor.GetMapper().GetInput().GetPoints().GetPoint(closest_point_id)
            )
            position = closest_point

        self.points.append(position)

        actor = self._create_point_actor(position)
        self.actors.append(actor)
        self.renderer.AddActor(actor)
        self._update_visualization()

    def _update_point_position(self, position, **kwargs):
        """Update the position of a control point"""
        try:
            index = self.actors.index(self.selected_actor)
        except ValueError:
            return None

        self.points[index] = np.array(position)
        point_data = self.selected_actor.GetMapper().GetInput().GetPoints()
        point_data.SetPoint(0, position)
        point_data.Modified()
        self._update_visualization()

    def _update_visualization(self):
        """Update the spline visualization"""
        if len(self.points) < 2:
            return None

        if self.current_connection:
            self.renderer.RemoveActor(self.current_connection)

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

        self.current_connection = vtk.vtkActor()
        self.current_connection.SetMapper(mapper)
        self.current_connection.GetProperty().SetColor(1, 1, 0)
        self.renderer.AddActor(self.current_connection)
        self.parent.vtk_widget.GetRenderWindow().Render()

    def _add_points_to_cluster(self):
        """Create the final spline parametrization"""
        self.cdata._data.add(points=self.points)
        self.cdata.data.data_changed.emit()
        return self.cdata.data.render()

    def on_key_press(self, obj, event):
        key = self.GetInteractor().GetKeySym().lower()
        if key in ["return", "enter", "delete"]:
            self._add_points_to_cluster()
            self.cleanup()

        return self.OnKeyPress()
