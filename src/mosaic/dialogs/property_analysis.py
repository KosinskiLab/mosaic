"""
Dialog to analyze and interactively visualize properties of Geometry objects.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import warnings
import numpy as np
from qtpy.QtCore import Qt, QSize, QTimer
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
    QTableWidget,
    QHeaderView,
    QTableWidgetItem,
    QFileDialog,
    QDoubleSpinBox,
    QStackedWidget,
)
import pyqtgraph as pg

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..widgets import (
    ContainerTreeWidget,
    StyledListWidgetItem,
    ColorMapSelector,
    HistogramRangeSlider,
    TabWidget,
    generate_gradient_colors,
)
from ..utils import Throttle
from ..widgets.settings import get_widget_value, set_widget_value
from ..icons import icon as _icon
from ..stylesheets import (
    QTable_style,
    Colors,
)


def to_numeric(arr):
    """Encode a numpy array to float64, factorising string/object dtypes."""
    arr = np.asarray(arr)
    if arr.dtype.kind in ("U", "S", "O"):
        _, codes = np.unique(arr, return_inverse=True)
        return codes.astype(np.float64)
    return arr.astype(np.float64, copy=False)


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


def _make_uuid_to_items(geometries):
    """Build a uuid-to-StyledTreeWidgetItem map from geometry pairs."""
    return {
        obj.uuid: StyledListWidgetItem(geometry=obj, visible=obj.visible)
        for _, obj in geometries
    }


def _populate_list(geometries, tree_state=None):
    target_list = ContainerTreeWidget()
    target_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)

    uuid_to_items = _make_uuid_to_items(geometries)

    if tree_state is not None:
        target_list.apply_state(tree_state, uuid_to_items)
    else:
        target_list.update(uuid_to_items)

    return target_list


def _build_type_combo_option(dlg, key, items):
    """Add a QComboBox option row with given key and items."""
    combo = QComboBox()
    combo.addItems(items)
    dlg.property_options_layout.addRow("Type:", combo)
    dlg.option_widgets[key] = combo


def _build_vertex_properties_options(dlg):
    geometries = dlg._get_all_geometries()
    properties = set()
    for geometry in geometries:
        if geometry.vertex_properties is None:
            continue
        properties |= set(geometry.vertex_properties.properties)

    if len(properties) == 0:
        return dlg.property_combo.clear()

    options = QComboBox()
    options.addItems(sorted(list(properties)))
    dlg.property_options_layout.addRow("Type:", options)
    dlg.option_widgets["name"] = options


def _build_curvature_options(dlg):
    curvature, radius = dlg._create_curvature_options(dlg.property_options_layout)
    dlg.option_widgets["curvature"] = curvature
    dlg.option_widgets["radius"] = radius


def _build_area_options(dlg):
    _build_type_combo_option(dlg, "area_type", ["Total", "Per-Triangle"])


def _build_volume_options(dlg):
    _build_type_combo_option(dlg, "volume_type", ["Total", "Per-Triangle"])


def _build_mesh_statistics_options(dlg):
    _build_type_combo_option(
        dlg, "stat_type", ["Vertex Count", "Triangle Count", "Edge Length"]
    )


def _build_projected_curvature_options(dlg):
    group, layout, target_list, _ = dlg._create_target_list_group(
        "Target Mesh", "models", mesh_only=True
    )
    options_layout = QFormLayout()
    curvature, radius = dlg._create_curvature_options(options_layout)
    layout.addLayout(options_layout)

    dlg.property_options_layout.addRow(group)
    dlg.option_widgets["queries"] = target_list
    dlg.option_widgets["curvature"] = curvature
    dlg.option_widgets["radius"] = radius


def _build_angle_options(dlg):
    group, layout, target_list, _ = dlg._create_target_list_group(
        "Target Mesh", "models", mesh_only=True
    )
    dlg.property_options_layout.addRow(group)
    dlg.option_widgets["queries"] = target_list


def _build_geodesic_distance_options(dlg):
    group, layout, target_list, _ = dlg._create_target_list_group(
        "Target Mesh", "models", mesh_only=True
    )
    k_start, k_end, aggregation = dlg._create_knn_range_widget(layout)

    dlg.property_options_layout.addRow(group)
    dlg.option_widgets["queries"] = target_list
    dlg.option_widgets["k_start"] = k_start
    dlg.option_widgets["k"] = k_end
    dlg.option_widgets["aggregation"] = aggregation


def _build_thickness_options(dlg):
    group, layout, target_list, _ = dlg._create_target_list_group(
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

    dlg.property_options_layout.addRow(group)
    dlg.option_widgets["queries"] = target_list
    dlg.option_widgets["smoothing_radius"] = smoothing_spin


def _build_tomogram_options(dlg):
    from mosaic.widgets import PathSelector, SliderRow

    path_selector = PathSelector(
        placeholder="Path to tomogram (MRC, EM, MAP, ...)",
    )
    dlg.property_options_layout.addRow("Tomogram:", path_selector)
    dlg.option_widgets["file_path"] = path_selector

    texture_size = QSpinBox()
    texture_size.setRange(256, 2048)
    texture_size.setValue(512)
    texture_size.setSingleStep(128)
    texture_size.setToolTip(
        "Texture resolution in pixels. Larger meshes require larger textures to "
        "maintain texture resolution."
    )

    dlg.property_options_layout.addRow("Texture Size:", texture_size)
    dlg.option_widgets["texture_size"] = texture_size

    spline_order = QSpinBox()
    spline_order.setRange(1, 5)
    spline_order.setValue(3)
    spline_order.setToolTip(
        "Spline interpolation order for tomogram sampling. "
        "1 = linear (fast), 3 = cubic (smooth, default), 5 = quintic."
    )
    dlg.property_options_layout.addRow("Spline Order:", spline_order)
    dlg.option_widgets["interpolation_order"] = spline_order

    offset_slider = SliderRow(
        label="Normal Offset",
        min_val=-20.0,
        max_val=20.0,
        default=0.0,
        decimals=1,
        suffix=" vox",
        steps=80,
    )
    offset_slider.setToolTip(
        "Offset along surface normals in voxels. "
        "Positive = outward, negative = inward."
    )

    offset_slider.valueChanged.connect(dlg._preview_throttle)
    dlg.property_options_layout.addRow(offset_slider)
    dlg.option_widgets["normal_offset"] = offset_slider


def _build_to_cluster_options(dlg):
    group, layout, target_list, compare_all = dlg._create_target_list_group(
        "Options", "data", with_compare_all=True
    )
    include_self = QCheckBox("Within-Cluster Distance")
    # Insert checkbox next to Compare to All
    checkbox_layout = layout.itemAt(1).layout()
    checkbox_layout.addWidget(include_self)

    k_start, k_end, aggregation = dlg._create_knn_range_widget(layout)

    dlg.property_options_layout.addRow(group)
    dlg.option_widgets["queries"] = target_list
    dlg.option_widgets["include_self"] = include_self
    dlg.option_widgets["compare_to_all"] = compare_all
    dlg.option_widgets["k_start"] = k_start
    dlg.option_widgets["k"] = k_end
    dlg.option_widgets["aggregation"] = aggregation


def _build_to_self_options(dlg):
    group = QGroupBox("Options")
    layout = QVBoxLayout(group)

    self_checkbox = QCheckBox()
    self_checkbox.setChecked(True)
    k_start, k_end, aggregation = dlg._create_knn_range_widget(layout)

    dlg.property_options_layout.addRow(group)
    dlg.option_widgets["only_self"] = self_checkbox
    dlg.option_widgets["k_start"] = k_start
    dlg.option_widgets["k"] = k_end
    dlg.option_widgets["aggregation"] = aggregation


def _build_to_model_options(dlg):
    group, layout, target_list, compare_all = dlg._create_target_list_group(
        "Target Models", "models", with_compare_all=True
    )
    dlg.property_options_layout.addRow(group)
    dlg.option_widgets["queries"] = target_list
    dlg.option_widgets["compare_to_all"] = compare_all


_OPTION_BUILDERS = {
    "Vertex Properties": _build_vertex_properties_options,
    "Curvature": _build_curvature_options,
    "Area": _build_area_options,
    "Volume": _build_volume_options,
    "Mesh Statistics": _build_mesh_statistics_options,
    "Projected Curvature": _build_projected_curvature_options,
    "Angle": _build_angle_options,
    "Geodesic Distance": _build_geodesic_distance_options,
    "Thickness": _build_thickness_options,
    "Tomogram": _build_tomogram_options,
    "To Cluster": _build_to_cluster_options,
    "To Self": _build_to_self_options,
    "To Model": _build_to_model_options,
}


class ColorScaleSettingsDialog(QDialog):
    """Dialog for configuring color scale thresholds"""

    def __init__(self, parent=None):
        from ..icons import dialog_accept_icon, dialog_reject_icon

        super().__init__(parent)
        self.setWindowTitle("Color Scale Settings")
        self.setModal(True)

        self._dialog_accept_icon = dialog_accept_icon
        self._dialog_reject_icon = dialog_reject_icon
        self._dialog_margin = (10, 10, 10, 10)
        self._footer_margin = (0, 10, 0, 0)

        self.lower_enabled = False
        self.upper_enabled = False
        self.lower_value = 0.0
        self.upper_value = 1.0

        self._setup_ui()

    def sizeHint(self):
        return QSize(400, 350)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*self._dialog_margin)

        threshold_group = QGroupBox("Threshold Settings")
        threshold_layout = QVBoxLayout(threshold_group)

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
            "Tomogram",
        ],
        "Projection": ["Projected Curvature", "Geodesic Distance", "Angle"],
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
        "Tomogram": "mesh_tomogram",
        "Identity": "identity",
        "Width (X-axis)": "width",
        "Depth (Y-axis)": "depth",
        "Height (Z-axis)": "height",
        "Number of Points": "n_points",
        "Projected Curvature": "projected_curvature",
        "Geodesic Distance": "geodesic_distance",
        "Angle": "projected_angle",
        "Thickness": "thickness",
        "Vertex Properties": "vertex_property",
    }

    # Properties that bypass the standard compute + colormap preview flow.
    _CUSTOM_PREVIEWS = {"mesh_tomogram"}

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

        self._preview_throttle = Throttle(self._preview, interval_ms=150)
        self._update_plot_throttle = Throttle(self._update_plot, interval_ms=150)
        self.setWindowTitle("Property Analysis")

        self.legend = legend
        self._setup_ui()
        self.setStyleSheet(QTable_style)

        self.cdata.data.vtk_pre_render.connect(self._on_render_update)
        self.cdata.models.vtk_pre_render.connect(self._on_render_update)
        self.cdata.data.data_changed.connect(self._refresh_target_lists)
        self.cdata.models.data_changed.connect(self._refresh_target_lists)

    def _on_render_update(self):
        """Re-apply properties when models are re-rendered."""
        self.cdata.data.blockSignals(True)
        self.cdata.models.blockSignals(True)
        try:
            if self.live_update_checkbox.isChecked():
                self._preview(render=False)
                self._update_plot()
                self._update_statistics()
        except Exception:
            pass
        finally:
            self.cdata.data.blockSignals(False)
            self.cdata.models.blockSignals(False)

    def _refresh_target_lists(self):
        """Incrementally update any active target list with current geometries."""
        target_list = self.option_widgets.get("queries")
        if target_list is None:
            return
        data_source = getattr(target_list, "_data_source", None)
        if data_source is None:
            return
        kwargs = getattr(target_list, "_data_kwargs", {})
        geometries = self.cdata.format_datalist(data_source, **kwargs)
        uuid_to_items = _make_uuid_to_items(geometries)
        target_list.update(uuid_to_items)

    def closeEvent(self, event):
        """Disconnect when dialog closes"""
        try:
            self.cdata.data.vtk_pre_render.disconnect(self._on_render_update)
            self.cdata.models.vtk_pre_render.disconnect(self._on_render_update)
            self.cdata.data.data_changed.disconnect(self._refresh_target_lists)
            self.cdata.models.data_changed.disconnect(self._refresh_target_lists)
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

        tree_state = self.cdata.get_tree_state(data_source)
        target_list = _populate_list(
            self.cdata.format_datalist(data_source, **kwargs), tree_state
        )
        target_list._data_source = data_source
        target_list._data_kwargs = kwargs
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
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.visualization_tab = QWidget()
        self.analysis_tab = QWidget()
        self.statistics_tab = QWidget()

        self._setup_visualization_tab()
        self._setup_analysis_tab()
        self._setup_statistics_tab()

        self._tabs = TabWidget(tab_bar_margins=(0, 0, 0, 0))
        self._tabs.addTab(self.visualization_tab, "Visualize", _icon("ph.paint-brush"))
        self._tabs.addTab(self.analysis_tab, "Distribution", _icon("ph.chart-line"))
        self._tabs.addTab(self.statistics_tab, "Statistics", _icon("ph.chart-bar"))
        self._tabs.finalize()
        self._tabs.currentChanged.connect(self._switch_tab)

        main_layout.addWidget(self._tabs)

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
            settings_btn.setIcon(_icon("ph.gear"))
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

        self.filter_stack = QStackedWidget()

        self.filter_slider = HistogramRangeSlider()
        self.filter_slider.rangeReleased.connect(self._on_filter_changed)
        self._filter_throttle = Throttle(self._on_filter_changed, interval_ms=100)
        self.filter_slider.rangeChanged.connect(self._on_filter_dragging)
        self.filter_stack.addWidget(self.filter_slider)

        self.category_filter_list = QListWidget()
        self.category_filter_list.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection
        )
        self.category_filter_list.itemSelectionChanged.connect(
            lambda: self._on_filter_changed(0, 0)
        )
        self.filter_stack.addWidget(self.category_filter_list)

        filter_main_layout.addWidget(self.filter_stack, 1)

        filter_btn_layout = QVBoxLayout()
        filter_btn_layout.setContentsMargins(0, 0, 0, 0)
        filter_btn_layout.setSpacing(4)
        filter_btn_layout.addStretch()

        self.filter_live_checkbox = QCheckBox("Live")
        self.filter_live_checkbox.setChecked(True)
        self.filter_live_checkbox.setToolTip("Update preview while dragging slider")
        filter_btn_layout.addWidget(self.filter_live_checkbox)

        self.reset_filter_btn = QPushButton("Reset")
        self.reset_filter_btn.setIcon(
            _icon("ph.arrow-counter-clockwise", role="primary")
        )
        self.reset_filter_btn.setToolTip("Reset filter to show all points")
        self.reset_filter_btn.clicked.connect(self._reset_filter)
        filter_btn_layout.addWidget(self.reset_filter_btn)

        self.extract_btn = QPushButton("Extract")
        self.extract_btn.setIcon(_icon("ph.selection", role="primary"))
        self.extract_btn.setToolTip("Create new object from points within filter range")
        self.extract_btn.clicked.connect(self._extract_filtered)
        filter_btn_layout.addWidget(self.extract_btn)

        self.split_btn = QPushButton("Split")
        self.split_btn.setIcon(_icon("ph.git-fork", role="primary"))
        self.split_btn.setToolTip(
            "Split each object into separate objects per category"
        )
        self.split_btn.clicked.connect(self._split_by_category)
        self.split_btn.hide()
        filter_btn_layout.addWidget(self.split_btn)

        filter_main_layout.addLayout(filter_btn_layout)

        filter_group.setFixedHeight(150)
        layout.addWidget(filter_group)

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

        from ..widgets import SliderRow

        self.gamma_row = SliderRow(
            label="Gamma",
            min_val=0.01,
            max_val=3.0,
            default=1.0,
            decimals=2,
            steps=100,
        )
        self.gamma_row.setToolTip(
            format_tooltip(
                label="Gamma",
                description="Non-linear contrast adjustment. "
                "Values < 1 brighten dark regions, > 1 darken bright regions.",
            )
        )
        self.gamma_row.valueChanged.connect(self._preview_throttle)
        self.gamma_row.setContentsMargins(0, 0, 0, 0)

        options_layout.addLayout(colormap_layout)
        options_layout.addWidget(self.gamma_row)
        options_layout.addLayout(checkbox_layout)
        options_group.setFixedHeight(150)

        layout.addWidget(options_group)

        button_layout = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setIcon(_icon("ph.arrow-clockwise", role="primary"))
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

        self.visualize_export_btn = QPushButton("Export")
        self.visualize_export_btn.setIcon(_icon("ph.download", role="primary"))
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
        self.alpha_slider.valueChanged.connect(self._update_plot_throttle)
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

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.analysis_export_btn = QPushButton("Export Plot")
        self.analysis_export_btn.setIcon(_icon("ph.download", role="primary"))
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
        self.statistics_export_btn.setIcon(_icon("ph.download", role="primary"))
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

        while self.property_options_layout.rowCount() > 0:
            self.property_options_layout.removeRow(0)

        self.option_widgets = {}
        builder = _OPTION_BUILDERS.get(property_name)
        if builder is not None:
            builder(self)

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

    def _interactor_for(self, geometry):
        """Return the interactor (data or models) that owns *geometry*."""
        if self.cdata._models.get(geometry.uuid) is not None:
            return self.cdata.models
        return self.cdata.data

    def _get_or_create_texture_sampler(
        self, geometry, file_path: str, texture_size: int, interpolation_order: int
    ):
        """Get cached TextureSampler or create a new one."""
        import vtk as _vtk
        from .. import meshing

        if isinstance(geometry.actor, (_vtk.vtkLODActor, _vtk.vtkQuadricLODActor)):
            QMessageBox.warning(
                self,
                "Texture Error",
                "Texture mapping requires the 'Ultra' rendering quality preset. "
                "LOD actors (used by other presets) do not support VTK textures.\n\n"
                "Change the preset under Preferences > Appearance > Preset.",
            )
            return None

        if not hasattr(self, "_texture_samplers"):
            self._texture_samplers = {}

        no_texture = geometry.actor.GetTexture() is None
        cache_key = (geometry.uuid, texture_size, file_path)
        cached = self._texture_samplers.get(cache_key)

        # interpolation_order is intentionally not part of the cache key
        # because the sampler owns the VTK texture and mesh data on the
        # geometry. Recreating it is the only safe way to change the order,
        # since the old texture state would otherwise be left dangling on the actor.
        order_changed = (
            cached is not None and cached.interpolation_order != interpolation_order
        )
        if cached is None or no_texture or order_changed:
            if order_changed:
                cached.cleanup()
            try:
                sampler = meshing.TextureSampler(
                    geometry=geometry,
                    tomogram_path=file_path,
                    texture_size=texture_size,
                    interpolation_order=interpolation_order,
                )
                self._texture_samplers[cache_key] = sampler
            except Exception as e:
                QMessageBox.warning(self, "Texture Error", str(e))
                return None

        return self._texture_samplers[cache_key]

    def _update_texture_offset(self, normal_offset: float):
        """Update texture samplers with new normal offset (fast path)."""
        geometries = self._get_selected_geometries()
        file_path = get_widget_value(self.option_widgets.get("file_path"))
        texture_size = get_widget_value(self.option_widgets.get("texture_size", 512))
        interpolation_order = get_widget_value(
            self.option_widgets.get("interpolation_order", 3)
        )

        if not geometries or not len(file_path):
            return None

        colormap = self._get_colormap()
        gamma = self.gamma_row.value()
        normalize = self.normalize_checkbox.isChecked()
        quantiles = self.quantile_checkbox.isChecked()

        for geometry in geometries:
            fit = geometry.model
            if not hasattr(fit, "mesh"):
                continue

            sampler = self._get_or_create_texture_sampler(
                geometry, file_path, texture_size, interpolation_order
            )
            if sampler is None:
                continue

            scalar_range = None if normalize else sampler.scalar_range
            sampler.update(
                normal_offset=normal_offset,
                colormap=colormap,
                scalar_range=scalar_range,
                gamma=gamma,
                quantiles=quantiles,
            )

        self.render()

    def _compute_properties(self):
        from ..properties import GeometryProperties

        property_name = self.PROPERTY_MAP.get(self.property_combo.currentText())
        if property_name is None:
            return None

        # Build parameters from current widget values
        parameters = {"property_name": property_name}
        for k, widget in self.option_widgets.items():
            if isinstance(widget, (QListWidget, ContainerTreeWidget)):
                items = (
                    widget.selected_items()
                    if isinstance(widget, ContainerTreeWidget)
                    else widget.selectedItems()
                )
                parameters[k] = [item.data(Qt.ItemDataRole.UserRole) for item in items]
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

    def _is_categorical(self, geometries):
        """Check whether the current cached property values are categorical."""
        for g in geometries:
            v = self._cache.get_value(g.uuid)
            if v is not None and isinstance(v, np.ndarray):
                return v.dtype.kind in ("U", "S", "O")
        return False

    def _get_transformed_properties(self, geometries):
        """Apply the full visualization transform pipeline to cached properties.

        Applies normalization, quantization, and threshold clipping in the same
        order as ``_preview`` so that filter operations work on consistent values.
        """
        properties = {
            g.uuid: to_numeric(self._cache.get_value(g.uuid))
            for g in geometries
            if self._cache.get_value(g.uuid) is not None
        }
        if self.normalize_checkbox.isChecked():
            properties = {
                k: (
                    (v - np.nanmin(v)) / (np.nanmax(v) - np.nanmin(v))
                    if (np.nanmax(v) - np.nanmin(v)) > 0
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
        return properties

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

        property_name = self.PROPERTY_MAP.get(self.property_combo.currentText())
        if property_name in self._CUSTOM_PREVIEWS:
            return self._update_texture_offset(
                get_widget_value(self.option_widgets.get("normal_offset", 0.0))
            )

        # Clean up potential textures. TODO: Maybe move the mechanism to set_scalars
        texture_samplers = getattr(self, "_texture_samplers", {})
        for k in list(texture_samplers.keys()):
            for geometry in geometries:
                if k[0] != geometry.uuid:
                    continue
                v = texture_samplers.pop(k)
                v.cleanup()

        self._compute_properties()
        colormap = self._get_colormap()

        properties = self._get_transformed_properties(geometries)
        values = [x for x in properties.values() if x is not None]
        if len(values) == 0:
            return None

        max_value = np.nanmax([np.nanmax(x) for x in values])
        min_value = np.nanmin([np.nanmin(x) for x in values])
        gamma = self.gamma_row.value()
        lut, lut_range = cmap_to_vtkctf(
            colormap, max_value, min_value=min_value, gamma=gamma
        )
        for geometry in geometries:
            metric = properties.get(geometry.uuid)
            if metric is None:
                continue
            geometry.set_scalars(metric, lut, lut_range)

        self.legend.set_lookup_table(lut, self.property_combo.currentText())

        # Update filter widget — category checklist or histogram slider
        categorical = self._is_categorical(geometries)
        if categorical:
            raw_values = [
                self._cache.get_value(g.uuid)
                for g in geometries
                if self._cache.get_value(g.uuid) is not None
            ]
            all_labels = np.unique(
                np.concatenate([np.asarray(v).flatten() for v in raw_values])
            )
            self.category_filter_list.blockSignals(True)
            self.category_filter_list.clear()
            for label in all_labels:
                self.category_filter_list.addItem(str(label))
            self.category_filter_list.selectAll()
            self.category_filter_list.blockSignals(False)
            self.filter_stack.setCurrentWidget(self.category_filter_list)
            self.split_btn.show()
        else:
            all_values = np.concatenate([np.asarray(v).flatten() for v in values])
            self.filter_slider.setData(all_values)
            self.filter_stack.setCurrentWidget(self.filter_slider)
            self.split_btn.hide()

        if render:
            self.render()

    def _get_colormap(self) -> str:
        """Get the current colormap name, with inversion suffix if enabled."""
        colormap = self.colormap_combo.currentText()
        if self.invert_checkbox.isChecked():
            colormap += "_r"
        return colormap

    def render(self):
        try:
            self.cdata.data.blockSignals(True)
            self.cdata.models.blockSignals(True)

            self.cdata.data.render_vtk()
            self.cdata.models.render_vtk()
        finally:
            self.cdata.data.blockSignals(False)
            self.cdata.models.blockSignals(False)

    def _get_selected_categories(self):
        """Return the set of selected label strings from the category filter."""
        return {item.text() for item in self.category_filter_list.selectedItems()}

    def _on_filter_changed(self, lower, upper):
        """Hide points outside the filter range using transparent LUT colors."""
        from ..utils import cmap_to_vtkctf

        geometries = self._get_selected_geometries()
        if not geometries:
            return

        colormap = self._get_colormap()
        properties = self._get_transformed_properties(geometries)

        if self._is_categorical(geometries):
            checked = self._get_selected_categories()
            values = [x for x in properties.values() if x is not None]
            if not values:
                return
            max_code = np.nanmax([np.nanmax(x) for x in values])
            lut, lut_range = cmap_to_vtkctf(
                colormap, max_code, min_value=0.0, transparent_range=True
            )
            for geometry in geometries:
                raw = self._cache.get_value(geometry.uuid)
                coded = properties.get(geometry.uuid)
                if raw is None or coded is None:
                    continue
                raw_flat = np.asarray(raw).flatten()
                visible = np.array([str(v) in checked for v in raw_flat])
                display = np.where(visible, coded, -1.0)
                geometry.set_scalars(display, lut, lut_range)
        else:
            lut, lut_range = cmap_to_vtkctf(
                colormap, upper, min_value=lower, transparent_range=True
            )
            self.legend.set_lookup_table(lut, self.property_combo.currentText())
            for geometry in geometries:
                values = properties.get(geometry.uuid)
                if values is None:
                    continue
                values = np.asarray(values).flatten()
                geometry.set_scalars(values, lut, lut_range)

        self.render()

    def _on_filter_dragging(self, lower, upper):
        """Handle slider drag events with throttling for live preview."""
        if not self.filter_live_checkbox.isChecked():
            return
        self._filter_throttle(lower, upper)

    def _reset_filter(self):
        """Reset filter to show all points."""
        if self.filter_stack.currentWidget() is self.category_filter_list:
            self.category_filter_list.blockSignals(True)
            self.category_filter_list.selectAll()
            self.category_filter_list.blockSignals(False)
        else:
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
        geometries = self._get_selected_geometries()

        if not geometries:
            QMessageBox.warning(self, "No Selection", "Please select geometry first.")
            return

        categorical = self._is_categorical(geometries)

        dirty_interactors = set()
        for geometry in geometries:
            if categorical:
                raw = self._cache.get_value(geometry.uuid)
                if raw is None:
                    continue
                checked = self._get_selected_categories()
                raw_flat = np.asarray(raw).flatten()
                mask = np.array([str(v) in checked for v in raw_flat])
            else:
                lower, upper = self.filter_slider.getRange()
                properties = self._get_transformed_properties(geometries)
                values = properties.get(geometry.uuid)
                if values is None:
                    continue
                values = np.asarray(values).flatten()
                mask = (values >= lower) & (values <= upper)

            if not mask.any():
                continue

            subset = geometry[mask]
            if subset.get_number_of_points() > 0:
                interactor = self._interactor_for(geometry)
                interactor.add(subset)
                dirty_interactors.add(id(interactor))

        if dirty_interactors:
            if id(self.cdata.data) in dirty_interactors:
                self.cdata.data.render()
            if id(self.cdata.models) in dirty_interactors:
                self.cdata.models.render()
        else:
            QMessageBox.information(
                self, "No Points", "No points fall within the selected range."
            )

    def _split_by_category(self):
        """Split each selected geometry into one object per unique category."""
        geometries = self._get_selected_geometries()
        if not geometries:
            QMessageBox.warning(self, "No Selection", "Please select geometry first.")
            return

        if not self._is_categorical(geometries):
            return

        dirty_interactors = set()
        for geometry in geometries:
            raw = self._cache.get_value(geometry.uuid)
            if raw is None:
                continue

            raw_flat = np.asarray(raw).flatten()
            parent_name = geometry._meta.get("name", "Object")
            interactor = self._interactor_for(geometry)

            for label in np.unique(raw_flat):
                mask = raw_flat == label
                subset = geometry[mask]
                if subset.get_number_of_points() == 0:
                    continue
                subset._meta["name"] = f"{parent_name}_{label}"
                interactor.add(subset)
                dirty_interactors.add(id(interactor))

        if dirty_interactors:
            if id(self.cdata.data) in dirty_interactors:
                self.cdata.data.render()
            if id(self.cdata.models) in dirty_interactors:
                self.cdata.models.render()

    def _switch_tab(self, index):
        self._update_tab()

    def _update_tab(self):
        current_tab_index = self._tabs.currentIndex()

        self.plot_widget.clear()
        QTimer.singleShot(
            100,
            lambda: (
                self._update_plot()
                if current_tab_index == 1
                else self._update_statistics() if current_tab_index == 2 else None
            ),
        )

    def _set_stat_cell(self, row, col, text):
        """Set a read-only text cell in the statistics table."""
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self.stats_table.setItem(row, col, item)

    def _update_statistics(self):
        selected_items = self._get_selection()
        self.stats_table.setRowCount(len(selected_items))

        row_count, n_decimals = 0, 6
        for index, (item_text, obj) in enumerate(selected_items):
            value = self._cache.get_value(obj.uuid)
            if value is None:
                continue

            row_count += 1
            value = to_numeric(value)
            self._set_stat_cell(index, 0, item_text)
            self._set_stat_cell(index, 1, str(np.round(np.nanmin(value), n_decimals)))
            self._set_stat_cell(index, 2, str(np.round(np.nanmax(value), n_decimals)))
            self._set_stat_cell(index, 3, str(np.round(np.nanmean(value), n_decimals)))
            self._set_stat_cell(index, 4, str(np.round(np.nanstd(value), n_decimals)))
        self.stats_table.setRowCount(row_count)

    def _set_plot_type(self, plot_type):
        self.current_plot_type = plot_type
        self._update_plot_type_buttons()
        self._update_plot()

    def _update_plot_type_buttons(self):
        """Update plot type button icons and styling based on selection state."""
        for plot_type, (btn, icon_name) in self.plot_type_buttons.items():
            is_selected = plot_type == self.current_plot_type
            btn.setIcon(_icon(icon_name, role="primary" if is_selected else "muted"))

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
        if self._tabs.currentIndex() != 1:
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
                values = to_numeric(values)
                all_values.append(values)
                data_series.append((item_text, obj, values, colors[i % len(colors)]))

        if not data_series:
            return None

        try:
            self.plot_widget.setUpdatesEnabled(False)

            self.plot_widget.clear()
            all_scalar = np.asarray(all_values[0]).ndim == 0
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

    def _create_plot_item(
        self,
        plot_type,
        values,
        color,
        name=None,
        bins=None,
        x_range=None,
        offset=0,
        bar_width=None,
    ):
        """Create a single pyqtgraph item for the given plot type."""
        if plot_type == "Histogram":
            hist, edges = np.histogram(values, bins=bins)
            x = (edges[:-1] + edges[1:]) / 2
            width = bar_width if bar_width is not None else (edges[1] - edges[0]) * 0.8
            return pg.BarGraphItem(
                x=x + offset,
                height=hist,
                width=width,
                brush=color,
                pen=pg.mkPen("k", width=1),
                name=name,
            )
        elif plot_type == "Density":
            from scipy.stats import gaussian_kde

            kde = gaussian_kde(values)
            density = kde(x_range)
            return pg.PlotDataItem(
                x_range,
                density,
                pen=pg.mkPen(color, width=2),
                fillLevel=0,
                fillBrush=color,
                name=name,
            )
        else:
            x = np.arange(len(values))
            return pg.PlotDataItem(
                x,
                values,
                pen=pg.mkPen(color, width=2),
                name=name,
                symbol="o",
                symbolSize=5,
                symbolBrush=color,
            )

    def _create_plot(self, data_series, all_values, plot_mode, plot_type):
        """Create either histogram, density or line plot based on plot_type"""
        property_name = self.property_combo.currentText()

        bins, x_range = None, None
        if plot_type == "Histogram":
            all_data = np.concatenate(all_values)
            all_data = all_data[~np.isnan(all_data)]
            bins = np.histogram_bin_edges(all_data, bins="auto")
            y_label = "Frequency"
            x_label = property_name
        elif plot_type == "Density":
            all_data = np.concatenate(all_values)
            all_data = all_data[~np.isnan(all_data)]
            x_min, x_max = np.nanmin(all_data), np.nanmax(all_data)
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
            plot.setClipToView(True)
            plot.setDownsampling(auto=True, mode="peak")

            plot.disableAutoRange()
            plot.addLegend(offset=(-10, 10))

            # Compute per-series bar width for grouped histograms
            base_bar_width = None
            if plot_type == "Histogram" and len(data_series) > 1:
                _, edges = np.histogram(all_values[0], bins=bins)
                base_bar_width = (edges[1] - edges[0]) * 0.8 / len(data_series)

            for i, (name, obj, values, color) in enumerate(data_series):
                try:
                    bar_offset = 0
                    bar_width = None
                    if plot_type == "Histogram" and base_bar_width is not None:
                        bar_width = base_bar_width
                        bar_offset = (i - (len(data_series) - 1) / 2) * base_bar_width
                    item = self._create_plot_item(
                        plot_type,
                        values,
                        color,
                        name=name,
                        bins=bins,
                        x_range=x_range,
                        offset=bar_offset,
                        bar_width=bar_width,
                    )
                    plot.addItem(item)
                except Exception as e:
                    warnings.warn(f"Error creating plot for {name}: {e}")

            plot.enableAutoRange()
            plot.autoRange()
            return None

        # For separate plots mode
        for i, (name, obj, values, color) in enumerate(data_series):
            plot = self.plot_widget.addPlot(row=i // cols, col=i % cols)
            plot.setTitle(name)
            plot.setLabel("left", y_label)
            plot.setLabel("bottom", x_label)
            plot.setClipToView(True)
            plot.setDownsampling(auto=True, mode="peak")

            try:
                item = self._create_plot_item(
                    plot_type,
                    values,
                    color,
                    bins=bins,
                    x_range=x_range,
                )
                plot.addItem(item)
            except Exception as e:
                warnings.warn(f"Error creating plot for {name}: {e}")

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
            from ..properties import export_property_csv

            property_name = self.property_combo.currentText()
            geometries, values, sources = [], [], []
            for name, geom in selected_items:
                cached = self._cache.get_value(geom.uuid)
                if cached is not None:
                    geometries.append(geom)
                    values.append(cached)
                    sources.append(name)

            export_property_csv(file_path, property_name, geometries, values, sources)

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
