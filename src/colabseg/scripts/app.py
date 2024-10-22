#!python3
import sys
import pickle
from importlib_resources import files

import vtk
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
    QSplitter,
    QFileDialog,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QGuiApplication, QIcon
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from colabseg import ColabsegData, VolumeViewer
from colabseg.gui import (
    ClusterSelectionTab,
    ParametrizationTab,
    DevTab,
    AnalysisTab,
    BoundingBoxWidget,
    KeybindsDialog,
)


class App(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setup_menu()

        # Adapt to screen size
        screen = QGuiApplication.primaryScreen().geometry()
        width = int(screen.width() * 0.5)
        height = int(screen.height() * 1.0)
        self.resize(width, height)
        self.move((screen.width() - width) // 2, (screen.height() - height) // 2)
        self.setWindowTitle("Colabseg")

        frame = QWidget()
        self.setCentralWidget(frame)

        # Widget and option tab setup
        layout = QVBoxLayout(frame)
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Render Block
        self.vtk_widget = QVTKRenderWindowInteractor(frame)
        self.renderer = vtk.vtkRenderer()
        self.renderer.SetBackground(0.1, 0.1, 0.1)
        self.renderer_next_background = (1.0, 1.0, 1.0)
        self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)

        self.tab_widget = QTabWidget()
        self.tab_widget.resize(1000, 200)
        self.cdata = ColabsegData(self.vtk_widget)

        self.volume_viewer = VolumeViewer(self.vtk_widget)

        splitter.addWidget(self.tab_widget)
        splitter.addWidget(self.vtk_widget)
        splitter.addWidget(self.volume_viewer)
        splitter.setSizes([250, 1200, 50])
        layout.addWidget(splitter)

        # Setup GUI interactions
        self.interactor = self.vtk_widget.GetRenderWindow().GetInteractor()
        self.interactor.Initialize()
        self.interactor.AddObserver("RightButtonPressEvent", self.on_right_click)
        self.interactor.AddObserver("KeyPressEvent", self.on_key_press)

        self.setup_tabs()
        self.actor_collection = vtk.vtkActorCollection()
        self.bounding_box = BoundingBoxWidget(self.renderer, self.interactor)

    def on_key_press(self, obj, event):
        key = obj.GetKeyCode()

        if key in ["x", "c", "z"]:
            self.set_camera_view(key)
        elif key in ["d"]:
            current_color = self.renderer.GetBackground()
            self.renderer.SetBackground(*self.renderer_next_background)
            self.renderer_next_background = current_color
            self.vtk_widget.GetRenderWindow().Render()
        elif key == "\x7f":
            self.cdata.data.remove_cluster()
            self.cdata.data.remove_points()

    def on_right_click(self, obj, event):
        self.cdata.data.deselect()
        self.cdata.models.deselect()

    def set_camera_view(self, view_key):
        camera = self.renderer.GetActiveCamera()
        focal_point = camera.GetFocalPoint()

        distance = 1000
        if self.cdata.shape is not None:
            distance = max(self.cdata.shape) * 2.0

        if view_key == "z":
            view = (0, 1, 0)
            position = focal_point[0], focal_point[1], focal_point[2] + distance
        elif view_key == "c":
            view = (0, 0, 1)
            position = focal_point[0], focal_point[1] + distance, focal_point[2]
        elif view_key == "x":
            view = (0, 1, 0)
            position = focal_point[0] + distance, focal_point[1], focal_point[2]

        camera.SetPosition(*position)
        camera.SetViewUp(*view)
        self.renderer.ResetCamera()
        self.vtk_widget.GetRenderWindow().Render()

    def setup_tabs(self):
        self.tab_widget.addTab(ClusterSelectionTab(self.cdata), "Cluster Selection")
        self.tab_widget.addTab(ParametrizationTab(self.cdata), "Fits")
        self.tab_widget.addTab(AnalysisTab(self.cdata), "Analysis")
        self.tab_widget.addTab(DevTab(self.cdata), "Dev")
        for tab in self.tab_widget.children():
            if isinstance(tab, QWidget):
                tab.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
                )

    def setup_menu(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        help_menu = menu_bar.addMenu("Help")
        toolbar = self.addToolBar("Main")

        open_file_action = QAction("Open", self)
        open_file_action.setShortcut("Ctrl+O")
        open_file_action.triggered.connect(self.open_file)
        save_file_action = QAction("Save", self)
        save_file_action.setShortcut("Ctrl+S")
        save_file_action.triggered.connect(self.save_file)

        self.keybinds_dialog = KeybindsDialog()
        show_keybinds_action = QAction("Keybinds", self)
        show_keybinds_action.setShortcut("Ctrl+H")
        show_keybinds_action.triggered.connect(self.keybinds_dialog.show_keybinds)

        file_menu.addAction(open_file_action)
        file_menu.addAction(save_file_action)
        help_menu.addAction(show_keybinds_action)

        toolbar.addAction(open_file_action)
        toolbar.addAction(save_file_action)
        toolbar.addAction(show_keybinds_action)

    def open_file(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Open File")
        if not file_path:
            return -1

        try:
            self.cdata.open_file(file_path)

        except ValueError as e:
            print(f"Error opening file: {e}")
            return -1

        self.renderer.RemoveAllViewProps()
        self.bounding_box.setup(shape=self.cdata.shape)
        self.renderer.AddActor(self.bounding_box.box_actor)
        self.cdata.data.rendered_actors.clear()
        self.cdata.models.rendered_actors.clear()
        self.cdata.data.render()
        self.cdata.models.render()
        self.renderer.AddViewProp(self.volume_viewer.slice)
        self.set_camera_view("z")

    def save_file(self):
        file_dialog = QFileDialog()
        file_dialog.setDefaultSuffix("pickle")
        file_path, _ = file_dialog.getSaveFileName(
            self, "Save File", "", "Pickle Files (*.pickle)"
        )
        if not file_path:
            return -1

        self.cdata.to_file(file_path)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Colabseg")
    app.setApplicationDisplayName("Colabseg")

    icon = QIcon(str(files("colabseg.data").joinpath("data/logo.png")))
    app.setWindowIcon(icon)

    # Fixes alignment issue in default style
    # https://forum.qt.io/topic/105191/why-isn-t-a-qcombobox-positioned-correctly-in-a-layout/11
    app.setStyle("Fusion")

    window = App()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
