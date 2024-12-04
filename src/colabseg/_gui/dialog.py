""" Dialog functions used throughout the GUI.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""
from os.path import exists

import numpy as np
import qtawesome as qta
import pyqtgraph as pg
import pyqtgraph.exporters
from PyQt6.QtCore import Qt, QLocale
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QDialog,
    QLabel,
    QDialogButtonBox,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QFormLayout,
    QCheckBox,
    QHBoxLayout,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QGroupBox,
    QListWidgetItem,
    QListWidget,
    QWidget,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLineEdit,
)
from PyQt6.QtGui import QDoubleValidator

from ..utils import find_closest_points


def format_tooltip(title, description, default_value=None, notes=None):
    tooltip = f"""
    <div style='font-family: Arial, sans-serif;'>
        <b style='color: #2c3e50; font-size: 11pt;'>{title}</b>
        <p style='margin: 5px 0; color: #34495e;'>{description}</p>
    """

    if default_value is not None:
        tooltip += f"""
        <p style='margin: 5px 0;'>
            <span style='color: #7f8c8d;'>Default:</span>
            <span style='color: #2980b9;'>{default_value}</span>
        </p>
        """

    if notes:
        tooltip += f"""
        <p style='margin: 5px 0; font-style: italic; color: #95a5a6;'>
            Note: {notes}
        </p>
        """

    tooltip += "</div>"
    return tooltip


class OperationDialog(QDialog):
    def __init__(self, operation_type, parameters, parent=None):
        super().__init__(parent)
        self.operation_type = operation_type
        self.parameters = parameters
        self.parameter_widgets = {}
        self.label_widgets = {}
        self.is_hierarchical = isinstance(parameters, dict)

        self.setWindowTitle(self.operation_type)
        self.main_layout = QVBoxLayout(self)
        self.params_layout = QFormLayout()

        if self.is_hierarchical:
            self.type_selector = QComboBox()
            self.type_selector.addItems(list(self.parameters.keys()))
            self.type_selector.currentIndexChanged.connect(
                self.update_operation_options
            )
            self.params_layout.addRow("Option:", self.type_selector)

        self.main_layout.addLayout(self.params_layout)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.main_layout.addWidget(button_box)

        if self.is_hierarchical:
            return self.update_operation_options(0)
        return self.update_parameters(self.parameters)

    def update_operation_options(self, index):
        current_type = list(self.parameters.keys())[index]
        self.update_parameters(self.parameters[current_type])

    def update_parameters(self, parameters):
        while self.params_layout.rowCount() > (1 if self.is_hierarchical else 0):
            self.params_layout.removeRow(self.params_layout.rowCount() - 1)
        self.parameter_widgets.clear()
        self.label_widgets.clear()

        for param_info in parameters:
            label, value, min_value, tooltip_info = param_info
            tooltip = format_tooltip(**tooltip_info)
            label_widget = QLabel(f"{tooltip_info['title']}:")
            label_widget.setToolTip(tooltip)

            if isinstance(value, bool):
                widget = QCheckBox()
                widget.setChecked(value)
            elif isinstance(min_value, list):
                widget = QComboBox()
                widget.addItems(min_value)
                widget.setCurrentText(value)
            elif isinstance(value, float):
                widget = QLineEdit()
                if isinstance(min_value, float):
                    validator = QDoubleValidator()
                    validator.setLocale(QLocale.c())
                    validator.setNotation(QDoubleValidator.Notation.StandardNotation)
                    validator.setBottom(min_value)
                    widget.setValidator(validator)
                widget.setText(str(value))
            else:
                widget = QSpinBox()
                widget.setMinimum(int(min_value))
                widget.setMaximum(2147483647)
                widget.setValue(value)

            widget.setToolTip(tooltip)
            self.label_widgets[label] = label_widget
            self.parameter_widgets[label] = widget
            self.params_layout.addRow(label_widget, widget)

    def get_parameters(self):
        ret = {}
        for param_name, widget in self.parameter_widgets.items():
            if isinstance(widget, QCheckBox):
                ret[param_name] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                ret[param_name] = widget.currentText()
            elif isinstance(widget, QLineEdit):
                validator = widget.validator()
                if validator:
                    ret[param_name] = float(widget.text())
                else:
                    ret[param_name] = widget.text()
            else:
                ret[param_name] = widget.value()
        return ret


class ParameterHandler:
    def __init__(self, operation_dict, settings_button, selector):
        self.operation_dict = operation_dict
        self.settings_button = settings_button
        self.selector = selector
        self.parameters_store = {}

        self.update_button(self.selector.currentText())
        for op_type, params in self.operation_dict.items():
            if not params:
                continue
            self.parameters_store[op_type] = {x[0]: x[1] for x in params}

    def get(self, key, default=None):
        return self.parameters_store.get(key, default)

    def update_button(self, current_type):
        has_params = len(self.operation_dict[current_type]) > 0
        self.settings_button.setEnabled(has_params)

    def show_dialog(self):
        current_type = self.selector.currentText()
        params = []
        custom_parameters = self.parameters_store.get(current_type, {})

        for param in self.operation_dict[current_type].copy():
            default = custom_parameters.get(param[0], param[1])
            params.append(tuple(x if i != 1 else default for i, x in enumerate(param)))

        def _ident(**kwargs):
            return kwargs

        kwargs = show_parameter_dialog(
            current_type,
            params,
            self.settings_button.parent(),
            {current_type: _ident},
            self.settings_button,
        )

        if isinstance(kwargs, dict):
            self.parameters_store[current_type] = kwargs


def show_parameter_dialog(
    operation_type, parameters, obj, mapping={}, source_widget=None
):
    dialog = OperationDialog(operation_type, parameters, obj)
    if source_widget:
        pos = source_widget.mapToGlobal(source_widget.rect().bottomLeft())
        dialog.move(pos)

    if dialog.exec() == QDialog.DialogCode.Rejected:
        return -1

    params = dialog.get_parameters()
    if dialog.is_hierarchical:
        params["method"] = dialog.type_selector.currentText()

    func = mapping.get(operation_type)
    if func is None:
        print(f"{operation_type} is unknown - Supported are {mapping.keys()}.")
    return func(**params)


def make_param(param, default, min_val=0, description=None, notes=None):
    return (
        param,
        default,
        min_val,
        {
            "title": param.lower().replace("_", " ").capitalize(),
            "description": description or param,
            "default_value": str(default),
            "notes": notes if notes else None,
        },
    )


class MeshEquilibrationDialog(OperationDialog):
    def __init__(self, parent=None):
        self._operations = [
            make_param("average_edge_length", 40.0, 0, "Average edge length of mesh."),
            make_param("lower_bound", 35.0, 0, "Minimum edge length of mesh (lc1)."),
            make_param("upper_bound", 45.0, 0, "Maximumg edge length of mesh (lc0)."),
            make_param("steps", 5000, 0, "Number of minimization steps."),
            make_param("kappa_b", 300.0, 0, "Bending energy coefficient (kappa_b)."),
            make_param("kappa_a", 1e6, 0, "Area conservation coefficient (kappa_a)."),
            make_param("kappa_v", 1e6, 0, "Volume conservation coefficient (kappa_v)."),
            make_param("kappa_c", 0.0, 0, "Curvature energy coefficient (kappa_c)."),
            make_param("kappa_t", 1e5, 0, "Edge tension coefficient (kappa_t)."),
            make_param("kappa_r", 1e3, 0, "Surface repulsion coefficient (kappa_r)."),
            make_param("volume_fraction", 1.1, 0, "Fraction VN/V0."),
            make_param("area_fraction", 1.1, 0, "Fraction AN/A0."),
            make_param(
                "scaling_lower", 1.0, 0, "Lower bound for rescalde mesh edge length."
            ),
        ]

        super().__init__("Mesh Equilibration", self._operations, parent)
        self.setup_custom_ui()

    def setup_custom_ui(self):
        # Hide all parameter widgets initially except edge length
        self.edge_length = self.parameter_widgets[self._operations[0][0]]
        self.edge_length.textChanged.connect(self.update_bounds)

        # Add parameter mode selection
        self.mode_selector = QComboBox()
        self.mode_selector.addItems(["Default", "Advanced"])
        self.mode_selector.currentTextChanged.connect(self.toggle_advanced)
        self.params_layout.insertRow(1, "Settings:", self.mode_selector)
        self.toggle_advanced("Default")

    def update_bounds(self, value):
        try:
            val = float(value)
            lower_bound = self.parameter_widgets["lower_bound"]
            upper_bound = self.parameter_widgets["upper_bound"]
            if lower_bound and upper_bound:
                lower_bound.setText(f"{val * 0.75}")
                upper_bound.setText(f"{val * 1.25}")
        except ValueError:
            pass

    def toggle_advanced(self, mode):
        for name, widget in self.parameter_widgets.items():
            if widget != self.edge_length:
                widget.setVisible(mode == "Advanced")

        for name, widget in self.label_widgets.items():
            if name != "average_edge_length":
                widget.setVisible(mode == "Advanced")


class HMFFDialog(OperationDialog):
    def __init__(self, parent=None, mesh_options=[""]):
        self._operations = [
            make_param("mesh", mesh_options[0], mesh_options, "Mesh to simulate."),
            make_param("volume_path", 0.0, "", "Path to HMFF potential file."),
            make_param(
                "lowpass_cutoff", 140.0, 0.0, "Resolution to lowpass filter to [Å]."
            ),
            make_param(
                "highpass_cutoff", 900.0, 0.0, "Resolution to highpass filter to [Å]."
            ),
            make_param(
                "invert_contrast",
                True,
                [False, True],
                "Invert data, i.e. switch from Black-White to White-Black contrast.",
            ),
            make_param("xi", 5.0, 0.0, "Weighting factor of HMFF potential."),
            make_param(
                "gradient_step_size",
                0.0,
                0.0,
                "Gradient step size along HMFF potential.",
            ),
            make_param("kappa", 25.0, 0.0, "Membrane rigidity."),
            make_param("steps", 50000, 0.0, "Simulation steps."),
            make_param("threads", 1, 0, "Simulation threads."),
        ]
        super().__init__("Setup HMFF", self._operations, parent)
        self.setup_custom_ui()

    def setup_custom_ui(self):
        self.volume_input = self.parameter_widgets["volume_path"]
        self.volume_input.setText("")
        self.select_volume_button = QPushButton()
        self.select_volume_button.setIcon(
            qta.icon("fa5s.folder-open", opacity=0.7, color="gray")
        )
        self.select_volume_button.clicked.connect(self.browse_volume)

        volume_layout = QHBoxLayout()
        label = QLabel("Volume path:")
        volume_layout.addWidget(self.volume_input)
        volume_layout.addWidget(self.select_volume_button)

        row_index = 0
        for i, k in enumerate(self._operations):
            if k[0] == "volume_path":
                row_index = i

        self.params_layout.removeRow(row_index)
        self.params_layout.insertRow(row_index, label, volume_layout)

        self.lowpass_input = self.parameter_widgets["lowpass_cutoff"]
        self.highpass_input = self.parameter_widgets["highpass_cutoff"]

        self.lowpass_input.textChanged.connect(self.validate_filters)
        self.highpass_input.textChanged.connect(self.validate_filters)

        self.volume_input.textChanged.connect(self.validate_volume)

    def browse_volume(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Volume File",
            "",
            "Volume Files (*.mrc *.map *.em);;All Files (*.*)",
        )
        if file_path:
            self.volume_input.setText(file_path)

    def validate_filters(self):
        lowpass = float(self.lowpass_input.text())
        highpass = float(self.highpass_input.text())

        valid_range = all([highpass >= lowpass])
        style = "" if valid_range else "background-color: #d32f2f;"
        self.lowpass_input.setStyleSheet(style)
        self.highpass_input.setStyleSheet(style)

        return valid_range

    def validate_volume(self):
        vol_path = self.volume_input.text()
        if not vol_path:
            return False

        if not exists(vol_path):
            self.volume_input.setStyleSheet("background-color: #d32f2f;")
            return False

        self.volume_input.setStyleSheet("")
        return True

    def accept(self):
        if not self.validate_volume():
            QMessageBox.warning(
                self, "Invalid Input", "Please select a valid volume file."
            )
            return

        if not self.validate_filters():
            QMessageBox.warning(
                self, "Invalid Input", "Please provide a valid filter specification."
            )
            return

        super().accept()


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
    def __init__(self, clusters, parent=None):
        super().__init__(parent)
        self.clusters = clusters
        self.setWindowTitle("Distance Analysis")
        self.resize(1200, 800)

        self.distances = []

        # Maintain access to pyqtgraph plot modulation features
        self.setWindowFlags(Qt.WindowType.Window)
        self.setup_ui()

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

        source_group = QGroupBox("Select Source Clusters")
        source_layout = QVBoxLayout()
        self.source_list = QListWidget()
        self.source_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        for name, data in self.clusters:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, data)
            self.source_list.addItem(item)
        source_layout.addWidget(self.source_list)
        source_group.setLayout(source_layout)
        config_layout.addWidget(source_group)

        target_group = QGroupBox("Select Target Clusters")
        target_layout = QVBoxLayout()

        self.exclude_self_checkbox = QCheckBox("Exclude within-cluster distances")
        self.exclude_self_checkbox.setChecked(True)

        self.all_targets_checkbox = QCheckBox("Compare with all other clusters")
        self.all_targets_checkbox.stateChanged.connect(self.toggle_target_list)
        target_layout.addWidget(self.exclude_self_checkbox)
        target_layout.addWidget(self.all_targets_checkbox)

        self.target_list = QListWidget()
        self.target_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        for name, data in self.clusters:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, data)
            self.target_list.addItem(item)
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
        self.alpha_value.setValue(255)
        alpha_layout.addWidget(alpha_label)
        alpha_layout.addWidget(self.alpha_value)
        self.alpha_value.valueChanged.connect(self._update_plot)

        neighbor_layout = QHBoxLayout()
        neighbor_label = QLabel("k-Nearest Neighbor:")
        self.neighbor_value = QSpinBox()
        self.neighbor_value.setRange(1, 255)
        self.neighbor_value.setValue(1)
        neighbor_layout.addWidget(neighbor_label)
        neighbor_layout.addWidget(self.neighbor_value)

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
        return config_widget

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

        ret = []
        k = int(self.neighbor_value.value())
        for source in sources:
            temp = [x for x in targets if x.text() != source.text()]
            if not self.exclude_self_checkbox.isChecked():
                temp = [x for x in targets]

            source = source.data(Qt.ItemDataRole.UserRole)
            target_data, bins = [], []
            for target_cluster in temp:
                xdata = target_cluster.data(Qt.ItemDataRole.UserRole)
                target_data.append(xdata)
                bins.append(xdata.shape[0])

            if not len(target_data):
                return -1

            target_data = np.concatenate(target_data)
            distances, indices = find_closest_points(target_data, source, k=k)
            if k > 1:
                k_index = k - 1
                distances, indices = distances[:, k_index], indices[:, k_index]

            bins = np.cumsum(bins)
            clusters = np.digitize(indices, bins)
            ret.append((distances, clusters))

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
        for idx, (distance, index) in enumerate(distances):
            subplot = self.plot_widget.addPlot(row=idx // n_cols, col=idx % n_cols)
            subplot.setTitle(sources[idx].text())
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
                    name=f"Target {target}",
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

        exporter = pg.exporters.ImageExporter(self.plot_widget.plotItem)
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
            ofile.write("\n".join([f"{x}" for x in self.distances]))
        QMessageBox.information(self, "Success", "Data export successful.")


class DistanceStatsDialog(QDialog):
    def __init__(self, cluster_data, parent=None):
        super().__init__(parent)
        self.cluster_data = cluster_data
        self.setWindowTitle("Distance Statistics")
        self.resize(600, 300)

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.table = QTableWidget()

        self.header = ["Count", "Centroid", "Std", "Min", "Max", "Density"]

        self.table.setRowCount(len(self.header))
        self.table.setColumnCount(len(self.cluster_data))

        headers = [name for name, _ in self.cluster_data]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setVerticalHeaderLabels(self.header)

        for col, (_, points) in enumerate(self.cluster_data):
            stats = self.calculate_stats(points)
            for row, value in enumerate(stats):
                if isinstance(value, tuple):
                    text = f"({value[0]:.2f}, {value[1]:.2f}, {value[2]:.2f})"
                else:
                    text = str(value)
                self.table.setItem(row, col, QTableWidgetItem(text))

        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )

        export_btn = QPushButton("Export Statistics")
        export_btn.clicked.connect(self.export_stats)

        layout.addWidget(self.table)
        layout.addWidget(export_btn)
        self.setLayout(layout)

    def calculate_stats(self, points):
        mins = np.min(points, axis=0)
        maxs = np.max(points, axis=0)
        volume = np.prod(maxs - mins)
        density = len(points) / volume if volume > 0 else 0

        return [
            len(points),
            tuple(np.mean(points, axis=0)),
            tuple(np.std(points, axis=0)),
            tuple(mins),
            tuple(maxs),
            density,
            volume,
        ]

    def export_stats(self):
        sep = "\t"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Statistics", "", "TSV Files (*.tsv)"
        )
        if not filename:
            return -1
        header = (
            "Statistic"
            + sep
            + sep.join(
                self.table.horizontalHeaderItem(i).text()
                for i in range(self.table.columnCount())
            )
        )
        rows = []
        for row in range(self.table.rowCount()):
            row_data = [self.table.verticalHeaderItem(row).text()]
            row_data.extend(
                self.table.item(row, col).text()
                for col in range(self.table.columnCount())
            )
            rows.append(sep.join(row_data))

        with open(filename, mode="w", encoding="utf-8") as ofile:
            ofile.write(header + "\n")
            ofile.write("\n".join(rows))

        QMessageBox.information(self, "Success", "Data saved successfully.")


class DistanceCropDialog(QDialog):
    def __init__(self, cluster_data, parent=None):
        super().__init__(parent)
        self.cluster_data = cluster_data
        self.setWindowTitle("Distance Crop")
        self.resize(500, 250)
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout()

        source_layout = QVBoxLayout()
        label = QLabel("Source Clusters")
        tooltip = format_tooltip("Source Clusters", "Clusters to crop.", None)
        label.setToolTip(tooltip)
        source_layout.addWidget(label)
        self.source_list = QListWidget()
        self.source_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        source_layout.addWidget(self.source_list)

        target_layout = QVBoxLayout()
        label = QLabel("Target Clusters")
        tooltip = format_tooltip(
            "Target Clusters", "Reference to compute source distances to.", None
        )
        label.setToolTip(tooltip)
        target_layout.addWidget(label)
        self.target_list = QListWidget()
        self.target_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        target_layout.addWidget(self.target_list)

        for name, _ in self.cluster_data:
            self.source_list.addItem(name)
            self.target_list.addItem(name)

        param_layout = QVBoxLayout()
        dist_layout = QHBoxLayout()
        label = QLabel("Distance:")
        tooltip = format_tooltip(
            "Distance", "Maximum distance between source and target.", 40
        )
        label.setToolTip(tooltip)
        dist_layout.addWidget(label)
        self.distance_input = QDoubleSpinBox()
        self.distance_input.setValue(40.0)
        self.distance_input.setMaximum(float("inf"))
        self.distance_input.setMinimumWidth(100)
        self.distance_input.setDecimals(2)
        dist_layout.addWidget(self.distance_input)

        apply_btn = QPushButton("Apply Crop")
        apply_btn.clicked.connect(self.apply_crop)

        param_layout.addLayout(dist_layout)
        param_layout.addWidget(apply_btn)
        param_layout.addStretch()

        layout.addLayout(source_layout)
        layout.addLayout(target_layout)
        layout.addLayout(param_layout)
        self.setLayout(layout)

    def get_results(self):
        if self.exec() == QDialog.DialogCode.Accepted:
            return self.sources, self.targets, self.distance
        return None, None, None

    def apply_crop(self):
        self.sources = [
            self.source_list.row(x) for x in self.source_list.selectedItems()
        ]
        self.targets = [
            self.target_list.row(x) for x in self.target_list.selectedItems()
        ]
        self.distance = self.distance_input.value()
        self.accept()
