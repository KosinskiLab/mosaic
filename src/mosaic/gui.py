"""
Mosaic GUI implementation

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import os
from typing import List
from os.path import exists

import vtk
import numpy as np
from qtpy.QtCore import (
    Qt,
    QEvent,
    QSize,
    QTimer,
)
from qtpy.QtWidgets import (
    QApplication,
    QMainWindow,
    QVBoxLayout,
    QGridLayout,
    QWidget,
    QStackedWidget,
    QSplitter,
    QFileDialog,
    QMenu,
    QPushButton,
    QDockWidget,
    QFrame,
    QShortcut,
    QMessageBox,
    QDialog,
)
from qtpy.QtGui import (
    QAction,
    QGuiApplication,
    QActionGroup,
    QKeyEvent,
    QDragEnterEvent,
)
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from .data import MosaicData
from .icons import icon
from .settings import Settings
from .stylesheets import Colors
from .animation._utils import ScreenshotManager
from .parallel import BackgroundTaskManager
from .tabs import SegmentationTab, ModelTab, IntelligenceTab, DevelopmentTab
from .dialogs import ImportDataDialog
from .widgets import (
    AxesWidget,
    RibbonToolBar,
    TabBar,
    TrajectoryPlayer,
    LegendWidget,
    ScaleBarWidget,
    ObjectBrowserSidebar,
    ViewerModes,
    StatusIndicator,
    CursorModeHandler,
    BoundingBoxManager,
)
from .widgets.dock import toggle_dock
from .widgets.volume_viewer_hud import VolumeViewerHUD
from .widgets.viewport_placeholder import ViewportPlaceholder, default_actions


class App(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowState(Qt.WindowNoState)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        self.vtk_widget = QVTKRenderWindowInteractor()

        # Stacked widget lets us swap the VTK viewport with the empty-state
        # placeholder without having to overlay widgets on top of VTK's GL
        # surface (which doesn't work reliably on Linux/X11).
        self.viewport_stack = QStackedWidget()
        self.viewport_stack.addWidget(self.vtk_widget)

        # Viewport container holds the stacked viewport and the volume-viewer
        # HUD in the same grid cell, letting the HUD float at the bottom of
        # the viewport.  The HUD uses WA_NativeWindow (see volume_viewer_hud)
        # so Qt gives it its own native X11 window that the compositor layers
        # above VTK's GL surface.
        self.viewport_container = QWidget()
        _vp_layout = QGridLayout(self.viewport_container)
        _vp_layout.setContentsMargins(0, 0, 0, 0)
        _vp_layout.setSpacing(0)
        _vp_layout.addWidget(self.viewport_stack, 0, 0)

        self.cdata = MosaicData(self.vtk_widget)
        self.cdata.thumbnail_provider = self._capture_thumbnail

        self.renderer = vtk.vtkRenderer()
        self.render_window = self.vtk_widget.GetRenderWindow()
        self.render_window.AddRenderer(self.renderer)
        self.apply_render_settings()

        self.interactor = self.vtk_widget.GetRenderWindow().GetInteractor()
        self.interactor.Initialize()
        self.interactor.AddObserver("RightButtonPressEvent", self.on_right_click)
        self.interactor.AddObserver("KeyPressEvent", self.on_key_press)
        self.interactor.SetDesiredUpdateRate(Settings.rendering.target_fps)

        self.tab_bar = TabBar()

        self.setup_widgets()
        self.tab_ribbon = RibbonToolBar(self)
        data = {"cdata": self.cdata, "ribbon": self.tab_ribbon, "legend": self.legend}

        self.tabs = [
            (SegmentationTab(**data), "Segmentation"),
            (ModelTab(**data), "Parametrization"),
            (IntelligenceTab(**data), "Intelligence"),
        ]
        if os.environ.get("MOSAIC_DEV"):
            self.tabs.append(
                (
                    DevelopmentTab(**data, volume_viewer=self.volume_viewer),
                    "Development",
                )
            )

        for _index, (tab, name) in enumerate(self.tabs):
            self.tab_bar.addTab(name)

        def on_tab_changed(tab_id):
            self.tabs[tab_id][0].show_ribbon()

        self.tab_bar.currentChanged.connect(on_tab_changed)
        self.tab_bar.finalize()

        from .widgets.theme_toggle import ThemeToggle

        self._tab_gear = QPushButton()
        self._tab_gear.setIcon(icon("ph.gear", role="muted"))
        self._tab_gear.setFlat(True)
        self._tab_gear.setFixedSize(28, 28)
        self._tab_gear.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_gear.setStyleSheet(
            f"""
            QPushButton {{ border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {Colors.BG_HOVER}; }}
            QPushButton:focus {{ outline: none; }}
        """
        )
        self.theme_toggle = ThemeToggle()
        self.theme_toggle.set_initial_state(Colors.is_dark())
        self.theme_toggle.toggled.connect(self._on_theme_toggled)
        self.tab_bar._layout.addWidget(self.theme_toggle)

        self._tab_gear.clicked.connect(self._toggle_appearance_panel)
        self.tab_bar._layout.addWidget(self._tab_gear)

        self.tabs[0][0].show_ribbon()

        layout.addWidget(self.tab_bar)
        layout.addWidget(self.tab_ribbon)

        self.ribbon_separator = QFrame()
        self.ribbon_separator.setFixedHeight(1)
        self.ribbon_separator.setFrameShape(QFrame.Shape.NoFrame)
        self.ribbon_separator.setStyleSheet(f"background: {Colors.BORDER_DARK};")
        layout.addWidget(self.ribbon_separator)

        # Create sidebar
        self.list_wrapper = ObjectBrowserSidebar()
        self.list_wrapper.add_widget("Clusters", self.cdata.data.data_list)
        self.list_wrapper.add_widget("Models", self.cdata.models.data_list)

        # Create splitter with sidebar on left, viewport on right
        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter.addWidget(self.list_wrapper)
        self._main_splitter.addWidget(self.viewport_container)
        self._main_splitter.setSizes([200, self.width() - 200])
        self._main_splitter.setStretchFactor(0, 0)
        self._main_splitter.setStretchFactor(1, 1)
        self._main_splitter.setHandleWidth(4)
        self._main_splitter.setStyleSheet(
            "QSplitter::handle { background: transparent; }"
        )

        layout.addWidget(self._main_splitter)

        self.actor_collection = vtk.vtkActorCollection()
        self.setup_menu()

        self.escape_shortcut = QShortcut(Qt.Key.Key_Escape, self.vtk_widget)
        self.escape_shortcut.activated.connect(self.handle_escape_key)

        QTimer.singleShot(2000, self._check_for_updates)

        self.setAcceptDrops(True)

    def closeEvent(self, event):
        Settings.ui.window_geometry = self.saveGeometry()
        BackgroundTaskManager.instance()._shutdown()
        super().closeEvent(event)

    def _toggle_volume_dock(self, checked: bool):
        self.volume_viewer.setVisible(checked)

    def dragEnterEvent(self, event: QDragEnterEvent):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if any(url.isLocalFile() for url in urls):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        self._handle_import(paths)

    def _handle_import(self, file_paths):
        from .formats.session import is_session_file
        from .formats.reader import is_volume_file

        session_files = [f for f in file_paths if is_session_file(f)]
        volume_files = [
            f for f in file_paths if not is_session_file(f) and is_volume_file(f)
        ]
        data_files = [
            f for f in file_paths if not is_session_file(f) and not is_volume_file(f)
        ]

        if session_files:
            if len(session_files) > 1:
                QMessageBox.warning(
                    self,
                    "Multiple Session Files",
                    "Only one session file can be loaded at a time. ",
                )
            self._load_session(session_files[0])

        if volume_files:
            remaining = self._triage_volumes(volume_files)
            data_files.extend(remaining)

        if data_files:
            self._open_files(data_files)

    def sizeHint(self):
        """Provide the preferred size for the main window."""
        screen = QGuiApplication.primaryScreen().geometry()
        return QSize(int(screen.width() * 0.95), int(screen.height() * 0.95))

    def show(self):
        """Override show to restore saved geometry or use default size."""
        saved = Settings.ui.window_geometry
        if saved and self.restoreGeometry(saved):
            super().show()
            return

        self.resize(self.sizeHint())
        super().show()

        screen = QGuiApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def set_lighting_mode(self, mode: str = "simple"):
        """Apply a lighting/effects mode to the renderer.

        Parameters
        ----------
        mode: str
            Can be one of 'simple', 'soft', 'full', 'flat', 'poster',
            'silhouettes'
        """
        renderer = self.renderer

        current_pass = renderer.GetPass()
        if current_pass is not None:
            current_pass.ReleaseGraphicsResources(self.render_window)
        renderer.SetPass(None)

        renderer.RemoveAllLights()
        renderer.CreateLight()

        actors = renderer.GetActors()
        actors.InitTraversal()
        for _ in range(actors.GetNumberOfItems()):
            actors.GetNextActor().GetProperty().LightingOn()

        if mode == "simple":
            pass

        elif mode == "soft":
            renderer.RemoveAllLights()
            light = vtk.vtkLight()
            light.SetLightTypeToHeadlight()
            light.SetAmbientColor(1.0, 1.0, 1.0)
            light.SetDiffuseColor(0.6, 0.6, 0.6)
            light.SetSpecularColor(0.1, 0.1, 0.1)
            light.SetIntensity(1.5)
            renderer.AddLight(light)

            passes = vtk.vtkRenderStepsPass()
            ssao = vtk.vtkSSAOPass()
            ssao.SetDelegatePass(passes)
            ssao.SetRadius(50.0)
            ssao.SetKernelSize(128)
            ssao.BlurOn()
            renderer.SetPass(ssao)

        elif mode == "full":
            renderer.RemoveAllLights()
            for pos, intensity, color in [
                ((1, 1, 1), 0.8, (1.0, 1.0, 0.95)),
                ((-1, 0.5, -0.5), 0.4, (0.3, 0.3, 0.4)),
                ((0, -1, 0.5), 0.3, (0.2, 0.2, 0.25)),
            ]:
                light = vtk.vtkLight()
                light.SetPosition(*pos)
                light.SetColor(*color)
                light.SetIntensity(intensity)
                light.SetLightTypeToSceneLight()
                renderer.AddLight(light)

        elif mode == "flat":
            actors = renderer.GetActors()
            actors.InitTraversal()
            for _ in range(actors.GetNumberOfItems()):
                actors.GetNextActor().GetProperty().LightingOff()

        elif mode == "poster":
            renderer.RemoveAllLights()
            for pos, intensity, color in [
                ((1, 1, 0.5), 0.6, (1.0, 1.0, 1.0)),
                ((-1, 0.5, -0.5), 0.4, (1.0, 1.0, 1.0)),
                ((0, -1, 0.5), 0.3, (1.0, 1.0, 1.0)),
            ]:
                l = vtk.vtkLight()
                l.SetPosition(*pos)
                l.SetColor(*color)
                l.SetIntensity(intensity)
                l.SetLightTypeToSceneLight()
                renderer.AddLight(l)

            passes = vtk.vtkRenderStepsPass()
            ssao = vtk.vtkSSAOPass()
            ssao.SetDelegatePass(passes)
            ssao.SetRadius(50.0)
            ssao.SetKernelSize(128)
            ssao.BlurOn()
            renderer.SetPass(ssao)

        elif mode == "silhouettes":
            passes = vtk.vtkRenderStepsPass()
            sobel = vtk.vtkSobelGradientMagnitudePass()
            sobel.SetDelegatePass(passes)
            renderer.SetPass(sobel)

    def apply_render_settings(self):
        dark = [float(x) for x in Settings.rendering.background_color]
        light = [float(x) for x in Settings.rendering.background_color_alt]

        # Preserve whichever background the user last selected (e.g. via 'd')
        # so unrelated setting changes don't snap the viewport back to dark.
        if getattr(self, "_use_alt_background", False):
            active, inactive = light, dark
        else:
            active, inactive = dark, light

        if Settings.rendering.use_gradient_background:
            # VTK treats SetBackground as the bottom color and SetBackground2
            # as the top — place dark at the top, light at the bottom.
            self.renderer.SetBackground(*light)
            self.renderer.SetBackground2(*dark)
            self.renderer.GradientBackgroundOn()
        else:
            self.renderer.SetBackground(*active)
            self.renderer.GradientBackgroundOff()
        self.renderer_next_background = inactive
        self.renderer.SetUseDepthPeeling(Settings.rendering.use_depth_peeling)
        self.renderer.SetOcclusionRatio(Settings.rendering.occlusion_ratio)
        self.renderer.SetMaximumNumberOfPeels(Settings.rendering.max_depth_peels)
        self.renderer.SetUseFXAA(Settings.rendering.enable_fxaa)

        self.render_window.SetMultiSamples(Settings.rendering.multisamples)
        self.render_window.SetPointSmoothing(Settings.rendering.point_smoothing)
        self.render_window.SetLineSmoothing(Settings.rendering.line_smoothing)
        self.render_window.SetPolygonSmoothing(Settings.rendering.polygon_smoothing)
        self.render_window.SetDesiredUpdateRate(Settings.rendering.target_fps)

        self.set_lighting_mode(Settings.rendering.lighting_mode)
        self.render_window.Render()

        if not hasattr(self, "cdata"):
            return None

        from .actor import ActorFactory  # noqa: E402

        if not ActorFactory().is_synced():
            ActorFactory().update_from_settings()
            self.cdata.refresh_actors()

        btm = BackgroundTaskManager.instance()
        target_workers = int(Settings.rendering.parallel_worker)
        if btm.num_workers != target_workers:
            if btm.futures:
                from qtpy.QtWidgets import QMessageBox

                ret = QMessageBox.question(
                    self,
                    "Active Tasks",
                    f"{len(btm.futures)} task(s) still running. "
                    "Changing worker count will cancel them. Continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if ret != QMessageBox.StandardButton.Yes:
                    Settings.rendering.parallel_worker = btm.num_workers
                    panel = self.appearance_panel
                    panel._workers_slider.blockSignals(True)
                    panel._workers_slider.setValue(btm.num_workers)
                    panel._workers_slider.blockSignals(False)
                    return
            btm._initialize()

    def handle_escape_key(self, *args, **kwargs):
        """Handle escape key press - switch to viewing mode if not already in it."""
        self._transition_modes(self.cursor_handler.current_mode)
        self.interactor.SetInteractorStyle(vtk.vtkInteractorStyleTrackballCamera())

    def on_key_press(self, obj, event):
        key = obj.GetKeyCode()

        if key in ["x", "c", "z"]:
            self.set_camera_view(key)
        elif key == "v":
            self.swap_camera_view_direction(key)
        elif key in ["d"]:
            self._use_alt_background = not getattr(self, "_use_alt_background", False)
            current_color = self.renderer.GetBackground()
            self.renderer.SetBackground(*self.renderer_next_background)
            self.renderer_next_background = current_color
            self.vtk_widget.GetRenderWindow().Render()
        elif key in ["\x7f", "\x08"]:
            self.cdata.data.remove()
            self.cdata.models.remove()
        elif key == "m":
            self.cdata.data.merge()
        elif key == "e":
            self.cdata.highlight_clusters_from_selected_points()
        elif key == "h":
            self.cdata.visibility_unselected(visible=False)
        elif key == "H":
            self.cdata.visibility_unselected(visible=True)
        elif key == "s":
            self._transition_modes(ViewerModes.VIEWING)
            self.cdata.swap_area_picker()
            self.toggle_selection_menu()
        elif key == "E":
            self._transition_modes(ViewerModes.PICKING)
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
            self.cdata.data.activate_drawing_mode()
        elif new_mode == ViewerModes.CURVE:
            from .styles import CurveBuilderInteractorStyle

            style = CurveBuilderInteractorStyle(self, self.cdata)
            self.interactor.SetInteractorStyle(style)
            style.SetDefaultRenderer(self.renderer)
        elif new_mode == ViewerModes.SELECTION:
            self.interactor.SetInteractorStyle(vtk.vtkInteractorStyleRubberBandPick())
        elif new_mode == ViewerModes.PICKING:
            self.cdata.activate_picking_mode()
        elif new_mode in (ViewerModes.MESH_ADD, ViewerModes.MESH_DELETE):
            from .styles import MeshEditInteractorStyle

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

        if hasattr(self, "camera_hud"):
            self.camera_hud.set_angles(elevation, azimuth, pitch)

    def swap_camera_view_direction(self, view_key):
        view = getattr(self, "_camera_view", None)
        if view is None:
            return -1

        direction = getattr(self, "_camera_direction", True)
        return self.set_camera_view(view, not direction)

    def _toggle_appearance_panel(self):
        panel = self.appearance_panel
        if panel.isVisible():
            panel.hide()
            return
        m = panel._MARGIN
        pos = self._tab_gear.mapToGlobal(self._tab_gear.rect().bottomRight())
        panel.move(max(0, pos.x() - panel.width() + m), pos.y() + 4 - m)
        panel.show()
        panel.raise_()

    def _on_theme_toggled(self, checked):
        from .stylesheets import Colors, switch_theme

        Settings.ui.theme_mode = "dark" if checked else "light"
        switch_theme(Colors.DARK if checked else Colors.LIGHT)

    def _on_theme_changed(self):
        self._update_style()
        self._main_splitter.setStyleSheet(
            "QSplitter::handle { background: transparent; }"
        )
        self.ribbon_separator.setStyleSheet(f"background: {Colors.BORDER_DARK};")

        self.tab_bar._on_theme_changed()
        if hasattr(self, "_tab_gear"):
            self._tab_gear.setIcon(icon("ph.gear", role="muted"))
        if hasattr(self, "_session_list_widget"):
            self._session_list_widget._on_theme_changed()

    def _update_style(self):
        self.setStyleSheet(
            f"""
            QMenuBar {{
                border-bottom: 1px solid {Colors.BORDER_DARK};
            }}
            QMenuBar::item {{
                padding: 4px 8px;
            }}
            QMenuBar::item:selected {{
                background-color: {Colors.BG_HOVER};
                border-radius: 4px;
            }}
        """
        )

    def changeEvent(self, event):
        if event.type() == QEvent.Type.PaletteChange:
            self._update_style()
        super().changeEvent(event)

    def setup_widgets(self):
        self.legend = LegendWidget(self.renderer, self.interactor)

        self._setup_volume_viewer()
        self._setup_camera_hud()
        self.cdata.data.render_update.connect(
            self.volume_viewer.primary.handle_projection_change
        )
        self.cdata.models.render_update.connect(
            self.volume_viewer.primary.handle_projection_change
        )

        self.cursor_handler = CursorModeHandler(self.vtk_widget)
        self.axes_widget = AxesWidget(self.renderer, self.interactor)
        self.trajectory_player = TrajectoryPlayer(self.cdata)
        self.scale_bar = ScaleBarWidget(self.renderer, self.interactor)
        self.screenshot_manager = ScreenshotManager(self.vtk_widget)
        self.status_indicator = StatusIndicator(self)

        self.bbox_manager = BoundingBoxManager(
            self.renderer, self.interactor, self.cdata
        )

        self.status_indicator.connect_signals()

        from .widgets.appsettings import AppSettingsPanel

        # Gear button is connected after tab bar creation in __init__
        self.appearance_panel = AppSettingsPanel(self)
        self.appearance_panel.settingsChanged.connect(self.apply_render_settings)

        self._setup_trajectory_player()

        self.viewport_placeholder = ViewportPlaceholder(
            self.vtk_widget, actions=default_actions(self)
        )
        self.viewport_stack.addWidget(self.viewport_placeholder)
        self.prime_viewport_placeholder()

    def prime_viewport_placeholder(self):
        """Show the placeholder and auto-hide once data arrives."""
        self.viewport_stack.setCurrentWidget(self.viewport_placeholder)
        self._placeholder_connections = []

        def _on_data_arrived():
            if (
                len(self.cdata._data.data) > 0
                or len(self.cdata._models.data) > 0
                or self.volume_viewer.primary.volume is not None
            ):
                self.viewport_stack.setCurrentWidget(self.vtk_widget)
                for sig in self._placeholder_connections:
                    sig.disconnect(_on_data_arrived)
                self._placeholder_connections.clear()

        for sig in (
            self.cdata.data.data_changed,
            self.cdata.models.data_changed,
            self.volume_viewer.primary.data_changed,
        ):
            sig.connect(_on_data_arrived)
            self._placeholder_connections.append(sig)

    def setup_menu(self):
        self._update_style()

        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        view_menu = menu_bar.addMenu("View")
        interact_menu = menu_bar.addMenu("Actions")
        preference_menu = menu_bar.addMenu("Preferences")

        new_session_action = QAction(icon("ph.folder-notch-open"), "Load Session", self)
        new_session_action.triggered.connect(self.load_session)
        new_session_action.setShortcut("Ctrl+N")

        add_file_action = QAction(icon("ph.folder-open"), "Open", self)
        add_file_action.triggered.connect(self.open_files)
        add_file_action.setShortcut("Ctrl+O")

        undo_action = QAction(icon("ph.arrow-u-up-left"), "Undo", self)
        undo_action.triggered.connect(
            lambda: (self.cdata.data.undo(), self.cdata.models.undo())
        )
        undo_action.setShortcut("Ctrl+Z")

        save_file_action = QAction(icon("ph.floppy-disk"), "Save Session", self)
        save_file_action.triggered.connect(self.save_session)
        save_file_action.setShortcut("Ctrl+S")

        close_file_action = QAction(icon("ph.x-circle"), "Close Session", self)
        close_file_action.triggered.connect(lambda: self.close_session(True))

        self.recent_file_actions = []
        self.recent_menu = QMenu("Recent Files", self)
        self.recent_menu.setIcon(icon("ph.clock-counter-clockwise"))
        for i in range(Settings.ui.max_recent_files):
            action = QAction(self)
            action.setVisible(False)
            action.triggered.connect(self._open_recent_file)
            self.recent_file_actions.append(action)
            self.recent_menu.addAction(action)

        self.update_recent_files_menu()

        quit_action = QAction(icon("ph.sign-out"), "Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)

        screenshot_action = QAction(icon("ph.camera"), "Save Viewer Screenshot", self)
        screenshot_action.triggered.connect(lambda x: self.screenshot_manager.save())
        screenshot_action.setShortcut("Ctrl+P")

        animation_action = QAction(icon("ph.film-strip"), "Export Animation", self)
        animation_action.triggered.connect(lambda x: self._animate())
        animation_action.setShortcut("Ctrl+E")

        clipboard_action = QAction(
            icon("ph.clipboard"), "Viewer Screenshot to Clipboard", self
        )
        clipboard_action.triggered.connect(
            lambda x: self.screenshot_manager.copy_to_clipboard()
        )
        clipboard_action.setShortcut("Ctrl+Shift+C")

        clipboard_window_action = QAction(
            icon("ph.app-window"), "Window Screenshot to Clipboard", self
        )
        clipboard_window_action.triggered.connect(
            lambda x: self.screenshot_manager.copy_to_clipboard(window=True)
        )
        clipboard_window_action.setShortcut("Ctrl+Shift+W")

        axes_menu = QMenu("Axes", self)
        axes_menu.setIcon(icon("ph.crosshair"))
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

        show_camera_hud = QAction(icon("ph.video-camera"), "Camera Angles", self)
        show_camera_hud._on = False

        def _toggle_camera_hud():
            show_camera_hud._on = not show_camera_hud._on
            on = show_camera_hud._on
            show_camera_hud.setIcon(
                icon("ph.video-camera", role="primary" if on else "muted")
            )
            self.camera_hud.setVisible(on)

        show_camera_hud.triggered.connect(_toggle_camera_hud)

        coloring_menu = QMenu("Coloring", self)
        coloring_menu.setIcon(icon("ph.palette"))
        coloring_group = QActionGroup(self)
        coloring_group.setExclusive(True)

        self.color_default_action = QAction("Default", self)
        self.color_default_action.setCheckable(True)
        self.color_default_action.setChecked(True)
        self.color_default_action.triggered.connect(
            lambda: self.cdata.set_coloring_mode("default")
        )
        coloring_group.addAction(self.color_default_action)

        self.color_by_entity_action = QAction("By Entity", self)
        self.color_by_entity_action.setCheckable(True)
        self.color_by_entity_action.triggered.connect(
            lambda: self.cdata.set_coloring_mode("entity")
        )
        coloring_group.addAction(self.color_by_entity_action)

        coloring_menu.addAction(self.color_default_action)
        coloring_menu.addAction(self.color_by_entity_action)

        show_legend = QAction(icon("ph.chart-bar"), "Legend", self)
        show_legend._on = False

        def _toggle_legend():
            show_legend._on = not show_legend._on
            on = show_legend._on
            show_legend.setIcon(icon("ph.chart-bar", role="primary" if on else "muted"))
            self.legend.show() if on else self.legend.hide()

        show_legend.triggered.connect(_toggle_legend)

        self.volume_action = QAction(icon("ph.cube"), "Volume Viewer", self)
        self.volume_action._on = False

        def _toggle_volume():
            self.volume_action._on = not self.volume_action._on
            on = self.volume_action._on
            self.volume_action.setIcon(
                icon("ph.cube", role="primary" if on else "muted")
            )
            self._toggle_volume_dock(on)

        self.volume_action.triggered.connect(_toggle_volume)

        self.trajectory_action = QAction(
            icon("ph.play-circle"), "Trajectory Player", self
        )
        self.trajectory_action._on = False

        def _toggle_trajectory():
            self.trajectory_action._on = not self.trajectory_action._on
            on = self.trajectory_action._on
            self.trajectory_action.setIcon(
                icon("ph.play-circle", role="primary" if on else "muted")
            )
            toggle_dock(self.trajectory_dock, on)

        self.trajectory_action.triggered.connect(_toggle_trajectory)

        file_menu.addAction(add_file_action)
        file_menu.addMenu(self.recent_menu)

        file_menu.addSeparator()
        file_menu.addAction(new_session_action)
        file_menu.addAction(save_file_action)
        file_menu.addAction(close_file_action)

        file_menu.addSeparator()
        batch_process_action = QAction(icon("ph.stack"), "Batch Processing", self)
        batch_process_action.triggered.connect(self.open_batch_pipeline)
        batch_process_action.setShortcut("Ctrl+Shift+P")

        self.batch_navigator_action = QAction(
            icon("ph.compass"), "Batch Navigator", self
        )
        self.batch_navigator_action.triggered.connect(self.open_batch_navigator)
        self.batch_navigator_action.setShortcut("Ctrl+Shift+N")

        czi_action = QAction(icon("ph.cloud"), "CZI Portal", self)
        czi_action.triggered.connect(self.open_czi_dialog)

        file_menu.addAction(batch_process_action)
        file_menu.addAction(self.batch_navigator_action)
        file_menu.addAction(czi_action)

        file_menu.addSeparator()
        file_menu.addAction(screenshot_action)
        file_menu.addAction(clipboard_action)
        file_menu.addAction(clipboard_window_action)
        file_menu.addAction(animation_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        show_scale_bar = QAction(icon("ph.ruler"), "Scale Bar", self)
        show_scale_bar._on = False

        def _toggle_scale_bar():
            show_scale_bar._on = not show_scale_bar._on
            on = show_scale_bar._on
            show_scale_bar.setIcon(icon("ph.ruler", role="primary" if on else "muted"))
            self.scale_bar.show() if on else self.scale_bar.hide()

        show_scale_bar.triggered.connect(_toggle_scale_bar)

        show_viewer_mode = QAction(icon("ph.info", role="primary"), "Status Bar", self)
        show_viewer_mode._on = True

        def _toggle_status_bar():
            show_viewer_mode._on = not show_viewer_mode._on
            on = show_viewer_mode._on
            show_viewer_mode.setIcon(icon("ph.info", role="primary" if on else "muted"))
            self.status_indicator.show() if on else self.status_indicator.hide()

        show_viewer_mode.triggered.connect(_toggle_status_bar)

        view_menu.addMenu(axes_menu)
        view_menu.addMenu(coloring_menu)

        view_menu.addSeparator()
        view_menu.addAction(show_legend)
        view_menu.addAction(show_scale_bar)
        view_menu.addAction(show_viewer_mode)
        view_menu.addAction(show_camera_hud)

        view_menu.addSeparator()

        xy_action = QAction("XY-Plane", self)
        xy_action.setText("Top View (XY)\tz")
        xy_action.triggered.connect(lambda: self.simulate_key_press("z"))
        yz_action = QAction("YZ-Plane", self)
        yz_action.setText("Side View (YZ)\tx")
        yz_action.triggered.connect(lambda: self.simulate_key_press("x"))
        xz_action = QAction("XZ-Plane", self)
        xz_action.setText("Front View (XZ)\tc")
        xz_action.triggered.connect(lambda: self.simulate_key_press("c"))

        flip_action = QAction(icon("ph.swap"), "Flip View lambda", self)
        flip_action.setText("Flip View Axis \tv")
        flip_action.triggered.connect(lambda: self.simulate_key_press("v"))

        view_menu.addAction(xy_action)
        view_menu.addAction(yz_action)
        view_menu.addAction(xz_action)
        view_menu.addAction(flip_action)
        view_menu.addSeparator()

        view_menu.addAction(self.volume_action)
        view_menu.addAction(self.trajectory_action)
        view_menu.addSeparator()

        bbox_menu = QMenu("Bounding Boxes", self)
        bbox_menu.setIcon(icon("ph.bounding-box"))

        self.computed_bbox = QAction("Dataset Bounds", self)
        self.computed_bbox.setCheckable(True)
        self.computed_bbox.setChecked(False)
        self.computed_bbox.triggered.connect(
            lambda checked: self.bbox_manager.show_dataset_bounds(checked)
        )

        self.dataset_bbox = QAction("Session Bound", self)
        self.dataset_bbox.setCheckable(True)
        self.dataset_bbox.setChecked(False)
        self.dataset_bbox.triggered.connect(
            lambda checked: _handle_session_bounds(checked)
        )

        def _handle_session_bounds(checked):
            self.bbox_manager.show_session_bounds(checked)
            if self.cdata.shape is None:
                self.dataset_bbox.setChecked(False)

        show_all_objects = QAction("Show All Visible", self)
        show_all_objects.triggered.connect(self.bbox_manager.show_all_object_boxes)

        show_selected_objects = QAction("Show Selected", self)
        show_selected_objects.triggered.connect(self.bbox_manager.show_selected_boxes)

        hide_object_boxes = QAction("Hide All", self)
        hide_object_boxes.triggered.connect(self.bbox_manager.clear_object_boxes)

        bbox_menu.addAction(hide_object_boxes)
        bbox_menu.addAction(show_all_objects)
        bbox_menu.addAction(show_selected_objects)
        bbox_menu.addSeparator()
        bbox_menu.addAction(self.computed_bbox)
        bbox_menu.addAction(self.dataset_bbox)

        view_menu.addMenu(bbox_menu)
        view_menu.addSeparator()

        show_settings = QAction(icon("ph.gear"), "Appearance\tCtrl+,", self)
        show_settings.setShortcut("Ctrl+,")
        show_settings.triggered.connect(self.show_app_settings)
        preference_menu.addAction(show_settings)

        viewing_action = QAction(icon("ph.eye"), "Viewing Mode\tEsc", self)
        viewing_action.triggered.connect(lambda: self.handle_escape_key())

        background_action = QAction(
            icon("ph.circle-half"), "Toggle Background\td", self
        )
        background_action.triggered.connect(lambda: self.simulate_key_press("d"))

        selection_action = QAction(icon("ph.cursor"), "Point Selection\tr", self)
        selection_action.triggered.connect(lambda: self.simulate_key_press("r"))

        expand_selection_action = QAction(
            icon("ph.arrows-out"), "Expand Selection\te", self
        )
        expand_selection_action.triggered.connect(lambda: self.simulate_key_press("e"))

        hide_unselected_action = QAction(
            icon("ph.eye-slash"), "Hide Unselected\th", self
        )
        hide_unselected_action.triggered.connect(lambda: self.simulate_key_press("h"))

        show_unselected_action = QAction(
            icon("ph.eye"), "Show Unselected\tShift+H", self
        )
        show_unselected_action.triggered.connect(lambda: self.simulate_key_press("H"))

        picking_action = QAction(
            icon("ph.hand-pointing"), "Pick Objects\tShift+E", self
        )
        picking_action.triggered.connect(lambda: self.simulate_key_press("E"))

        remove_action = QAction(icon("ph.trash"), "Remove Selection\tDelete", self)
        remove_action.triggered.connect(lambda: self.simulate_key_press("\x7f"))

        merge_action = QAction(icon("ph.git-merge"), "Merge Selection", self)
        merge_action.setText("Merge Selection\tm")
        merge_action.triggered.connect(lambda: self.simulate_key_press("m"))

        drawing_action = QAction(icon("ph.pencil-line"), "Free Hand Drawing", self)
        drawing_action.setText("Free Hand Drawing\ta")
        drawing_action.triggered.connect(lambda: self.simulate_key_press("a"))

        curve_action = QAction(icon("ph.path"), "Curve Drawing\tShift+A", self)
        curve_action.triggered.connect(lambda: self.simulate_key_press("A"))

        mesh_delete_action = QAction(
            icon("ph.eraser"), "Delete Mesh Triangles\tq", self
        )
        mesh_delete_action.triggered.connect(lambda: self.simulate_key_press("q"))

        mesh_add_action = QAction(
            icon("ph.polygon"), "Add Mesh Triangles\tShift+Q", self
        )
        mesh_add_action.triggered.connect(lambda: self.simulate_key_press("m"))

        interaction_target_menu = QMenu("Interaction Target", self)
        target_group = QActionGroup(self)
        target_group.setExclusive(True)
        self.cluster_target_action = QAction("Clusters\ts", self)
        self.cluster_target_action.setCheckable(True)
        self.cluster_target_action.setChecked(True)
        self.cluster_target_action.triggered.connect(
            lambda: self.simulate_key_press("s")
        )
        target_group.addAction(self.cluster_target_action)

        self.model_target_action = QAction("Models\ts", self)
        self.model_target_action.setCheckable(True)
        self.model_target_action.triggered.connect(lambda: self.simulate_key_press("s"))
        target_group.addAction(self.model_target_action)
        interaction_target_menu.addAction(self.cluster_target_action)
        interaction_target_menu.addAction(self.model_target_action)

        interact_menu.addAction(undo_action)
        interact_menu.addAction(viewing_action)
        interact_menu.addAction(background_action)
        interact_menu.addSeparator()

        interact_menu.addAction(selection_action)
        interact_menu.addAction(picking_action)
        interact_menu.addMenu(interaction_target_menu)
        interact_menu.addSeparator()

        interact_menu.addAction(merge_action)
        interact_menu.addAction(remove_action)
        interact_menu.addAction(expand_selection_action)
        interact_menu.addSeparator()

        interact_menu.addAction(hide_unselected_action)
        interact_menu.addAction(show_unselected_action)
        interact_menu.addSeparator()

        interact_menu.addAction(drawing_action)
        interact_menu.addAction(curve_action)
        interact_menu.addSeparator()

        interact_menu.addAction(mesh_add_action)
        interact_menu.addAction(mesh_delete_action)

    def open_batch_pipeline(self):
        """Open the PipelineBuilderDialog dialog."""
        from .parallel import submit_task_batch
        from .pipeline.executor import execute_run
        from .pipeline.builder import PipelineBuilderDialog

        dialog = PipelineBuilderDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None

        settings = dialog.get_settings()

        tasks = []
        for run in settings["runs"]:
            skip_complete = settings.get("skip_complete", False)
            tasks.append(
                {
                    "name": f"Pipeline {run['run_id']}",
                    "func": execute_run,
                    "callback": None,
                    "kwargs": {
                        "run_config": run,
                        "skip_complete": skip_complete,
                        "verbose": True,
                    },
                }
            )

        submit_task_batch(tasks, max_concurrent=int(settings.get("workers", 4)))

    def open_batch_navigator(self):
        """Toggle the batch navigator sessions pane in the sidebar."""
        from .widgets.container_list import SessionListWidget

        if not hasattr(self, "_session_list_widget"):
            self._session_list_widget = SessionListWidget(self.cdata)
            self._session_list_widget.load_requested.connect(self._load_session)

        widget = self._session_list_widget

        if "Sessions" in self.list_wrapper._widgets:
            widget.deactivate()
            self.list_wrapper.remove_widget("Sessions")
            self.batch_navigator_action.setIcon(icon("ph.compass", role="muted"))
        else:
            self.list_wrapper.add_widget("Sessions", widget)
            widget.activate()
            self.batch_navigator_action.setIcon(icon("ph.compass", role="primary"))

    def open_czi_dialog(self):
        """Open the CZI CryoET Data Portal browser."""
        try:
            from .czi.dialog import CZIPortalDialog

            if getattr(self, "_czi_dialog", None) is not None:
                self._czi_dialog.raise_()
                self._czi_dialog.activateWindow()
                return

            self._czi_dialog = CZIPortalDialog(self)
            self._czi_dialog.finished.connect(
                lambda: setattr(self, "_czi_dialog", None)
            )
            self._czi_dialog.show()

        except ImportError:
            QMessageBox.warning(self, "Error", "Failed to import CZI dialog.")

    def toggle_selection_menu(self):
        """Update the menu radio buttons to reflect current selection target."""
        if self.model_target_action.isChecked():
            self.cluster_target_action.setChecked(True)
            self.status_indicator.update_status(target="Clusters")
        else:
            self.model_target_action.setChecked(True)
            self.status_indicator.update_status(target="Models")

    def simulate_key_press(self, key):
        self.vtk_widget.setFocus()

        key_code = (
            ord(key.upper())
            if len(key) == 1
            else getattr(Qt.Key, f"Key_{key}", ord(key))
        )

        key_press = QKeyEvent(
            QEvent.Type.KeyPress, key_code, Qt.KeyboardModifier.NoModifier, key
        )

        key_release = QKeyEvent(
            QEvent.Type.KeyRelease, key_code, Qt.KeyboardModifier.NoModifier, key
        )

        QApplication.postEvent(self.vtk_widget, key_press)
        QApplication.postEvent(self.vtk_widget, key_release)
        QApplication.processEvents()

    def _animate(self):
        from .widgets.dock import create_or_toggle_dock
        from mosaic.animation.compose import AnimationComposerDialog

        dialog = AnimationComposerDialog(
            self.vtk_widget, self.volume_viewer, self.cdata
        )
        create_or_toggle_dock(self, "animation_composer", dialog)

    def _setup_camera_hud(self):
        from .widgets.camera_hud import CameraHUD

        self.camera_hud = CameraHUD(parent=self)
        self.camera_hud.attach(self)

    def _setup_volume_viewer(self):
        # HUD is a top-level translucent tool window that tracks the
        # viewport, it is NOT added to any layout. See
        # volume_viewer_hud.py for the rationale.
        self.volume_viewer = VolumeViewerHUD(
            self.vtk_widget, legend=self.legend, parent=self
        )
        self.volume_viewer.attach_to_viewport(self.viewport_container)
        self.cdata.register_session_hook(
            collect=lambda: (
                {"volume_paths": self.volume_viewer.recent_paths}
                if self.volume_viewer.recent_paths
                else {}
            ),
            restore=lambda meta: self.volume_viewer.set_recent_paths(
                meta.get("volume_paths", [])
            ),
        )

    def _load_volume_file(self, path: str) -> None:
        """Show the volume dock if hidden and load *path* into the primary viewer."""
        if not self.volume_viewer.isVisible():
            self.volume_viewer.setVisible(True)
            self.volume_action._on = True
            self.volume_action.setIcon(icon("ph.cube", role="primary"))
        try:
            self.volume_viewer.primary.load_volume(path)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open volume:\n{e}")

    def _triage_volumes(self, volume_paths: list) -> list:
        """Classify volume files and prompt for density maps."""
        from .formats.reader import is_likely_density_map

        density_maps = []
        segmentations = []
        for path in volume_paths:
            try:
                if is_likely_density_map(path):
                    density_maps.append(path)
                else:
                    segmentations.append(path)
            except Exception:
                segmentations.append(path)

        if density_maps:
            self._load_volume_files(density_maps)

        return segmentations

    def _load_volume_files(self, paths: list) -> None:
        """Load each path into its own volume viewer."""
        if not self.volume_viewer.isVisible():
            self.volume_viewer.setVisible(True)
            self.volume_action._on = True
            self.volume_action.setIcon(icon("ph.cube", role="primary"))
        for path in paths:
            try:
                self.volume_viewer.load_into_viewer(path)
                self._add_file_to_recent(path)
            except Exception as e:
                QMessageBox.warning(
                    self, "Error", f"Failed to open volume:\n{path}\n\n{e}"
                )

    def _setup_trajectory_player(self):
        self.trajectory_dock = QDockWidget(parent=self)
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
        self.trajectory_dock.setVisible(False)

    def show_app_settings(self):
        self._toggle_appearance_panel()

    def _load_session(self, file_path: str):
        self.close_session(render=False)

        try:
            self.cdata.load_session(file_path)
        except ValueError as e:
            print(f"Error opening file: {e}")
            return -1

        if hasattr(self, "_session_list_widget"):
            from .pipeline._utils import natural_sort_key

            widget = self._session_list_widget
            if file_path in widget.session_files:
                widget.set_current(file_path)
            else:
                widget.session_files.append(file_path)
                widget.session_files.sort(key=natural_sort_key)
                widget._rebuild_items()
                widget.set_current(file_path)

        self._add_file_to_recent(file_path)

        self.cdata.data.render(defer_render=True)
        self.cdata.models.render(defer_render=True)
        self._camera_view = None
        self.set_camera_view("z")

    def load_session(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(
            self,
            "Open Session",
            "",
            "Session Files (*.mosaic *.pickle)"
            ";;Mosaic Sessions (*.mosaic)"
            ";;Legacy Pickle (*.pickle)",
        )
        if not file_path:
            return -1
        return self._load_session(file_path)

    def close_session(self, render: bool = True):
        if hasattr(self, "_session_list_widget"):
            self._session_list_widget.current_index = -1
            self._session_list_widget._update_highlight()

        self.renderer.RemoveAllViewProps()
        self.volume_viewer.close()

        self.dataset_bbox.setChecked(False)
        self.computed_bbox.setChecked(False)

        if self.scale_bar.visible:
            self.scale_bar.show()

        if self.status_indicator.visible:
            self.status_indicator.show()

        self.cdata.reset()
        self.cdata.data.render(defer_render=True)
        self.cdata.models.render(defer_render=True)
        self.prime_viewport_placeholder()

        if render:
            self.set_camera_view("z")

    def _open_files(self, filenames: List[str]):
        from .formats.session import is_session_file

        if isinstance(filenames, str):
            filenames = [filenames]

        session_hits = [f for f in filenames if is_session_file(f)]
        if session_hits:
            QMessageBox.warning(
                self,
                "Session Files",
                "Use Load Session to open session files:\n" + "\n".join(session_hits),
            )
            return -1

        dialog = ImportDataDialog(self)
        dialog.set_files(filenames)
        if not dialog.exec():
            return -1

        file_parameters = dialog.get_all_parameters()

        from .parallel import submit_io_task

        submit_io_task(
            "Reading Files",
            _read_files_worker,
            self._on_files_read,
            self.cdata,
            filenames,
            file_parameters,
        )

    def _on_files_read(self, results):
        """GUI-thread callback: surface errors, render, recentre camera."""
        from .formats.parser import NotASegmentationError

        density_paths = []
        failures = []
        for filename, outcome in results:
            if isinstance(outcome, NotASegmentationError):
                density_paths.append(filename)
            elif isinstance(outcome, Exception):
                failures.append((filename, str(outcome)))
            else:
                self._add_file_to_recent(filename)

        self.cdata.data.data_changed.emit()
        self.cdata.models.data_changed.emit()
        self.cdata.data.render(defer_render=False)
        self.cdata.models.render(defer_render=False)
        self.set_camera_view("z")

        if density_paths:
            from pathlib import Path

            listing = "\n".join(Path(p).name for p in density_paths)
            box = QMessageBox(self)
            box.setWindowTitle("Not a Segmentation")
            box.setIcon(QMessageBox.Icon.Question)
            box.setText(
                f"{len(density_paths)} file(s) contain more than 10 000 "
                f"unique values and are likely density maps. "
                f"Open in the Volume Viewer?"
            )
            box.setDetailedText(listing)
            yes_btn = box.addButton("Yes", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("No", QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(yes_btn)
            for btn in box.buttons():
                if box.buttonRole(btn) == QMessageBox.ButtonRole.ActionRole:
                    btn.setMinimumWidth(120)
            box.exec()
            if box.clickedButton() is yes_btn:
                self._load_volume_files(density_paths)

        if failures:
            if len(failures) == 1:
                fn, msg = failures[0]
                QMessageBox.warning(self, "Read Failed", f"{fn}\n\n{msg}")
            else:
                lines = [f"{len(failures)} file(s) failed:"]
                for fn, msg in failures[:20]:
                    lines.append(f"  {fn}: {msg}")
                if len(failures) > 20:
                    lines.append(f"  ... and {len(failures) - 20} more")
                QMessageBox.warning(self, "Read Failed", "\n".join(lines))

    def open_files(self):
        filenames, _ = QFileDialog.getOpenFileNames(self, "Import Files")
        if not filenames:
            return -1

        return self._open_files(filenames)

    def _capture_thumbnail(self):
        """Capture a PNG thumbnail cropped to visible data."""
        from .animation._utils import (
            compute_crop_context,
            capture_cropped,
            restore_window_size,
        )
        from qtpy.QtGui import QImage
        from qtpy.QtCore import QBuffer, QIODevice

        try:
            rw = self.vtk_widget.GetRenderWindow()
            ctx = compute_crop_context(rw, 320, 240)
            if ctx is None:
                return None
            frame = capture_cropped(rw, ctx)
            restore_window_size(rw, ctx)

            h, w = frame.shape[:2]
            channels = frame.shape[2] if frame.ndim == 3 else 1
            fmt = (
                QImage.Format.Format_RGBA8888
                if channels == 4
                else QImage.Format.Format_RGB888
            )
            img = QImage(frame.data, w, h, w * channels, fmt)
            buf = QBuffer()
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            img.save(buf, "PNG")
            return bytes(buf.data())
        except Exception:
            return None

    def save_session(self):
        file_dialog = QFileDialog()
        file_dialog.setDefaultSuffix("mosaic")
        file_path, _ = file_dialog.getSaveFileName(
            self,
            "Save File",
            "",
            "Mosaic Sessions (*.mosaic);;Legacy Pickle (*.pickle)",
        )
        if not file_path:
            return -1

        if not file_path.lower().endswith((".mosaic", ".pickle")):
            file_path += ".mosaic"
        self.cdata.to_file(file_path)

    def update_recent_files_menu(self):
        Settings.ui.recent_files = [x for x in Settings.ui.recent_files if exists(x)]

        files_to_show = list(dict.fromkeys(Settings.ui.recent_files))
        for i, file_path in enumerate(files_to_show):
            text = f"&{i + 1} {os.path.basename(file_path)}"
            self.recent_file_actions[i].setText(text)
            self.recent_file_actions[i].setData(file_path)
            self.recent_file_actions[i].setVisible(True)

        for j in range(len(files_to_show), Settings.ui.max_recent_files):
            self.recent_file_actions[j].setVisible(False)

        self.recent_menu.setEnabled(len(files_to_show) > 0)

    def _add_file_to_recent(self, file_path):
        if file_path in Settings.ui.recent_files:
            return None

        recent_files = [file_path] + list(Settings.ui.recent_files)
        while len(recent_files) > Settings.ui.max_recent_files:
            recent_files.pop()
        Settings.ui.recent_files = list(dict.fromkeys(recent_files))

        self.update_recent_files_menu()

    def _open_recent_file(self):
        action = self.sender()
        if not action:
            return None

        file_path = action.data()
        if not os.path.exists(file_path):
            QMessageBox.critical(self, "Error", f"{file_path} not found.")
            recent_files = list(Settings.ui.recent_files)
            try:
                recent_files.remove(file_path)
            except Exception:
                pass
            Settings.ui.recent_files = recent_files
            return self.update_recent_files_menu()

        from .formats.session import is_session_file

        if is_session_file(file_path):
            return self._load_session(file_path)
        return self._open_files([file_path])

    def _check_for_updates(self):
        from .dialogs import UpdateChecker, UpdateDialog
        from .__version__ import __version__

        def _show_update_dialog(latest_version, release_notes):
            if Settings.ui.skipped_version == latest_version:
                return None
            dialog = UpdateDialog(
                __version__, latest_version, release_notes, parent=self
            )
            dialog.exec()

        # We assign the thread to keep it alive
        self.update_checker = UpdateChecker(__version__)
        self.update_checker.update_available.connect(_show_update_dialog)
        self.update_checker.start()


def _read_files_worker(cdata, filenames, file_parameters):
    """I/O worker: read each file into ``cdata`` and report progress.

    Parameters
    ----------
    cdata : MosaicData
        Application data layer. ``cdata.open_file`` mutates the raw
        ``DataContainer`` instances in place; actor/render work is
        deferred to the GUI callback.
    filenames : list of str
        Files to read, in order.
    file_parameters : dict
        Map of filename to per-file import parameters from
        :class:`ImportDataDialog`.

    Returns
    -------
    list of tuple
        ``(filename, exception_or_None)`` per input file, in input order.
    """
    from pathlib import Path
    from .parallel import report_progress

    results = []
    total = len(filenames)
    for i, fn in enumerate(filenames):
        report_progress(current=i, total=total, message=Path(fn).name)
        params = file_parameters.get(fn, {})
        try:
            cdata.open_file(
                fn,
                offset=params.get("offset", 0),
                scale=params.get("scale", 1),
                sampling_rate=params.get("sampling_rate", 1),
                segmentation=params.get("render_as_segmentation", False),
            )
            results.append((fn, None))
        except Exception as e:
            results.append((fn, e))
    report_progress(current=total, total=total)
    return results
