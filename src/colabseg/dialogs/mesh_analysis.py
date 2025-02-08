import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QDialog,
    QLabel,
    QSpinBox,
    QComboBox,
    QHBoxLayout,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QGroupBox,
    QListWidgetItem,
    QListWidget,
    QWidget,
    QSplitter,
)


def _get_distinct_colors(cmap_name, n):
    from matplotlib.pyplot import get_cmap

    cmap = get_cmap(cmap_name)
    colors = []
    for i in range(n):
        rgba = cmap(i)
        rgb = tuple(int(x * 255) for x in rgba[:3])
        color = pg.mkColor(*rgb, 255)
        colors.append(color)
    return colors


class MeshPropertiesDialog(QDialog):
    def __init__(self, fits=[], parent=None):
        super().__init__(parent)
        self.fits = fits

        self.setWindowTitle("Mesh Properties Analysis")
        self.resize(1200, 800)

        self.properties_data = []

        self.setWindowFlags(Qt.WindowType.Window)
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)

        default_btn = QPushButton(self)
        default_btn.setDefault(True)
        default_btn.setFixedSize(0, 0)

        config_widget = self._create_config_widget()
        viz_widget = self._create_histogram_widget()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(config_widget)
        splitter.addWidget(viz_widget)
        splitter.setSizes([360, 720])

        layout.addWidget(splitter)

    def _create_config_widget(self):
        config_widget = QWidget()
        config_layout = QVBoxLayout(config_widget)

        source_group = QGroupBox("Select Sources")
        source_layout = QVBoxLayout()
        self.source_list = QListWidget()
        self.source_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        for name, fit in self.fits:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, fit)
            self.source_list.addItem(item)
        source_layout.addWidget(self.source_list)
        source_group.setLayout(source_layout)

        preset_group = QGroupBox("Quick Presets")
        preset_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.preset_all_sources)
        none_btn = QPushButton("Clear Selection")
        none_btn.clicked.connect(self.source_list.clearSelection)
        preset_layout.addWidget(select_all_btn)
        preset_layout.addWidget(none_btn)
        preset_group.setLayout(preset_layout)
        config_layout.addWidget(preset_group)

        config_layout.addWidget(source_group)

        metric_group = QGroupBox("Select Metric")
        metric_layout = QVBoxLayout()
        self.metric_combo = QComboBox()
        self.metric_combo.addItems(["Curvature", "Area", "Volume"])
        metric_layout.addWidget(self.metric_combo)
        metric_group.setLayout(metric_layout)
        config_layout.addWidget(metric_group)

        viz_group = QGroupBox("Visualization Options")
        viz_layout = QVBoxLayout()

        plot_type_layout = QHBoxLayout()
        self.plot_type_label = QLabel("Plot Type:")
        self.plot_type_combo = QComboBox()
        self.plot_type_combo.addItems(["Combined", "Separate"])
        self.plot_type_combo.currentIndexChanged.connect(self._update_plot)
        plot_type_layout.addWidget(self.plot_type_label)
        plot_type_layout.addWidget(self.plot_type_combo)

        palette_layout = QHBoxLayout()
        self.palette_label = QLabel("Color Palette:")
        self.palette_combo = QComboBox()
        self.palette_combo.addItems(
            [
                "Set1",
                "Set2",
                "Set3",
                "tab10",
                "tab20",
                "Paired",
                "Accent",
                "Dark2",
                "Pastel1",
                "Pastel2",
            ]
        )
        self.palette_combo.currentIndexChanged.connect(self._update_plot)
        palette_layout.addWidget(self.palette_label)
        palette_layout.addWidget(self.palette_combo)

        alpha_layout = QHBoxLayout()
        alpha_label = QLabel("Blend Alpha:")
        self.alpha_value = QSpinBox()
        self.alpha_value.setRange(0, 255)
        self.alpha_value.setValue(127)
        self.alpha_value.valueChanged.connect(self._update_plot)
        alpha_layout.addWidget(alpha_label)
        alpha_layout.addWidget(self.alpha_value)

        viz_layout.addLayout(plot_type_layout)
        viz_layout.addLayout(palette_layout)
        viz_layout.addLayout(alpha_layout)
        viz_group.setLayout(viz_layout)
        config_layout.addWidget(viz_group)

        compute_btn = QPushButton("Compute Properties")
        compute_btn.clicked.connect(self._compute_properties)
        config_layout.addWidget(compute_btn)

        return config_widget

    def preset_all_sources(self):
        self.source_list.selectAll()

    def _create_histogram_widget(self):
        viz_widget = QWidget()
        viz_layout = QVBoxLayout(viz_widget)

        self.plot_widget = pg.GraphicsLayoutWidget()
        self.plot_widget.setBackground(None)
        viz_layout.addWidget(self.plot_widget)

        button_layout = QHBoxLayout()
        save_plot_btn = QPushButton("Save Plot")
        save_plot_btn.clicked.connect(self.save_plot)
        export_data_btn = QPushButton("Export Data")
        export_data_btn.clicked.connect(self.export_data)
        button_layout.addWidget(save_plot_btn)
        button_layout.addWidget(export_data_btn)
        button_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)
        viz_layout.addLayout(button_layout)

        return viz_widget

    def _compute_properties(self):
        sources = self.source_list.selectedItems()

        if not len(sources):
            QMessageBox.critical(self, "Error", "No sources selected.")
            return -1

        metric = self.metric_combo.currentText().lower()
        self.properties_data = []

        for source in sources:
            source_name = source.text()
            fit = source.data(Qt.ItemDataRole.UserRole)

            if metric == "curvature":
                values = fit.compute_curvature()
            elif metric == "area":
                values = fit.mesh.get_surface_area()
            else:
                try:
                    values = fit.mesh.get_volume()
                except Exception:
                    print(f"{source_name} is not watertight, cannot compute volume.")
                    values = 0

            self.properties_data.append((source_name, values))

        self._update_plot()

    def _update_plot(self):
        if not len(self.properties_data):
            return -1

        self.plot_widget.clear()
        plot_type = self.plot_type_combo.currentText()
        alpha = self.alpha_value.value()
        metric = self.metric_combo.currentText()

        if plot_type == "Combined":
            # Create single plot with all data
            plot = self.plot_widget.addPlot(row=0, col=0)
            plot.setTitle(f"{metric} Distribution")
            plot.setLabel("left", "Frequency")
            plot.setLabel("bottom", metric)

            # Find global bins for consistent comparison
            all_values = np.concatenate([values for _, values in self.properties_data])
            bins = np.histogram_bin_edges(all_values, bins="auto")

            colors = _get_distinct_colors(
                self.palette_combo.currentText(), len(self.properties_data)
            )

            legend = plot.addLegend(offset=(-10, 10))
            legend.setPos(plot.getViewBox().screenGeometry().width() - 20, 0)

            for idx, (name, values) in enumerate(self.properties_data):
                self._create_histogram(
                    plot, values, colors[idx], bins=bins, name=name, alpha=alpha
                )
        else:
            # Create separate plots for each source
            n_sources = len(self.properties_data)
            n_cols = min(2, n_sources)

            for idx, (name, values) in enumerate(self.properties_data):
                subplot = self.plot_widget.addPlot(row=idx // n_cols, col=idx % n_cols)
                subplot.setTitle(name)
                subplot.setLabel("left", "Frequency")
                subplot.setLabel("bottom", metric)

                bins = np.histogram_bin_edges(values, bins="auto")
                self._create_histogram(
                    subplot,
                    values,
                    pg.mkColor(70, 130, 180, 200),
                    bins=bins,
                    alpha=alpha,
                )

    def _create_histogram(
        self, subplot, values, color, bins, width=None, name=None, y0=None, alpha=255
    ):
        if width is None:
            width = (bins[1] - bins[0]) * 0.8

        hist, _ = np.histogram(values, bins=bins)
        bin_centers = (bins[:-1] + bins[1:]) / 2
        color.setAlpha(alpha)
        bargraph = pg.BarGraphItem(
            x=bin_centers,
            height=hist,
            y0=y0,
            width=width,
            brush=color,
            pen=pg.mkPen("k", width=1),
            name=name,
        )
        subplot.addItem(bargraph)
        return hist

    def save_plot(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Plot", "", "PNG Files (*.png);;All Files (*.*)"
        )
        if not filename:
            QMessageBox.critical(self, "Error", "Failed to save plot.")
            return -1

        exporter = pg.exporters.ImageExporter(self.plot_widget.scene())
        exporter.parameters()["width"] = 1920
        exporter.export(filename)
        QMessageBox.information(self, "Success", "Plot saved successfully.")

    def export_data(self):
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Data",
            "",
            "CSV Files (*.csv);;TSV Files (*.tsv);;All Files (*.*)",
        )
        if not filename:
            QMessageBox.critical(self, "Error", "Failed to export data.")
            return -1

        metric = self.metric_combo.currentText().lower()
        with open(filename, mode="w", encoding="utf-8") as ofile:
            ofile.write(f"source,{metric}\n")
            for source, values in self.properties_data:
                lines = "\n".join([f"{source},{value}" for value in values])
                ofile.write(lines + "\n")

        QMessageBox.information(self, "Success", "Data export successful.")
