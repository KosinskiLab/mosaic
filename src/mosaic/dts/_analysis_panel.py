"""
Analysis panel widget for DTS screening dialog.

Unified metric viewer with compute-new-metric dialog, multi-run
plotting, and data export.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from pathlib import Path
from typing import Callable, Optional

import numpy as np
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QComboBox,
    QSpinBox,
    QPushButton,
    QFormLayout,
    QWidget,
    QMessageBox,
    QGroupBox,
    QSizePolicy,
    QStackedWidget,
)
import pyqtgraph as pg
import qtawesome as qta

from ..widgets import ColorMapSelector, generate_gradient_colors
from ..stylesheets import (
    QGroupBox_style,
    QLineEdit_style,
    Colors,
)


class AnalysisPanel(QWidget):
    """Right-side analysis panel: plot, metric options, compute, export.

    Parameters
    ----------
    cdata : MosaicData or None
        Application data (provides reference models for distance compute).
    get_mesh_transform : callable
        ``() -> (float, ndarray)`` returning scale factor and offset.
    get_selected_run_ids : callable
        ``() -> list[str]`` returning currently selected run IDs.
    parent : QWidget, optional
        Parent widget.
    """

    def __init__(
        self,
        cdata=None,
        get_mesh_transform: Optional[Callable] = None,
        get_selected_run_ids: Optional[Callable] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.cdata = cdata
        self._get_mesh_transform = get_mesh_transform or (
            lambda: (1.0, np.array([0.0, 0.0, 0.0]))
        )
        self._get_selected_run_ids = get_selected_run_ids or (lambda: [])
        self._screen_results = None
        self._screen_dir = None

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._plot_widget = pg.GraphicsLayoutWidget()
        self._plot_widget.setBackground(None)
        self._plot_widget.ci.setContentsMargins(0, 0, 0, 0)
        self._plot_widget.setMinimumHeight(300)
        self._plot_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._plot_item = self._plot_widget.addPlot()
        self._style_plot(self._plot_item)

        self._placeholder = QLabel(
            "No time series data available.\n"
            "Run the screen and refresh the overview."
        )
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 13px;")

        self._stack = QStackedWidget()
        self._stack.addWidget(self._placeholder)
        self._stack.addWidget(self._plot_widget)
        layout.addWidget(self._stack)

        options_group = QGroupBox("Options")
        grid = QGridLayout(options_group)
        grid.setSpacing(6)
        grid.setContentsMargins(8, 8, 8, 8)

        self._metric_combo = QComboBox()
        self._metric_combo.currentTextChanged.connect(self._update_plot)

        add_metric_btn = QPushButton()
        add_metric_btn.setIcon(qta.icon("ph.plus", color=Colors.PRIMARY))
        add_metric_btn.setToolTip("Compute a new metric")
        add_metric_btn.setFlat(True)
        add_metric_btn.setFixedWidth(26)
        add_metric_btn.clicked.connect(self._show_compute_dialog)

        self._norm_combo = QComboBox()
        self._norm_combo.addItems(["None", "Per-run", "Global", "Relative"])
        self._norm_combo.currentTextChanged.connect(self._update_plot)

        lbl_metric = QLabel("Metric:")
        lbl_metric.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        grid.addWidget(lbl_metric, 0, 0)
        grid.addWidget(self._metric_combo, 0, 1)
        grid.addWidget(add_metric_btn, 0, 2)
        lbl_norm = QLabel("Normalize:")
        lbl_norm.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        grid.addWidget(lbl_norm, 0, 3)
        grid.addWidget(self._norm_combo, 0, 4)

        self._color_combo = QComboBox()
        self._color_combo.addItem("(auto)")
        self._color_combo.currentTextChanged.connect(self._update_plot)

        self._cmap_selector = ColorMapSelector(default="Dark2")
        self._cmap_selector.colormapChanged.connect(self._update_plot)

        lbl_color = QLabel("Color by:")
        lbl_color.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        grid.addWidget(lbl_color, 1, 0)
        grid.addWidget(self._color_combo, 1, 1, 1, 2)
        lbl_palette = QLabel("Palette:")
        lbl_palette.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        grid.addWidget(lbl_palette, 1, 3)
        grid.addWidget(self._cmap_selector, 1, 4)

        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(4, 1)

        layout.addWidget(options_group)

        footer = QHBoxLayout()
        export_plot_btn = QPushButton("Export Plot")
        export_plot_btn.setIcon(qta.icon("ph.download", color=Colors.PRIMARY))
        export_plot_btn.clicked.connect(self._export_plot)
        footer.addWidget(export_plot_btn)

        export_data_btn = QPushButton("Export Data")
        export_data_btn.setIcon(qta.icon("ph.file-arrow-down", color=Colors.PRIMARY))
        export_data_btn.clicked.connect(self._export_data)
        footer.addWidget(export_data_btn)
        footer.addStretch()
        layout.addLayout(footer)

    def load_results(self, screen_dir: str):
        """Load screen results from *screen_dir* and refresh the panel."""
        from ..dts import load_screen_results

        self._screen_dir = screen_dir
        self._screen_results = load_screen_results(screen_dir)
        self.refresh()

    def refresh(self):
        """Rebuild metric/color combos from current screen results and replot."""
        old_metric = self._metric_combo.currentText()
        self._metric_combo.blockSignals(True)
        self._metric_combo.clear()
        metrics = self._collect_available_metrics()
        self._metric_combo.addItems(metrics)
        if old_metric in metrics:
            self._metric_combo.setCurrentText(old_metric)
        self._metric_combo.blockSignals(False)

        old_color = self._color_combo.currentText()
        self._color_combo.blockSignals(True)
        self._color_combo.clear()
        self._color_combo.addItem("(auto)")
        if self._screen_results is not None:
            for name in self._screen_results.get("parameter_names", []):
                self._color_combo.addItem(name)
        if old_color and self._color_combo.findText(old_color) >= 0:
            self._color_combo.setCurrentText(old_color)
        self._color_combo.blockSignals(False)

        self._update_plot()

    def _collect_available_metrics(self) -> list:
        if self._screen_results is None:
            return []

        col_sources = {}
        for run in self._screen_results["runs"]:
            for ts in run.get("time_series") or []:
                meta = ts.get("metadata") or {}
                if meta.get("format") == "per_vertex":
                    continue
                for col in ts["columns"][1:]:
                    col_sources.setdefault(col, set()).add(ts["source"])

        metrics = []
        seen = set()
        for run in self._screen_results["runs"]:
            for ts in run.get("time_series") or []:
                meta = ts.get("metadata") or {}
                if meta.get("format") == "per_vertex":
                    continue
                for col in ts["columns"][1:]:
                    if len(col_sources.get(col, set())) > 1:
                        display = f"{ts['source']}/{col}"
                    else:
                        display = col
                    if display not in seen:
                        seen.add(display)
                        metrics.append(display)

        return sorted(metrics)

    def _get_completed_run_ids(self) -> list:
        if self._screen_results is None:
            return []
        return [
            r["run_id"]
            for r in self._screen_results["runs"]
            if r["status"] == "available"
        ]

    def _get_run_dict(self, run_id: str) -> dict:
        if self._screen_results is None:
            return {}
        for r in self._screen_results["runs"]:
            if r["run_id"] == run_id:
                return r
        return {}

    def _selected_run_ids(self) -> list:
        """Selected run IDs from the overview, or all completed."""
        ids = self._get_selected_run_ids()
        return ids if ids else self._get_completed_run_ids()

    def _show_compute_dialog(self):
        from ..stylesheets import QPushButton_style, QComboBox_style, QSpinBox_style

        dlg = QDialog(self)
        dlg.setWindowTitle("Compute Metric")
        dlg.setFixedWidth(360)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        prop_group = QGroupBox("Property")
        prop_layout = QFormLayout(prop_group)
        prop_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        prop_combo = QComboBox()
        prop_combo.addItems(["Distance", "Fluctuation", "Area", "Volume"])
        prop_layout.addRow("Type:", prop_combo)
        layout.addWidget(prop_group)

        # Dynamic options
        options_group = QGroupBox("Parameters")
        options_layout = QFormLayout(options_group)
        options_layout.setContentsMargins(8, 12, 8, 8)
        options_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(options_group)

        option_widgets = {}

        def _clear_options():
            option_widgets.clear()
            while options_layout.rowCount() > 0:
                options_layout.removeRow(0)

        def _build_distance_options():
            ref_combo = QComboBox()
            if self.cdata is not None:
                for label, _ in self.cdata.format_datalist("models", mesh_only=True):
                    ref_combo.addItem(label)
            options_layout.addRow("Reference:", ref_combo)
            option_widgets["ref"] = ref_combo

            metric_combo = QComboBox()
            metric_combo.addItems(["rmse", "hausdorff", "mean_distance"])
            options_layout.addRow("Metric:", metric_combo)
            option_widgets["metric"] = metric_combo

        def _build_fluctuation_options():
            window_spin = QSpinBox()
            window_spin.setRange(1, 1000)
            window_spin.setValue(5)
            window_spin.setToolTip(
                "Half-window size: each frame uses \u00b1window neighbours"
            )
            options_layout.addRow("Window (\u00b1):", window_spin)
            option_widgets["window"] = window_spin

            frame_row = QHBoxLayout()
            from_spin = QSpinBox()
            from_spin.setRange(0, 999999)
            from_spin.setSpecialValueText("start")
            frame_row.addWidget(from_spin)
            frame_row.addWidget(QLabel("\u2013"))
            to_spin = QSpinBox()
            to_spin.setRange(0, 999999)
            to_spin.setSpecialValueText("end")
            frame_row.addWidget(to_spin)
            options_layout.addRow("Frames:", frame_row)
            option_widgets["from"] = from_spin
            option_widgets["to"] = to_spin

        def _build_area_options():
            type_combo = QComboBox()
            type_combo.addItems(["Total", "Per-Triangle"])
            options_layout.addRow("Type:", type_combo)
            option_widgets["area_type"] = type_combo

        def _build_volume_options():
            type_combo = QComboBox()
            type_combo.addItems(["Total", "Per-Triangle"])
            options_layout.addRow("Type:", type_combo)
            option_widgets["volume_type"] = type_combo

        _BUILDERS = {
            "Distance": _build_distance_options,
            "Fluctuation": _build_fluctuation_options,
            "Area": _build_area_options,
            "Volume": _build_volume_options,
        }

        def _on_property_changed(text):
            _clear_options()
            builder = _BUILDERS.get(text)
            if builder:
                builder()
            dlg.adjustSize()

        prop_combo.currentTextChanged.connect(_on_property_changed)
        _on_property_changed(prop_combo.currentText())

        compute_btn = QPushButton("Compute")
        compute_btn.setIcon(qta.icon("ph.play-fill", color=Colors.PRIMARY))
        layout.addWidget(compute_btn)

        def _on_compute():
            prop = prop_combo.currentText()
            if prop == "Distance":
                self._submit_distance(
                    ref_name=option_widgets["ref"].currentText(),
                    metric=option_widgets["metric"].currentText(),
                )
            elif prop == "Fluctuation":
                start = option_widgets["from"].value() or None
                end = option_widgets["to"].value() or None
                self._submit_fluctuation(
                    window=option_widgets["window"].value(),
                    start_frame=start,
                    end_frame=end,
                )
            elif prop == "Area":
                self._submit_property(
                    "mesh_area",
                    area_type=option_widgets["area_type"].currentText(),
                )
            elif prop == "Volume":
                self._submit_property(
                    "mesh_volume",
                    volume_type=option_widgets["volume_type"].currentText(),
                )
            dlg.accept()

        compute_btn.clicked.connect(_on_compute)

        dlg.setStyleSheet(
            QPushButton_style
            + QGroupBox_style
            + QLineEdit_style
            + QComboBox_style
            + QSpinBox_style
        )
        for btn in dlg.findChildren(QPushButton):
            btn.setAutoDefault(False)

        dlg.exec()

    def _submit_computation(self, task_label: str, compute_fn, **kwargs):
        """Submit a computation across all selected runs.

        Common boilerplate for distance, fluctuation, and property tasks.
        """
        from ..parallel import submit_task

        scale_factor, offset = self._get_mesh_transform()
        run_ids = self._selected_run_ids()

        if not run_ids:
            return QMessageBox.warning(self, "Error", "No available runs found.")

        for run_id in run_ids:
            run = self._get_run_dict(run_id)
            run_dir = run.get("run_dir")
            if not run_dir:
                continue

            traj_dir = Path(run_dir) / "TrajTSI"
            if not traj_dir.exists():
                continue

            submit_task(
                f"{task_label} ({run_id})",
                compute_fn,
                lambda _result: self._reload_results(),
                trajectory_dir=str(traj_dir),
                scale_factor=scale_factor,
                offset=offset,
                output_dir=run_dir,
                **kwargs,
            )

    def _submit_distance(self, ref_name: str, metric: str):
        from ..dts import compute_trajectory_distance

        if not ref_name or self.cdata is None:
            return QMessageBox.warning(self, "Error", "Select a reference model.")

        ref_geom = None
        for label, geom in self.cdata.format_datalist("models", mesh_only=True):
            if label == ref_name:
                ref_geom = geom
                break

        if ref_geom is None:
            return QMessageBox.warning(self, "Error", "Reference geometry not found.")

        self._submit_computation(
            "Distance",
            compute_trajectory_distance,
            reference_points=ref_geom.points,
            metric=metric,
            reference_label=ref_name,
        )

    def _submit_fluctuation(self, window=5, start_frame=None, end_frame=None):
        from ..dts import compute_vertex_fluctuation

        self._submit_computation(
            "RMSF",
            compute_vertex_fluctuation,
            window=window,
            start_frame=start_frame,
            end_frame=end_frame,
        )

    def _submit_property(self, property_name: str, **kwargs):
        from ..dts import compute_trajectory_property

        self._submit_computation(
            property_name,
            compute_trajectory_property,
            property_name=property_name,
            **kwargs,
        )

    def _reload_results(self):
        """Re-read results from disk and refresh the panel."""
        if self._screen_dir is not None:
            self.load_results(self._screen_dir)

    def _style_plot(self, plot):
        fg = Colors.TEXT_PRIMARY
        for axis_name in ("left", "bottom", "top", "right"):
            axis = plot.getAxis(axis_name)
            axis.setPen(pg.mkPen(fg))
            axis.setTextPen(pg.mkPen(fg))
        plot.setClipToView(True)
        pg.setConfigOptions(antialias=True)

    @staticmethod
    def _resolve_metric(display_name: str):
        if "/" in display_name:
            source, col = display_name.split("/", 1)
            return source, col
        return None, display_name

    def _plot_multi_run(self, series, ylabel, xlabel="Frame"):
        plot = self._plot_item

        self._plot_widget.setUpdatesEnabled(False)
        plot.vb.disableAutoRange()

        plot.clear()
        if plot.legend is not None:
            scene = plot.legend.scene()
            if scene is not None:
                scene.removeItem(plot.legend)
            plot.legend = None

        if not series:
            self._stack.setCurrentIndex(0)
            self._plot_widget.setUpdatesEnabled(True)
            return

        self._stack.setCurrentIndex(1)

        color_by = self._color_combo.currentText()
        norm_mode = self._norm_combo.currentText()
        cmap_name = self._cmap_selector.currentText()

        if color_by and color_by != "(auto)":
            try:
                series = sorted(
                    series,
                    key=lambda s: float(s[0]["params"].get(color_by, 0)),
                )
            except (ValueError, TypeError):
                pass

        global_min = min(np.min(y) for _, _, y in series)
        global_max = max(np.max(y) for _, _, y in series)
        global_range = global_max - global_min + 1e-12

        plot.setLabel("left", ylabel)
        plot.setLabel("bottom", xlabel)
        plot.addLegend(offset=(-10, 10))

        colors = generate_gradient_colors(cmap_name, max(len(series), 2))

        for i, (run, x, y) in enumerate(series):
            if norm_mode == "Per-run" and np.max(np.abs(y)) > 0:
                y = (y - np.min(y)) / (np.max(y) - np.min(y) + 1e-12)
            elif norm_mode == "Global":
                y = (y - global_min) / global_range
            elif norm_mode == "Relative" and len(y) > 0 and abs(y[0]) > 1e-12:
                y = y / y[0]

            color = colors[i % len(colors)]
            pen_color = pg.mkColor(color.red(), color.green(), color.blue())

            label_parts = [run["run_id"]]
            if color_by and color_by != "(auto)":
                val = run["params"].get(color_by, "?")
                label_parts.append(f"{color_by}={val}")

            plot.plot(
                x,
                y,
                pen=pg.mkPen(pen_color, width=1.5),
                name=" ".join(label_parts),
            )

        plot.vb.enableAutoRange()
        self._plot_widget.setUpdatesEnabled(True)

    def _update_plot(self, *_args):
        metric_display = self._metric_combo.currentText()
        if not metric_display:
            self._plot_item.clear()
            self._stack.setCurrentIndex(0)
            return

        if self._screen_results is None:
            self._stack.setCurrentIndex(0)
            return

        source_filter, col_name = self._resolve_metric(metric_display)
        selected_ids = set(self._selected_run_ids())

        series = []
        for run in self._screen_results["runs"]:
            if run["run_id"] not in selected_ids:
                continue

            for ts in run.get("time_series") or []:
                meta = ts.get("metadata") or {}
                if meta.get("format") == "per_vertex":
                    continue

                if source_filter is not None and ts["source"] != source_filter:
                    continue

                cols = ts["columns"]
                data = ts["data"]

                metric_idx = None
                for j, name in enumerate(cols):
                    if col_name.lower() == name.lower():
                        metric_idx = j
                        break
                if metric_idx is None:
                    continue

                x = np.arange(data.shape[0], dtype=float)
                y = data[:, metric_idx]
                series.append((run, x, y))
                break

        self._plot_multi_run(series, metric_display)

    def _export_plot(self):
        from qtpy.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Plot", "", "PNG (*.png);;SVG (*.svg)"
        )
        if not path:
            return

        from pyqtgraph.exporters import ImageExporter, SVGExporter

        if path.endswith(".svg"):
            exporter = SVGExporter(self._plot_widget.scene())
        else:
            exporter = ImageExporter(self._plot_widget.scene())
        exporter.export(path)

    def _export_data(self):
        from qtpy.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Data", "", "CSV (*.csv);;TSV (*.tsv)"
        )
        if not path:
            return

        sep = "\t" if path.endswith(".tsv") else ","
        metric_display = self._metric_combo.currentText()

        if not metric_display or self._screen_results is None:
            return

        source_filter, col_name = self._resolve_metric(metric_display)

        try:
            with open(path, "w") as f:
                param_names = self._screen_results.get("parameter_names", [])
                header = ["run_id"] + param_names + ["frame", col_name]
                f.write(sep.join(header) + "\n")

                selected_ids = set(self._selected_run_ids())
                for run in self._screen_results["runs"]:
                    if run["run_id"] not in selected_ids:
                        continue

                    for ts in run.get("time_series") or []:
                        meta = ts.get("metadata") or {}
                        if meta.get("format") == "per_vertex":
                            continue
                        if source_filter is not None and ts["source"] != source_filter:
                            continue

                        cols = ts["columns"]
                        data = ts["data"]

                        metric_idx = None
                        for j, name in enumerate(cols):
                            if col_name.lower() == name.lower():
                                metric_idx = j
                                break
                        if metric_idx is None:
                            continue

                        for frame_i, row in enumerate(data):
                            parts = [run["run_id"]]
                            parts.extend(
                                str(run["params"].get(p, "")) for p in param_names
                            )
                            parts.append(str(frame_i))
                            parts.append(str(row[metric_idx]))
                            f.write(sep.join(parts) + "\n")
                        break
        except Exception as e:
            QMessageBox.warning(self, "Export Error", str(e))
