import vtk


class MeshEditInteractorStyle(vtk.vtkInteractorStyleTrackballCamera):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.cell_picker = vtk.vtkCellPicker()
        self.cell_picker.SetTolerance(0.0005)
        self.point_picker = vtk.vtkPointPicker()
        self.point_picker.SetTolerance(0.0005)

        self.selected_mapper = vtk.vtkDataSetMapper()
        self.selected_actor = vtk.vtkActor()
        self.current_selection = None

        self.add_face_mode = False
        self.selected_points = []
        self.point_markers = []

        self.AddObserver("LeftButtonPressEvent", self.on_left_button_down)
        self.AddObserver("KeyPressEvent", self.on_key_press)

    def toggle_add_face_mode(self):
        self.add_face_mode = not self.add_face_mode
        if not self.add_face_mode:
            self.clear_point_selection()
        print(f"Add face mode: {'ON' if self.add_face_mode else 'OFF'}")

    def on_left_button_down(self, obj, event):
        if self.add_face_mode:
            self.handle_point_selection()
        else:
            self.handle_face_selection()

        self.OnLeftButtonDown()

    def handle_point_selection(self):
        click_pos = self.GetInteractor().GetEventPosition()
        self.point_picker.Pick(click_pos[0], click_pos[1], 0, self.parent.renderer)

        point_id = self.point_picker.GetPointId()
        if point_id != -1:
            picked_actor = self.point_picker.GetActor()
            try:
                print(picked_actor)
                print(self.parent.cdata._models.get_actors())
                geometry_index = self.parent.cdata._models.get_actors().index(
                    picked_actor
                )
            except Exception:
                print("hehexd")
                return None

            geometry = self.parent.cdata.models.container.data[geometry_index]

            if not self.selected_points:
                self.current_geometry = geometry
            elif geometry != self.current_geometry:
                print("Points must be from the same geometry")
                return

            self.selected_points.append(point_id)
            self.add_point_marker(geometry._data.GetPoint(point_id))

            if len(self.selected_points) == 3:
                self.create_new_face()
                self.clear_point_selection()

    def handle_face_selection(self):
        click_pos = self.GetInteractor().GetEventPosition()

        self.cell_picker.Pick(click_pos[0], click_pos[1], 0, self.parent.renderer)
        cell_id = self.cell_picker.GetCellId()

        if cell_id != -1:
            picked_actor = self.cell_picker.GetActor()
            try:
                geometry_index = self.parent.cdata._models.get_actors().index(
                    picked_actor
                )
            except Exception:
                return None

            if geometry_index is not None:
                geometry = self.parent.cdata.models.container.data[geometry_index]

                self.current_selection = {"geometry": geometry, "cell_id": cell_id}

                self.highlight_selected_face(geometry, cell_id)

    def add_point_marker(self, point):
        sphere = vtk.vtkSphereSource()
        sphere.SetCenter(point)
        sphere.SetRadius(0.1)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(sphere.GetOutputPort())

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(0.0, 1.0, 0.0)

        self.point_markers.append(actor)
        self.parent.renderer.AddActor(actor)
        self.parent.vtk_widget.GetRenderWindow().Render()

    def clear_point_selection(self):
        self.selected_points = []
        for actor in self.point_markers:
            self.parent.renderer.RemoveActor(actor)
        self.point_markers = []
        self.parent.vtk_widget.GetRenderWindow().Render()

    def create_new_face(self):
        if not hasattr(self, "current_geometry") or len(self.selected_points) != 3:
            return

        geometry = self.current_geometry

        cell = vtk.vtkTriangle()
        for i, point_id in enumerate(self.selected_points):
            cell.GetPointIds().SetId(i, point_id)

        polys = geometry._data.GetPolys()
        polys.InsertNextCell(cell)
        geometry._data.Modified()

        print(f"Added new face with points: {self.selected_points}")

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

        print("Before deletion:")
        print(f"VTK cells: {geometry._data.GetNumberOfCells()}")
        print(f"VTK points: {geometry._data.GetNumberOfPoints()}")
        print(f"Polys: {geometry._data.GetPolys().GetNumberOfCells()}")
        print(
            f"Verts: {geometry._data.GetVerts().GetNumberOfCells() if geometry._data.GetVerts() else 0}"
        )

        ids = vtk.vtkIdTypeArray()
        ids.SetNumberOfComponents(1)
        ids.InsertNextValue(cell_id)

        selection_node = vtk.vtkSelectionNode()
        selection_node.SetFieldType(vtk.vtkSelectionNode.CELL)
        selection_node.SetContentType(vtk.vtkSelectionNode.INDICES)
        selection_node.SetSelectionList(ids)
        selection_node.GetProperties().Set(vtk.vtkSelectionNode.INVERSE(), 1)

        selection = vtk.vtkSelection()
        selection.AddNode(selection_node)

        extract_selection = vtk.vtkExtractSelection()
        extract_selection.SetInputData(0, geometry._data)
        extract_selection.SetInputData(1, selection)
        extract_selection.Update()

        new_mesh = extract_selection.GetOutput()

        print("\nAfter extraction:")
        print(f"New mesh cells: {new_mesh.GetNumberOfCells()}")
        print(f"New mesh points: {new_mesh.GetNumberOfPoints()}")

        geometry._cells = vtk.vtkCellArray()
        geometry._data.SetVerts(None)
        geometry._data.SetLines(None)
        geometry._data.SetPolys(None)

        cells = vtk.vtkCellArray()
        faces = []

        for i in range(new_mesh.GetNumberOfCells()):
            cell = new_mesh.GetCell(i)
            if cell.GetCellType() == vtk.VTK_TRIANGLE:
                cells.InsertNextCell(cell)
                face = [cell.GetPointId(j) for j in range(3)]
                faces.append(face)

        geometry._data.SetPolys(cells)
        geometry._data.Modified()

        print("\nAfter update:")
        print(f"Final cells: {geometry._data.GetNumberOfCells()}")
        print(f"Final polys: {geometry._data.GetPolys().GetNumberOfCells()}")
        print(f"Faces in meta: {len(faces)}")

        self.parent.renderer.RemoveActor(self.selected_actor)
        self.current_selection = None
        self.parent.vtk_widget.GetRenderWindow().Render()
        self.parent.cdata.models.render_vtk()

    def on_key_press(self, obj, event):
        key = self.GetInteractor().GetKeySym()
        if key == "Delete" or key == "BackSpace":
            self.delete_selected_face()
        elif key == "a":
            self.toggle_add_face_mode()
        elif key == "Escape":
            self.clear_point_selection()
