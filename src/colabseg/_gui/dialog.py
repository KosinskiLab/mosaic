import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters
from PyQt6.QtCore import Qt
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
)
from ..trimesh.utils import find_closest_points


class KeybindsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keybinds")

        layout = QVBoxLayout()

        keybinds = [
            ("z", "Set camera view along Z-axis"),
            ("x", "Set camera view along X-axis"),
            ("c", "Set camera view along Y-axis"),
            ("a", "Toggle draawing mode"),
            ("d", "Toggle renderer background color"),
            ("h", "Toggle visibility of selected clusters"),
            ("m", "Merge selected cluster or points"),
            ("Delete", "Remove selected cluster or points"),
            ("R", "Bring up point selector"),
            ("Right Mouse", "Deselect cluster or points"),
            ("Left Mouse Drag", "Rotate scene"),
            ("Shift Left Mouse Drag", "Translate scene"),
            ("Ctrl+O", "Open file"),
            ("Ctrl+S", "Save file"),
            ("Ctrl+H", "Show this keybinds popup"),
        ]

        for key, description in keybinds:
            key_label = QLabel(f"<b>{key}</b>: {description}")
            layout.addWidget(key_label)

        close_button = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        close_button.accepted.connect(self.accept)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setLayout(layout)

    def show_keybinds(parent):
        dialog = KeybindsDialog(parent)
        dialog.setStyleSheet(
            """
            QDialog {
                background-color: #f0f0f0;
            }
            QLabel {
                color: #333333;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """
        )
        dialog.exec()


def format_tooltip(title, description, default_value=None, notes=None):
    """Create a formatted HTML tooltip with consistent styling."""
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
            self.params_layout.addRow("Method:", self.type_selector)

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
                widget = QDoubleSpinBox()
                widget.setMinimum(min_value)
                widget.setMaximum(float("inf"))
                widget.setDecimals(4)
                widget.setValue(value)
            else:
                widget = QSpinBox()
                widget.setMinimum(min_value)
                widget.setMaximum(2147483647)
                widget.setValue(value)

            widget.setToolTip(tooltip)
            self.parameter_widgets[label] = widget
            self.params_layout.addRow(label_widget, widget)


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

        kwargs = show_parameter_dialog(
            current_type,
            params,
            self.settings_button.parent(),
            {current_type: ident},
            self.settings_button,
        )

        if isinstance(kwargs, dict):
            self.parameters_store[current_type] = kwargs


def ident(**kwargs):
    return kwargs


def show_parameter_dialog(
    operation_type, parameters, obj, mapping={}, source_widget=None
):
    dialog = OperationDialog(operation_type, parameters, obj)
    if source_widget:
        pos = source_widget.mapToGlobal(source_widget.rect().bottomLeft())
        dialog.move(pos)

    if dialog.exec() == QDialog.DialogCode.Rejected:
        return -1

    params = {}
    for label, widget in dialog.parameter_widgets.items():
        if isinstance(widget, QComboBox):
            params[label] = widget.currentText()
        elif isinstance(widget, QCheckBox):
            params[label] = widget.isChecked()
        else:
            params[label] = widget.value()

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

        self.all_targets_checkbox = QCheckBox("Compare with all other clusters")
        self.all_targets_checkbox.stateChanged.connect(self.toggle_target_list)
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

        strat_layout.addLayout(strat_attr_layout)
        strat_layout.addLayout(palette_layout)
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
        for source in sources:
            temp = [x for x in targets if x.text() != source.text()]

            source = source.data(Qt.ItemDataRole.UserRole)

            target_data, bins = [], []
            for target_cluster in temp:
                xdata = target_cluster.data(Qt.ItemDataRole.UserRole)
                target_data.append(xdata)
                bins.append(xdata.shape[0])

            target_data = np.concatenate(target_data)
            distances, indices = find_closest_points(target_data, source, k=1)
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
        n_sources = len(distances)
        n_cols = min(2, n_sources)

        strat_mode = self.strat_attr_combo.currentText()
        for idx, (distance, index) in enumerate(distances):
            subplot = self.plot_widget.addPlot(row=idx // n_cols, col=idx % n_cols)
            subplot.setTitle(f"Source: {idx}")
            subplot.setLabel("left", "Frequency")
            subplot.setLabel("bottom", "Distance")

            bins = np.histogram_bin_edges(distance, bins="auto")

            if strat_mode == "Default":
                self._create_histogram(
                    subplot,
                    distance,
                    color=pg.mkColor(70, 130, 180, 200),
                    bins=bins,
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
                )

    def _create_histogram(self, subplot, distances, color, bins, width=None, name=None):
        if width is None:
            width = (bins[1] - bins[0]) * 0.8

        hist, _ = np.histogram(distances, bins=bins)
        bin_centers = (bins[:-1] + bins[1:]) / 2

        bargraph = pg.BarGraphItem(
            x=bin_centers,
            height=hist,
            width=width,
            brush=color,
            pen=pg.mkPen("k", width=1),
            name=name,
        )
        subplot.addItem(bargraph)

    def toggle_target_list(self, state):
        self.target_list.setEnabled(not state)

    def preset_one_to_all(self):
        self.source_list.clearSelection()
        if self.source_list.count() > 0:
            self.source_list.item(0).setSelected(True)
        self.all_targets_checkbox.setChecked(True)
        self._update_plot()

    def preset_all_to_all(self):
        self.source_list.selectAll()
        self.all_targets_checkbox.setChecked(True)
        self._update_plot()

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
        QMessageBox.information(self, "Success", "Plot saved successfully!")

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
        QMessageBox.information(self, "Success", "Data exported successfully!")
