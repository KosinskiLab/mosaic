#!python3
""" GUI entrypoint.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""
import os
import sys
from typing import List
from importlib_resources import files
from os.path import splitext, basename

import vtk
import numpy as np
from qtpy.QtCore import Qt, QEvent, QSettings
from qtpy.QtWidgets import (
    QApplication,
    QMainWindow,
    QVBoxLayout,
    QWidget,
    QSplitter,
    QFileDialog,
    QMenu,
    QHBoxLayout,
    QPushButton,
    QDockWidget,
)
from qtpy.QtGui import (
    QAction,
    QGuiApplication,
    QIcon,
    QActionGroup,
)
import qtawesome as qta
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from mosaic import MosaicData, ExportManager
from mosaic.tabs import SegmentationTab, ModelTab, IntelligenceTab
from mosaic.dialogs import (
    TiltControlDialog,
    KeybindsDialog,
    ImportDataDialog,
    ProgressDialog,
)
from mosaic.stylesheets import QMessageBox_style
from mosaic.widgets import (
    MultiVolumeViewer,
    BoundingBoxWidget,
    AxesWidget,
    RibbonToolBar,
    TrajectoryPlayer,
    LegendWidget,
    ScaleBarWidget,
    ObjectBrowserSidebar,
    ViewerModes,
    StatusIndicator,
    CursorModeHandler,
)


class App(QMainWindow):
    def __init__(self):
        super().__init__()

        self.max_recent_files = 10
        self.recent_file_actions = []
        self.recent_files = self.load_recent_files()

        # Adapt to screen size
        screen = QGuiApplication.primaryScreen().geometry()
        width = int(screen.width() * 0.7)
        height = int(screen.height() * 0.9)
        self.resize(width, height)
        self.move((screen.width() - width) // 2, (screen.height() - height) // 2)
        self.setWindowTitle("Mosaic")

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
        self.renderer.SetUseFXAA(True)

        render_window = self.vtk_widget.GetRenderWindow()
        render_window.AddRenderer(self.renderer)
        render_window.SetMultiSamples(0)
        render_window.SetPointSmoothing(False)
        render_window.SetLineSmoothing(False)
        render_window.SetPolygonSmoothing(False)

        # Setup GUI interactions
        self.interactor = self.vtk_widget.GetRenderWindow().GetInteractor()
        self.interactor.Initialize()
        self.interactor.AddObserver("RightButtonPressEvent", self.on_right_click)
        self.interactor.AddObserver("KeyPressEvent", self.on_key_press)

        self.cdata = MosaicData(self.vtk_widget)

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

        self.setup_widgets()
        self.tab_buttons = {}
        self.tab_ribbon = RibbonToolBar(self)
        data = {"cdata": self.cdata, "ribbon": self.tab_ribbon, "legend": self.legend}
        self.tabs = [
            (SegmentationTab(**data), "Segmentation"),
            (ModelTab(**data), "Parametrization"),
            (IntelligenceTab(**data), "Intelligence"),
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
                    padding: 11px 24px;
                    font-size: 13px;
                    border-bottom: 2px solid transparent;
                }
                QPushButton:hover {
                    color: #696c6f;
                }
                QPushButton:checked {
                    color: rgba(99, 102, 241, 1.0);
                    border-bottom: 2px solid rgba(99, 102, 241, 1.0);
                }
                QPushButton:focus {
                    outline: none;
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

        list_wrapper = ObjectBrowserSidebar()
        list_wrapper.set_title("Object Browser")
        list_wrapper.add_widget("cluster", "Cluster", self.cdata.data.data_list)
        list_wrapper.add_widget("model", "Model", self.cdata.models.data_list)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(list_wrapper)
        splitter.addWidget(self.vtk_widget)
        splitter.setSizes([200, self.width() - 200])

        v_splitter = QSplitter(Qt.Orientation.Vertical)
        v_splitter.addWidget(splitter)
        v_splitter.setSizes([self.height()])
        layout.addWidget(v_splitter)

        self.actor_collection = vtk.vtkActorCollection()
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
            self.cdata.data.remove()
        elif key == "m":
            self.cdata.data.merge()
        elif key == "e":
            self.cdata.highlight_clusters_from_selected_points()
        elif key == "s":
            self._transition_modes(ViewerModes.VIEWING)
            self.cdata.swap_area_picker()
        elif key == "S":
            self._transition_modes(ViewerModes.PICKING)
        elif key == "h":
            self.cdata.data.toggle_visibility()
        elif key == "a":
            self._transition_modes(ViewerModes.DRAWING)
        elif key == "A":
            self._transition_modes(ViewerModes.CURVE)
        elif key == "q":
            self._transition_modes(ViewerModes.MESH_DELETE)
        elif key == "Q":
            self._transition_modes(ViewerModes.MESH_ADD)
        elif key == "r":
            self._transition_modes(ViewerModes.SELECTION)

    def on_right_click(self, obj, event):
        self.cdata.data.deselect()
        self.cdata.models.deselect()

    def _transition_modes(self, new_mode):
        from mosaic.styles import MeshEditInteractorStyle, CurveBuilderInteractorStyle

        current_mode = self.cursor_handler.current_mode
        if current_mode in (
            ViewerModes.MESH_ADD,
            ViewerModes.MESH_DELETE,
            ViewerModes.CURVE,
        ):
            current_style = self.interactor.GetInteractorStyle()
            if hasattr(current_style, "cleanup"):
                current_style.cleanup()

            self.cdata.swap_area_picker()
            self.cdata.swap_area_picker()

        self.cdata.activate_viewing_mode()
        self.status_indicator.update_status(interaction=new_mode.value)
        if current_mode == new_mode:
            self.status_indicator.update_status(interaction=ViewerModes.VIEWING.value)
            return self.cursor_handler.update_mode(ViewerModes.VIEWING)

        if new_mode == ViewerModes.DRAWING:
            self.cdata.data.toggle_drawing_mode()
        elif new_mode == ViewerModes.CURVE:
            style = CurveBuilderInteractorStyle(self, self.cdata)
            self.interactor.SetInteractorStyle(style)
            style.SetDefaultRenderer(self.renderer)
        elif new_mode == ViewerModes.SELECTION:
            self.interactor.SetInteractorStyle(vtk.vtkInteractorStyleRubberBandPick())
        elif new_mode == ViewerModes.PICKING:
            self.cdata.toggle_picking_mode()
        elif new_mode in (ViewerModes.MESH_ADD, ViewerModes.MESH_DELETE):
            style = MeshEditInteractorStyle(self, self.cdata)
            self.interactor.SetInteractorStyle(style)
            style.SetDefaultRenderer(self.renderer)
            if new_mode == ViewerModes.MESH_ADD:
                style.toggle_add_face_mode()

        return self.cursor_handler.update_mode(new_mode)

    def set_camera_view(
        self, view_key, aligned_direction=True, elevation=0, azimuth=0, pitch=0
    ):
        camera = self.renderer.GetActiveCamera()
        focal_point = camera.GetFocalPoint()
        position = camera.GetPosition()

        distance = np.linalg.norm(np.subtract(position, focal_point))
        distance = distance if aligned_direction else -distance
        if view_key == "z":
            view = (1, 0, 1)
            position_vec = (0, 0, 1)
        elif view_key == "c":
            view = (1, 0, 0)
            position_vec = (0, 1, 0)
        elif view_key == "x":
            view = (0, 1, 0)
            position_vec = (1, 0, 0)
        else:
            return -1

        transform = vtk.vtkTransform()
        transform.Identity()
        transform.RotateWXYZ(elevation, *(0, 0, 1))
        transform.RotateWXYZ(azimuth, *(0, 1, 0))
        transform.RotateWXYZ(pitch, *(1, 0, 0))

        view = transform.TransformVector(view)
        position_vec = np.array(transform.TransformVector(position_vec))
        position_vec /= np.linalg.norm(position_vec)
        position_vec *= distance

        position = np.add(focal_point, position_vec)
        current_view = getattr(self, "_camera_view", None)
        if current_view != view_key:
            focal_point = (0, 0, 0)
            position = position_vec

        camera.SetPosition(*position)
        camera.SetViewUp(*view)
        camera.SetFocalPoint(*focal_point)
        if current_view != view_key:
            self.renderer.ResetCamera()

        self._camera_view = view_key
        self._camera_elevation = elevation
        self._camera_azimuth = azimuth
        self._camera_pitch = pitch
        self._camera_direction = aligned_direction
        self.vtk_widget.GetRenderWindow().Render()

    def swap_camera_view_direction(self, view_key):
        view = getattr(self, "_camera_view", None)
        if view is None:
            return -1

        direction = getattr(self, "_camera_direction", True)
        return self.set_camera_view(view, not direction)

    def _update_style(self):
        # This also sets the style of the list widgets
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

    def setup_widgets(self):
        self.legend = LegendWidget(self.renderer, self.interactor)

        self.volume_dock = None
        self.volume_viewer = MultiVolumeViewer(self.vtk_widget, legend=self.legend)

        self.cursor_handler = CursorModeHandler(self.vtk_widget)
        self.axes_widget = AxesWidget(self.renderer, self.interactor)
        self.bounding_box = BoundingBoxWidget(self.renderer, self.interactor)
        self.trajectory_player = TrajectoryPlayer(self.cdata)
        self.scale_bar = ScaleBarWidget(self.renderer, self.interactor)
        self.export_manager = ExportManager(
            self.vtk_widget, self.volume_viewer, self.cdata
        )
        self.status_indicator = StatusIndicator(self.renderer, self.interactor)

        from mosaic.parallel import BackgroundTaskManager

        task_manager = BackgroundTaskManager.instance()
        task_manager.task_started.connect(
            lambda name: self.status_indicator.update_status(status=name)
        )
        task_manager.task_completed.connect(
            lambda name, result: self.status_indicator.update_status(status="Ready")
        )
        task_manager.task_failed.connect(
            lambda name, error: self.status_indicator.update_status(status="Ready")
        )

    def setup_menu(self):
        self._update_style()

        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        view_menu = menu_bar.addMenu("View")
        help_menu = menu_bar.addMenu("Help")

        # File menu actions
        new_session_action = QAction("Load Session", self)
        new_session_action.triggered.connect(self.load_session)
        new_session_action.setShortcut("Ctrl+N")

        add_file_action = QAction("Open", self)
        add_file_action.triggered.connect(self.open_files)
        add_file_action.setShortcut("Ctrl+O")

        save_file_action = QAction("Save Session", self)
        save_file_action.triggered.connect(self.save_session)
        save_file_action.setShortcut("Ctrl+S")

        self.recent_menu = QMenu("Recent Files", self)
        for i in range(self.max_recent_files):
            action = QAction(self)
            action.setVisible(False)
            action.triggered.connect(self._open_recent_file)
            self.recent_file_actions.append(action)
            self.recent_menu.addAction(action)

        self.update_recent_files_menu()

        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)

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
        tilt_menu = QMenu("Camera", self)
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
                    view_angle=a,
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

        legend_bar_menu = QMenu("Legend", self)
        legend_bar = QAction("Show", self)
        legend_bar.setCheckable(True)
        legend_bar.setChecked(False)
        legend_bar.triggered.connect(
            lambda checked: self.legend.show() if checked else self.legend.hide()
        )

        orientation_menu = QMenu("Orientation", self)
        vertical = QAction("Vertical", self)
        vertical.triggered.connect(lambda: self.legend.set_orientation("vertical"))
        horizontal = QAction("Horizontal", self)
        horizontal.triggered.connect(lambda: self.legend.set_orientation("horizontal"))

        orientation_menu.addAction(vertical)
        orientation_menu.addAction(horizontal)
        legend_bar_menu.addAction(legend_bar)
        legend_bar_menu.addMenu(orientation_menu)

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
        file_menu.addAction(add_file_action)
        file_menu.addMenu(self.recent_menu)
        file_menu.addSeparator()
        file_menu.addAction(new_session_action)
        file_menu.addAction(save_file_action)

        file_menu.addSeparator()
        file_menu.addAction(screenshot_action)
        file_menu.addAction(clipboard_action)
        file_menu.addAction(clipboard_window_action)
        file_menu.addAction(animation_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        show_scale_bar = QAction("Scale Bar", self)
        show_scale_bar.setCheckable(True)
        show_scale_bar.setChecked(False)
        show_scale_bar.triggered.connect(
            lambda checked: self.scale_bar.show() if checked else self.scale_bar.hide()
        )

        show_viewer_mode = QAction("Viewer Mode", self)
        show_viewer_mode.setCheckable(True)
        show_viewer_mode.setChecked(True)
        show_viewer_mode.triggered.connect(
            lambda checked: (
                self.status_indicator.show()
                if checked
                else self.status_indicator.hide()
            )
        )

        view_menu.addMenu(axes_menu)
        view_menu.addMenu(tilt_menu)
        view_menu.addMenu(legend_bar_menu)
        view_menu.addAction(show_scale_bar)
        view_menu.addAction(show_viewer_mode)
        view_menu.addSeparator()
        view_menu.addAction(self.volume_action)
        view_menu.addAction(self.trajectory_action)

        help_menu.addAction(show_keybinds_action)

    def _setup_volume_viewer(self):
        self.volume_dock = QDockWidget(self)
        self.volume_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.volume_dock.setTitleBarWidget(QWidget())

        self.volume_dock.setWidget(self.volume_viewer)
        self.addDockWidget(
            Qt.DockWidgetArea.BottomDockWidgetArea,
            self.volume_dock,
            Qt.Orientation.Vertical,
        )
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
        self.addDockWidget(
            Qt.DockWidgetArea.BottomDockWidgetArea,
            self.trajectory_dock,
            Qt.Orientation.Vertical,
        )
        self.trajectory_dock.hide()

    def _set_trajectory_player(self, visible):
        if visible:
            self._setup_trajectory_player()
        self.trajectory_dock.setVisible(visible)

    def _load_session(self, file_path: str):
        try:
            self.cdata.load_session(file_path)
        except ValueError as e:
            print(f"Error opening file: {e}")
            return -1

        self._add_file_to_recent(file_path)
        self.renderer.RemoveAllViewProps()
        self.volume_viewer.close()
        self.bounding_box.setup(shape=self.cdata.shape)
        self.renderer.AddActor(self.bounding_box.box_actor)
        self.renderer.AddActor(self.status_indicator.text_actor)
        self.cdata.data.rendered_actors.clear()
        self.cdata.models.rendered_actors.clear()
        self.cdata.data.render()
        self.cdata.models.render()
        self.set_camera_view("x")

    def load_session(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Open Session")
        if not file_path:
            return -1

        return self._load_session(file_path)

    def _open_files(self, filenames: List[str]):
        from mosaic.formats import open_file
        from mosaic.meshing import to_open3d
        from mosaic.parametrization import TriangularMesh

        if isinstance(filenames, str):
            filenames = [
                filenames,
            ]

        dialog = ImportDataDialog(self)
        dialog.set_files(filenames)

        if not dialog.exec():
            return -1

        file_parameters = dialog.get_all_parameters()
        with ProgressDialog(filenames, title="Reading Files", parent=None) as pbar:
            for filename in pbar:
                self._add_file_to_recent(filename)
                parameters = file_parameters[filename]

                offset = parameters.get("offset", 0)
                scale = parameters.get("scale", 1)
                sampling = parameters.get("sampling_rate", 1)

                try:
                    container = open_file(filename)
                except ValueError as e:
                    print(e)
                    if filename.endswith(".pickle"):
                        print("Use Load Session to open session files.")
                    continue

                base, _ = splitext(basename(filename))
                use_index = len(container) > 1
                for index, data in enumerate(container):
                    data.vertices = np.multiply(
                        np.subtract(data.vertices, offset), scale
                    )

                    name = base if not use_index else f"{index}_base"
                    if data.faces is None:
                        index = self.cdata.data.add(
                            points=data.vertices,
                            normals=data.normals,
                            sampling_rate=sampling,
                        )
                        self.cdata._data.data[index]._meta["name"] = name
                    else:
                        index = self.cdata._add_fit(
                            fit=TriangularMesh(to_open3d(data.vertices, data.faces)),
                            sampling_rate=sampling,
                        )
                        self.cdata._models.data[index]._meta["name"] = name

        self.cdata.data.data_changed.emit()
        self.cdata.models.data_changed.emit()
        self.cdata.data.render()
        self.cdata.models.render()
        return 0

    def open_files(self):
        filenames, _ = QFileDialog.getOpenFileNames(self, "Import Files")
        if not filenames:
            return -1

        return self._open_files(filenames)

    def save_session(self):
        file_dialog = QFileDialog()
        file_dialog.setDefaultSuffix("pickle")
        file_path, _ = file_dialog.getSaveFileName(
            self, "Save File", "", "Pickle Files (*.pickle)"
        )
        if not file_path:
            return -1

        self.cdata.to_file(file_path)

    def load_recent_files(self):
        return QSettings("Mosaic").value("recentFiles", [])

    def save_recent_files(self):
        settings = QSettings("Mosaic")
        settings.setValue("recentFiles", self.recent_files)

    def update_recent_files_menu(self):
        files_to_show = self.recent_files[: self.max_recent_files]

        for i, file_path in enumerate(files_to_show):
            text = f"&{i + 1} {os.path.basename(file_path)}"
            self.recent_file_actions[i].setText(text)
            self.recent_file_actions[i].setData(file_path)
            self.recent_file_actions[i].setVisible(True)

        for j in range(len(files_to_show), self.max_recent_files):
            self.recent_file_actions[j].setVisible(False)

        self.recent_menu.setEnabled(len(files_to_show) > 0)

    def _add_file_to_recent(self, file_path):
        if file_path in self.recent_files:
            self.recent_files.remove(file_path)
        self.recent_files.insert(0, file_path)

        while len(self.recent_files) > self.max_recent_files:
            self.recent_files.pop()

        self.save_recent_files()
        self.update_recent_files_menu()

    def _open_recent_file(self):
        action = self.sender()
        if not action:
            return None

        file_path = action.data()
        if not os.path.exists(file_path):
            self.recent_files.remove(file_path)
            self.save_recent_files()
            return self.update_recent_files_menu()

        if file_path.endswith(".pickle"):
            return self._load_session(file_path)
        return self._open_files([file_path])


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Mosaic")
    app.setApplicationDisplayName("Mosaic")

    icon = QIcon(str(files("mosaic.data").joinpath("data/mosaic.icns")))
    app.setWindowIcon(icon)

    # Fixes alignment issue in default style
    # https://forum.qt.io/topic/105191/why-isn-t-a-qcombobox-positioned-correctly-in-a-layout/11
    app.setStyle("Fusion")

    from mosaic.stylesheets import (
        QPushButton_style,
        QLineEdit_style,
        QSpinBox_style,
        QDoubleSpinBox_style,
        QComboBox_style,
    )

    app.setStyleSheet(
        QMessageBox_style
        + QLineEdit_style
        + QSpinBox_style
        + QDoubleSpinBox_style
        + QComboBox_style
    )

    window = App()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
