#!python3
""" GUI entrypoint.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""
import os

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import sys
import enum
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
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import (
    QAction,
    QGuiApplication,
    QIcon,
    QCursor,
    QColor,
    QPixmap,
    QPainter,
    QPen,
)
import qtawesome as qta
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from colabseg import ColabsegData, VolumeViewer, ExportManager
from colabseg._gui import (
    ClusterSelectionTab,
    ParametrizationTab,
    DevTab,
    BoundingBoxWidget,
    KeybindsDialog,
)


class Mode(enum.Enum):
    VIEWING = "Viewing"
    SELECTION = "Selection"
    DRAWING = "Drawing"


class CursorModeHandler:
    def __init__(self, widget: QWidget):
        self.widget = widget
        self._current_mode = Mode.VIEWING

        self.cursor_colors = {
            Mode.VIEWING: None,
            Mode.SELECTION: QColor("#2196F3"),
            Mode.DRAWING: QColor("#FFC107"),
        }

        self.cursors = {
            Mode.VIEWING: Qt.CursorShape.ArrowCursor,
            Mode.SELECTION: self._create_custom_cursor(
                self.cursor_colors[Mode.SELECTION]
            ),
            Mode.DRAWING: self._create_custom_cursor(self.cursor_colors[Mode.DRAWING]),
        }

    def _create_custom_cursor(self, color: QColor, size: int = 16) -> QCursor:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(color)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawEllipse(1, 1, size - 2, size - 2)

        pen.setWidth(1)
        painter.setPen(pen)
        center = size // 2
        painter.drawLine(QPoint(center - 3, center), QPoint(center + 3, center))
        painter.drawLine(QPoint(center, center - 3), QPoint(center, center + 3))
        painter.end()

        return QCursor(pixmap, size // 2, size // 2)

    def update_mode(self, mode: Mode):
        self._current_mode = mode
        self.widget.setCursor(self.cursors[mode])

    @property
    def current_mode(self):
        return self._current_mode


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

        # Check how these settings perform
        # self.renderer.GradientBackgroundOff()
        # self.renderer.SetUseDepthPeeling(1)
        # self.renderer.SetOcclusionRatio(0.0)
        # self.renderer.SetMaximumNumberOfPeels(4)

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
        self.cursor_handler = CursorModeHandler(self.vtk_widget)

        self.export_manager = ExportManager(
            self.vtk_widget,
            self.volume_viewer,
            self.tab_widget.findChild(ParametrizationTab),
        )

    def on_key_press(self, obj, event):
        key = obj.GetKeyCode()

        if key in ["x", "c", "z"]:
            self.set_camera_view(key)
        elif key in ["d"]:
            current_color = self.renderer.GetBackground()
            self.renderer.SetBackground(*self.renderer_next_background)
            self.renderer_next_background = current_color
            self.vtk_widget.GetRenderWindow().Render()
        elif key in ["\x7f", "\x08"]:
            self.cdata.data.remove_cluster()
            self.cdata.data.remove_points()
        elif key == "m":
            # In case both clusters and points are selected
            new_cluster = self.cdata.data.merge_cluster()
            point_cluster = self.cdata.data.cluster_points()
            self.cdata.data.merge_cluster(indices=(new_cluster, point_cluster))
        elif key == "h":
            self.cdata.data.toggle_visibility()
        elif key == "a":
            self.cdata.data.toggle_drawing_mode()
            self._transition_modes(Mode.DRAWING)
        elif key == "r":
            self._transition_modes(Mode.SELECTION)

    def on_right_click(self, obj, event):
        self.cdata.data.deselect()
        self.cdata.models.deselect()

    def _transition_modes(self, new_mode):
        current_mode = self.cursor_handler.current_mode

        if current_mode == new_mode:
            return self.cursor_handler.update_mode(Mode.VIEWING)

        if current_mode == Mode.DRAWING:
            self.cdata.data.deactivate_drawing_mode()
        elif current_mode == Mode.SELECTION:
            self.interactor.SetInteractorStyle(vtk.vtkInteractorStyleRubberBandPick())

        return self.cursor_handler.update_mode(new_mode)

    def set_camera_view(self, view_key):
        camera = self.renderer.GetActiveCamera()
        focal_point = camera.GetFocalPoint()

        distance = 1000
        if self.cdata.shape is not None:
            distance = max(self.cdata.shape) * 2.0

        if view_key == "z":
            # view = (0, 0, 0)
            view = (1, 0, 1)
            position = focal_point[0], focal_point[1], focal_point[2] + distance
        elif view_key == "c":
            view = (1, 0, 0)
            position = focal_point[0], focal_point[1] + distance, focal_point[2]
        elif view_key == "x":
            # view = (0, 0, 1)
            view = (0, 1, 0)
            position = focal_point[0] + distance, focal_point[1], focal_point[2]

        camera.SetPosition(*position)
        camera.SetViewUp(*view)
        self.renderer.ResetCamera()
        self.vtk_widget.GetRenderWindow().Render()

    def setup_tabs(self):
        self.tab_widget.addTab(ClusterSelectionTab(self.cdata), "Segmentation")
        self.tab_widget.addTab(ParametrizationTab(self.cdata), "Fits")
        self.tab_widget.addTab(DevTab(self.cdata, self.volume_viewer), "Dev")

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

        open_file_action = QAction(
            qta.icon("fa5s.folder-open", opacity=0.7, color="gray"), "Open File", self
        )
        open_file_action.setShortcut("Ctrl+O")
        open_file_action.triggered.connect(self.open_file)

        save_file_action = QAction(
            qta.icon("fa5s.save", opacity=0.7, color="gray"), "Save Session", self
        )
        save_file_action.setShortcut("Ctrl+S")
        save_file_action.triggered.connect(self.save_file)

        self.keybinds_dialog = KeybindsDialog(self)
        show_keybinds_action = QAction(
            qta.icon("fa5s.keyboard", opacity=0.7, color="gray"), "Keybinds", self
        )
        show_keybinds_action.setShortcut("Ctrl+H")
        show_keybinds_action.triggered.connect(self.keybinds_dialog.show)

        screenshot_action = QAction(
            qta.icon("fa5s.camera", opacity=0.7, color="gray"),
            "Save Viewer Screenshot",
            self,
        )
        screenshot_action.setShortcut("Ctrl+P")
        screenshot_action.triggered.connect(
            lambda x: self.export_manager.save_screenshot()
        )

        animation_action = QAction(
            qta.icon("fa5s.film", opacity=0.7, color="gray"), "Export Animation", self
        )
        animation_action.setShortcut("Ctrl+E")
        animation_action.triggered.connect(
            lambda x: self.export_manager.export_animation()
        )

        clipboard_action = QAction(
            qta.icon("fa5s.clipboard", opacity=0.7, color="gray"),
            "Viewer Screenshot to Clipboard",
            self,
        )
        clipboard_action.setShortcut("Ctrl+Shift+C")
        clipboard_action.triggered.connect(
            lambda x: self.export_manager.copy_screenshot_to_clipboard()
        )
        clipboard_window_action = QAction(
            qta.icon("mdi.monitor-screenshot", opacity=0.7, color="gray"),
            "Window Screenshot to Clipboard",
            self,
        )
        clipboard_window_action.setShortcut("Ctrl+Shift+W")
        clipboard_window_action.triggered.connect(
            lambda x: self.export_manager.copy_screenshot_to_clipboard(window=True)
        )

        file_menu.addAction(open_file_action)
        file_menu.addAction(save_file_action)
        file_menu.addSeparator()
        file_menu.addAction(screenshot_action)
        file_menu.addAction(clipboard_action)
        file_menu.addAction(clipboard_window_action)
        file_menu.addAction(animation_action)

        help_menu.addAction(show_keybinds_action)

        toolbar.addAction(open_file_action)
        toolbar.addAction(save_file_action)
        toolbar.addSeparator()
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
        self.set_camera_view("x")

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
