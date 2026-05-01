"""
Getting Started onboarding chapter.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import urllib.request
from pathlib import Path

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from . import register
from ..base import OnboardingChapter, OnboardingStep

_BASE = "https://oc.embl.de/index.php/s/KhbLe0Y1JI61ct8/download"
_DOWNLOADS = (
    (
        f"{_BASE}?path=%2F&files=tomogram_solvated_ctf_noise.mrc",
        "tomogram_solvated_ctf_noise.mrc",
    ),
    (f"{_BASE}?path=%2F&files=segmentation.mrc", "segmentation.mrc"),
    (f"{_BASE}?path=%2Fresults&files=ha_coordinates.star", "ha_coordinates.star"),
    (f"{_BASE}?path=%2Fresults&files=na_coordinates.star", "na_coordinates.star"),
    (f"{_BASE}?path=%2Ftemplates&files=ha_6.8_aligned.mrc", "ha_6.8_aligned.mrc"),
    (f"{_BASE}?path=%2Ftemplates&files=na_6.8_aligned.mrc", "na_6.8_aligned.mrc"),
)
_SAMPLING_RATE = 6.8


@register
class BasicsChapter(OnboardingChapter):
    id = "basics"
    title = "Getting Started"
    description = (
        "First analysis with a real cryo-ET dataset: import, mesh, and analyze"
    )
    duration = "~20 min"

    def __init__(self):
        super().__init__()
        self._data_dir: Path | None = None
        self._segmentation_loaded = False
        self._proteins_loaded = False
        self._volume_loaded = False

    def _download(self, parent) -> bool:
        from mosaic.widgets import MosaicMessageBox
        from mosaic.stylesheets import Colors, Typography

        assert self._data_dir is not None
        n = len(_DOWNLOADS)

        dlg = QDialog(parent)
        dlg.setWindowTitle("Mosaic")
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.CustomizeWindowHint
        )
        dlg.setFixedWidth(460)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(36, 32, 36, 32)
        layout.setSpacing(0)

        heading = QLabel("Downloading sample data")
        heading.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY};"
            f"font-size: {Typography.BODY + 2}px;"
            "font-weight: 600;"
        )

        status = QLabel("Starting")
        status.setStyleSheet(
            f"color: {Colors.TEXT_MUTED};" f"font-size: {Typography.SMALL}px;"
        )

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(6)
        bar.setStyleSheet(
            f"QProgressBar {{ border: none; background-color: {Colors.BG_TERTIARY};"
            "border-radius: 3px; }"
            f"QProgressBar::chunk {{ background-color: {Colors.PRIMARY};"
            "border-radius: 3px; }"
        )

        pct_label = QLabel("0%")
        pct_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        pct_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED};" f"font-size: {Typography.CAPTION}px;"
        )

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(cancel_btn)

        layout.addWidget(heading)
        layout.addSpacing(6)
        layout.addWidget(status)
        layout.addSpacing(20)
        layout.addWidget(bar)
        layout.addSpacing(6)
        layout.addWidget(pct_label)
        layout.addSpacing(20)
        layout.addLayout(button_row)

        state = {"cancelled": False}

        def on_reject():
            state["cancelled"] = True

        dlg.rejected.connect(on_reject)
        cancel_btn.clicked.connect(dlg.reject)

        dlg.show()
        QApplication.processEvents()

        dest: Path | None = None
        for i, (url, rel) in enumerate(_DOWNLOADS):
            if state["cancelled"]:
                break
            dest = self._data_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            base = i / n

            status.setText(dest.name)
            QApplication.processEvents()

            try:
                response = urllib.request.urlopen(url)
                file_size = int(response.headers.get("Content-Length", 0))
                downloaded = 0

                with open(dest, "wb") as f:
                    while True:
                        if state["cancelled"]:
                            break
                        chunk = response.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if file_size > 0:
                            pct = int((base + downloaded / file_size / n) * 100)
                            bar.setValue(pct)
                            pct_label.setText(f"{pct}%")
                        QApplication.processEvents()

            except Exception as e:
                dest.unlink(missing_ok=True)
                dlg.close()
                MosaicMessageBox.warning(
                    parent,
                    "Download Failed",
                    f"Could not download {dest.name}:\n{e}\n\n"
                    "Check your connection and try 'mosaic --onboard basics' again.",
                )
                return False

        if state["cancelled"]:
            if dest is not None:
                dest.unlink(missing_ok=True)
            dlg.close()
            return False

        bar.setValue(100)
        pct_label.setText("100%")
        QApplication.processEvents()
        dlg.close()
        return True

    def _files_present(self) -> bool:
        assert self._data_dir is not None
        return all((self._data_dir / rel).exists() for _, rel in _DOWNLOADS)

    def _gate(self, flag: str):
        """Return ``(data_dir, main_window)`` and arm *flag*, or None if already run."""
        if getattr(self, flag) or self._data_dir is None or self._main_window is None:
            return None
        setattr(self, flag, True)
        return self._data_dir, self._main_window

    def _ensure_segmentation_loaded(self) -> None:
        gated = self._gate("_segmentation_loaded")
        if gated is None:
            return None
        data_dir, window = gated
        window.cdata.reset()

        seg = data_dir / "segmentation.mrc"
        if seg.exists():
            window.cdata.open_file(
                str(seg), sampling_rate=_SAMPLING_RATE, scale=_SAMPLING_RATE
            )

        window.cdata.data.data_changed.emit()
        window.cdata.data.render(defer_render=False)
        window.set_camera_view("z")

    def _ensure_proteins_loaded(self) -> None:
        gated = self._gate("_proteins_loaded")
        if gated is None:
            return None
        data_dir, window = gated

        for star in (
            data_dir / "ha_coordinates.star",
            data_dir / "na_coordinates.star",
        ):
            if star.exists():
                window.cdata.open_file(
                    str(star), sampling_rate=_SAMPLING_RATE, scale=_SAMPLING_RATE
                )

        window.cdata.data.data_changed.emit()
        window.cdata.data.render(defer_render=False)

    def _ensure_volume_loaded(self) -> None:
        gated = self._gate("_volume_loaded")
        if gated is None:
            return None
        data_dir, window = gated

        tomogram = data_dir / "tomogram_solvated_ctf_noise.mrc"
        if tomogram.exists():
            window._load_volume_file(str(tomogram))

    def _switch_to_segmentation_tab(self) -> None:
        if self._main_window is not None:
            self._main_window.tab_bar.setCurrentIndex(0)

    def _after_proteins_model(self) -> None:
        self._attach_protein_templates()
        self._switch_to_segmentation_tab()

    def _attach_protein_templates(self) -> None:
        """Attach the matching density template to ha_coordinates and na_coordinates."""
        if self._main_window is None or self._data_dir is None:
            return None

        container = self._main_window.cdata.data.container
        pairs = {
            "ha_coordinates": "ha_6.8_aligned.mrc",
            "na_coordinates": "na_6.8_aligned.mrc",
        }
        for geom in list(container.data):
            name = geom._meta.get("name", "")
            for prefix, template in pairs.items():
                if not name.startswith(prefix):
                    continue
                template_path = self._data_dir / template
                if not template_path.exists():
                    continue
                params = dict(geom._appearance)
                params["volume_path"] = str(template_path)
                params["scale"] = -1.0
                params["reattach_volume"] = True
                params["sampling_rate"] = geom.sampling_rate
                container.update_appearance([geom.uuid], params)
                break
        self._main_window.cdata.data.data_changed.emit()
        self._main_window.cdata.data.render(defer_render=False)

    def _keep_membrane_clusters(self) -> None:
        """After clustering: keep clusters with at least 300k points (outer + inner membrane)."""
        if self._main_window is None:
            return None

        container = self._main_window.cdata.data.container
        if len(container.data) <= 1:
            return None

        threshold = 300_000
        to_remove = [g.uuid for g in container.data if len(g.points) < threshold]
        if to_remove:
            container.remove(to_remove)

        self._main_window.cdata.data.data_changed.emit()
        self._main_window.cdata.data.render(defer_render=False)

    def _select_outer_membrane(self) -> None:
        """Select the smaller of the remaining clusters (outer membrane sits outside, fewer points)."""
        if self._main_window is None:
            return None
        container = self._main_window.cdata.data.container
        if not len(container.data):
            return None
        outer = min(container.data, key=lambda g: len(g.points))
        self._main_window.cdata.data.set_selection_by_uuid([outer.uuid])

    def _select_latest_for_meshing(self) -> None:
        """Before meshing: hide everything else, select the most recent (downsampled) cluster."""
        if self._main_window is None:
            return None
        container = self._main_window.cdata.data.container
        if not len(container.data):
            return None
        latest = container.data[-1]
        for geom in container.data:
            geom.set_visibility(geom.uuid == latest.uuid)
        self._main_window.cdata.data.set_selection_by_uuid([latest.uuid])
        self._main_window.cdata.data.data_changed.emit()
        self._main_window.cdata.data.render(defer_render=False)

    def _select_new_mesh(self) -> None:
        """After meshing: select the just-created mesh in Models."""
        if self._main_window is None:
            return None
        models = self._main_window.cdata.models.container
        if not len(models.data):
            return None
        latest = models.data[-1]
        self._main_window.cdata.models.set_selection_by_uuid([latest.uuid])
        self._main_window.cdata.models.data_changed.emit()

    def _reload_proteins(self) -> None:
        # Reset the load guard so transition() can retrigger a fresh load
        # even after a snapshot restore swapped state out from under it.
        self._proteins_loaded = False
        self._ensure_proteins_loaded()

    def setup(self, main_window) -> None:
        self._data_dir = Path.cwd() / "mosaic_basics"
        self._data_dir.mkdir(exist_ok=True)

        if not self._files_present() and not self._download(main_window):
            self._data_dir = None
            return

        super().setup(main_window)

    def steps(self) -> list[OnboardingStep]:
        if self._data_dir is None:
            return [
                OnboardingStep(
                    id="cancelled",
                    target="viewport_container",
                    title="Setup Cancelled",
                    body=(
                        "The download failed or was interrupted. "
                        "Run 'mosaic --onboard basics' to try again."
                    ),
                )
            ]

        d = self._data_dir.name

        return [
            OnboardingStep(
                id="welcome",
                target="viewport_container",
                title="Welcome to Mosaic",
                body=(
                    f"Example data has been downloaded to {d}/. "
                    "This tour shows you how to import, clean, mesh, and analyze it. \n\n"
                    "Click Next to get started."
                ),
                position="auto",
                show_spotlight=False,
                dim=False,
            ),
            OnboardingStep(
                id="theme",
                target="theme_toggle",
                title="Set Your Theme",
                body="Pick your theme. Use the toggle to switch between light and dark mode.",
                position="below",
            ),
            OnboardingStep(
                id="open_data",
                target="viewport_container",
                title="Load the Segmentation",
                body=(
                    f"Use File > Open (⌘O / Ctrl+O) or drag segmentation.mrc "
                    f"from {d} into the viewport."
                ),
                position="auto",
                before_next=self.transition(
                    transform=self._ensure_segmentation_loaded,
                    snapshot="segmentation",
                ),
            ),
            OnboardingStep(
                id="open_volume",
                target="viewport_container",
                title="Open the Tomogram",
                body=(
                    "See your data in context.\n\n"
                    "Drag the tomogram into the viewport, "
                    "or open the Volume Viewer via View > Volume Viewer and use the Load button."
                ),
                position="auto",
                before_next=self._ensure_volume_loaded,
            ),
            OnboardingStep(
                id="volume_browse",
                target="volume_viewer",
                title="Browse the Tomogram",
                body=(
                    "Scroll through slices and cross-check the segmentation above.\n\n"
                    "You can also switch the viewing axis, toggle projections, "
                    "adjust the colormap, or add a second viewer."
                ),
                position="above",
            ),
            OnboardingStep(
                id="viewport_nav",
                target="vtk_widget",
                title="Navigate the Viewport",
                body=(
                    "Left-drag rotates, Shift-drag pans, scroll zooms. "
                    "X/Y/Z snap to axes, V flips camera, D toggles background color."
                ),
                position="left",
                before_next=self.transition(restore="segmentation"),
            ),
            OnboardingStep(
                id="object_browser",
                target="list_wrapper",
                title="Pick the Segmentation",
                body="Click the segmentation in the sidebar to select it.",
                position="right",
                mode="action",
                completion_signal="cdata.data.data_list.itemSelectionChanged",
                auto_advance=True,
            ),
            OnboardingStep(
                id="cluster",
                target="tab_ribbon.button('Cluster')",
                title="Separate Signal from Noise",
                body=(
                    "Click Cluster in the ribbon.\n\n"
                    "The raw mask mixes membrane signal with background noise. "
                    "Clustering splits them into connected components. "
                    "Watch the status indicator at the bottom right while it runs."
                ),
                position="above",
                mode="action",
                completion_signal="cdata.data.data_changed",
                auto_advance=True,
            ),
            OnboardingStep(
                id="select_open",
                target="tab_ribbon.button('Select')",
                title="Filter by Cluster Size",
                body="Click Select to open the size filter.",
                position="above",
                mode="action",
                completion_signal="tab_ribbon.button('Select').clicked",
                auto_advance=True,
                # cluster cdata.data.data_changed will fire on first added object.
                # We avoid storing that by taking the snapshot here
                before_next=self.transition(snapshot="cluster"),
            ),
            OnboardingStep(
                id="select_filter",
                target="tabs[0][0].histogram_dock",
                title="Drop the Small Clusters",
                body=(
                    "Drag the slider so only clusters with more than 300,000 points "
                    "stay selected. That keeps the outer and inner membranes and "
                    "drops the noise.\n\n"
                    "Then click Remove in the ribbon to drop everything else."
                ),
                position="left",
                dim=False,
                before_next=self.transition(
                    restore="cluster",
                    transform=self._keep_membrane_clusters,
                    snapshot="membranes",
                ),
            ),
            OnboardingStep(
                id="select_close",
                target="tab_ribbon.button('Select')",
                title="Close the Filter",
                body="Click Select again to close the size filter.",
                position="above",
                mode="action",
                completion_signal="tab_ribbon.button('Select').clicked",
                auto_advance=True,
            ),
            OnboardingStep(
                id="pick_outer",
                target="vtk_widget",
                title="Pick the Outer Membrane",
                body=(
                    "Two clusters remain: the outer and inner membrane. We want "
                    "the outer one. Press E and click it in the viewport.\n\n"
                    "Press E again or Esc to get back to regular viewing mode.\n\n"
                    "Another useful mode is rubber-band selection activated by pressing R. The Actions menu has the rest."
                ),
                position="left",
                before_next=self.transition(
                    restore="membranes",
                    transform=self._select_outer_membrane,
                ),
            ),
            OnboardingStep(
                id="downsample",
                target="tab_ribbon.button('Downsample')",
                title="Downsample",
                body=(
                    "Dense segmentations carry far more points than meshing needs. "
                    "Extra points cost compute without improving quality. We thin the "
                    "cluster down through skeletonization or, in this tour, downsampling.\n\n"
                    "Click the chevron next to Downsample, pick Center of Mass with "
                    "Radius 48, hit Apply."
                ),
                position="center",
                mode="action",
                completion_signal="cdata.data.data_changed",
                auto_advance=True,
                dim=False,
                before_next=self.transition(snapshot="downsample"),
            ),
            OnboardingStep(
                id="param_tab",
                target="tab_bar",
                title="Switch to Parametrization",
                body="Click the Parametrization tab to get to the meshing tools.",
                position="below",
                mode="action",
                completion_signal="tab_bar.currentChanged",
                auto_advance=True,
                before_next=self.transition(
                    restore="downsample",
                    transform=self._select_latest_for_meshing,
                ),
            ),
            OnboardingStep(
                id="mesh",
                target="tab_ribbon.button('Mesh')",
                title="Generate a Mesh",
                body=(
                    "Click the chevron next to Mesh, pick Ball Pivoting. Set Radii to "
                    "60, Smoothness to 1, and Curvature Weight to 1. Hit Apply.\n\n"
                    "The weights smooth the mesh across regions where the segmentation "
                    "is missing. The new mesh shows up under Models."
                ),
                position="center",
                mode="action",
                completion_signal="cdata.models.data_changed",
                auto_advance=True,
                dim=False,
                before_next=self._select_new_mesh,
            ),
            OnboardingStep(
                id="proteins_load",
                target="list_wrapper",
                title="Add the Proteins",
                body=(
                    "Use File > Open (⌘O / Ctrl+O) to load ha_coordinates.star and "
                    "na_coordinates.star.\n\n"
                    "STAR files carry orientations alongside positions. The coordinates "
                    f"are in voxel units, so set Sampling Rate to {_SAMPLING_RATE} in "
                    "the import dialog."
                ),
                position="right",
                dim=False,
                before_next=self.transition(
                    transform=self._reload_proteins,
                    snapshot="proteins",
                ),
            ),
            OnboardingStep(
                id="proteins_repr",
                target="list_wrapper",
                title="Show Orientations",
                body=(
                    "Right-click ha_coordinates and try Representation > Normals "
                    "to see the orientation vector at each position.\n\n"
                    "Basis shows the full local frame. Different representations are "
                    "available depending on the object type."
                ),
                position="right",
                dim=False,
                before_next=self.transition(restore="proteins"),
            ),
            OnboardingStep(
                id="proteins_model",
                target="list_wrapper",
                title="Attach a 3D Template",
                body=(
                    "Right-click ha_coordinates and open Properties.\n\n"
                    "Under Model > Browse, pick ha_6.8_aligned.mrc to render each "
                    "position as the aligned density. Repeat with na_coordinates "
                    "and na_6.8_aligned.mrc."
                ),
                position="right",
                before_next=self.transition(
                    restore="proteins",
                    transform=self._after_proteins_model,
                ),
            ),
            OnboardingStep(
                id="analysis_open",
                target="tab_ribbon.button('Properties')",
                title="Open Property Analysis",
                body=(
                    "Click Properties in the ribbon.\n\n"
                    "A dock opens with everything you can quantify on the loaded data: "
                    "distances, areas, curvature, and more."
                ),
                position="left",
                mode="action",
                completion_signal="tab_ribbon.button('Properties').clicked",
                auto_advance=True,
                dim=False,
            ),
            OnboardingStep(
                id="analysis_dock",
                target="list_wrapper",
                title="Distances, Areas, Curvature",
                body=(
                    "Try a few: Nearest Neighbor on the proteins gives spacing, "
                    "Area on the mesh gives the VLP surface size, Curvature shades "
                    "the mesh by local geometry.\n\n"
                    "Pick the geometry on the left, the metric on the right, hit Compute."
                ),
                position="right",
                show_spotlight=False,
                dim=False,
            ),
            OnboardingStep(
                id="settings_open",
                target="_tab_gear",
                title="Appearance and Performance",
                body="Open the panel next to the theme toggle.",
                position="below",
                mode="action",
                completion_signal="_tab_gear.clicked",
                auto_advance=True,
                dim=False,
            ),
            OnboardingStep(
                id="settings_panel",
                target="appearance_panel",
                title="Lighting, Themes, LOD",
                body=(
                    "Switch presets, tweak lighting, and tune the LOD system here.\n\n"
                    "LOD drops detail during interaction so high point counts stay "
                    "smooth, handy on laptops."
                ),
                position="left",
                dim=False,
            ),
            OnboardingStep(
                id="done",
                target="viewport_container",
                title="Save Your Work",
                body=(
                    "Use Cmd/Ctrl+P for a screenshot and Cmd/Ctrl+S to save the session."
                ),
                position="auto",
            ),
        ]

    def teardown(self, main_window) -> None:
        if self._data_dir is None:
            return None

        import shutil
        from mosaic.widgets import MosaicMessageBox

        box = MosaicMessageBox(main_window)
        box.setWindowTitle("Sample Data")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f"Delete the sample dataset?\n\n{self._data_dir}")
        keep_btn = box.addButton("Keep", QMessageBox.ButtonRole.RejectRole)
        delete_btn = box.addButton("Delete", QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(keep_btn)
        box.exec()

        if box.clickedButton() is delete_btn:
            shutil.rmtree(self._data_dir, ignore_errors=True)
