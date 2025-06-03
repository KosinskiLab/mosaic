import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QVBoxLayout,
    QDialog,
    QLabel,
    QSpinBox,
    QComboBox,
    QCheckBox,
    QHBoxLayout,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QGroupBox,
    QListWidget,
    QWidget,
    QSplitter,
)

from ..widgets import ContainerListWidget, StyledListWidgetItem
from ..stylesheets import QGroupBox_style, QPushButton_style, QListWidget_style


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


class DistanceAnalysisDialog(QDialog):
    def __init__(self, clusters, fits=[], parent=None):
        super().__init__(parent)
        self.clusters, self.fits = clusters, fits

        self.setWindowTitle("Distance Analysis")

        self.distances = []

        # Maintain access to pyqtgraph plot modulation features
        self.setWindowFlags(Qt.WindowType.Window)
        self.setup_ui()
        self.setStyleSheet(QGroupBox_style + QPushButton_style + QListWidget_style)
        self.resize(1200, 800)

    def setup_ui(self):
        layout = QHBoxLayout(self)

        # Catch QDialog auto highlight
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

        preset_group = QGroupBox("Quick Presets")
        preset_layout = QHBoxLayout()

        one_to_all_btn = QPushButton("One → All")
        one_to_all_btn.clicked.connect(self.preset_one_to_all)
        all_to_all_btn = QPushButton("All ↔ All")
        all_to_all_btn.clicked.connect(self.preset_all_to_all)

        preset_layout.addWidget(one_to_all_btn)
        preset_layout.addWidget(all_to_all_btn)
        preset_group.setLayout(preset_layout)
        config_layout.addWidget(preset_group)

        source_group = QGroupBox("Select Source")
        source_layout = QVBoxLayout()
        self.source_list = ContainerListWidget(border=False)
        self.source_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        for name, data in self.clusters:
            item = StyledListWidgetItem(name, data.visible, data._meta.get("info"))
            item.setData(Qt.ItemDataRole.UserRole, data)
            self.source_list.addItem(item)
        source_layout.addWidget(self.source_list)
        source_group.setLayout(source_layout)
        config_layout.addWidget(source_group)

        target_group = QGroupBox("Select Target")
        target_layout = QVBoxLayout()

        target_type_layout = QHBoxLayout()
        target_type_label = QLabel("Target Type:")
        self.target_type_combo = QComboBox()
        self.target_type_combo.addItems(["Clusters", "Fits", "Both"])
        self.target_type_combo.currentTextChanged.connect(self._update_target_list)
        target_type_layout.addWidget(target_type_label)
        target_type_layout.addWidget(self.target_type_combo)
        target_layout.addLayout(target_type_layout)

        checkbox_group = QGroupBox("Comparison Options")
        checkbox_layout = QVBoxLayout()
        self.all_targets_checkbox = QCheckBox("Compare to All")
        self.all_targets_checkbox.stateChanged.connect(self.toggle_target_list)
        self.include_self_checkbox = QCheckBox("Include Within-Cluster Distance")
        self.include_self_checkbox.setChecked(False)
        checkbox_layout.addWidget(self.all_targets_checkbox)
        checkbox_layout.addWidget(self.include_self_checkbox)
        checkbox_group.setLayout(checkbox_layout)

        target_layout.addWidget(checkbox_group)

        self.target_list = ContainerListWidget(border=False)
        self.target_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)

        target_layout.addWidget(self.target_list)
        target_group.setLayout(target_layout)
        config_layout.addWidget(target_group)

        strat_group = QGroupBox("Options")
        strat_layout = QVBoxLayout()

        strat_attr_layout = QHBoxLayout()
        self.strat_attr_label = QLabel("Stratification:")
        self.strat_attr_combo = QComboBox()
        self.strat_attr_combo.addItems(["Default", "Target"])
        self.strat_attr_combo.setEnabled(True)
        self.strat_attr_combo.currentIndexChanged.connect(self._update_plot)
        strat_attr_layout.addWidget(self.strat_attr_label)
        strat_attr_layout.addWidget(self.strat_attr_combo)

        # Color palette selection
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
        self.palette_combo.setEnabled(True)
        self.palette_combo.currentIndexChanged.connect(self._update_plot)
        palette_layout.addWidget(self.palette_label)
        palette_layout.addWidget(self.palette_combo)

        alpha_layout = QHBoxLayout()
        alpha_label = QLabel("Blend Alpha:")
        self.alpha_value = QSpinBox()
        self.alpha_value.setRange(0, 255)
        self.alpha_value.setValue(127)
        alpha_layout.addWidget(alpha_label)
        alpha_layout.addWidget(self.alpha_value)
        self.alpha_value.valueChanged.connect(self._update_plot)

        neighbor_layout = QHBoxLayout()
        neighbor_label = QLabel("k-Nearest Neighbors:")
        knn_layout = QHBoxLayout()
        self.neighbor_start = QSpinBox()
        self.neighbor_start.setRange(1, 255)
        self.neighbor_start.setValue(1)
        neighbor_to_label = QLabel("to")
        self.neighbor_end = QSpinBox()
        self.neighbor_end.setRange(1, 255)
        self.neighbor_end.setValue(1)
        knn_layout.addWidget(self.neighbor_start)
        neighbor_to_label.setAlignment(Qt.AlignCenter)
        knn_layout.addWidget(neighbor_to_label)
        knn_layout.addWidget(self.neighbor_end)
        neighbor_layout.addWidget(neighbor_label)
        neighbor_layout.addLayout(knn_layout)

        strat_layout.addLayout(neighbor_layout)
        strat_layout.addLayout(strat_attr_layout)
        strat_layout.addLayout(palette_layout)
        strat_layout.addLayout(alpha_layout)
        strat_group.setLayout(strat_layout)
        config_layout.addWidget(strat_group)

        compute_btn = QPushButton("Compute Distances")
        compute_btn.clicked.connect(self._compute_distances)
        config_layout.addStretch()
        config_layout.addWidget(compute_btn)

        self._update_target_list()
        return config_widget

    def _update_target_list(self):
        self.target_list.clear()

        self.include_self_checkbox.setEnabled(True)
        self.neighbor_start.setEnabled(True)
        self.neighbor_end.setEnabled(True)

        data = self.clusters
        if self.target_type_combo.currentText() in ["Fits", "Both"]:
            data = self.fits
            if self.target_type_combo.currentText() == "Both":
                data = [*self.clusters, *self.fits]
            self.include_self_checkbox.setEnabled(False)
            self.neighbor_start.setEnabled(False)
            self.neighbor_end.setEnabled(False)

        for name, element in data:
            item = StyledListWidgetItem(
                name, element.visible, element._meta.get("info")
            )
            item.setData(Qt.ItemDataRole.UserRole, element)
            self.target_list.addItem(item)
        return 0

    def _create_histogram_widget(self):
        from ..icons import dialog_accept_icon

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
        close_btn = QPushButton("Done")
        close_btn.setIcon(dialog_accept_icon)
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)
        viz_layout.addLayout(button_layout)

        return viz_widget

    def _get_distances(self, source, targets, k, k_start):
        from ..utils import find_closest_points

        source_name = source.text()
        query_points = source.data(Qt.ItemDataRole.UserRole).points

        distances, bins = [], []
        if self.target_type_combo.currentText() in ["Fits", "Both"]:
            for index, target in enumerate(targets):
                target_data = target.data(Qt.ItemDataRole.UserRole)

                dist = target_data.compute_distance(query_points)

                distances.append(dist)
                bins.append(np.array([target.text()] * dist.size))

            return (source_name, np.concatenate(distances), np.concatenate(bins))

        target_data, bins = [], []
        for target_cluster in targets:
            xdata = target_cluster.data(Qt.ItemDataRole.UserRole).points
            target_data.append(xdata)
            bins.append(xdata.shape[0])

        if not len(target_data):
            return None

        target_data = np.concatenate(target_data)
        distances, indices = find_closest_points(target_data, query_points, k=k)
        if k > 1:
            k_slice = (slice(None), slice(k_start, k))
            distances, indices = distances[k_slice].ravel(), indices[k_slice].ravel()

        bins = np.cumsum(bins)
        clusters = np.digitize(indices, bins)
        clusters = np.array([targets[i].text() for i in clusters])
        return (source_name, distances, clusters)

    def _compute_distances(self):
        sources = self.source_list.selectedItems()

        targets = self.target_list.selectedItems()
        if self.all_targets_checkbox.isChecked():
            targets = [
                self.target_list.item(i) for i in range(self.target_list.count())
            ]

        if not len(sources) or not len(targets):
            QMessageBox.critical(self, "Error", "Sources and targets are required.")
            return -1

        k = int(self.neighbor_end.value())
        k_start = max(int(self.neighbor_start.value()) - 1, 0)
        if k <= k_start:
            return -1

        ret = []
        for source in sources:
            temp = [x for x in targets if x.text() != source.text()]
            if self.include_self_checkbox.isChecked():
                temp = [x for x in targets]

            distance = self._get_distances(source, temp, k, k_start)
            if distance is None:
                continue
            ret.append(distance)

        self.distances = ret
        self._update_plot()

    def _update_plot(self):
        distances = self.distances

        if not len(distances):
            return -1

        self.plot_widget.clear()
        sources = self.source_list.selectedItems()
        n_sources = len(sources)
        n_cols = min(2, n_sources)

        if n_cols == 0:
            return -1

        alpha = self.alpha_value.value()
        strat_mode = self.strat_attr_combo.currentText()
        for idx, (source, distance, index) in enumerate(distances):
            subplot = self.plot_widget.addPlot(row=idx // n_cols, col=idx % n_cols)
            subplot.setTitle(source)
            subplot.setLabel("left", "Frequency")
            subplot.setLabel("bottom", "Distance")

            bins = np.histogram_bin_edges(distance, bins="auto")

            if strat_mode == "Default":
                self._create_histogram(
                    subplot,
                    distance,
                    color=pg.mkColor(70, 130, 180, 200),
                    bins=bins,
                    alpha=alpha,
                )
                continue

            unique_targets = np.unique(index)

            colors = _get_distinct_colors(
                self.palette_combo.currentText(), unique_targets.size
            )

            legend = subplot.addLegend(offset=(-10, 10))
            legend.setPos(subplot.getViewBox().screenGeometry().width() - 20, 0)
            for target_idx, target in enumerate(unique_targets):
                self._create_histogram(
                    subplot,
                    distance[index == target],
                    colors[target_idx],
                    name=target,
                    bins=bins,
                    alpha=alpha,
                )

    def _create_histogram(
        self,
        subplot,
        distances,
        color,
        bins,
        width=None,
        name=None,
        y0=None,
        alpha=255,
    ):
        if width is None:
            width = (bins[1] - bins[0]) * 0.8

        hist, _ = np.histogram(distances, bins=bins)
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

    def toggle_target_list(self, state):
        self.target_list.setEnabled(not state)

    def preset_one_to_all(self):
        self.source_list.clearSelection()
        if self.source_list.count() > 0:
            self.source_list.item(0).setSelected(True)
        self.all_targets_checkbox.setChecked(True)

    def preset_all_to_all(self):
        self.source_list.selectAll()
        self.all_targets_checkbox.setChecked(True)

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

        with open(filename, mode="w", encoding="utf-8") as ofile:
            ofile.write("source,distance,target\n")
            for idx, (source, distance, index) in enumerate(self.distances):
                lines = "\n".join(
                    [f"{source},{d},{i}" for d, i in zip(distance, index)]
                )
                ofile.write(lines + "\n")

        QMessageBox.information(self, "Success", "Data export successful.")
