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
    QPropertyAnimation,
    QEasingCurve,
    QRect,
)
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
    QButtonGroup,
    QShortcut,
    QMessageBox,
    QCheckBox,
    QDialog,
)
from qtpy.QtGui import (
    QAction,
    QGuiApplication,
    QActionGroup,
    QKeyEvent,
    QCursor,
    QDragEnterEvent,
)
import qtawesome as qta
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from .data import MosaicData
from .settings import Settings
from .stylesheets import Colors
from .animation._utils import ScreenshotManager
from .parallel import BackgroundTaskManager
from .tabs import SegmentationTab, ModelTab, IntelligenceTab, DevelopmentTab
from .dialogs import (
    TiltControlDialog,
    ImportDataDialog,
    ProgressDialog,
    AppSettingsDialog,
)
from .widgets import (
    MultiVolumeViewer,
    AxesWidget,
    RibbonToolBar,
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
from .widgets.drop_overlay import DropOverlay


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

        self.cdata = MosaicData(self.vtk_widget)

        self.renderer = vtk.vtkRenderer()
        self.render_window = self.vtk_widget.GetRenderWindow()
        self.render_window.AddRenderer(self.renderer)
        self.apply_render_settings()

        self.interactor = self.vtk_widget.GetRenderWindow().GetInteractor()
        self.interactor.Initialize()
        self.interactor.AddObserver("RightButtonPressEvent", self.on_right_click)
        self.interactor.AddObserver("KeyPressEvent", self.on_key_press)
        self.interactor.SetDesiredUpdateRate(Settings.rendering.target_fps)

        self.tab_bar = QWidget()
        self.tab_bar.setFixedHeight(32)
        tab_layout = QHBoxLayout(self.tab_bar)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(2)

        self.tab_button_group = QButtonGroup(self)
        self.tab_button_group.setExclusive(True)

        self.setup_widgets()
        self.tab_buttons = {}
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

        for index, (tab, name) in enumerate(self.tabs):
            btn = QPushButton(name)
            btn.setObjectName("TabButton")
            btn.setProperty("tab_id", index)
            btn.setCheckable(True)
            self.tab_button_group.addButton(btn, index)

            btn.setStyleSheet(
                f"""
                QPushButton {{
                    border: none;
                    padding: 6px 8px;
                    font-size: 12px;
                    background: transparent;
                    min-width: 90px;
                }}
                QPushButton:checked {{
                    color: {Colors.PRIMARY};
                }}
                QPushButton:focus {{
                    outline: none;
                }}
            """
            )
            tab_layout.addWidget(btn)
            self.tab_buttons[index] = btn

        self.tab_indicator = QWidget(self.tab_bar)
        self.tab_indicator.setFixedHeight(2)
        self.tab_indicator.setStyleSheet(f"background-color: {Colors.PRIMARY};")

        self.tab_indicator_anim = QPropertyAnimation(self.tab_indicator, b"geometry")
        self.tab_indicator_anim.setDuration(150)
        self.tab_indicator_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def update_indicator(tab_id):
            self.tabs[tab_id][0].show_ribbon()
            btn = self.tab_buttons[tab_id]
            QTimer.singleShot(0, lambda: self._animate_tab_indicator(btn))

        self.tab_button_group.idClicked.connect(update_indicator)

        tab_layout.addStretch()
        self.tab_buttons[0].setChecked(True)
        self.tabs[0][0].show_ribbon()

        # Position indicator on first tab after layout is ready
        QTimer.singleShot(0, lambda: self._animate_tab_indicator(self.tab_buttons[0]))

        layout.addWidget(self.tab_bar)
        layout.addWidget(self.tab_ribbon)

        # Create sidebar with Object Browser
        list_wrapper = ObjectBrowserSidebar()
        list_wrapper.set_title("Object Browser")
        list_wrapper.add_widget("cluster", "Clusters", self.cdata.data.data_list)
        list_wrapper.add_widget("model", "Models", self.cdata.models.data_list)

        # Create splitter with sidebar on left, viewport on right
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(list_wrapper)
        splitter.addWidget(self.vtk_widget)
        splitter.setSizes([200, self.width() - 200])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

        self.actor_collection = vtk.vtkActorCollection()
        self.setup_menu()

        self.escape_shortcut = QShortcut(Qt.Key.Key_Escape, self.vtk_widget)
        self.escape_shortcut.activated.connect(self.handle_escape_key)

        QTimer.singleShot(2000, self._check_for_updates)

        self.setAcceptDrops(True)

        from .formats.reader import is_volume_file

        self._import_overlay = DropOverlay("Import", self.vtk_widget)
        self._volume_overlay = DropOverlay(
            "Render Volume", self.volume_viewer, file_filter=is_volume_file
        )
        self._import_overlay.dropped.connect(self._on_import_dropped)
        self._volume_overlay.dropped.connect(self._on_volume_dropped)
        self._import_overlay.drag_ended.connect(self._end_drag)
        self._volume_overlay.drag_ended.connect(self._end_drag)

    def _toggle_volume_dock(self, checked: bool):
        toggle_dock(self.volume_dock, checked)

    def _end_drag(self):
        QApplication.restoreOverrideCursor()
        self._import_overlay.active = False
        self._import_overlay.hide()
        self._volume_overlay.active = False
        self._volume_overlay.hide()
        if getattr(self, "_drag_opened_dock", False):
            self._toggle_volume_dock(False)
            self.volume_action.setChecked(False)
            self._drag_opened_dock = False

    def dragEnterEvent(self, event: QDragEnterEvent):
        if not event.mimeData().hasUrls():
            return
        if not any(url.isLocalFile() for url in event.mimeData().urls()):
            return

        if hasattr(self, "_drag_leave_timer"):
            self._drag_leave_timer.stop()

        event.acceptProposedAction()
        if QApplication.overrideCursor() is None:
            QApplication.setOverrideCursor(QCursor(Qt.DragCopyCursor))

        if self._import_overlay.isVisible():
            return

        from .formats.reader import is_volume_file

        has_volumes = any(
            url.isLocalFile() and is_volume_file(url.toLocalFile())
            for url in event.mimeData().urls()
        )
        if has_volumes and not self.volume_dock.isVisible():
            self._toggle_volume_dock(True)
            self.volume_action.setChecked(True)
            self._drag_opened_dock = True

        self._import_overlay.refit()
        self._import_overlay.show()
        if has_volumes:
            self._volume_overlay.refit()
            self._volume_overlay.show()

    def _handle_import(self, file_paths):
        session_files = [f for f in file_paths if f.lower().endswith(".pickle")]
        data_files = [f for f in file_paths if not f.lower().endswith(".pickle")]

        if session_files:
            if len(session_files) > 1:
                QMessageBox.warning(
                    self,
                    "Multiple Session Files",
                    "Only one session file can be loaded at a time. ",
                )
            self._load_session(session_files[0])

        if data_files:
            self._open_files(data_files)

    def _on_import_dropped(self, paths):
        self._handle_import(paths)

    def sizeHint(self):
        """Provide the preferred size for the main window."""
        screen = QGuiApplication.primaryScreen().geometry()
        return QSize(int(screen.width() * 0.95), int(screen.height() * 0.95))

    def show(self):
        """Override show to position after Qt sizes the window."""
        self.resize(self.sizeHint())
        super().show()

        # Position after showing (when size is established)
        screen = QGuiApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def set_lighting_mode(self, mode: str = "simple"):
        """Apply a lighting/effects mode to the renderer.

        Parameters
        ----------
        mode: str
            Can be one of 'simple', 'soft', 'full', 'flat', 'shadow', 'silhouettes'
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
            passes = vtk.vtkRenderStepsPass()
            ssao = vtk.vtkSSAOPass()
            ssao.SetDelegatePass(passes)
            ssao.SetRadius(200.0)
            ssao.SetKernelSize(64)
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

        elif mode == "shadow":
            passes = vtk.vtkRenderStepsPass()
            shadows = vtk.vtkShadowMapPass()

            seq = vtk.vtkSequencePass()
            collection = vtk.vtkRenderPassCollection()
            collection.AddItem(shadows.GetShadowMapBakerPass())
            collection.AddItem(passes)
            seq.SetPasses(collection)

            camera_pass = vtk.vtkCameraPass()
            camera_pass.SetDelegatePass(seq)
            renderer.SetPass(camera_pass)

            renderer.RemoveAllLights()
            light = vtk.vtkLight()
            light.SetPosition(1, 1, 1)
            light.SetFocalPoint(0, 0, 0)
            light.SetColor(1.0, 1.0, 0.95)
            light.SetPositional(True)
            light.SetConeAngle(60)
            renderer.AddLight(light)

        elif mode == "silhouettes":
            passes = vtk.vtkRenderStepsPass()
            sobel = vtk.vtkSobelGradientMagnitudePass()
            sobel.SetDelegatePass(passes)
            renderer.SetPass(sobel)

    def apply_render_settings(self):
        self.renderer.SetBackground(
            *[float(x) for x in Settings.rendering.background_color]
        )
        self.renderer_next_background = [
            float(x) for x in Settings.rendering.background_color_alt
        ]

        self.renderer.GradientBackgroundOff()
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

        BackgroundTaskManager.instance()._initialize()

    def _animate_tab_indicator(self, btn):
        """Animate the tab indicator to the given button."""
        from qtpy.QtGui import QFontMetrics

        # Calculate text width
        fm = QFontMetrics(btn.font())
        text_width = fm.horizontalAdvance(btn.text())

        # Center the indicator under the text
        btn_center = btn.x() + btn.width() // 2
        x = btn_center - text_width // 2
        y = self.tab_bar.height() - 2

        target_rect = QRect(x, y, text_width, 2)

        if self.tab_indicator_anim.state() == QPropertyAnimation.State.Running:
            self.tab_indicator_anim.stop()

        self.tab_indicator_anim.setStartValue(self.tab_indicator.geometry())
        self.tab_indicator_anim.setEndValue(target_rect)
        self.tab_indicator_anim.start()

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

    def swap_camera_view_direction(self, view_key):
        view = getattr(self, "_camera_view", None)
        if view is None:
            return -1

        direction = getattr(self, "_camera_direction", True)
        return self.set_camera_view(view, not direction)

    def _update_style(self):
        self.setStyleSheet(
            f"""
            QMenuBar {{
                border-bottom: 1px solid {Colors.TEXT_MUTED};
            }}
            QMenuBar::item {{
                padding: 4px 8px;
            }}
            QMenuBar::item:selected {{
                background-color: {Colors.BG_HOVER};
                border-radius: 4px;
            }}
            QMenu {{
                border-radius: 4px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 4px 24px 4px 8px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {Colors.BG_HOVER};
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

        self._setup_trajectory_player()

    def setup_menu(self):
        self._update_style()

        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        view_menu = menu_bar.addMenu("View")
        interact_menu = menu_bar.addMenu("Actions")
        preference_menu = menu_bar.addMenu("Preferences")

        new_session_action = QAction("Load Session", self)
        new_session_action.triggered.connect(self.load_session)
        new_session_action.setShortcut("Ctrl+N")

        add_file_action = QAction("Open", self)
        add_file_action.triggered.connect(self.open_files)
        add_file_action.setShortcut("Ctrl+O")

        undo_action = QAction("Undo", self)
        undo_action.triggered.connect(
            lambda: (self.cdata.data.undo(), self.cdata.models.undo())
        )
        undo_action.setShortcut("Ctrl+Z")

        save_file_action = QAction("Save Session", self)
        save_file_action.triggered.connect(self.save_session)
        save_file_action.setShortcut("Ctrl+S")

        close_file_action = QAction("Close Session", self)
        close_file_action.triggered.connect(self.close_session)

        self.recent_file_actions = []
        self.recent_menu = QMenu("Recent Files", self)
        for i in range(Settings.ui.max_recent_files):
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
        screenshot_action.triggered.connect(lambda x: self.screenshot_manager.save())
        screenshot_action.setShortcut("Ctrl+P")

        animation_action = QAction("Export Animation", self)
        animation_action.triggered.connect(lambda x: self._animate())
        animation_action.setShortcut("Ctrl+E")

        clipboard_action = QAction("Viewer Screenshot to Clipboard", self)
        clipboard_action.triggered.connect(
            lambda x: self.screenshot_manager.copy_to_clipboard()
        )
        clipboard_action.setShortcut("Ctrl+Shift+C")

        clipboard_window_action = QAction("Window Screenshot to Clipboard", self)
        clipboard_window_action.triggered.connect(
            lambda x: self.screenshot_manager.copy_to_clipboard(window=True)
        )
        clipboard_window_action.setShortcut("Ctrl+Shift+W")

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

        tilt_menu = QMenu("Camera", self)
        self.tilt_dialog = TiltControlDialog(self)
        show_tilt_control = QAction(
            qta.icon("ph.sliders", color=Colors.ICON),
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
            qta.icon("ph.arrow-counter-clockwise", color=Colors.ICON),
            "Reset Tilt",
            self,
        )
        reset_action.setShortcut("Ctrl+T")
        reset_action.triggered.connect(self.tilt_dialog.reset_tilt)
        tilt_menu.addAction(reset_action)

        coloring_menu = QMenu("Coloring", self)
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
        self.volume_action.triggered.connect(self._toggle_volume_dock)

        self.trajectory_action = QAction("Trajectory Player", self)
        self.trajectory_action.setCheckable(True)
        self.trajectory_action.setChecked(False)
        self.trajectory_action.triggered.connect(
            lambda checked: toggle_dock(self.trajectory_dock, checked)
        )

        file_menu.addAction(add_file_action)
        file_menu.addMenu(self.recent_menu)

        file_menu.addSeparator()
        file_menu.addAction(new_session_action)
        file_menu.addAction(save_file_action)
        file_menu.addAction(close_file_action)

        file_menu.addSeparator()
        batch_process_action = QAction("Batch Processing", self)
        batch_process_action.triggered.connect(self.open_batch_pipeline)
        batch_process_action.setShortcut("Ctrl+Shift+P")

        batch_navigator_action = QAction("Batch Navigator", self)
        batch_navigator_action.triggered.connect(self.open_batch_navigator)
        batch_navigator_action.setShortcut("Ctrl+Shift+N")

        czi_action = QAction("CZI Portal", self)
        czi_action.triggered.connect(self.open_czi_dialog)

        file_menu.addAction(batch_process_action)
        file_menu.addAction(batch_navigator_action)
        file_menu.addAction(czi_action)

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

        show_viewer_mode = QAction("Status Bar", self)
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
        view_menu.addMenu(coloring_menu)

        view_menu.addSeparator()
        view_menu.addAction(show_scale_bar)
        view_menu.addAction(show_viewer_mode)

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

        flip_action = QAction("Flip View lambda", self)
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

        show_settings = QAction("Appearance", self)
        show_settings.triggered.connect(self.show_app_settings)
        preference_menu.addAction(show_settings)

        viewing_action = QAction("Viewing Mode\tEsc", self)
        viewing_action.triggered.connect(lambda: self.handle_escape_key())

        background_action = QAction("Toggle Background\td", self)
        background_action.triggered.connect(lambda: self.simulate_key_press("d"))

        selection_action = QAction("Point Selection\tr", self)
        selection_action.triggered.connect(lambda: self.simulate_key_press("r"))

        expand_selection_action = QAction("Expand Selection\te", self)
        expand_selection_action.triggered.connect(lambda: self.simulate_key_press("e"))

        hide_unselected_action = QAction("Hide Unselected\th", self)
        hide_unselected_action.triggered.connect(lambda: self.simulate_key_press("h"))

        show_unselected_action = QAction("Show Unselected\tShift+H", self)
        show_unselected_action.triggered.connect(lambda: self.simulate_key_press("H"))

        picking_action = QAction("Pick Objects\tShift+E", self)
        picking_action.triggered.connect(lambda: self.simulate_key_press("E"))

        remove_action = QAction("Remove Selection\tDelete", self)
        remove_action.triggered.connect(lambda: self.simulate_key_press("\x7f"))

        merge_action = QAction("Merge Selection", self)
        merge_action.setText("Merge Selection\tm")
        merge_action.triggered.connect(lambda: self.simulate_key_press("m"))

        drawing_action = QAction("Free Hand Drawing", self)
        drawing_action.setText("Free Hand Drawing\ta")
        drawing_action.triggered.connect(lambda: self.simulate_key_press("a"))

        curve_action = QAction("Curve Drawing\tShift+A", self)
        curve_action.triggered.connect(lambda: self.simulate_key_press("A"))

        mesh_delete_action = QAction("Delete Mesh Triangles\tq", self)
        mesh_delete_action.triggered.connect(lambda: self.simulate_key_press("q"))

        mesh_add_action = QAction("Add Mesh Triangles\tShift+Q", self)
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
        from .pipeline.dialog import PipelineBuilderDialog

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
        """Open the batch navigator dialog."""
        from .widgets.dock import create_or_toggle_dock
        from .pipeline.dialog import BatchNavigatorDialog

        dialog = BatchNavigatorDialog(self)
        create_or_toggle_dock(self, "batch_navigator", dialog)

    def open_czi_dialog(self):
        """Open the CZI CryoET Data Portal browser."""
        try:
            from .formats.czi.dialog import CZIPortalDialog

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

    def _setup_volume_viewer(self):
        self.volume_viewer = MultiVolumeViewer(self.vtk_widget, legend=self.legend)

        self.volume_dock = QDockWidget(parent=self)
        self.volume_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.volume_dock.setTitleBarWidget(QWidget())

        self.volume_dock.setWidget(self.volume_viewer)
        self.addDockWidget(
            Qt.DockWidgetArea.BottomDockWidgetArea,
            self.volume_dock,
            Qt.Orientation.Vertical,
        )
        self.volume_dock.setVisible(False)

    def _on_volume_dropped(self, paths):
        self._drag_opened_dock = False
        if not self.volume_dock.isVisible():
            self.volume_dock.setVisible(True)
            self.volume_action.setChecked(True)
        for path in paths:
            try:
                self.volume_viewer.primary.load_volume(path)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to open volume:\n{e}")

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
        dialog = AppSettingsDialog(self)
        dialog.settingsChanged.connect(self.apply_render_settings)
        if dialog.exec() == 1:
            return self.apply_render_settings()

    def _load_session(self, file_path: str):
        self.close_session(render=False)

        try:
            self.cdata.load_session(file_path)
        except ValueError as e:
            print(f"Error opening file: {e}")
            return -1

        batch_navigator = getattr(self, "batch_navigator", None)
        if batch_navigator is not None:
            batch_navigator = batch_navigator.widget()
            if file_path in batch_navigator.session_files:
                batch_navigator.current_index = batch_navigator.session_files.index(
                    file_path
                )
            else:
                batch_navigator.session_files.append(file_path)
                batch_navigator.current_index = len(batch_navigator.session_files) - 1
            batch_navigator._populate_session_list()

        self._add_file_to_recent(file_path)

        self.cdata.data.render(defer_render=True)
        self.cdata.models.render(defer_render=True)
        self._camera_view = None
        self.set_camera_view("z")

    def load_session(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Open Session")
        if not file_path:
            return -1
        return self._load_session(file_path)

    def close_session(self, render: bool = True):
        batch_navigator = getattr(self, "batch_navigator", None)
        if batch_navigator is not None:
            batch_navigator.widget()._reset_selection()

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
        if render:
            self.set_camera_view("z")

    def _open_file(self, filename, parameters):
        try:
            self.cdata.open_file(
                filename,
                offset=parameters.get("offset", 0),
                scale=parameters.get("scale", 1),
                sampling_rate=parameters.get("sampling_rate", 1),
                segmentation=parameters.get("render_as_segmentation", False),
            )
        except Exception as e:
            if filename.endswith(".pickle"):
                raise ValueError("Use Load Session to open session files.")
            raise e

    def _open_files(self, filenames: List[str]):
        dialog = ImportDataDialog(self)
        if isinstance(filenames, str):
            filenames = [filenames]

        dialog.set_files(filenames)
        if not dialog.exec():
            return -1

        file_parameters = dialog.get_all_parameters()
        with ProgressDialog(filenames, title="Reading Files", parent=None) as pbar:
            for filename in pbar:
                self._open_file(filename, file_parameters[filename])
                self._add_file_to_recent(filename)

        self.cdata.data.data_changed.emit()
        self.cdata.models.data_changed.emit()
        self.cdata.data.render(defer_render=False)
        self.cdata.models.render(defer_render=False)

        # Make sure loaded objects are visible in scene
        self.set_camera_view("z")

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

        if not file_path.lower().endswith(".pickle"):
            file_path += ".pickle"
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

        if file_path.endswith(".pickle"):
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


def show_large_file_warning() -> bool:
    if Settings.warnings.suppress_large_file_warning:
        return True

    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Icon.Warning)
    msg_box.setWindowTitle("Large File Detected")

    msg_box.setText(
        "Large File Warning\n\n"
        "We found one or more files exceeding 10 million points."
    )

    msg_box.setInformativeText(
        "Please make sure this is a segmentation and not raw data. "
        "If you are on a laptop without dedicated GPU, consider reducing the number "
        "of points for a smooth experience using Segmentation > Downsample "
        "or process in batches."
    )

    msg_box.setStandardButtons(
        QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
    )
    msg_box.setDefaultButton(QMessageBox.StandardButton.Ok)
    msg_box.button(QMessageBox.StandardButton.Ok).setText("Accept")
    msg_box.button(QMessageBox.StandardButton.Cancel).setText("Skip File")

    help_button = msg_box.addButton("Help", QMessageBox.ButtonRole.HelpRole)

    def open_documentation():
        import webbrowser

        webbrowser.open(
            "https://kosinskilab.github.io/mosaic/tutorial/reference/troubleshooting.html#performance-issues"
        )

    help_button.clicked.connect(open_documentation)

    checkbox = QCheckBox("Don't show this warning again")
    msg_box.setCheckBox(checkbox)

    result = msg_box.exec()

    if checkbox.isChecked():
        Settings.warnings.suppress_large_file_warning = True

    return result == QMessageBox.StandardButton.Ok
