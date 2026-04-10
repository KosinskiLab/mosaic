"""
DTS parameter screening and analysis dialog.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import functools
from pathlib import Path

import numpy as np
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
    QDialog,
    QMessageBox,
    QGroupBox,
    QTabWidget,
    QTableWidget,
    QHeaderView,
    QTableWidgetItem,
    QSplitter,
    QSizePolicy,
)
import pyqtgraph as pg
import qtawesome as qta

from ..widgets import PathSelector, SearchWidget
from ..widgets.settings import get_widget_value
from ..stylesheets import (
    QPushButton_style,
    QGroupBox_style,
    QScrollArea_style,
    QTabBar_style,
    QTable_style,
    QLineEdit_style,
    Colors,
)
from ._configure import ConfigurePanel
from ._analysis_panel import AnalysisPanel
from ._compute_panel import ComputePanel
from ._utils import parse_dts_content

__all__ = ["DTSScreeningDialog"]


def _icon_button(icon_name, size=22, tooltip="", flat=True):
    btn = QPushButton()
    btn.setIcon(qta.icon(icon_name, color=Colors.ICON))
    btn.setFixedSize(size, size)
    btn.setToolTip(tooltip)
    btn.setFlat(flat)
    return btn


class DTSScreeningDialog(QDialog):
    """DTS parameter screening and analysis dialog."""

    def __init__(self, cdata=None, parent=None):
        super().__init__(parent)
        self.cdata = cdata
        self._screen_dir = None

        self.setWindowTitle("DTS Parameter Screening")
        self.setMinimumSize(1100, 750)
        self.resize(1250, 820)

        self._setup_ui()
        self.setStyleSheet(
            QGroupBox_style
            + QPushButton_style
            + QTable_style
            + QScrollArea_style
            + QTabBar_style
            + QLineEdit_style
        )

        for btn in self.findChildren(QPushButton):
            btn.setAutoDefault(False)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._left_tabs = QTabWidget()

        self._configure_panel = ConfigurePanel()
        self._overview_tab = self._build_overview_tab()

        self._left_tabs.addTab(
            self._configure_panel,
            qta.icon("ph.sliders", color=Colors.ICON),
            "Configure",
        )
        self._left_tabs.addTab(
            self._overview_tab,
            qta.icon("ph.chart-line-up", color=Colors.ICON),
            "Analyze",
        )

        self._right_widget = QWidget()
        self._right_layout = QVBoxLayout(self._right_widget)
        self._right_layout.setContentsMargins(6, 6, 6, 0)
        self._right_layout.setSpacing(6)

        self._preview_container = QWidget()
        preview_layout = QVBoxLayout(self._preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(4)

        self._preview_plot = pg.GraphicsLayoutWidget()
        self._preview_plot.setBackground(None)
        self._preview_plot.ci.setContentsMargins(0, 0, 0, 0)
        self._preview_plot.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self._preview_plot_item = self._preview_plot.addPlot()

        preview_layout.addWidget(self._preview_plot)

        self._preview_placeholder = QLabel(
            "Enable screening on at least one parameter\n"
            "to see the parameter space preview."
        )
        self._preview_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_placeholder.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 13px;"
        )
        preview_layout.addWidget(self._preview_placeholder)

        self._right_layout.addWidget(self._preview_container)

        self._configure_panel.set_preview_widgets(
            self._preview_plot, self._preview_plot_item, self._preview_placeholder
        )

        self._analysis_panel = AnalysisPanel(
            get_selected_run_ids=self._get_selected_run_ids,
        )
        self._right_layout.addWidget(self._analysis_panel)

        self._analysis_panel.setVisible(False)

        self._left_tabs.currentChanged.connect(self._on_left_tab_changed)
        self._configure_panel.screenGenerated.connect(self._on_screen_generated)

        splitter.addWidget(self._left_tabs)
        splitter.addWidget(self._right_widget)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([400, 720])

        root.addWidget(splitter)

    def _build_overview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        screen_group = QGroupBox("Screen")
        screen_layout = QVBoxLayout(screen_group)

        dir_row = QHBoxLayout()
        self._screen_dir_input = PathSelector(
            placeholder="Screen directory", mode="directory"
        )
        self._screen_dir_input.path_input.textChanged.connect(
            self._load_screen_overview
        )
        dir_row.addWidget(self._screen_dir_input)

        refresh_btn = _icon_button(
            "ph.arrows-clockwise", size=28, tooltip="Refresh status"
        )
        refresh_btn.clicked.connect(self._refresh_overview)
        dir_row.addWidget(refresh_btn)
        screen_layout.addLayout(dir_row)

        self._search_widget = SearchWidget(placeholder="Filter runs...")
        self._search_widget.searchTextChanged.connect(self._apply_overview_filter)
        screen_layout.addWidget(self._search_widget)

        self._overview_table = QTableWidget()
        self._overview_table.setAlternatingRowColors(True)
        self._overview_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._overview_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._overview_table.setStyleSheet(
            "QTableWidget::item:hover { background: none; }"
            "QTableWidget::item:selected,"
            "QTableWidget::item:selected:hover"
            "{ background-color: rgba(99, 102, 241, 0.15); }"
        )
        self._overview_table.itemSelectionChanged.connect(
            self._on_overview_selection_changed
        )
        screen_layout.addWidget(self._overview_table)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 11px;"
        )
        screen_layout.addWidget(self._status_label)

        layout.addWidget(screen_group)

        self._compute_panel = ComputePanel(
            cdata=self.cdata,
            get_mesh_transform=self._configure_panel.get_mesh_transform,
            get_run_ids=self._get_compute_run_ids,
            get_run_dir=self._get_run_dir,
            on_complete=self._on_compute_complete,
        )
        layout.addWidget(self._compute_panel)

        return widget

    def _get_compute_run_ids(self):
        """Return selected run IDs, falling back to all available."""
        ids = self._get_selected_run_ids()
        return ids if ids else self._analysis_panel.available_run_ids()

    def _get_run_dir(self, run_id):
        """Return the run directory path for a run ID, or None."""
        results = self._analysis_panel.screen_results
        if not results:
            return None
        for r in results["runs"]:
            if r["run_id"] == run_id:
                return r.get("run_dir")
        return None

    def _on_compute_complete(self):
        if self._screen_dir:
            self._analysis_panel.load_results(self._screen_dir)

    def _on_left_tab_changed(self, index: int):
        is_configure = index == 0
        self._preview_container.setVisible(is_configure)
        self._analysis_panel.setVisible(not is_configure)

        if is_configure:
            self._configure_panel.update_preview_plot()
        else:
            self._analysis_panel.refresh()

    def _on_screen_generated(self, output_dir: str):
        self._screen_dir_input.set_path(output_dir)
        self._load_screen_overview(output_dir)
        self._left_tabs.setCurrentIndex(1)

    def _get_selected_run_ids(self) -> list:
        """Return selected run IDs from the overview table, or empty list."""
        selected = set()
        for item in self._overview_table.selectedItems():
            row = item.row()
            run_item = self._overview_table.item(row, 0)
            if run_item:
                selected.add(run_item.text())
        return list(selected)

    def _load_screen_overview(self, screen_dir=None):
        from ..dts import get_screen_status

        if not screen_dir:
            screen_dir = str(get_widget_value(self._screen_dir_input) or "")
        else:
            screen_dir = str(screen_dir)
        if not screen_dir:
            return

        self._screen_dir = screen_dir
        statuses = get_screen_status(screen_dir)

        if not statuses:
            self._overview_table.setRowCount(0)
            self._status_label.setText("No DTS runs found.")
            return

        param_keys = sorted({k for s in statuses for k in s["parameters"].keys()})
        columns = ["Run"] + param_keys + ["Status", "Actions"]
        actions_col = len(columns) - 1
        self._overview_table.setColumnCount(len(columns))
        self._overview_table.setHorizontalHeaderLabels(columns)
        self._overview_table.setRowCount(len(statuses))

        header = self._overview_table.horizontalHeader()
        for col in range(actions_col):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(actions_col, QHeaderView.ResizeMode.Fixed)
        self._overview_table.setColumnWidth(actions_col, 64)

        def _make_item(text):
            item = QTableWidgetItem(str(text))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            return item

        done_count = 0
        for row, status in enumerate(statuses):
            run_id = status["run_id"]
            self._overview_table.setItem(row, 0, _make_item(run_id))

            for col_idx, key in enumerate(param_keys, start=1):
                val = status["parameters"].get(key, "")
                if key == "volume_path" and isinstance(val, str) and "/" in val:
                    val = Path(val).name
                self._overview_table.setItem(row, col_idx, _make_item(val))

            status_col = len(param_keys) + 1
            is_available = status["status"] == "available"
            if is_available:
                indicator = "\u25cf Available"
                done_count += 1
                style_color = Colors.SUCCESS
            else:
                indicator = "\u25cb Pending"
                style_color = Colors.NEUTRAL

            status_item = _make_item(indicator)
            status_item.setForeground(pg.mkColor(style_color))
            self._overview_table.setItem(row, status_col, status_item)

            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 0, 2, 0)
            actions_layout.setSpacing(2)

            folder_btn = _icon_button("ph.folder-open", tooltip="Open run directory")
            folder_btn.clicked.connect(functools.partial(self._open_run_dir, run_id))
            actions_layout.addWidget(folder_btn)

            import_btn = _icon_button(
                "ph.upload", tooltip="Import trajectory into viewer"
            )
            import_btn.setEnabled(is_available)
            import_btn.clicked.connect(
                functools.partial(self._import_run_trajectory, run_id)
            )
            actions_layout.addWidget(import_btn)

            self._overview_table.setCellWidget(row, actions_col, actions_widget)

        self._status_label.setText(f"{done_count}/{len(statuses)} completed")
        self._analysis_panel.load_results(screen_dir)

    def _refresh_overview(self):
        self._load_screen_overview()

    def _apply_overview_filter(self, text: str):
        text = text.strip().lower()
        for row in range(self._overview_table.rowCount()):
            match = not text
            if not match:
                for col in range(self._overview_table.columnCount()):
                    item = self._overview_table.item(row, col)
                    if item and text in item.text().lower():
                        match = True
                        break
            self._overview_table.setRowHidden(row, not match)

    def _on_overview_selection_changed(self):
        self._analysis_panel._update_plot()

    def _resolve_run_dir(self, run_id: str) -> Path:
        """Resolve the filesystem path for a run ID.

        Handles both screen directories (run_id is a subdirectory) and single
        trajectory directories (the screen_dir itself is the run).
        """
        candidate = Path(self._screen_dir) / run_id
        if candidate.is_dir():
            return candidate
        return Path(self._screen_dir)

    def _open_run_dir(self, run_id: str):
        if self._screen_dir is None:
            return
        run_dir = self._resolve_run_dir(run_id)
        if not run_dir.exists():
            return
        from qtpy.QtGui import QDesktopServices
        from qtpy.QtCore import QUrl

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(run_dir)))

    def _import_run_trajectory(self, run_id: str):
        if self._screen_dir is None or self.cdata is None:
            return
        run_dir = self._resolve_run_dir(run_id)

        from ._utils import resolve_trajectory_dir

        traj_dir = resolve_trajectory_dir(str(run_dir))
        if traj_dir is None:
            return QMessageBox.warning(self, "Error", "No trajectory output found.")

        from ..geometry import GeometryTrajectory
        from ._utils import (
            list_trajectory_files,
            build_trajectory_frames,
            collect_vertex_properties,
        )

        files = list_trajectory_files(str(traj_dir))
        if not files:
            return QMessageBox.warning(self, "Error", "No trajectory frames found.")

        scale, offset = self._configure_panel.get_mesh_transform()
        dts_file = run_dir / "input.dts"
        if dts_file.exists():
            known, _ = parse_dts_content(dts_file.read_text(encoding="utf-8"))
            if "scale_factor" in known:
                scale = float(known["scale_factor"])
            if "offset" in known:
                offset = np.array([float(x) for x in known["offset"].split(",")])

        vertex_props = collect_vertex_properties(str(run_dir))
        frames = build_trajectory_frames(str(traj_dir), scale, offset, vertex_props)
        trajectory = GeometryTrajectory(
            sampling_rate=1 / scale,
            trajectory=frames,
            model=frames[0]["fit"],
            vertex_properties=frames[0].get("vertex_properties"),
            meta={"name": run_id},
        )
        trajectory.change_representation("mesh")
        self.cdata.models.add(trajectory)
        self.cdata.models.data_changed.emit()
        self.cdata.models.render()
