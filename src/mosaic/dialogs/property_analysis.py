"""
Dialog to analyze and interactively visualize properties of Geometry objects.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np
from qtpy.QtCore import Qt, QTimer, QSize
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
    QTabWidget,
    QTableWidget,
    QHeaderView,
    QTableWidgetItem,
    QFileDialog,
    QDoubleSpinBox,
)
import pyqtgraph as pg
import qtawesome as qta

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..widgets import (
    ContainerTreeWidget,
    StyledListWidgetItem,
    ColorMapSelector,
    HistogramRangeSlider,
    generate_gradient_colors,
)
from ..utils import Throttle
from ..widgets.settings import get_widget_value, set_widget_value
from ..stylesheets import (
    QPushButton_style,
    QScrollArea_style,
    QTabBar_style,
    QTable_style,
    Colors,
)


@dataclass
class CacheEntry:
    """Single cache entry storing a computed value with its context."""

    value: Any
    parameters: Dict[str, Any]
    geometry_uuid: str
    model_id: Optional[int]
    point_count: int


class PropertyCache:
    """Cache for computed geometry properties."""

    def __init__(self):
        self._entries: Dict[str, CacheEntry] = {}

    def get(self, geometry, parameters: Dict[str, Any]) -> Optional[Any]:
        """Get cached value if still valid, None otherwise."""
        entry = self._entries.get(geometry.uuid)
        if entry is None:
            return None

        model_id = id(geometry.model) if geometry.model is not None else None
        if entry.model_id != model_id:
            return None

        if entry.point_count != geometry.points.shape[0]:
            return None

        if not self._parameters_equal(entry.parameters, parameters):
            return None

        return entry.value

    def set(self, geometry, parameters: Dict[str, Any], value: Any):
        """Store a computed value with its computation context."""
        model_id = id(geometry.model) if geometry.model is not None else None
        self._entries[geometry.uuid] = CacheEntry(
            value=value,
            parameters=parameters.copy(),
            geometry_uuid=geometry.uuid,
            model_id=model_id,
            point_count=geometry.points.shape[0],
        )

    def get_value(self, geometry_uuid: str) -> Optional[Any]:
        """Get cached value by UUID without validation (for display)."""
        entry = self._entries.get(geometry_uuid)
        if entry is None:
            return None
        if hasattr(entry.value, "copy"):
            return entry.value.copy()
        return entry.value

    def clear(self):
        """Clear all cached entries."""
        self._entries.clear()

    def _parameters_equal(self, cached: Dict, current: Dict) -> bool:
        """Check if two parameter dicts are equivalent."""
        if set(cached.keys()) != set(current.keys()):
            return False

        for key in cached:
            if not self._values_equal(cached[key], current[key]):
                return False
        return True

    def _values_equal(self, a: Any, b: Any) -> bool:
        """Compare two values for equality, handling numpy arrays and lists."""
        if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
            try:
                return np.allclose(a, b)
            except (TypeError, ValueError):
                return False

        if isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                return False
            return all(self._values_equal(x, y) for x, y in zip(a, b))

        try:
            result = a == b
            if hasattr(result, "__iter__") and not isinstance(result, str):
                return all(result)
            return bool(result)
        except Exception:
            return False


def _populate_list(geometries):
    target_list = ContainerTreeWidget(border=False)
    target_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)

    for name, obj in geometries:
        item = StyledListWidgetItem(name, obj.visible, obj._meta.get("info"))
        item.setData(Qt.ItemDataRole.UserRole, obj)
        target_list.addItem(item)
    return target_list


class ColorScaleSettingsDialog(QDialog):
    """Dialog for configuring color scale thresholds"""

    def __init__(self, parent=None):
        from ..icons import (
            dialog_accept_icon,
            dialog_reject_icon,
            dialog_margin,
            footer_margin,
        )

        super().__init__(parent)
        self.setWindowTitle("Color Scale Settings")
        self.setModal(True)

        self._dialog_accept_icon = dialog_accept_icon
        self._dialog_reject_icon = dialog_reject_icon
        self._dialog_margin = dialog_margin
        self._footer_margin = footer_margin

        # Default threshold values
        self.lower_enabled = False
        self.upper_enabled = False
        self.lower_value = 0.0
        self.upper_value = 1.0

        self._setup_ui()
        self.setStyleSheet(QPushButton_style)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*self._dialog_margin)

        # Threshold settings group
        threshold_group = QGroupBox("Threshold Settings")
        threshold_layout = QVBoxLayout(threshold_group)

        # Lower threshold
        self.lower_checkbox = QCheckBox("Enable Lower Threshold")
        self.lower_checkbox.stateChanged.connect(self._update_spinbox_states)
        threshold_layout.addWidget(self.lower_checkbox)

        lower_value_layout = QFormLayout()
        lower_value_layout.setContentsMargins(20, 5, 0, 10)
        self.lower_spinbox = QDoubleSpinBox()
        self.lower_spinbox.setRange(-1e10, 1e10)
        self.lower_spinbox.setDecimals(6)
        self.lower_spinbox.setValue(0.0)
        self.lower_spinbox.setEnabled(False)
        lower_value_layout.addRow("Minimum Value:", self.lower_spinbox)
        threshold_layout.addLayout(lower_value_layout)

        # Upper threshold
        self.upper_checkbox = QCheckBox("Enable Upper Threshold")
        self.upper_checkbox.stateChanged.connect(self._update_spinbox_states)
        threshold_layout.addWidget(self.upper_checkbox)

        upper_value_layout = QFormLayout()
        upper_value_layout.setContentsMargins(20, 5, 0, 0)
        self.upper_spinbox = QDoubleSpinBox()
        self.upper_spinbox.setRange(-1e10, 1e10)
        self.upper_spinbox.setDecimals(6)
        self.upper_spinbox.setValue(1.0)
        self.upper_spinbox.setEnabled(False)
        upper_value_layout.addRow("Maximum Value:", self.upper_spinbox)
        threshold_layout.addLayout(upper_value_layout)

        layout.addWidget(threshold_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(*self._footer_margin)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setIcon(self._dialog_reject_icon)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        apply_btn = QPushButton("Apply")
        apply_btn.setIcon(self._dialog_accept_icon)
        apply_btn.clicked.connect(self.accept)
        button_layout.addWidget(apply_btn)

        layout.addLayout(button_layout)

    def _update_spinbox_states(self):
        """Enable/disable spinboxes based on checkbox states"""
        self.lower_spinbox.setEnabled(self.lower_checkbox.isChecked())
        self.upper_spinbox.setEnabled(self.upper_checkbox.isChecked())

    def get_settings(self):
        """Return the current threshold settings"""
        return {
            "lower_enabled": self.lower_checkbox.isChecked(),
            "upper_enabled": self.upper_checkbox.isChecked(),
            "lower_value": self.lower_spinbox.value(),
            "upper_value": self.upper_spinbox.value(),
        }

    def set_settings(self, settings):
        """Apply threshold settings"""
        self.lower_checkbox.setChecked(settings.get("lower_enabled", False))
        self.upper_checkbox.setChecked(settings.get("upper_enabled", False))
        self.lower_spinbox.setValue(settings.get("lower_value", 0.0))
        self.upper_spinbox.setValue(settings.get("upper_value", 1.0))


class PropertyAnalysisDialog(QDialog):
    """Dialog for analyzing and visualizing geometry properties."""

    PROPERTY_CATEGORIES = {
        "Distance": ["To Camera", "To Cluster", "To Model", "To Self"],
        "Mesh": [
            "Curvature",
            "Area",
            "Volume",
            "Mesh Statistics",
            "Thickness",
        ],
        "Projection": ["Projected Curvature", "Geodesic Distance"],
        "Geometric": [
            "Identity",
            "Width (X-axis)",
            "Depth (Y-axis)",
            "Height (Z-axis)",
            "Number of Points",
        ],
        "Custom": ["Vertex Properties"],
    }

    PROPERTY_MAP = {
        "To Camera": "distance",
        "To Cluster": "distance",
        "To Model": "distance",
        "To Self": "distance",
        "Curvature": "mesh_curvature",
        "Area": "mesh_area",
        "Volume": "mesh_volume",
        "Mesh Statistics": "mesh_statistics",
        "Identity": "identity",
        "Width (X-axis)": "width",
        "Depth (Y-axis)": "depth",
        "Height (Z-axis)": "height",
        "Number of Points": "n_points",
        "Projected Curvature": "projected_curvature",
        "Geodesic Distance": "geodesic_distance",
        "Thickness": "thickness",
        "Vertex Properties": "vertex_property",
    }

    def __init__(self, cdata, legend=None, parent=None):
        super().__init__(parent)
        self.cdata = cdata
        self._cache = PropertyCache()

        # Threshold settings
        self.threshold_settings = {
            "lower_enabled": False,
            "upper_enabled": False,
            "lower_value": 0.0,
            "upper_value": 1.0,
        }

        self.setWindowTitle("Property Analysis")

        self.legend = legend
        self.setWindowFlags(Qt.WindowType.Window)

        self._setup_ui()
        self.setStyleSheet(
            QTabBar_style + QTable_style + QPushButton_style + QScrollArea_style
        )

        self.cdata.data.vtk_pre_render.connect(self._on_render_update)
        self.cdata.models.vtk_pre_render.connect(self._on_render_update)

    def sizeHint(self):
        return QSize(400, 350)

    def _on_render_update(self):
        """Re-apply properties when models are re-rendered."""
        if not self.live_update_checkbox.isChecked():
            return

        self.cdata.data.blockSignals(True)
        self.cdata.models.blockSignals(True)
        try:
            self._update_property_list()
            self._preview(render=False)
            self._update_plot()
            self._update_statistics()
        except Exception:
            pass
        finally:
            self.cdata.data.blockSignals(False)
            self.cdata.models.blockSignals(False)

    def closeEvent(self, event):
        """Disconnect when dialog closes"""
        try:
            self.cdata.data.vtk_pre_render.disconnect(self._on_render_update)
            self.cdata.models.vtk_pre_render.disconnect(self._on_render_update)
        except Exception:
            pass
        super().closeEvent(event)

    def _create_knn_range_widget(self, layout: QVBoxLayout) -> tuple:
        """Create k-nearest neighbor range spinboxes and aggregation combo.

        Returns
        -------
        tuple
            (k_start_spinbox, k_end_spinbox, aggregation_combobox)
        """
        neighbor_layout = QHBoxLayout()
        neighbor_layout.addWidget(QLabel("Neighbors:"))

        knn_layout = QHBoxLayout()
        k_start = QSpinBox()
        k_start.setRange(1, 255)
        k_start.setValue(1)

        k_end = QSpinBox()
        k_end.setRange(1, 255)
        k_end.setValue(1)

        k_start.valueChanged.connect(lambda x: k_end.setRange(x, 255))

        knn_layout.addWidget(k_start)
        knn_layout.addWidget(QLabel("to"))
        knn_layout.addWidget(k_end)
        neighbor_layout.addLayout(knn_layout)
        layout.addLayout(neighbor_layout)

        aggregation_layout = QHBoxLayout()
        aggregation_layout.addWidget(QLabel("Aggregation:"))
        aggregation_combo = QComboBox()
        aggregation_combo.addItems(["Mean", "Min", "Max", "Median"])
        aggregation_layout.addWidget(aggregation_combo)
        layout.addLayout(aggregation_layout)

        return k_start, k_end, aggregation_combo

    def _create_curvature_options(self, layout: QFormLayout) -> tuple:
        """Create curvature method and radius options.

        Returns
        -------
        tuple
            (curvature_combobox, radius_spinbox)
        """
        curvature_combo = QComboBox()
        curvature_combo.addItems(["Mean", "Gaussian"])
        layout.addRow("Method:", curvature_combo)

        radius_spin = QSpinBox()
        radius_spin.setRange(1, 20)
        radius_spin.setValue(5)
        layout.addRow("Radius:", radius_spin)

        return curvature_combo, radius_spin

    def _create_target_list_group(
        self, title: str, data_source: str, with_compare_all: bool = False, **kwargs
    ) -> tuple:
        """Create a target selection group with optional 'Compare to All' checkbox.

        Returns
        -------
        tuple
            (group_box, target_list, compare_all_checkbox or None)
        """
        group = QGroupBox(title)
        layout = QVBoxLayout(group)

        target_list = _populate_list(self.cdata.format_datalist(data_source, **kwargs))
        layout.addWidget(target_list)

        compare_all = None
        if with_compare_all:
            compare_all = QCheckBox("Compare to All")
            compare_all.stateChanged.connect(
                lambda state: self.toggle_all_targets(state, target_list)
            )
            checkbox_layout = QHBoxLayout()
            checkbox_layout.addWidget(compare_all)
            layout.addLayout(checkbox_layout)

        return group, layout, target_list, compare_all

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

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

        self.tabs_widget.addTab(
            self.visualization_tab,
            qta.icon("ph.paint-brush", color=Colors.ICON),
            "Visualize",
        )
        self.tabs_widget.addTab(
            self.analysis_tab,
            qta.icon("ph.chart-line", color=Colors.ICON),
            "Distribution",
        )
        self.tabs_widget.addTab(
            self.statistics_tab,
            qta.icon("ph.chart-bar", color=Colors.ICON),
            "Statistics",
        )
        self.tabs_widget.currentChanged.connect(self._update_tab)
        main_layout.addWidget(self.tabs_widget)

    def _create_colormap_combo(self, with_settings_button=False):
        """Create a colormap combo widget with optional settings button"""
        colormap = ColorMapSelector()

        def _open_colormap_settings():
            """Open dialog to configure color scale thresholds"""
            dialog = ColorScaleSettingsDialog(self)
            dialog.set_settings(self.threshold_settings)

            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.threshold_settings = dialog.get_settings()
                self._preview()

        if with_settings_button:
            settings_btn = QPushButton()
            settings_btn.setIcon(qta.icon("ph.gear", color=Colors.ICON))
            settings_btn.setToolTip("Color Scale Settings")
            settings_btn.setFixedSize(28, 28)
            settings_btn.clicked.connect(_open_colormap_settings)
            return colormap, settings_btn
        return colormap

    def _setup_visualization_tab(self):
        from ..icons import dialog_accept_icon
        from ..widgets.settings import format_tooltip

        layout = QVBoxLayout(self.visualization_tab)
        layout.setSpacing(6)

        # Property group
        property_group = QGroupBox("Property")
        property_layout = QVBoxLayout()
        property_layout.setSpacing(4)

        category_layout = QHBoxLayout()
        category_layout.addWidget(QLabel("Category:"))
        self.category_combo = QComboBox()
        self.category_combo.addItems(
            ["Distance", "Mesh", "Geometric", "Projection", "Custom"]
        )
        self.category_combo.currentTextChanged.connect(self._update_property_list)
        category_layout.addWidget(self.category_combo)

        category_layout.addSpacing(15)
        category_layout.addWidget(QLabel("Property:"))
        self.property_combo = QComboBox()
        self.property_combo.currentTextChanged.connect(self._update_options)
        category_layout.addWidget(self.property_combo, 1)
        property_layout.addLayout(category_layout)

        self.property_options_container = QWidget()
        self.property_options_layout = QFormLayout(self.property_options_container)
        self.property_options_layout.setContentsMargins(0, 6, 0, 0)
        property_layout.addWidget(self.property_options_container)

        property_group.setLayout(property_layout)
        layout.addWidget(property_group)

        # Filter group - two column layout
        filter_group = QGroupBox("Filter")
        filter_main_layout = QHBoxLayout(filter_group)
        filter_main_layout.setContentsMargins(8, 4, 8, 4)
        filter_main_layout.setSpacing(8)

        # Left column: histogram and slider
        self.filter_slider = HistogramRangeSlider()
        self.filter_slider.rangeReleased.connect(self._on_filter_changed)
        self._filter_throttle = Throttle(self._on_filter_changed, interval_ms=100)
        self.filter_slider.rangeChanged.connect(self._on_filter_dragging)
        filter_main_layout.addWidget(self.filter_slider, 1)

        # Right column: buttons at bottom
        filter_btn_layout = QVBoxLayout()
        filter_btn_layout.setContentsMargins(0, 0, 0, 0)
        filter_btn_layout.setSpacing(4)
        filter_btn_layout.addStretch()

        self.filter_live_checkbox = QCheckBox("Live")
        self.filter_live_checkbox.setToolTip("Update preview while dragging slider")
        filter_btn_layout.addWidget(self.filter_live_checkbox)

        self.reset_filter_btn = QPushButton("Reset")
        self.reset_filter_btn.setIcon(
            qta.icon("ph.arrow-counter-clockwise", color=Colors.PRIMARY)
        )
        self.reset_filter_btn.setToolTip("Reset filter to show all points")
        self.reset_filter_btn.clicked.connect(self._reset_filter)
        filter_btn_layout.addWidget(self.reset_filter_btn)

        self.extract_btn = QPushButton("Extract")
        self.extract_btn.setIcon(qta.icon("ph.selection", color=Colors.PRIMARY))
        self.extract_btn.setToolTip("Create new object from points within filter range")
        self.extract_btn.clicked.connect(self._extract_filtered)
        filter_btn_layout.addWidget(self.extract_btn)

        filter_main_layout.addLayout(filter_btn_layout)

        filter_group.setFixedHeight(150)
        layout.addWidget(filter_group)

        # Options group
        options_group = QGroupBox("Visualization")
        options_layout = QVBoxLayout(options_group)
        options_layout.setSpacing(4)

        colormap_layout = QHBoxLayout()
        colormap_layout.addWidget(QLabel("Color Map:"))

        self.colormap_combo, self.colormap_settings_btn = self._create_colormap_combo(
            with_settings_button=True
        )
        self.colormap_combo.colormapChanged.connect(self._preview)
        colormap_layout.addWidget(self.colormap_combo, 1)
        colormap_layout.addWidget(self.colormap_settings_btn)

        checkbox_layout = QHBoxLayout()
        self.normalize_checkbox = QCheckBox("Normalize")
        self.normalize_checkbox.setToolTip(
            format_tooltip(
                label="Normalize",
                description="Scale values to 0-1 per object.",
            )
        )
        self.normalize_checkbox.checkStateChanged.connect(self._preview)
        checkbox_layout.addWidget(self.normalize_checkbox)

        self.quantile_checkbox = QCheckBox("Use Quantiles")
        self.quantile_checkbox.setToolTip(
            format_tooltip(
                label="Use Quantiles",
                description="Plot quantiles instead of raw values.",
            )
        )
        self.quantile_checkbox.checkStateChanged.connect(self._preview)
        checkbox_layout.addWidget(self.quantile_checkbox)

        self.invert_checkbox = QCheckBox("Invert Colors")
        self.invert_checkbox.setToolTip(
            format_tooltip(
                label="Invert Colors",
                description="Invert color map.",
            )
        )
        self.invert_checkbox.checkStateChanged.connect(self._preview)
        checkbox_layout.addWidget(self.invert_checkbox)

        options_layout.addLayout(colormap_layout)
        options_layout.addLayout(checkbox_layout)
        options_group.setFixedHeight(150)

        layout.addWidget(options_group)

        # Dialog Control Buttons
        button_layout = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setIcon(qta.icon("ph.arrow-clockwise", color=Colors.PRIMARY))
        refresh_btn.clicked.connect(self._preview)
        button_layout.addWidget(refresh_btn)

        self.live_update_checkbox = QCheckBox("Live Update")
        self.live_update_checkbox.setToolTip(
            format_tooltip(
                label="Live Update",
                description="Automatically update visualization on render events.",
            )
        )
        button_layout.addWidget(self.live_update_checkbox)
        button_layout.addStretch()

        self.visualize_export_btn = QPushButton("Export Data")
        self.visualize_export_btn.setIcon(qta.icon("ph.download", color=Colors.PRIMARY))
        self.visualize_export_btn.clicked.connect(self._export_data)
        button_layout.addWidget(self.visualize_export_btn)

        apply_btn = QPushButton("Done")
        apply_btn.setIcon(dialog_accept_icon)
        apply_btn.clicked.connect(self.close)
        button_layout.addWidget(apply_btn)
        layout.addLayout(button_layout)

        self._update_property_list("Distance")

    def _setup_analysis_tab(self):
        from ..icons import dialog_accept_icon

        layout = QVBoxLayout(self.analysis_tab)

        # Plot type buttons
        header_layout = QHBoxLayout()
        header_layout.addStretch()

        plot_type_layout = QHBoxLayout()
        plot_type_layout.setSpacing(4)
        self.plot_types = ["Histogram", "Density", "Line"]
        self.current_plot_type = "Density"

        self.plot_type_buttons = {}

        self.bar_btn = QPushButton()
        self.bar_btn.setToolTip("Histogram")
        self.bar_btn.setFixedSize(28, 28)
        self.bar_btn.clicked.connect(lambda: self._set_plot_type("Histogram"))
        self.plot_type_buttons["Histogram"] = (self.bar_btn, "ph.chart-bar")

        self.density_btn = QPushButton()
        self.density_btn.setToolTip("Density")
        self.density_btn.setFixedSize(28, 28)
        self.density_btn.clicked.connect(lambda: self._set_plot_type("Density"))
        self.plot_type_buttons["Density"] = (self.density_btn, "ph.cell-signal-full")

        self.line_btn = QPushButton()
        self.line_btn.setToolTip("Line Chart")
        self.line_btn.setFixedSize(28, 28)
        self.line_btn.clicked.connect(lambda: self._set_plot_type("Line"))
        self.plot_type_buttons["Line"] = (self.line_btn, "ph.chart-line")

        plot_type_layout.addWidget(self.bar_btn)
        plot_type_layout.addWidget(self.density_btn)
        plot_type_layout.addWidget(self.line_btn)

        self._update_plot_type_buttons()
        header_layout.addLayout(plot_type_layout)
        layout.addLayout(header_layout)

        # Plot widget
        self.plot_widget = pg.GraphicsLayoutWidget(self)
        self.plot_widget.setBackground(None)
        self.plot_widget.ci.setContentsMargins(0, 0, 0, 0)

        options_group = QGroupBox("Visualization")
        options_group.setFixedHeight(150)
        options_layout = QVBoxLayout(options_group)

        strat_layout = QHBoxLayout()
        self.plot_title = QLabel("Stratification")
        self.plot_mode_combo = QComboBox()
        self.plot_mode_combo.addItems(["Combined", "Separate"])
        self.plot_mode_combo.currentTextChanged.connect(self._update_plot)
        strat_layout.addWidget(self.plot_title)
        strat_layout.addWidget(self.plot_mode_combo)
        options_layout.addLayout(strat_layout)

        alpha_layout = QHBoxLayout()
        alpha_layout.addWidget(QLabel("Alpha:"))
        self.alpha_slider = QSpinBox()
        self.alpha_slider.setRange(0, 255)
        self.alpha_slider.setValue(128)
        self.alpha_slider.valueChanged.connect(self._update_plot)
        alpha_layout.addWidget(self.alpha_slider)
        options_layout.addLayout(alpha_layout)

        colormap_layout = QHBoxLayout()
        colormap_layout.addWidget(QLabel("Color Palette:"))

        self.vis_colormap_combo = self._create_colormap_combo(
            with_settings_button=False
        )
        self.vis_colormap_combo.setCurrentText("Dark2")
        self.vis_colormap_combo.colormapChanged.connect(self._update_plot)
        colormap_layout.addWidget(self.vis_colormap_combo)
        options_layout.addLayout(colormap_layout)

        layout.addWidget(self.plot_widget)
        layout.addWidget(options_group)

        # Dialog Control Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.analysis_export_btn = QPushButton("Export Plot")
        self.analysis_export_btn.setIcon(qta.icon("ph.download", color=Colors.PRIMARY))
        self.analysis_export_btn.clicked.connect(self._export_plot)
        button_layout.addWidget(self.analysis_export_btn)

        apply_btn = QPushButton("Done")
        apply_btn.setIcon(dialog_accept_icon)
        apply_btn.clicked.connect(self.close)
        button_layout.addWidget(apply_btn)
        layout.addLayout(button_layout)

    def _setup_statistics_tab(self):
        from ..icons import dialog_accept_icon

        layout = QVBoxLayout(self.statistics_tab)

        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(5)
        self.stats_table.setHorizontalHeaderLabels(
            ["Object", "Min", "Max", "Mean", "Std Dev"]
        )
        self.stats_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        layout.addWidget(self.stats_table)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.statistics_export_btn = QPushButton("Export Statistics")
        self.statistics_export_btn.setIcon(
            qta.icon("ph.download", color=Colors.PRIMARY)
        )
        self.statistics_export_btn.clicked.connect(self._export_statistics)
        button_layout.addWidget(self.statistics_export_btn)

        apply_btn = QPushButton("Done")
        apply_btn.setIcon(dialog_accept_icon)
        apply_btn.clicked.connect(self.close)
        button_layout.addWidget(apply_btn)
        layout.addLayout(button_layout)

    def _update_property_list(self, category: str = None):
        if category is None:
            category = self.category_combo.currentText()

        previous_text = self.property_combo.currentText()

        self.property_combo.blockSignals(True)
        self.property_combo.clear()
        self.property_combo.addItems(self.PROPERTY_CATEGORIES.get(category, []))
        if previous_text is not None:
            index = self.property_combo.findText(previous_text)
            if index >= 0:
                self.property_combo.setCurrentIndex(index)

        if self.property_combo.count() > 0:
            self._update_options(self.property_combo.currentText())
        self.property_combo.blockSignals(False)

    def _update_options(self, property_name: str = None):
        if property_name is None:
            property_name = self.property_combo.currentText()

        previous_parameters = {}
        if hasattr(self, "option_widgets"):
            previous_parameters = {
                k: (
                    get_widget_value(w)
                    if not isinstance(w, (QListWidget, ContainerTreeWidget))
                    else [x.metadata.get("uuid") for x in w.selected_items()]
                )
                for k, w in self.option_widgets.items()
            }

        while self.property_options_layout.rowCount() > 0:
            self.property_options_layout.removeRow(0)

        self.option_widgets = {}
        if property_name == "Vertex Properties":
            geometries = self._get_all_geometries()
            properties = set()
            for geometry in geometries:
                if geometry.vertex_properties is None:
                    continue
                properties |= set(geometry.vertex_properties.properties)

            if len(properties) == 0:
                return self.property_combo.clear()

            options = QComboBox()
            options.addItems(sorted(list(properties)))
            self.property_options_layout.addRow("Type:", options)
            self.option_widgets["name"] = options

        elif property_name == "Curvature":
            curvature, radius = self._create_curvature_options(
                self.property_options_layout
            )
            self.option_widgets["curvature"] = curvature
            self.option_widgets["radius"] = radius

        elif property_name == "Area":
            area_type = QComboBox()
            area_type.addItems(["Total", "Per-Triangle"])
            self.property_options_layout.addRow("Type:", area_type)
            self.option_widgets["area_type"] = area_type

        elif property_name == "Volume":
            volume_type = QComboBox()
            volume_type.addItems(["Total", "Per-Triangle"])
            self.property_options_layout.addRow("Type:", volume_type)
            self.option_widgets["volume_type"] = volume_type

        elif property_name == "Mesh Statistics":
            stat_type = QComboBox()
            stat_type.addItems(["Vertex Count", "Triangle Count", "Edge Length"])
            self.property_options_layout.addRow("Type:", stat_type)
            self.option_widgets["stat_type"] = stat_type

        elif property_name == "Projected Curvature":
            group, layout, target_list, _ = self._create_target_list_group(
                "Target Mesh", "models", mesh_only=True
            )
            options_layout = QFormLayout()
            curvature, radius = self._create_curvature_options(options_layout)
            layout.addLayout(options_layout)

            self.property_options_layout.addRow(group)
            self.option_widgets["queries"] = target_list
            self.option_widgets["curvature"] = curvature
            self.option_widgets["radius"] = radius

        elif property_name == "Geodesic Distance":
            group, layout, target_list, _ = self._create_target_list_group(
                "Target Mesh", "models", mesh_only=True
            )
            k_start, k_end, aggregation = self._create_knn_range_widget(layout)

            self.property_options_layout.addRow(group)
            self.option_widgets["queries"] = target_list
            self.option_widgets["k_start"] = k_start
            self.option_widgets["k"] = k_end
            self.option_widgets["aggregation"] = aggregation

        elif property_name == "Thickness":
            group, layout, target_list, _ = self._create_target_list_group(
                "Target Cluster", "data", with_compare_all=False
            )
            smoothing_layout = QHBoxLayout()
            smoothing_layout.addWidget(QLabel("Smoothing Radius:"))
            smoothing_spin = QDoubleSpinBox()
            smoothing_spin.setRange(0.0, 1000.0)
            smoothing_spin.setValue(0.0)
            smoothing_spin.setDecimals(1)
            smoothing_spin.setSingleStep(1.0)
            smoothing_spin.setToolTip(
                "Radius for Gaussian-weighted spatial smoothing (0 = no smoothing)"
            )
            smoothing_layout.addWidget(smoothing_spin)
            layout.addLayout(smoothing_layout)

            self.property_options_layout.addRow(group)
            self.option_widgets["queries"] = target_list
            self.option_widgets["smoothing_radius"] = smoothing_spin

        elif property_name == "To Cluster":
            group, layout, target_list, compare_all = self._create_target_list_group(
                "Options", "data", with_compare_all=True
            )
            include_self = QCheckBox("Within-Cluster Distance")
            # Insert checkbox next to Compare to All
            checkbox_layout = layout.itemAt(1).layout()
            checkbox_layout.addWidget(include_self)

            k_start, k_end, aggregation = self._create_knn_range_widget(layout)

            self.property_options_layout.addRow(group)
            self.option_widgets["queries"] = target_list
            self.option_widgets["include_self"] = include_self
            self.option_widgets["compare_to_all"] = compare_all
            self.option_widgets["k_start"] = k_start
            self.option_widgets["k"] = k_end
            self.option_widgets["aggregation"] = aggregation

        elif property_name == "To Self":
            group = QGroupBox("Options")
            layout = QVBoxLayout(group)

            self_checkbox = QCheckBox()
            self_checkbox.setChecked(True)
            k_start, k_end, aggregation = self._create_knn_range_widget(layout)

            self.property_options_layout.addRow(group)
            self.option_widgets["only_self"] = self_checkbox
            self.option_widgets["k_start"] = k_start
            self.option_widgets["k"] = k_end
            self.option_widgets["aggregation"] = aggregation

        elif property_name == "To Model":
            group, layout, target_list, compare_all = self._create_target_list_group(
                "Target Models", "models", with_compare_all=True
            )
            self.property_options_layout.addRow(group)
            self.option_widgets["queries"] = target_list
            self.option_widgets["compare_to_all"] = compare_all

        # Restore previous parameter values
        for k, widget in self.option_widgets.items():
            if k in previous_parameters:
                value = previous_parameters[k]
                if isinstance(widget, (QListWidget, ContainerTreeWidget)):
                    widget.set_selection(value)
                    continue
                set_widget_value(widget, value)

    def toggle_all_targets(self, state, target_list):
        target_list.setEnabled(not bool(state))

        if bool(state):
            items = []
            for item, parent, _ in target_list.traverse(reverse=False):
                items.append(item)
            target_list._set_selection(items)
        else:
            target_list.clearSelection()

    def _get_selected_geometries(self):
        return [x[1] for x in self._get_selection()]

    def _get_all_geometries(self):
        return [x[1] for x in self._get_selection(selected=False)]

    def _get_selection(self, selected: bool = True):
        return [
            *self.cdata.format_datalist("data", selected=selected),
            *self.cdata.format_datalist("models", selected=selected),
        ]

    def _compute_properties(self):
        from ..properties import GeometryProperties

        property_name = self.PROPERTY_MAP.get(self.property_combo.currentText())
        if property_name is None:
            return None

        # Build parameters from current widget values
        parameters = {"property_name": property_name}
        for k, widget in self.option_widgets.items():
            if isinstance(widget, (QListWidget, ContainerTreeWidget)):
                parameters[k] = [
                    item.data(Qt.ItemDataRole.UserRole)
                    for item in widget.selectedItems()
                ]
            else:
                parameters[k] = get_widget_value(widget)

        if self.property_combo.currentText() == "To Camera":
            vtk_widget = self.cdata.data.vtk_widget
            renderer = vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer()
            parameters["queries"] = np.array(
                renderer.GetActiveCamera().GetPosition()
            ).reshape(1, -1)

        geometries = self._get_selected_geometries()

        # Handle identity property specially (no computation needed)
        if property_name == "identity":
            for i, geometry in enumerate(geometries):
                self._cache.set(geometry, parameters, i)
            return None

        # Compute properties for geometries not in cache or with changed parameters
        for geometry in geometries:
            if self._cache.get(geometry, parameters) is not None:
                continue

            try:
                value = GeometryProperties.compute(geometry=geometry, **parameters)

                # Some properties will return None for an empty query. This by itself is
                # fine, but will be automatically triggered when deselecting and
                # reselecting an object due to the dialog being connected to the
                # vtk_pre_render signal emitted by DataContainerInteractor. That will
                # cause a redraw of list widgets for query selection and trigger a
                # computation with empty query yielding None which we do not store.
                if value is not None:
                    self._cache.set(geometry, parameters, value)
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))
                return None

    def _apply_threshold_clipping(self, properties):
        """Apply threshold clipping to property values"""
        if (
            not self.threshold_settings["lower_enabled"]
            and not self.threshold_settings["upper_enabled"]
        ):
            return properties

        clipped_properties = {}
        for k, v in properties.items():
            v_clipped = v.copy() if isinstance(v, np.ndarray) else v

            if self.threshold_settings["lower_enabled"]:
                lower_val = self.threshold_settings["lower_value"]
                if isinstance(v_clipped, np.ndarray):
                    v_clipped = np.maximum(v_clipped, lower_val)
                else:
                    v_clipped = max(v_clipped, lower_val)

            if self.threshold_settings["upper_enabled"]:
                upper_val = self.threshold_settings["upper_value"]
                if isinstance(v_clipped, np.ndarray):
                    v_clipped = np.minimum(v_clipped, upper_val)
                else:
                    v_clipped = min(v_clipped, upper_val)

            clipped_properties[k] = v_clipped

        return clipped_properties

    def _preview(self, render: bool = True):
        from ..utils import cmap_to_vtkctf

        geometries = self._get_selected_geometries()
        if not geometries:
            return None

        self._compute_properties()
        colormap = self.colormap_combo.currentText()
        if self.invert_checkbox.isChecked():
            colormap += "_r"

        # Build properties dict from cache for selected geometries
        properties = {
            g.uuid: self._cache.get_value(g.uuid)
            for g in geometries
            if self._cache.get_value(g.uuid) is not None
        }
        if self.normalize_checkbox.isChecked():
            properties = {
                k: (
                    (v - np.min(v)) / (np.max(v) - np.min(v))
                    if (np.max(v) - np.min(v)) > 0
                    else v
                )
                for k, v in properties.items()
            }

        if self.quantile_checkbox.isChecked():
            all_curvatures = np.concatenate(
                [np.asarray(v).flatten() for v in properties.values()]
            )
            valid_curvatures = all_curvatures[~np.isnan(all_curvatures)]
            n_bins = min(valid_curvatures.size // 10, 100)
            bins = np.percentile(valid_curvatures, np.linspace(0, 100, n_bins + 1))
            properties = {k: np.digitize(v, bins) - 1 for k, v in properties.items()}

        properties = self._apply_threshold_clipping(properties)
        values = [x for x in properties.values() if x is not None]
        if len(values) == 0:
            return None

        max_value = np.max([np.max(x) for x in values])
        min_value = np.min([np.min(x) for x in values])
        lut, lut_range = cmap_to_vtkctf(colormap, max_value, min_value=min_value)
        for geometry in geometries:
            metric = properties.get(geometry.uuid)
            if metric is None:
                continue
            geometry.set_scalars(metric, lut, lut_range)

        self.legend.set_lookup_table(lut, self.property_combo.currentText())

        # Update filter slider with all property values
        all_values = np.concatenate([np.asarray(v).flatten() for v in values])
        self.filter_slider.setData(all_values)

        if render:
            self.cdata.data.render_vtk()
            self.cdata.models.render_vtk()

    def _on_filter_changed(self, lower, upper):
        """Hide points outside the filter range using transparent LUT colors."""
        from ..utils import cmap_to_vtkctf

        geometries = self._get_selected_geometries()
        if not geometries:
            return

        colormap = self.colormap_combo.currentText()
        if self.invert_checkbox.isChecked():
            colormap += "_r"

        lut, lut_range = cmap_to_vtkctf(
            colormap, upper, min_value=lower, transparent_range=True
        )

        for geometry in geometries:
            values = self._cache.get_value(geometry.uuid)
            if values is None:
                continue

            values = np.asarray(values).flatten()
            geometry.set_scalars(values, lut, lut_range)

        self.cdata.data.render_vtk()
        self.cdata.models.render_vtk()

    def _on_filter_dragging(self, lower, upper):
        """Handle slider drag events with throttling for live preview."""
        if not self.filter_live_checkbox.isChecked():
            return
        self._filter_throttle(lower, upper)

    def _reset_filter(self):
        """Reset filter to show all points."""
        self.filter_slider._slider.setValues(
            self.filter_slider._slider.min_val,
            self.filter_slider._slider.max_val,
        )
        self.filter_slider._histogram.setSelection(
            self.filter_slider._slider.min_val,
            self.filter_slider._slider.max_val,
        )
        self._preview()

    def _extract_filtered(self):
        """Create new geometry from points within filter range."""
        lower, upper = self.filter_slider.getRange()
        geometries = self._get_selected_geometries()

        if not geometries:
            QMessageBox.warning(self, "No Selection", "Please select geometry first.")
            return

        extracted_any = False
        for geometry in geometries:
            values = self._cache.get_value(geometry.uuid)
            if values is None:
                continue

            values = np.asarray(values).flatten()
            mask = (values >= lower) & (values <= upper)

            if not mask.any():
                continue

            # Create subset geometry
            subset = geometry[mask]
            if subset.get_number_of_points() > 0:
                self.cdata.data.add(subset)
                extracted_any = True

        if extracted_any:
            self.cdata.data.render()
        else:
            QMessageBox.information(
                self, "No Points", "No points fall within the selected range."
            )

    def _update_tab(self):
        current_tab_index = self.tabs_widget.currentIndex()

        self.plot_widget.clear()
        QTimer.singleShot(
            100,
            lambda: (
                self._update_plot()
                if current_tab_index == 1
                else self._update_statistics() if current_tab_index == 2 else None
            ),
        )

    def _update_statistics(self):
        selected_items = self._get_selection()
        self.stats_table.setRowCount(len(selected_items))

        row_count, n_decimals = 0, 6
        for index, (item_text, obj) in enumerate(selected_items):
            value = self._cache.get_value(obj.uuid)
            if value is None:
                continue

            row_count += 1
            item = QTableWidgetItem(item_text)
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
        self._update_plot_type_buttons()
        self._update_plot()

    def _update_plot_type_buttons(self):
        """Update plot type button icons and styling based on selection state."""
        for plot_type, (btn, icon_name) in self.plot_type_buttons.items():
            is_selected = plot_type == self.current_plot_type
            icon_color = Colors.PRIMARY if is_selected else Colors.ICON
            btn.setIcon(qta.icon(icon_name, color=icon_color))

            if is_selected:
                btn.setStyleSheet(
                    f"""
                    QPushButton {{
                        border: 1px solid {Colors.PRIMARY};
                        border-radius: 4px;
                        background: transparent;
                    }}
                """
                )
            else:
                btn.setStyleSheet(
                    f"""
                    QPushButton {{
                        border: 1px solid {Colors.BORDER_DARK};
                        border-radius: 4px;
                        background: transparent;
                    }}
                    QPushButton:hover {{
                        background: {Colors.BG_HOVER};
                        border: 1px solid {Colors.BORDER_HOVER};
                    }}
                """
                )

    def _update_plot(self):
        """Update the plot based on the current property and selected objects"""
        if self.tabs_widget.currentIndex() != 1:
            return None

        selected_items = self._get_selection()
        if not selected_items:
            return None

        plot_type = getattr(self, "current_plot_type", "Density")
        plot_mode = getattr(self, "plot_mode_combo", lambda: "Combined").currentText()
        alpha = getattr(self, "alpha_slider", lambda: 150).value()
        colormap = getattr(self, "vis_colormap_combo", lambda: "viridis").currentText()
        colors = generate_gradient_colors(colormap, len(selected_items))
        colors = [pg.mkColor(c.red(), c.green(), c.blue(), alpha) for c in colors]

        data_series = []
        all_values = []
        for i, (item_text, obj) in enumerate(selected_items):
            if (values := self._cache.get_value(obj.uuid)) is not None:
                all_values.append(values)
                data_series.append((item_text, obj, values, colors[i % len(colors)]))

        if not data_series:
            return None

        try:
            self.plot_widget.setUpdatesEnabled(False)

            self.plot_widget.clear()
            all_scalar = not isinstance(all_values[0], np.ndarray)
            if all_scalar:
                all_values = np.asarray(all_values)
                self._create_categorical_plot(data_series, all_values, plot_type)
            else:
                self._create_plot(data_series, all_values, plot_mode, plot_type)
        finally:
            self.plot_widget.setUpdatesEnabled(True)

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
        plot.addLegend(offset=(-10, 10))

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

            plot.disableAutoRange()
            plot.addLegend(offset=(-10, 10))

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

            plot.enableAutoRange()
            plot.autoRange()
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

    def _run_export(self, title: str, file_filter: str, export_func) -> None:
        """Run an export operation with file dialog and error handling."""
        file_path, _ = QFileDialog.getSaveFileName(self, title, "", file_filter)
        if not file_path:
            return

        try:
            export_func(file_path)
            QMessageBox.information(self, "Success", f"{title} completed successfully")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export: {str(e)}")

    def _export_data(self):
        """Export analysis data to a CSV file."""
        selected_items = self._get_selection()
        if not selected_items:
            QMessageBox.warning(
                self, "No Selection", "Please select at least one object."
            )
            return

        def write_data(file_path):
            property_name = self.property_combo.currentText()
            with open(file_path, mode="w", encoding="utf-8") as ofile:
                per_point = all(
                    self._cache.get_value(geom.uuid).size == geom.get_number_of_points()
                    for name, geom in selected_items
                    if self._cache.get_value(geom.uuid) is not None
                )

                header = f"source,{property_name}\n"
                if per_point:
                    header = f"source,point_id,x,y,z,{property_name}\n"
                ofile.write(header)

                for name, geom in selected_items:
                    if (values := self._cache.get_value(geom.uuid)) is None:
                        continue

                    values = np.asarray(values).reshape(-1)
                    if per_point:
                        lines = "\n".join(
                            f"{name},{pid},{p[0]},{p[1]},{p[2]},{v}"
                            for pid, (p, v) in enumerate(zip(geom.points, values))
                        )
                    else:
                        lines = "\n".join(f"{name},{v}" for v in values)
                    ofile.write(lines + "\n")

        self._run_export(
            "Export Data", "CSV Files (*.csv);;All Files (*.*)", write_data
        )

    def _export_plot(self):
        """Save the current plot as an image."""
        from pyqtgraph.exporters import ImageExporter

        def write_plot(file_path):
            exporter = ImageExporter(self.plot_widget.scene())
            exporter.parameters()["width"] = 1920
            exporter.parameters()["height"] = 1080
            exporter.parameters()["antialias"] = True
            exporter.export(file_path)

        self._run_export("Save Plot", "PNG Files (*.png);;All Files (*.*)", write_plot)

    def _export_statistics(self):
        """Export statistics table to a CSV file."""

        def write_stats(file_path):
            with open(file_path, mode="w", encoding="utf-8") as ofile:
                headers = [
                    (
                        self.stats_table.horizontalHeaderItem(col).text()
                        if self.stats_table.horizontalHeaderItem(col)
                        else f"Column{col}"
                    )
                    for col in range(self.stats_table.columnCount())
                ]
                ofile.write(",".join(headers) + "\n")

                for row in range(self.stats_table.rowCount()):
                    row_data = [
                        (
                            self.stats_table.item(row, col).text()
                            if self.stats_table.item(row, col)
                            else ""
                        )
                        for col in range(self.stats_table.columnCount())
                    ]
                    ofile.write(",".join(row_data) + "\n")

        self._run_export(
            "Export Statistics", "CSV Files (*.csv);;All Files (*.*)", write_stats
        )
