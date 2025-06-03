import numpy as np
from qtpy.QtCore import Qt, QTimer
from qtpy.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QListWidget,
    QGroupBox,
    QCheckBox,
    QSpinBox,
    QPushButton,
    QFormLayout,
    QWidget,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QHeaderView,
    QTableWidgetItem,
    QFileDialog,
)
import pyqtgraph as pg
import qtawesome as qta

from ..widgets.settings import get_widget_value
from ..widgets.color_preview import ColorPreviewWidget
from ..widgets import ContainerListWidget, StyledListWidgetItem
from ..stylesheets import QPushButton_style, QScrollArea_style


def _populate_list(geometries):
    target_list = ContainerListWidget(border=False)
    target_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)

    for name, obj in geometries:
        item = StyledListWidgetItem(name, obj.visible, obj._meta.get("info"))
        item.setData(Qt.ItemDataRole.UserRole, obj)
        target_list.addItem(item)
    return target_list


class PropertyAnalysisDialog(QDialog):
    def __init__(self, cdata, legend=None, parent=None):
        super().__init__(parent)
        self.cdata = cdata
        self.properties = {}
        self.property_parameters = {}

        self.setWindowTitle("Property Analysis")
        self.resize(900, 600)

        self.legend = legend
        self.color_preview = ColorPreviewWidget()
        self.setWindowFlags(Qt.WindowType.Window)

        self._setup_ui()
        self._setup_styling()

    def _setup_ui(self):
        from ..icons import dialog_selectall_icon, dialog_selectnone_icon

        main_layout = QVBoxLayout(self)

        self.main_splitter = QSplitter(Qt.Horizontal)

        # Object selection
        self.objects_panel = QGroupBox("Objects")
        objects_layout = QVBoxLayout()
        quick_select_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.setIcon(dialog_selectall_icon)
        select_all_btn.clicked.connect(lambda: self.objects_list.selectAll())
        select_none_btn = QPushButton("Clear")
        select_none_btn.setIcon(dialog_selectnone_icon)
        select_none_btn.clicked.connect(lambda: self.objects_list.clearSelection())
        quick_select_layout.addWidget(select_all_btn)
        quick_select_layout.addWidget(select_none_btn)
        objects_layout.addLayout(quick_select_layout)

        self.objects_list = ContainerListWidget(border=False)
        self.objects_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.populate_lists()
        objects_layout.addWidget(self.objects_list)

        self.objects_panel.setLayout(objects_layout)
        self.main_splitter.addWidget(self.objects_panel)

        self.tabs_container = QWidget()
        tabs_layout = QVBoxLayout(self.tabs_container)
        tabs_layout.setContentsMargins(0, 0, 0, 0)

        self.tabs_widget = QTabWidget()
        self.visualization_tab = QWidget()
        self.analysis_tab = QWidget()
        self.statistics_tab = QWidget()

        self._setup_visualization_tab()
        self._setup_analysis_tab()
        self._setup_statistics_tab()

        # Add tabs with icons
        self.tabs_widget.addTab(
            self.visualization_tab, qta.icon("mdi.brush", color="#4f46e5"), "Visualize"
        )
        self.tabs_widget.addTab(
            self.analysis_tab,
            qta.icon("mdi.chart-bell-curve", color="#4f46e5"),
            "Distribution",
        )
        self.tabs_widget.addTab(
            self.statistics_tab,
            qta.icon("mdi.chart-bar", color="#4f46e5"),
            "Statistics",
        )
        self.tabs_widget.currentChanged.connect(self._update_tab)

        tabs_layout.addWidget(self.tabs_widget)
        self.main_splitter.addWidget(self.tabs_container)
        self.main_splitter.setSizes([300, 600])
        main_layout.addWidget(self.main_splitter)

    def populate_lists(self):
        self.objects_list.clear()

        clusters = self.cdata.format_datalist("data")
        models = self.cdata.format_datalist("models")
        for name, obj in clusters:
            item = StyledListWidgetItem(name, obj.visible, obj._meta.get("info"))

            item.setData(Qt.ItemDataRole.UserRole, obj)
            item.setData(Qt.ItemDataRole.UserRole + 1, "cluster")
            self.objects_list.addItem(item)

        for name, obj in models:
            item = StyledListWidgetItem(name, obj.visible, obj._meta.get("info"))

            item.setData(Qt.ItemDataRole.UserRole, obj)
            item.setData(Qt.ItemDataRole.UserRole + 1, "mesh")
            self.objects_list.addItem(item)

    def _setup_visualization_tab(self):
        from ..icons import dialog_accept_icon

        layout = QVBoxLayout(self.visualization_tab)

        property_group = QGroupBox("Property")
        property_layout = QVBoxLayout()

        category_layout = QHBoxLayout()
        category_layout.addWidget(QLabel("Category:"))
        self.category_combo = QComboBox()
        self.category_combo.addItems(
            ["Distance", "Surface", "Geometric", "Projection", "Custom"]
        )
        self.category_combo.currentTextChanged.connect(self._update_property_list)
        category_layout.addWidget(self.category_combo)

        category_layout.addSpacing(15)
        category_layout.addWidget(QLabel("Property:"))
        self.property_combo = QComboBox()
        self.property_combo.currentTextChanged.connect(self._update_options)
        category_layout.addWidget(self.property_combo, 1)
        property_layout.addLayout(category_layout)

        # Property-specific options container
        self.property_options_container = QWidget()
        self.property_options_layout = QFormLayout(self.property_options_container)
        self.property_options_layout.setContentsMargins(0, 10, 0, 0)
        property_layout.addWidget(self.property_options_container)

        property_group.setLayout(property_layout)
        layout.addWidget(property_group)

        options_group = QGroupBox("Visualization Options")
        options_layout = QVBoxLayout()

        colormap_layout = QHBoxLayout()
        colormap_layout.addWidget(QLabel("Color Map:"))

        self.colormap_combo = QComboBox()
        self.colormap_combo.addItems(self.color_preview.colormaps.copy())
        self.colormap_combo.currentTextChanged.connect(self._update_colormap_preview)
        colormap_layout.addWidget(self.colormap_combo)

        checkbox_layout = QHBoxLayout()
        self.normalize_checkbox = QCheckBox("Normalize per Object")
        checkbox_layout.addWidget(self.normalize_checkbox)
        self.quantile_checkbox = QCheckBox("Compute Quantiles")
        checkbox_layout.addWidget(self.quantile_checkbox)
        self.invert_checkbox = QCheckBox("Invert Colors")
        self.invert_checkbox.stateChanged.connect(self._update_colormap_preview)
        checkbox_layout.addWidget(self.invert_checkbox)

        options_layout.addLayout(colormap_layout)
        options_layout.addWidget(self.color_preview)
        options_layout.addLayout(checkbox_layout)
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # Dialog Control Buttons
        button_layout = QHBoxLayout()
        refresh_btn = QPushButton("Compute")
        refresh_btn.setIcon(qta.icon("mdi.monitor", color="#4f46e5"))
        refresh_btn.clicked.connect(self._preview)
        button_layout.addWidget(refresh_btn)
        button_layout.addStretch()

        show_dist_btn = QPushButton("Show Distribution")
        show_dist_btn.setIcon(qta.icon("mdi.chart-bell-curve", color="#4f46e5"))
        show_dist_btn.clicked.connect(lambda: self.tabs_widget.setCurrentIndex(1))
        button_layout.addWidget(show_dist_btn)

        export_btn = QPushButton("Export Data")
        export_btn.setIcon(qta.icon("mdi.download", color="#4f46e5"))
        export_btn.clicked.connect(self._export_data)
        button_layout.addWidget(export_btn)

        apply_btn = QPushButton("Done")
        apply_btn.setIcon(dialog_accept_icon)
        apply_btn.clicked.connect(self.accept)
        button_layout.addWidget(apply_btn)
        layout.addLayout(button_layout)

        self._update_property_list("Distance")
        self._update_colormap_preview()

    def _setup_analysis_tab(self):
        from ..icons import dialog_accept_icon

        layout = QVBoxLayout(self.analysis_tab)

        plot_group = QGroupBox("Distribution")
        plot_layout = QVBoxLayout(plot_group)

        header_layout = QHBoxLayout()
        header_layout.addStretch()

        plot_type_layout = QHBoxLayout()
        self.plot_types = ["Histogram", "Density", "Line"]
        self.current_plot_type = "Density"
        self.bar_btn = QPushButton()
        self.bar_btn.setIcon(qta.icon("mdi.chart-histogram", color="#4f46e5"))
        self.bar_btn.setToolTip("Histogram")
        self.bar_btn.setFixedSize(28, 28)
        self.bar_btn.clicked.connect(lambda: self._set_plot_type("Histogram"))

        self.density_btn = QPushButton()
        self.density_btn.setIcon(qta.icon("mdi.chart-bell-curve", color="#4f46e5"))
        self.density_btn.setFixedSize(28, 28)
        self.density_btn.clicked.connect(lambda: self._set_plot_type("Density"))

        self.line_btn = QPushButton()
        self.line_btn.setIcon(qta.icon("mdi.chart-line", color="#4f46e5"))
        self.line_btn.setToolTip("Line Chart")
        self.line_btn.setFixedSize(28, 28)
        self.line_btn.clicked.connect(lambda: self._set_plot_type("Line"))
        plot_type_layout.addWidget(self.bar_btn)
        plot_type_layout.addWidget(self.density_btn)
        plot_type_layout.addWidget(self.line_btn)
        header_layout.addLayout(plot_type_layout)
        plot_layout.addLayout(header_layout)

        self.plot_widget = pg.GraphicsLayoutWidget(self)
        self.plot_widget.setBackground(None)
        plot_layout.addWidget(self.plot_widget)

        strat_layout = QHBoxLayout()
        self.plot_title = QLabel("Stratification")
        self.plot_mode_combo = QComboBox()
        self.plot_mode_combo.addItems(["Combined", "Separate"])
        self.plot_mode_combo.currentTextChanged.connect(self._update_plot)
        strat_layout.addWidget(self.plot_title)
        strat_layout.addWidget(self.plot_mode_combo)
        plot_layout.addLayout(strat_layout)

        alpha_layout = QHBoxLayout()
        alpha_layout.addWidget(QLabel("Alpha:"))
        self.alpha_slider = QSpinBox()
        self.alpha_slider.setRange(0, 255)
        self.alpha_slider.setValue(128)
        self.alpha_slider.valueChanged.connect(self._update_plot)
        alpha_layout.addWidget(self.alpha_slider)
        plot_layout.addLayout(alpha_layout)

        colormap_layout = QHBoxLayout()
        colormap_layout.addWidget(QLabel("Color Palette:"))

        self.analysis_colormap_combo = QComboBox()
        self.analysis_colormap_combo.addItems(self.color_preview.colormaps)
        self.analysis_colormap_combo.currentTextChanged.connect(self._update_plot)
        colormap_layout.addWidget(self.analysis_colormap_combo)
        plot_layout.addLayout(colormap_layout)
        layout.addWidget(plot_group)

        # Dialog Control Buttons
        button_layout = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setIcon(qta.icon("mdi.refresh", color="#4f46e5"))
        refresh_btn.clicked.connect(self._update_plot)
        button_layout.addWidget(refresh_btn)
        button_layout.addStretch()

        save_plot_btn = QPushButton("Save Plot")
        save_plot_btn.setIcon(qta.icon("mdi.content-save", color="#4f46e5"))
        save_plot_btn.clicked.connect(self._export_plot)
        button_layout.addWidget(save_plot_btn)

        export_btn = QPushButton("Export Data")
        export_btn.setIcon(qta.icon("mdi.download", color="#4f46e5"))
        export_btn.clicked.connect(self._export_data)
        button_layout.addWidget(export_btn)

        apply_btn = QPushButton("Done")
        apply_btn.setIcon(dialog_accept_icon)
        apply_btn.clicked.connect(self.accept)
        button_layout.addWidget(apply_btn)
        layout.addLayout(button_layout)

    def _setup_statistics_tab(self):
        from ..icons import dialog_accept_icon

        layout = QVBoxLayout(self.statistics_tab)

        stats_group = QGroupBox("Statistics")
        stats_layout = QVBoxLayout(stats_group)
        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(5)
        self.stats_table.setHorizontalHeaderLabels(
            ["Object", "Min", "Max", "Mean", "Std Dev"]
        )
        self.stats_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        stats_layout.addWidget(self.stats_table)

        layout.addWidget(stats_group)

        button_layout = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setIcon(qta.icon("mdi.refresh", color="#4f46e5"))
        refresh_btn.clicked.connect(self._update_statistics)
        button_layout.addWidget(refresh_btn)
        button_layout.addStretch()

        save_plot_btn = QPushButton("Save Plot")
        save_plot_btn.setIcon(qta.icon("mdi.content-save", color="#4f46e5"))
        save_plot_btn.clicked.connect(self._export_plot)
        button_layout.addWidget(save_plot_btn)

        export_btn = QPushButton("Export Data")
        export_btn.setIcon(qta.icon("mdi.download", color="#4f46e5"))
        export_btn.clicked.connect(self._export_data)
        button_layout.addWidget(export_btn)

        apply_btn = QPushButton("Done")
        apply_btn.setIcon(dialog_accept_icon)
        apply_btn.clicked.connect(self.accept)
        button_layout.addWidget(apply_btn)
        layout.addLayout(button_layout)

    def _update_property_list(self, category):
        self.property_combo.clear()

        properties = {
            "Distance": [
                "To Camera",
                "To Cluster",
                "To Model",
            ],
            "Surface": [
                "Curvature",
                "Edge Length",
                "Surface Area",
                "Triangle Area",
                "Volume",
                "Triangle Volume",
                "Number of Vertices",
                "Number of Triangles",
            ],
            "Projection": [
                "Projected Curvature",
                "Geodesic Distance",
            ],
            "Geometric": [
                "Identity",
                "Width (X-axis)",
                "Depth (Y-axis)",
                "Height (Z-axis)",
                "Number of Points",
            ],
        }
        self.property_map = {
            # Distance
            "To Camera": "distance",
            "To Cluster": "distance",
            "To Model": "distance",
            # Surface
            "Curvature": "mesh_curvature",
            "Edge Length": "mesh_edge_length",
            "Surface Area": "mesh_surface_area",
            "Triangle Area": "mesh_triangle_area",
            "Volume": "mesh_volume",
            "Triangle Volume": "mesh_triangle_volume",
            "Number of Vertices": "mesh_vertices",
            "Number of Triangles": "mesh_triangles",
            # Geometric
            "Identity": "identity",
            "Width (X-axis)": "width",
            "Depth (Y-axis)": "depth",
            "Height (Z-axis)": "height",
            "Number of Points": "n_points",
            # Projection
            "Projected Curvature": "projected_curvature",
            "Geodesic Distance": "geodesic_distance",
        }

        self.property_combo.addItems(properties.get(category, []))
        if self.property_combo.count() > 0:
            self._update_options(self.property_combo.currentText())

    def _update_options(self, property_name):
        while self.property_options_layout.rowCount() > 0:
            self.property_options_layout.removeRow(0)

        self.option_widgets = {}

        if property_name == "Custom Attribute":
            return

        elif property_name == "Curvature":
            curvature_combobox = QComboBox()
            curvature_combobox.addItems(["Gaussian", "Mean"])

            radius_spinbox = QSpinBox()
            radius_spinbox.setRange(1, 20)
            radius_spinbox.setValue(5)
            self.property_options_layout.addRow("Method:", curvature_combobox)
            self.property_options_layout.addRow("Radius:", radius_spinbox)

            self.option_widgets["curvature"] = curvature_combobox
            self.option_widgets["radius"] = radius_spinbox

        elif property_name == "Projected Curvature":
            # Target mesh selection
            target_group = QGroupBox("Target Mesh")
            target_layout = QVBoxLayout(target_group)

            target_list = _populate_list(
                self.cdata.format_datalist("models", mesh_only=True)
            )
            target_layout.addWidget(target_list)

            options_layout = QFormLayout()

            curvature_combobox = QComboBox()
            curvature_combobox.addItems(["Gaussian", "Mean"])
            options_layout.addRow("Method:", curvature_combobox)

            radius_spinbox = QSpinBox()
            radius_spinbox.setRange(1, 20)
            radius_spinbox.setValue(5)
            options_layout.addRow("Radius:", radius_spinbox)

            target_layout.addLayout(options_layout)

            self.property_options_layout.addRow(target_group)
            self.option_widgets["queries"] = target_list
            self.option_widgets["curvature"] = curvature_combobox
            self.option_widgets["radius"] = radius_spinbox

        elif property_name == "Geodesic Distance":
            target_group = QGroupBox("Target Mesh")
            target_layout = QVBoxLayout(target_group)

            target_list = _populate_list(
                self.cdata.format_datalist("models", mesh_only=True)
            )
            target_layout.addWidget(target_list)

            neighbor_layout = QHBoxLayout()
            neighbor_label = QLabel("k-Nearest Neighbors:")
            knn_layout = QHBoxLayout()

            neighbor_start = QSpinBox()
            neighbor_start.setRange(1, 255)
            neighbor_start.setValue(1)

            neighbor_to_label = QLabel("to")
            neighbor_to_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            neighbor_end = QSpinBox()
            neighbor_end.setRange(1, 255)
            neighbor_end.setValue(1)

            knn_layout.addWidget(neighbor_start)
            knn_layout.addWidget(neighbor_to_label)
            knn_layout.addWidget(neighbor_end)
            neighbor_layout.addWidget(neighbor_label)
            neighbor_layout.addLayout(knn_layout)
            target_layout.addLayout(neighbor_layout)

            self.property_options_layout.addRow(target_group)
            self.option_widgets["queries"] = target_list
            self.option_widgets["k_start"] = neighbor_start
            self.option_widgets["k"] = neighbor_end

        elif property_name == "To Cluster":
            target_group = QGroupBox("Target Clusters")
            target_layout = QVBoxLayout(target_group)

            target_list = _populate_list(self.cdata.format_datalist("data"))
            target_layout.addWidget(target_list)

            # Checkboxes
            all_targets_checkbox = QCheckBox("Compare to All")
            include_self_checkbox = QCheckBox("Include Within-Cluster Distance")

            checkbox_layout = QHBoxLayout()
            checkbox_layout.addWidget(all_targets_checkbox)
            checkbox_layout.addWidget(include_self_checkbox)
            target_layout.addLayout(checkbox_layout)

            # KNN range
            neighbor_layout = QHBoxLayout()
            neighbor_label = QLabel("k-Nearest Neighbors:")
            knn_layout = QHBoxLayout()

            neighbor_start = QSpinBox()
            neighbor_start.setRange(1, 255)
            neighbor_start.setValue(1)

            neighbor_to_label = QLabel("to")
            neighbor_to_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            neighbor_end = QSpinBox()
            neighbor_end.setRange(1, 255)
            neighbor_end.setValue(1)

            knn_layout.addWidget(neighbor_start)
            knn_layout.addWidget(neighbor_to_label)
            knn_layout.addWidget(neighbor_end)
            neighbor_layout.addWidget(neighbor_label)
            neighbor_layout.addLayout(knn_layout)
            target_layout.addLayout(neighbor_layout)

            all_targets_checkbox.stateChanged.connect(
                lambda state: self.toggle_all_targets(state, target_list)
            )

            self.property_options_layout.addRow(target_group)

            self.option_widgets["queries"] = target_list
            self.option_widgets["include_self"] = include_self_checkbox
            self.option_widgets["k_start"] = neighbor_start
            self.option_widgets["k"] = neighbor_end

        elif property_name == "To Model":
            target_group = QGroupBox("Target Models")
            target_layout = QVBoxLayout(target_group)

            target_list = _populate_list(self.cdata.format_datalist("models"))
            target_layout.addWidget(target_list)

            all_targets_checkbox = QCheckBox("Compare to All")
            checkbox_layout = QHBoxLayout()
            checkbox_layout.addWidget(all_targets_checkbox)
            target_layout.addLayout(checkbox_layout)

            all_targets_checkbox.stateChanged.connect(
                lambda state: self.toggle_all_targets(state, target_list)
            )

            self.property_options_layout.addRow(target_group)
            self.option_widgets["queries"] = target_list

    def toggle_all_targets(self, state, target_list):
        target_list.setEnabled(not bool(state))

        if bool(state):
            for i in range(target_list.count()):
                item = target_list.item(i)
                item.setSelected(True)
        else:
            target_list.clearSelection()

    def _update_colormap_preview(self):
        cmap = self.colormap_combo.currentText()
        reverse = self.invert_checkbox.isChecked()
        self.color_preview.set_colormap(cmap, reverse)

    def _get_selected_objects(self):
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.objects_list.selectedItems()
        ]

    def _compute_properties(self):
        from ..properties import GeometryProperties

        options = {}
        for k, widget in self.option_widgets.items():
            if isinstance(widget, (QListWidget, ContainerListWidget)):
                value = [
                    item.data(Qt.ItemDataRole.UserRole)
                    for item in widget.selectedItems()
                ]
            else:
                value = get_widget_value(widget)
            options[k] = value

        # Assuming identical parameters, which geometric properties need computation
        missing_geometries = []
        geometries = self._get_selected_objects()
        for geometry in geometries:
            geometry_id = id(geometry)
            if geometry_id in self.properties:
                continue
            missing_geometries.append(geometry)

        property_name = self.property_map.get(self.property_combo.currentText())
        if property_name is None:
            print(f"{property_name} is missing from property_map.")
            return None

        options["property_name"] = property_name
        if self.property_combo.currentText() == "To Camera":
            vtk_widget = self.cdata.data.vtk_widget
            renderer = vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer()
            options["queries"] = np.array(
                renderer.GetActiveCamera().GetPosition()
            ).reshape(1, -1)

        # Recompute all properties if parameters changed
        cache_miss = len(options) != len(self.property_parameters)
        for key, value in options.items():
            if key not in self.property_parameters:
                cache_miss = True
            other_value = self.property_parameters.get(key)

            try:
                if isinstance(value, np.ndarray) or isinstance(other_value, np.ndarray):
                    cache_miss = not np.allclose(value, other_value)

                cache_miss = value != other_value
                if not isinstance(cache_miss, bool):
                    cache_miss = all(cache_miss)
            except Exception:
                cache_miss = True

            if cache_miss:
                missing_geometries = geometries
                self.properties.clear()
                break

        self.property_parameters = options
        if options["property_name"] == "identity":
            self.properties = {id(x): i for i, x in enumerate(geometries)}
            return None

        try:
            self.properties.update(
                {
                    id(x): GeometryProperties.compute(geometry=x, **options)
                    for i, x in enumerate(missing_geometries)
                }
            )
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
            self.properties.clear()

    def _preview(self):
        from ..utils import cmap_to_vtkctf

        geometries = self._get_selected_objects()
        if not geometries:
            QMessageBox.warning(
                self, "No Selection", "Please select at least one object."
            )
            return None

        self._compute_properties()
        colormap = self.colormap_combo.currentText()
        if self.invert_checkbox.isChecked():
            colormap += "_r"

        properties = self.properties
        if self.normalize_checkbox.isChecked():
            properties = {
                k: (v - v.min()) / (v.max() - v.min()) for k, v in properties.items()
            }

        if self.quantile_checkbox.isChecked():
            all_curvatures = np.concatenate([v.flatten() for v in properties.values()])
            valid_curvatures = all_curvatures[~np.isnan(all_curvatures)]
            n_bins = min(valid_curvatures.size // 10, 100)
            bins = np.percentile(valid_curvatures, np.linspace(0, 100, n_bins + 1))
            properties = {k: np.digitize(v, bins) - 1 for k, v in properties.items()}

        values = [x for x in properties.values() if x is not None]
        if len(values) == 0:
            return None

        max_value = np.max([np.max(x) for x in values])
        min_value = np.min([np.min(x) for x in values])
        lut, lut_range = cmap_to_vtkctf(colormap, max_value, min_value=min_value)
        for geometry in geometries:
            metric = properties.get(id(geometry))
            if metric is None:
                continue
            geometry.set_scalars(metric, lut, lut_range)

        self.legend.set_lookup_table(lut, self.property_combo.currentText())
        self.cdata.data.render_vtk()
        self.cdata.models.render_vtk()

    def _update_tab(self):
        current_tab_index = self.tabs_widget.currentIndex()

        self.plot_widget.clear()
        QTimer.singleShot(
            100,
            lambda: (
                self._update_plot()
                if current_tab_index == 1
                else self._update_statistics()
                if current_tab_index == 2
                else None
            ),
        )

    def _update_statistics(self):
        selected_items = self.objects_list.selectedItems()
        self.stats_table.setRowCount(len(selected_items))

        row_count, n_decimals = 0, 6
        for index, item in enumerate(selected_items):
            obj = item.data(Qt.ItemDataRole.UserRole)

            value = self.properties.get(id(obj))
            if value is None:
                continue

            row_count += 1
            item = QTableWidgetItem(item.text())
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.stats_table.setItem(index, 0, item)

            item = QTableWidgetItem(str(np.round(np.min(value), n_decimals)))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.stats_table.setItem(index, 1, item)

            item = QTableWidgetItem(str(np.round(np.max(value), n_decimals)))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.stats_table.setItem(index, 2, item)

            item = QTableWidgetItem(str(np.round(np.mean(value), n_decimals)))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.stats_table.setItem(index, 3, item)

            item = QTableWidgetItem(str(np.round(np.std(value), n_decimals)))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.stats_table.setItem(index, 4, item)
        self.stats_table.setRowCount(row_count)

    def _set_plot_type(self, plot_type):
        self.current_plot_type = plot_type
        self._update_plot()

    def _update_plot(self):
        """Update the plot based on the current property and selected objects"""
        if self.tabs_widget.currentIndex() != 1:
            return None

        selected_items = self.objects_list.selectedItems()
        if not selected_items or not hasattr(self, "properties"):
            return None

        plot_type = getattr(self, "current_plot_type", "Density")
        plot_mode = getattr(self, "plot_mode_combo", lambda: "Combined").currentText()
        alpha = getattr(self, "alpha_slider", lambda: 150).value()
        colormap = getattr(
            self, "analysis_colormap_combo", lambda: "viridis"
        ).currentText()
        colors = self.color_preview.generate_gradient(colormap, len(selected_items))
        colors = [pg.mkColor(c.red(), c.green(), c.blue(), alpha) for c in colors]

        data_series = []
        all_values = []
        for i, item in enumerate(selected_items):
            obj = item.data(Qt.ItemDataRole.UserRole)
            obj_id = id(obj)
            values = self.properties.get(obj_id)
            if values is not None:
                all_values.append(values)
                data_series.append((item.text(), obj, values, colors[i % len(colors)]))

        if not data_series:
            return None

        self.plot_widget.clear()
        all_scalar = not isinstance(all_values[0], np.ndarray)
        if all_scalar:
            all_values = np.asarray(all_values)
            return self._create_categorical_plot(data_series, all_values, plot_type)
        return self._create_plot(data_series, all_values, plot_mode, plot_type)

    def _create_categorical_plot(self, data_series, values, plot_type):
        """Create a categorical plot with names on x-axis for single values"""
        property_name = self.property_combo.currentText()

        plot = self.plot_widget.addPlot()
        plot.setLabel("left", property_name)

        ax = plot.getAxis("bottom")
        names = [name for name, _, _, _ in data_series]
        colors = [color for _, _, _, color in data_series]
        ax.setTicks([[(i, name) for i, name in enumerate(names)]])

        if plot_type == "Histogram":
            for i in range(len(data_series)):
                bar = pg.BarGraphItem(
                    x=[i],
                    height=[values[i]],
                    width=0.7,
                    brush=colors[i],
                    pen=pg.mkPen("k", width=1),
                )
                plot.addItem(bar)
        else:
            scatter = pg.ScatterPlotItem()
            min_val, max_val = min(values), max(values)
            range_val = max_val - min_val if max_val > min_val else 1

            for i, (name, _, value, color) in enumerate(data_series):
                size = 10 + 40 * (values[i] - min_val) / range_val
                scatter.addPoints(
                    x=[i],
                    y=[values[i]],
                    size=size,
                    brush=color,
                    pen=pg.mkPen("k", width=1),
                    name=name,
                )
            plot.addItem(scatter)

        legend = plot.addLegend(offset=(-10, 10))
        legend.setPos(plot.getViewBox().screenGeometry().width() - 20, 0)

    def _create_plot(self, data_series, all_values, plot_mode, plot_type):
        """Create either histogram, density or line plot based on plot_type"""
        property_name = self.property_combo.currentText()

        if plot_type == "Histogram":
            all_data = np.concatenate(all_values)
            bins = np.histogram_bin_edges(all_data, bins="auto")
            y_label = "Frequency"
            x_label = property_name
        elif plot_type == "Density":
            from scipy.stats import gaussian_kde

            all_data = np.concatenate(all_values)
            x_min, x_max = np.min(all_data), np.max(all_data)
            x_range = np.linspace(x_min, x_max, 500)
            y_label = "Density"
            x_label = property_name
        elif plot_type == "Line":
            y_label = "Value"
            x_label = "Index"
        else:
            print("Supported plot types are Histogram, Density and Line.")
            return None

        is_combined = plot_mode == "Combined" or len(data_series) == 1
        cols = 1 if is_combined else min(2, len(data_series))
        if is_combined:
            plot = self.plot_widget.addPlot(row=0, col=0)
            plot.setLabel("left", y_label)
            plot.setLabel("bottom", x_label)

            legend = plot.addLegend(offset=(-10, 10))
            legend.setPos(plot.getViewBox().screenGeometry().width() - 20, 0)

            for i, (name, obj, values, color) in enumerate(data_series):
                if plot_type == "Histogram":
                    hist, edges = np.histogram(values, bins=bins)
                    x = (edges[:-1] + edges[1:]) / 2
                    width = (edges[1] - edges[0]) * 0.8

                    if len(data_series) > 1:
                        width = width / len(data_series)
                        offset = (i - (len(data_series) - 1) / 2) * width
                    else:
                        offset = 0

                    item = pg.BarGraphItem(
                        x=x + offset,
                        height=hist,
                        width=width,
                        brush=color,
                        pen=pg.mkPen("k", width=1),
                        name=name,
                    )
                elif plot_type == "Density":
                    try:
                        kde = gaussian_kde(values)
                        density = kde(x_range)
                        item = pg.PlotDataItem(
                            x_range,
                            density,
                            pen=pg.mkPen(color, width=2),
                            fillLevel=0,
                            fillBrush=color,
                            name=name,
                        )
                    except Exception as e:
                        print(f"Error computing KDE for {name}: {e}")
                        continue
                else:
                    x = np.arange(len(values))
                    item = pg.PlotDataItem(
                        x,
                        values,
                        pen=pg.mkPen(color, width=2),
                        name=name,
                        symbol="o",
                        symbolSize=5,
                        symbolBrush=color,
                    )

                plot.addItem(item)
            return None

        # For separate plots mode
        for i, (name, obj, values, color) in enumerate(data_series):
            plot = self.plot_widget.addPlot(row=i // cols, col=i % cols)
            plot.setTitle(name)
            plot.setLabel("left", y_label)
            plot.setLabel("bottom", x_label)

            if plot_type == "Histogram":
                hist, edges = np.histogram(values, bins=bins)
                x = (edges[:-1] + edges[1:]) / 2
                width = (edges[1] - edges[0]) * 0.8

                item = pg.BarGraphItem(
                    x=x,
                    height=hist,
                    width=width,
                    brush=color,
                    pen=pg.mkPen("k", width=1),
                )
            elif plot_type == "Density":
                try:
                    kde = gaussian_kde(values)
                    density = kde(x_range)
                    item = pg.PlotDataItem(
                        x_range,
                        density,
                        pen=pg.mkPen(color, width=2),
                        fillLevel=0,
                        fillBrush=color,
                    )
                except Exception as e:
                    print(f"Error computing KDE for {name}: {e}")
                    continue
            else:  # Line plot
                x = np.arange(len(values))
                item = pg.PlotDataItem(
                    x,
                    values,
                    pen=pg.mkPen(color, width=2),
                    symbol="o",
                    symbolSize=5,
                    symbolBrush=color,
                )

            plot.addItem(item)

    def _export_data(self):
        """Export analysis data to a CSV file"""
        property_name = self.property_combo.currentText()
        selected_items = self.objects_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(
                self, "No Selection", "Please select at least one object."
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Data", "", "CSV Files (*.csv);;All Files (*.*)"
        )

        if not file_path:
            return

        try:
            with open(file_path, mode="w", encoding="utf-8") as ofile:
                ofile.write(f"source,{property_name}\n")

                for item in selected_items:
                    obj = item.data(Qt.ItemDataRole.UserRole)
                    values = self.properties.get(id(obj))
                    if values is None:
                        return None

                    values = np.asarray(values).reshape(-1)
                    lines = "\n".join([f"{item.text()},{v}" for v in values])
                    ofile.write(lines + "\n")

            QMessageBox.information(self, "Success", "Data exported successfully")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export data: {str(e)}")

    def _export_plot(self):
        """Save the current plot as an image"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Plot", "", "PNG Files (*.png);;All Files (*.*)"
        )

        if not file_path:
            return None

        try:
            exporter = pg.exporters.ImageExporter(self.plot_widget.scene())
            exporter.parameters()["width"] = 1920
            exporter.parameters()["height"] = 1080
            exporter.parameters()["antialias"] = True
            exporter.export(file_path)
            QMessageBox.information(self, "Success", "Plot saved successfully")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save plot: {str(e)}")

    def _setup_styling(self):
        base_style = """
            QTabWidget::pane {
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                top: -1px;
            }
            QTabBar::tab {
                background: transparent;
                border: 1px solid #cbd5e1;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 6px 12px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                color: rgba(99, 102, 241, 1.0);
                border-color: rgba(99, 102, 241, 1.0);

            }
            QTabBar::tab:hover:!selected {
                color: #696c6f;
            }
            QTableWidget {
                border: 1px solid #cbd5e1;
                background-color: transparent;
                border-radius: 4px;
                outline: none;
            }
            QTableWidget QHeaderView::section {
                background-color: transparent;
                border: 1px solid #cbd5e1;
                padding: 4px;
            }
        """
        return self.setStyleSheet(base_style + QPushButton_style + QScrollArea_style)
