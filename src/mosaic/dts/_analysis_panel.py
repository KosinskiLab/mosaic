"""
Analysis panel widget for DTS screening dialog.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import Callable, Optional

import numpy as np
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QSpinBox,
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
from ..stylesheets import Colors
from ..icons import icon
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

    def __init__(
        self,
        get_selected_run_ids: Optional[Callable] = None,
        parent=None,
    ):
        super().__init__(parent)
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
        self._plot_widget.setMinimumHeight(240)
        self._plot_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._plot_item = self._plot_widget.addPlot()
        self._style_plot(self._plot_item)

        self._placeholder = QLabel(
            "No time series data available.\n" "Select a metric to display."
        )
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 13px;")

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

        self._alpha_spin = QSpinBox()
        self._alpha_spin.setRange(10, 100)
        self._alpha_spin.setValue(100)
        self._alpha_spin.setSuffix("%")
        self._alpha_spin.setToolTip("Line opacity")
        self._alpha_spin.valueChanged.connect(self._update_plot)
        form.addRow("Alpha:", self._alpha_spin)

        columns.addWidget(display, stretch=1, alignment=Qt.AlignmentFlag.AlignTop)

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
        self._readout_table.setMaximumHeight(168)
        self._readout_table.setStyleSheet(
            "QTableWidget::item:hover { background: none; }"
            "QTableWidget::item:selected,"
            "QTableWidget::item:selected:hover"
            "{ background-color: rgba(99, 102, 241, 0.15); }"
        )
        stats_layout.addWidget(self._readout_table)

        columns.addWidget(stats, stretch=2)

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

    def refresh(self):
        """Rebuild metric/color combos from current screen results."""
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

    def _style_plot(self, plot):
        fg = Colors.TEXT_PRIMARY
        for axis_name in ("left", "bottom", "top", "right"):
            axis = plot.getAxis(axis_name)
            axis.setPen(pg.mkPen(fg))
            axis.setTextPen(pg.mkPen(fg))
        plot.setClipToView(True)
        pg.setConfigOptions(antialias=True)

    def _extract_series(self):
        """Extract (run_dict, x, y) tuples for the selected metric and runs."""
        metric_display = self._metric_combo.currentText()
        if not metric_display or self._screen_results is None:
            return [], ""
        series = extract_metric_series(
            self._screen_results, metric_display, set(self._selected_run_ids())
        )
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

            for col, val in enumerate([np.mean(y), np.min(y), np.max(y)], start=1):
                item = QTableWidgetItem()
                item.setData(Qt.ItemDataRole.DisplayRole, f"{val:.4g}")
                item.setData(Qt.ItemDataRole.UserRole, float(val))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row, col, item)

        table.setSortingEnabled(True)

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

        plot.setLabel("left", ylabel)
        plot.setLabel("bottom", xlabel)
        plot.addLegend(offset=(-10, 10))

        colors = generate_gradient_colors(cmap_name, max(len(series), 2))

        for i, (run, x, y) in enumerate(series):
            if norm_mode == "Per-run" and np.max(np.abs(y)) > 0:
                y = (y - np.min(y)) / (np.max(y) - np.min(y) + 1e-12)
            elif norm_mode == "Relative" and len(y) > 0 and abs(y[0]) > 1e-12:
                y = y / y[0]

            color = colors[i % len(colors)]
            alpha = int(self._alpha_spin.value() * 255 / 100)
            pen_color = pg.mkColor(color.red(), color.green(), color.blue(), alpha)

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
        series, metric_display = self._extract_series()
        self._plot_multi_run(series, metric_display)
        self._update_readout(series)

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
