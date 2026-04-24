"""
Analysis panel widget for DTS screening dialog.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import Callable, Optional

import numpy as np
from qtpy.QtCore import Qt, QTimer
from qtpy.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QCompleter,
    QLineEdit,
    QPushButton,
    QFormLayout,
    QWidget,
    QGroupBox,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
)
import pyqtgraph as pg

from ..widgets import ColorMapSelector, generate_gradient_colors
from ..stylesheets import Colors, Typography
from ..icons import icon
from ..utils import Throttle
import re

from ..dts._utils import collect_available_metrics, extract_metric_series


class AnalysisPanel(QWidget):
    """Right-side analysis panel: plot, display options, readout table.

    Parameters
    ----------
    get_selected_run_ids : callable
        ``() -> list[str]`` returning currently selected run IDs.
    parent : QWidget, optional
        Parent widget.
    """

    _LOD_TARGET_POINTS = 1000
    _LOD_IDLE_MS = 150

    def __init__(
        self,
        get_selected_run_ids: Optional[Callable] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._get_selected_run_ids = get_selected_run_ids or (lambda: [])
        self._screen_results = None
        self._screen_dir = None

        self._lod_active = False
        self._lod_downsample: Optional[int] = None
        self._lod_timer = QTimer(self)
        self._lod_timer.setSingleShot(True)
        self._lod_timer.setInterval(self._LOD_IDLE_MS)
        self._lod_timer.timeout.connect(self._restore_full_quality)

        self._update_plot_throttled = Throttle(self._update_plot, interval_ms=500)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._plot_widget = pg.GraphicsLayoutWidget()
        self._plot_widget.setBackground(None)
        self._plot_widget.ci.setContentsMargins(0, 0, 0, 0)
        self._plot_widget.setMinimumHeight(240)
        self._plot_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._plot_item = self._plot_widget.addPlot()
        self._style_plot(self._plot_item)
        self._plot_item.vb.sigRangeChangedManually.connect(self._on_user_interaction)

        self._placeholder = QLabel(
            "No time series data available.\n" "Select a metric to display."
        )
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: {Typography.BODY}px;"
        )

        self._stack = QStackedWidget()
        self._stack.addWidget(self._placeholder)
        self._stack.addWidget(self._plot_widget)
        layout.addWidget(self._stack, stretch=3)

        columns = QHBoxLayout()
        columns.setSpacing(6)

        display = QGroupBox("Display")
        form = QFormLayout(display)
        form.setSpacing(4)
        form.setContentsMargins(4, 4, 4, 4)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._metric_combo = QComboBox()
        self._metric_combo.currentTextChanged.connect(self._update_plot)
        form.addRow("Metric:", self._metric_combo)

        derived_row = QHBoxLayout()
        derived_row.setSpacing(4)
        self._derived_edit = QLineEdit()
        self._derived_edit.setPlaceholderText("e.g. mesh_area / mesh_volume")
        self._derived_edit.setToolTip(
            "Binary expression on computed metrics.\n"
            "Operators: /  *  -  +\n"
            "Press Enter to evaluate."
        )
        self._derived_edit.setMinimumHeight(Colors.WIDGET_HEIGHT)
        self._derived_metrics = []
        self._derived_completer = QCompleter()
        self._derived_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._derived_completer.setCompletionMode(
            QCompleter.CompletionMode.InlineCompletion
        )
        self._derived_edit.setCompleter(self._derived_completer)
        self._derived_edit.returnPressed.connect(self._on_derived_committed)
        self._derived_edit.textChanged.connect(self._on_derived_text_changed)
        derived_row.addWidget(self._derived_edit, stretch=1)

        self._derived_save_btn = QPushButton()
        self._derived_save_btn.setIcon(icon("ph.floppy-disk"))
        self._derived_save_btn.setToolTip("Save derived metric to run directories")
        self._derived_save_btn.clicked.connect(self._save_derived)
        self._derived_save_btn.setMaximumWidth(30)
        self._derived_save_btn.setMinimumHeight(Colors.WIDGET_HEIGHT)
        derived_row.addWidget(self._derived_save_btn, stretch=0)
        form.addRow("Derived:", derived_row)

        self._norm_combo = QComboBox()
        self._norm_combo.addItems(["None", "Per-run", "Relative"])
        self._norm_combo.currentTextChanged.connect(self._update_plot)
        form.addRow("Normalize:", self._norm_combo)

        self._color_combo = QComboBox()
        self._color_combo.addItem("(auto)")
        self._color_combo.currentTextChanged.connect(self._update_plot)
        form.addRow("Color by:", self._color_combo)

        self._cmap_selector = ColorMapSelector(default="Dark2")
        self._cmap_selector.colormapChanged.connect(self._update_plot)
        form.addRow("Palette:", self._cmap_selector)

        self._smooth_combo = QComboBox()
        for w in (1, 5, 10, 25, 50, 100, 200, 500):
            label = "None" if w == 1 else str(w)
            self._smooth_combo.addItem(label, w)
        self._smooth_combo.setToolTip("Moving average window size")
        self._smooth_combo.currentIndexChanged.connect(self._update_plot)
        form.addRow("Smooth:", self._smooth_combo)

        columns.addWidget(display, stretch=2, alignment=Qt.AlignmentFlag.AlignTop)

        stats = QGroupBox("Statistics")
        stats_layout = QVBoxLayout(stats)
        stats_layout.setContentsMargins(4, 4, 4, 4)
        stats_layout.setSpacing(4)

        self._readout_table = QTableWidget()
        self._readout_table.setAlternatingRowColors(True)
        self._readout_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._readout_table.setSortingEnabled(True)
        self._readout_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._readout_table.verticalHeader().setVisible(False)
        self._readout_table.verticalHeader().setDefaultSectionSize(22)
        self._readout_table.setMaximumHeight(198)
        stats_layout.addWidget(self._readout_table)

        columns.addWidget(stats, stretch=3)

        footer = QHBoxLayout()
        export_plot_btn = QPushButton("Export Plot")
        export_plot_btn.setIcon(icon("ph.download", role="primary"))
        export_plot_btn.clicked.connect(self._export_plot)
        footer.addWidget(export_plot_btn)

        export_data_btn = QPushButton("Export Data")
        export_data_btn.setIcon(icon("ph.file-arrow-down", role="primary"))
        export_data_btn.clicked.connect(self._export_data)
        footer.addWidget(export_data_btn)

        export_stats_btn = QPushButton("Export Statistics")
        export_stats_btn.setIcon(icon("ph.table", role="primary"))
        export_stats_btn.clicked.connect(self._export_statistics)
        footer.addWidget(export_stats_btn)
        footer.addStretch()
        layout.addLayout(columns, stretch=0)
        layout.addLayout(footer)

    @property
    def screen_results(self):
        return self._screen_results

    def available_run_ids(self):
        """Return run IDs with status 'available'."""
        if self._screen_results is None:
            return []
        return [
            r["run_id"]
            for r in self._screen_results["runs"]
            if r["status"] == "available"
        ]

    def load_results(self, screen_dir: str):
        """Load screen results from *screen_dir* and refresh the panel."""
        from ..dts import load_screen_results

        self._screen_dir = screen_dir
        self._screen_results = load_screen_results(screen_dir)
        self.refresh()

    def update_run(self, screen_dir: str, run_id: str):
        """Re-read data for a single run and schedule a throttled plot update.

        Called when a compute job finishes for *run_id*.  Only that run's
        time-series files are re-parsed; the rest of the cached data is kept.
        """
        from pathlib import Path
        from ..dts._utils import parse_run_time_series

        self._screen_dir = screen_dir
        if self._screen_results is None:
            self.load_results(screen_dir)
            return None

        screen_path = Path(screen_dir)
        run_dir = screen_path / run_id
        if not run_dir.exists():
            run_dir = screen_path

        for run in self._screen_results["runs"]:
            if run["run_id"] == run_id:
                run["time_series"] = parse_run_time_series(str(run_dir))
                break

        self.refresh()

    def refresh(self):
        """Rebuild metric/color combos from current screen results and update the plot."""
        old_metric = self._metric_combo.currentText()
        self._metric_combo.blockSignals(True)
        self._metric_combo.clear()
        metrics = collect_available_metrics(self._screen_results)
        self._metric_combo.addItems(metrics)
        if old_metric in metrics:
            self._metric_combo.setCurrentText(old_metric)
        elif not old_metric:
            for m in metrics:
                if "energy" in m.lower():
                    self._metric_combo.setCurrentText(m)
                    break
        self._metric_combo.blockSignals(False)

        self._derived_metrics = metrics

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

        self._update_plot_throttled()

    def _selected_run_ids(self) -> list:
        ids = self._get_selected_run_ids()
        if ids:
            return ids
        if self._screen_results is None:
            return []
        return [
            r["run_id"]
            for r in self._screen_results["runs"]
            if r["status"] == "available"
        ]

    def _on_user_interaction(self, *_args):
        """Switch to aggressive downsampling while zooming/panning."""
        if self._lod_downsample is None:
            return
        if not self._lod_active:
            self._lod_active = True
            self._plot_item.setDownsampling(
                ds=self._lod_downsample, auto=False, mode="peak"
            )
        self._lod_timer.start()

    def _restore_full_quality(self):
        """Restore auto downsampling once interaction has stopped."""
        if not self._lod_active:
            return
        self._lod_active = False
        self._plot_item.setDownsampling(auto=True, mode="peak")

    def _style_plot(self, plot):
        fg = Colors.TEXT_PRIMARY
        for axis_name in ("left", "bottom", "top", "right"):
            axis = plot.getAxis(axis_name)
            axis.setPen(pg.mkPen(fg))
            axis.setTextPen(pg.mkPen(fg))
        plot.setClipToView(True)
        plot.setDownsampling(auto=True, mode="peak")
        pg.setConfigOptions(antialias=True)

    def _on_derived_text_changed(self, text):
        """Update completer model to complete the last token."""
        from qtpy.QtCore import QStringListModel

        parts = re.split(r"\s+[/\*\-\+]\s+", text, maxsplit=1)
        prefix = ""
        if len(parts) == 2:
            sep = text[len(parts[0]) : len(text) - len(parts[1])]
            prefix = parts[0] + sep

        if prefix != getattr(self, "_derived_prefix", None):
            self._derived_prefix = prefix
            completions = [prefix + m for m in self._derived_metrics]
            self._derived_completer.setModel(QStringListModel(completions))

        if not text.strip():
            self._update_plot()

    def _on_derived_committed(self):
        """Evaluate the derived expression on Enter."""
        self._update_plot()

    _DERIVED_OPS = {
        "/": lambda a, b: np.where(np.abs(b) > 1e-12, a / b, 0.0),
        "*": lambda a, b: a * b,
        "-": lambda a, b: a - b,
        "+": lambda a, b: a + b,
    }
    _DERIVED_RE = re.compile(r"^\s*(.+?)\s+([/\*\-\+])\s+(.+?)\s*$")

    def _parse_derived(self):
        """Parse the derived expression field.

        Returns ``(metric_a, op, metric_b)`` or *None* if empty/invalid.
        """
        text = self._derived_edit.text().strip()
        if not text:
            return None
        m = self._DERIVED_RE.match(text)
        if m is None:
            return None
        return m.group(1), m.group(2), m.group(3)

    def _derive_series(self, parsed, run_ids):
        """Build derived ``(run, x, y)`` tuples from two metric series."""
        metric_a, op_char, metric_b = parsed
        op = self._DERIVED_OPS[op_char]

        series_a = extract_metric_series(self._screen_results, metric_a, run_ids)
        series_b = extract_metric_series(self._screen_results, metric_b, run_ids)
        b_by_run = {run["run_id"]: (run, x, y) for run, x, y in series_b}

        result = []
        for run, x_a, y_a in series_a:
            if run["run_id"] not in b_by_run:
                continue
            _, _, y_b = b_by_run[run["run_id"]]
            n = min(len(y_a), len(y_b))
            with np.errstate(divide="ignore", invalid="ignore"):
                y = op(y_a[:n], y_b[:n])
            result.append((run, x_a[:n], y))
        return result

    def _extract_series(self):
        """Extract (run_dict, x, y) tuples for the active metric or derived expression."""
        if self._screen_results is None:
            return [], ""

        run_ids = set(self._selected_run_ids())
        parsed = self._parse_derived()
        if parsed is not None:
            label = f"{parsed[0]} {parsed[1]} {parsed[2]}"
            series = self._derive_series(parsed, run_ids)
            return series, label

        metric_display = self._metric_combo.currentText()
        if not metric_display:
            return [], ""
        series = extract_metric_series(self._screen_results, metric_display, run_ids)
        return series, metric_display

    def _update_readout(self, series):
        """Populate the readout table with per-run aggregates."""
        table = self._readout_table
        table.setSortingEnabled(False)

        if not series:
            table.setRowCount(0)
            table.setColumnCount(0)
            table.setSortingEnabled(True)
            return

        cols = ["Run", "Mean", "Min", "Max"]
        table.setColumnCount(len(cols))
        table.setHorizontalHeaderLabels(cols)
        table.setRowCount(len(series))

        for row, (run, _, y) in enumerate(series):
            run_item = QTableWidgetItem(run["run_id"])
            run_item.setFlags(run_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 0, run_item)

            for col, val in enumerate(
                [np.nanmean(y), np.nanmin(y), np.nanmax(y)], start=1
            ):
                item = QTableWidgetItem()
                item.setData(Qt.ItemDataRole.DisplayRole, f"{val:.4g}")
                item.setData(Qt.ItemDataRole.UserRole, float(val))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row, col, item)

        table.setSortingEnabled(True)

    def _plot_multi_run(self, series, ylabel, xlabel="Frame"):
        plot = self._plot_item

        # Cancel any pending LOD restore and return the plot to a known
        # downsample state before rebuilding. Without this the new curves
        # inherit whatever fixed-ds mode was active mid-gesture, and a
        # late-firing timer can touch a half-rebuilt plot.
        self._lod_timer.stop()
        if self._lod_active:
            self._lod_active = False
            plot.setDownsampling(auto=True, mode="peak")

        self._plot_widget.setUpdatesEnabled(False)
        plot.vb.disableAutoRange()

        plot.clear()
        if plot.legend is not None:
            scene = plot.legend.scene()
            if scene is not None:
                scene.removeItem(plot.legend)
            plot.legend = None

        if not series:
            self._lod_downsample = None
            self._stack.setCurrentIndex(0)
            self._plot_widget.setUpdatesEnabled(True)
            return

        total_points = sum(len(y) for _, _, y in series)
        if total_points <= self._LOD_TARGET_POINTS:
            self._lod_downsample = None
        else:
            self._lod_downsample = max(2, total_points // self._LOD_TARGET_POINTS)

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

        plot.setLabel("left", ylabel)
        plot.setLabel("bottom", xlabel)
        show_legend = len(series) <= 20
        if show_legend:
            plot.addLegend(offset=(-10, 10))

        colors = generate_gradient_colors(cmap_name, max(len(series), 2))

        for i, (run, x, y) in enumerate(series):
            if norm_mode == "Per-run" and np.max(np.abs(y)) > 0:
                y = (y - np.min(y)) / (np.max(y) - np.min(y) + 1e-12)
            elif norm_mode == "Relative" and len(y) > 0 and abs(y[0]) > 1e-12:
                y = y / y[0]

            window = self._smooth_combo.currentData()
            if window > 1:
                pad = window // 2
                y_padded = np.pad(y, pad, mode="edge")
                kernel = np.ones(window) / window
                y = np.convolve(y_padded, kernel, mode="same")[pad : pad + len(y)]

            color = colors[i % len(colors)]

            name = None
            if show_legend:
                label_parts = [run["run_id"]]
                if color_by and color_by != "(auto)":
                    val = run["params"].get(color_by, "?")
                    label_parts.append(f"{color_by}={val}")
                name = " ".join(label_parts)

            plot.plot(
                x,
                y,
                pen=pg.mkPen(color, width=1.5),
                name=name,
                skipFiniteCheck=True,
            )

        self._plot_widget.setUpdatesEnabled(True)
        plot.vb.enableAutoRange()
        QTimer.singleShot(0, plot.vb.autoRange)

    def _update_plot(self, *_args):
        series, metric_display = self._extract_series()
        self._plot_multi_run(series, metric_display)
        self._update_readout(series)

    def _save_derived(self):
        """Write the derived metric as .xvg into each run's mosaic/ folder."""
        from pathlib import Path
        from ..dts._utils import write_xvg, sanitize_label

        parsed = self._parse_derived()
        if parsed is None:
            return

        series, label = self._extract_series()
        if not series:
            return

        stem = sanitize_label(label)
        written = 0
        for run, x, y in series:
            run_dir = run.get("run_dir")
            if not run_dir:
                continue
            mosaic_dir = Path(run_dir) / "mosaic"
            mosaic_dir.mkdir(parents=True, exist_ok=True)
            write_xvg(
                str(mosaic_dir / f"{stem}.xvg"),
                ["frame", stem],
                np.column_stack([x, y]),
                metadata={"computation": "derived", "expression": label},
            )
            written += 1

        if written:
            self.refresh()

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
        series, metric_display = self._extract_series()
        if not series:
            return

        if self._parse_derived() is not None:
            col_name = metric_display
        else:
            col_name = metric_display.split("/", 1)[-1]

        try:
            with open(path, "w") as f:
                param_names = self._screen_results.get("parameter_names", [])
                header = ["run_id"] + param_names + ["frame", col_name]
                f.write(sep.join(header) + "\n")

                for run, x, y in series:
                    for frame_i in range(len(y)):
                        parts = [run["run_id"]]
                        parts.extend(str(run["params"].get(p, "")) for p in param_names)
                        parts.append(str(frame_i))
                        parts.append(str(y[frame_i]))
                        f.write(sep.join(parts) + "\n")
        except Exception as e:
            from qtpy.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Export Error", str(e))

    def _export_statistics(self):
        from qtpy.QtWidgets import QFileDialog

        tbl = self._readout_table
        if tbl.rowCount() == 0:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Statistics", "", "CSV (*.csv);;TSV (*.tsv)"
        )
        if not path:
            return

        sep = "\t" if path.endswith(".tsv") else ","
        cols = [tbl.horizontalHeaderItem(c).text() for c in range(tbl.columnCount())]
        with open(path, "w") as f:
            f.write(sep.join(cols) + "\n")
            for row in range(tbl.rowCount()):
                parts = []
                for col in range(tbl.columnCount()):
                    item = tbl.item(row, col)
                    parts.append(item.text() if item else "")
                f.write(sep.join(parts) + "\n")
