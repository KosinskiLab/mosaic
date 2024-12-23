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
import numpy as np
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
    QSplitter,
    QFileDialog,
    QMenu,
    QHBoxLayout,
    QPushButton,
    QDockWidget,
)
from PyQt6.QtCore import Qt, QPoint, QEvent
from PyQt6.QtGui import (
    QAction,
    QGuiApplication,
    QIcon,
    QCursor,
    QColor,
    QPixmap,
    QPainter,
    QPen,
    QActionGroup,
)
import qtawesome as qta
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from colabseg import ColabsegData, ExportManager
from colabseg.tabs.segmentation_tab import SegmentationTab
from colabseg.tabs.development_tab import DevelopmentTab
from colabseg.tabs.model_tab import ModelTab

from colabseg.dialogs.import_data import ImportDataDialog
from colabseg.io_utils import import_points
from colabseg.dialogs import TiltControlDialog, KeybindsDialog
from colabseg.widgets import MultiVolumeViewer, BoundingBoxWidget, AxesWidget
from colabseg.widgets.ribbon import RibbonToolBar
from colabseg.widgets.trajectory_player import TrajectoryPlayer


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

        # Adapt to screen size
        screen = QGuiApplication.primaryScreen().geometry()
        width = int(screen.width() * 0.7)
        height = int(screen.height() * 0.9)
        self.resize(width, height)
        self.move((screen.width() - width) // 2, (screen.height() - height) // 2)
        self.setWindowTitle("Colabseg")

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Render Block
        self.vtk_widget = QVTKRenderWindowInteractor()
        self.renderer = vtk.vtkRenderer()
        self.renderer.SetBackground(0.1, 0.1, 0.1)
        self.renderer_next_background = (1.0, 1.0, 1.0)

        # Check how these settings perform
        self.renderer.GradientBackgroundOff()
        self.renderer.SetUseDepthPeeling(1)
        self.renderer.SetOcclusionRatio(0.0)
        self.renderer.SetMaximumNumberOfPeels(4)
        self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)

        # Setup GUI interactions
        self.interactor = self.vtk_widget.GetRenderWindow().GetInteractor()
        self.interactor.Initialize()
        self.interactor.AddObserver("RightButtonPressEvent", self.on_right_click)
        self.interactor.AddObserver("KeyPressEvent", self.on_key_press)

        self.cdata = ColabsegData(self.vtk_widget)
        self.volume_dock = None
        self.volume_viewer = MultiVolumeViewer(self.vtk_widget)

        self.tab_bar = QWidget()
        self.tab_bar.setFixedHeight(40)
        self.tab_bar.setStyleSheet(
            """
            QWidget {
                border-bottom: 1px solid #6b7280;
            }
        """
        )
        tab_layout = QHBoxLayout(self.tab_bar)
        tab_layout.setContentsMargins(16, 0, 16, 0)
        tab_layout.setSpacing(4)

        self.tab_buttons = {}
        self.tab_ribbon = RibbonToolBar(self)
        self.tabs = [
            (SegmentationTab(self.cdata, self.tab_ribbon), "Segmentation"),
            (ModelTab(self.cdata, self.tab_ribbon), "Parametrization"),
            (DevelopmentTab(self.cdata, self.tab_ribbon), "Development"),
        ]
        for index, (tab, name) in enumerate(self.tabs):
            btn = QPushButton(name)
            btn.setProperty("tab_id", index)
            btn.setCheckable(True)
            btn.clicked.connect(self.on_tab_clicked)
            btn.setStyleSheet(
                """
                QPushButton {
                    border: none;
                    border-bottom: 2px solid transparent;
                    padding: 12px 24px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    color: #374151;
                }
                QPushButton:checked {
                    color: #2563eb;
                    border-bottom: 2px solid #2563eb;
                }
            """
            )
            tab_layout.addWidget(btn)
            self.tab_buttons[index] = btn
        tab_layout.addStretch()
        self.tab_buttons[0].setChecked(True)
        self.tabs[0][0].show_ribbon()

        layout.addWidget(self.tab_bar)
        layout.addWidget(self.tab_ribbon)

        lists_widget = QWidget()
        lists_widget.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        lists_layout = QVBoxLayout(lists_widget)
        lists_layout.setContentsMargins(0, 0, 0, 0)
        lists_layout.setSpacing(0)
        lists_widget.setMinimumWidth(150)

        lists_layout.addWidget(self.cdata.data.data_list)
        lists_layout.addWidget(self.cdata.models.data_list)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(lists_widget)
        splitter.addWidget(self.vtk_widget)
        splitter.setSizes([150, self.width() - 150])

        # v_splitter = QSplitter(Qt.Orientation.Vertical)
        # v_splitter.addWidget(splitter)
        # v_splitter.addWidget(self.volume_viewer)
        # v_splitter.setSizes([self.height(), 50])
        # layout.addWidget(v_splitter)

        v_splitter = QSplitter(Qt.Orientation.Vertical)
        v_splitter.addWidget(splitter)
        v_splitter.setSizes([self.height()])
        layout.addWidget(v_splitter)

        self.actor_collection = vtk.vtkActorCollection()
        self.bounding_box = BoundingBoxWidget(self.renderer, self.interactor)
        self.axes_widget = AxesWidget(self.renderer, self.interactor)
        self.cursor_handler = CursorModeHandler(self.vtk_widget)

        self.export_manager = ExportManager(
            self.vtk_widget, self.volume_viewer, self.cdata
        )
        self.trajectory_player = TrajectoryPlayer(self.cdata)
        self.setup_menu()

    def on_tab_clicked(self):
        # Uncheck all other buttons
        sender = self.sender()
        tab_id = sender.property("tab_id")

        for btn in self.tab_buttons.values():
            if btn != sender:
                btn.setChecked(False)

        self.tabs[tab_id][0].show_ribbon()

    def on_key_press(self, obj, event):
        key = obj.GetKeyCode()

        if key in ["x", "c", "z"]:
            self.set_camera_view(key)
        elif key == "v":
            self.swap_camera_view_direction(key)
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

    def set_camera_view(self, view_key, aligned_direction=True, view_angle=0):
        camera = self.renderer.GetActiveCamera()
        focal_point = camera.GetFocalPoint()

        distance = 1000
        if self.cdata.shape is not None:
            distance = max(self.cdata.shape) * 2.0

        distance = distance if aligned_direction else -distance
        if view_key == "z":
            # view = (0, 0, 0)
            view = (1, 0, 1)
            rotation_axis = (0, 1, 0)
            position = (0, 0, distance)
        elif view_key == "c":
            view = (1, 0, 0)
            position = (0, distance, 0)
            rotation_axis = (0, 0, 1)
        elif view_key == "x":
            # view = (0, 0, 1)
            view = (0, 1, 0)
            position = (distance, 0, 0)
            rotation_axis = (0, 0, 1)
        else:
            return -1

        if view_angle != 0:
            rotation_matrix = vtk.vtkTransform()
            rotation_matrix.Identity()
            rotation_matrix.RotateWXYZ(view_angle, *rotation_axis)

            view = rotation_matrix.TransformVector(view)
            position = rotation_matrix.TransformPoint(position)

        position = tuple(sum(x) for x in zip(focal_point, position))
        camera.SetPosition(*position)
        camera.SetViewUp(*view)

        self.renderer.ResetCamera()
        self._camera_view = view_key
        self._camera_tilt = view_angle
        self._camera_direction = aligned_direction
        self.vtk_widget.GetRenderWindow().Render()

    def swap_camera_view_direction(self, view_key):
        view = getattr(self, "_camera_view", None)
        if view is None:
            return -1

        direction = getattr(self, "_camera_direction", True)
        return self.set_camera_view(view, not direction)

    def _update_style(self):
        self.setStyleSheet(
            """
            QMenuBar {
                border-bottom: 1px solid #6b7280;
            }
            QMenuBar::item {
                padding: 4px 8px;
            }
            QMenuBar::item:selected {
                background-color: #1a000000;
                border-radius: 4px;
            }
            QMenu {
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 4px 24px 4px 8px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #1a000000;
            }
        """
        )

    def changeEvent(self, event):
        if event.type() == QEvent.Type.PaletteChange:
            self._update_style()
        super().changeEvent(event)

    def setup_menu(self):
        self._update_style()

        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        view_menu = menu_bar.addMenu("View")
        help_menu = menu_bar.addMenu("Help")

        # File menu actions
        new_session_action = QAction("New Session", self)
        new_session_action.triggered.connect(self.open_session)
        new_session_action.setShortcut("Ctrl+N")

        add_file_action = QAction("Import Files", self)
        add_file_action.triggered.connect(self.open_file)
        add_file_action.setShortcut("Ctrl+O")

        save_file_action = QAction("Save Session", self)
        save_file_action.triggered.connect(self.save_session)
        save_file_action.setShortcut("Ctrl+S")

        screenshot_action = QAction("Save Viewer Screenshot", self)
        screenshot_action.triggered.connect(
            lambda x: self.export_manager.save_screenshot()
        )
        screenshot_action.setShortcut("Ctrl+P")

        animation_action = QAction("Export Animation", self)
        animation_action.triggered.connect(
            lambda x: self.export_manager.export_animation()
        )
        animation_action.setShortcut("Ctrl+E")

        clipboard_action = QAction("Viewer Screenshot to Clipboard", self)
        clipboard_action.triggered.connect(
            lambda x: self.export_manager.copy_screenshot_to_clipboard()
        )
        clipboard_action.setShortcut("Ctrl+Shift+C")

        clipboard_window_action = QAction("Window Screenshot to Clipboard", self)
        clipboard_window_action.triggered.connect(
            lambda x: self.export_manager.copy_screenshot_to_clipboard(window=True)
        )
        clipboard_window_action.setShortcut("Ctrl+Shift+W")
        # Setup axes control menu
        axes_menu = QMenu("Axes", self)
        visible_action = QAction("Visible", self)
        visible_action.setCheckable(True)
        visible_action.setChecked(self.axes_widget.visible)
        visible_action.triggered.connect(
            lambda checked: (
                self.axes_widget.set_visibility(checked),
                self.vtk_widget.GetRenderWindow().Render(),
            )
        )
        labels_action = QAction("Labels", self)
        labels_action.setCheckable(True)
        labels_action.setChecked(self.axes_widget.labels_visible)
        labels_action.triggered.connect(
            lambda checked: (
                self.axes_widget.set_labels_visible(checked),
                self.vtk_widget.GetRenderWindow().Render(),
            )
        )
        colored_action = QAction("Colored", self)
        colored_action.setCheckable(True)
        colored_action.setChecked(self.axes_widget.colored)
        colored_action.triggered.connect(
            lambda checked: (
                self.axes_widget.set_colored(checked),
                self.vtk_widget.GetRenderWindow().Render(),
            )
        )
        arrow_action = QAction("Arrows", self)
        arrow_action.setCheckable(True)
        arrow_action.setChecked(self.axes_widget.arrow_heads_visible)
        arrow_action.triggered.connect(
            lambda checked: (
                self.axes_widget.set_arrow_heads_visible(checked),
                self.vtk_widget.GetRenderWindow().Render(),
            )
        )
        axes_menu.addAction(visible_action)
        axes_menu.addAction(labels_action)
        axes_menu.addAction(colored_action)
        axes_menu.addAction(arrow_action)

        # Handle differnt camera angles
        tilt_menu = QMenu("Camera Tilt", self)
        self.tilt_dialog = TiltControlDialog(self)
        show_tilt_control = QAction(
            qta.icon("fa5s.sliders-h", opacity=0.7, color="gray"),
            "Tilt Controls...",
            self,
        )
        show_tilt_control.triggered.connect(self.tilt_dialog.show)
        tilt_menu.addAction(show_tilt_control)

        tilt_menu.addSeparator()
        tilt_group = QActionGroup(self)
        tilt_group.setExclusive(True)
        for angle in [0, 15, 30, 45, 60, 90]:
            action = QAction(f"{angle}°", self)
            action.triggered.connect(
                lambda checked, a=angle: self.set_camera_view(
                    getattr(self, "_camera_view", "x"),
                    getattr(self, "_camera_direction", True),
                    tilt_angle=a,
                )
            )
            tilt_menu.addAction(action)

        tilt_menu.addSeparator()
        reset_action = QAction(
            qta.icon("fa5s.undo", opacity=0.7, color="gray"), "Reset Tilt", self
        )
        reset_action.setShortcut("Ctrl+T")
        reset_action.triggered.connect(self.tilt_dialog.reset_tilt)
        tilt_menu.addAction(reset_action)

        self.volume_action = QAction("Volume Viewer", self)
        self.volume_action.setCheckable(True)
        self.volume_action.setChecked(False)
        self.volume_action.triggered.connect(
            lambda checked: self._set_volume_viewer(checked)
        )

        self.trajectory_action = QAction("Trajectory Player", self)
        self.trajectory_action.setCheckable(True)
        self.trajectory_action.setChecked(False)
        self.trajectory_action.triggered.connect(
            lambda checked: (self._set_trajectory_player(checked),)
        )

        # Help menu
        show_keybinds_action = QAction("Keybinds", self)
        self.keybinds_dialog = KeybindsDialog(self)
        show_keybinds_action.triggered.connect(self.keybinds_dialog.show)
        show_keybinds_action.setShortcut("Ctrl+H")

        # Add actions to menus
        file_menu.addAction(new_session_action)
        file_menu.addAction(add_file_action)
        file_menu.addAction(save_file_action)
        file_menu.addSeparator()
        file_menu.addAction(screenshot_action)
        file_menu.addAction(clipboard_action)
        file_menu.addAction(clipboard_window_action)
        file_menu.addAction(animation_action)

        view_menu.addMenu(axes_menu)
        view_menu.addMenu(tilt_menu)
        view_menu.addAction(self.volume_action)
        view_menu.addAction(self.trajectory_action)
        view_menu.addSeparator()

        help_menu.addAction(show_keybinds_action)

    def _setup_volume_viewer(self):
        self.volume_dock = QDockWidget(self)
        self.volume_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.volume_dock.setTitleBarWidget(QWidget())

        self.volume_dock.setWidget(self.volume_viewer)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.volume_dock)
        self.volume_dock.hide()

    def _set_volume_viewer(self, visible):
        if visible:
            if self.volume_dock is None:
                self._setup_volume_viewer()
            self.volume_dock.setVisible(visible)
        elif self.volume_dock is not None:
            self.volume_dock.hide()

    def _setup_trajectory_player(self):
        self.trajectory_dock = QDockWidget(self)
        self.trajectory_dock.setFeatures(
            QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
        )
        self.trajectory_dock.setTitleBarWidget(QWidget())

        self.trajectory_player = TrajectoryPlayer(self.cdata)
        self.trajectory_dock.setWidget(self.trajectory_player)

        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.trajectory_dock)
        self.trajectory_dock.hide()

    def _set_trajectory_player(self, visible):
        if visible:
            self._setup_trajectory_player()
        self.trajectory_dock.setVisible(visible)

    def open_session(self):
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
        self.set_camera_view("x")

    def open_file(self):
        filenames, _ = QFileDialog.getOpenFileNames(self, "Import Files")

        if not filenames:
            return -1

        dialog = ImportDataDialog(self)
        dialog.set_files(filenames)

        if not dialog.exec():
            return -1

        file_parameters = dialog.get_all_parameters()
        for filename in filenames:
            parameters = file_parameters[filename]
            points = import_points(filename, **parameters)
            for point in points:
                self.cdata._data.add(points=point.astype(np.float32))

        self.cdata.data.data_changed.emit()
        self.cdata.data.render()
        return 0

    def save_session(self):
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
