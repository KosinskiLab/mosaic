"""
Modulate visual properties of Geometry objects.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from os.path import exists

from qtpy.QtCore import Signal, Qt

from mosaic.geometry import BASE_COLOR
from mosaic.utils import Throttle
from qtpy.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QDialog,
    QPushButton,
    QFileDialog,
    QWidget,
    QLabel,
    QGroupBox,
)
from ..icons import icon
from ..widgets import (
    DialogFooter,
    create_setting_widget,
    get_widget_value,
    ColorPickerRow,
    SliderRow,
)
from ..widgets.segmented_control import SegmentedControl


def tuple_or_value(v):
    """Coerce scalars to a 3-tuple of themselves; pass tuples through."""
    if isinstance(v, (tuple, list)):
        return tuple(v)
    return (v, v, v)


class GeometryPropertiesDialog(QDialog):
    parametersChanged = Signal(dict)

    def __init__(self, initial_properties=None, parent=None, anchor=None):
        super().__init__(parent)
        self.setWindowTitle("Properties")
        self.setFixedWidth(400)
        self.parameters = {}
        self._anchor = anchor

        if initial_properties is None:
            property_list = [{}]
        elif isinstance(initial_properties, dict):
            property_list = [initial_properties]
        else:
            property_list = list(initial_properties) or [{}]

        self._property_list = property_list
        self.initial_properties = property_list[0]

        # Seed values for widgets default to the first geometry's values; the
        # mixed-field logic below decides whether they actually display as such.
        self.base_color = self.initial_properties.get("base_color", BASE_COLOR)
        self.highlight_color = self.initial_properties.get(
            "highlight_color", (0.8, 0.2, 0.2)
        )

        self._touched: set[str] = set()
        self._initially_unanimous: set[str] = set()
        self._indeterminate_widgets: set = set()

        self.volume_path = self.initial_properties.get("volume_path", None)
        if self._field_is_mixed("volume_path"):
            self.volume_path = None
        try:
            if not exists(self.volume_path):
                self.volume_path = None
        except Exception:
            pass

        self.setup_ui()
        self.connect_signals()
        self._apply_initial_mix_state()

    def _field_values(self, field: str):
        """Return the list of values for a field across input dicts."""
        import numpy as np

        sentinel = object()
        values = []
        for props in self._property_list:
            v = props.get(field, sentinel)
            if v is sentinel:
                continue
            if isinstance(v, np.ndarray):
                v = tuple(v.tolist())
            values.append(v)
        return values

    def _field_is_mixed(self, field: str) -> bool:
        values = self._field_values(field)
        if not values:
            return False
        first = values[0]
        return any(v != first for v in values[1:])

    def _apply_initial_mix_state(self) -> None:
        """Mark widgets indeterminate for fields with multiple values across
        the input dicts, and remember which fields were unanimous at open."""

        widget_map = {
            "opacity": self.opacity_slider,
            "ambient": self.ambient_slider,
            "diffuse": self.diffuse_slider,
            "specular": self.specular_slider,
            "base_color": self.base_color_picker,
            "highlight_color": self.highlight_color_picker,
            "isovalue_percentile": self.isovalue_slider,
        }
        for field, widget in widget_map.items():
            if self._field_is_mixed(field):
                widget.set_indeterminate()
            elif self._field_values(field):
                self._initially_unanimous.add(field)

        if self._field_is_mixed("size"):
            self.size_spin.setSpecialValueText(" ")
            self.size_spin.blockSignals(True)
            self.size_spin.setValue(self.size_spin.minimum())
            self.size_spin.blockSignals(False)
            self._indeterminate_widgets.add(self.size_spin)
        elif self._field_values("size"):
            self._initially_unanimous.add("size")

        axis_widgets = {
            "_sampling_x": self.sampling_x,
            "_sampling_y": self.sampling_y,
            "_sampling_z": self.sampling_z,
        }
        sampling_values = self._field_values("sampling_rate")
        for axis_idx, (key, widget) in enumerate(axis_widgets.items()):
            axis_vals = {tuple_or_value(v)[axis_idx] for v in sampling_values}
            if len(axis_vals) > 1:
                self._indeterminate_widgets.add(widget)
                widget.setText("")
            elif axis_vals:
                self._initially_unanimous.add(key)

        scale_values = self._field_values("volume_scale")
        if scale_values:
            signs = {-1 if v < 0 else 1 for v in scale_values}
            if len(signs) > 1:
                self.scale_control.set_indeterminate()
            else:
                self._initially_unanimous.add("scale")

    def _widget_is_indeterminate(self, widget) -> bool:
        """Indeterminate check that works for both widget-owned and dialog-tracked widgets."""
        if hasattr(widget, "is_indeterminate"):
            return widget.is_indeterminate()
        return widget in self._indeterminate_widgets

    def _panel_ancestor(self):
        """Return the object browser panel enclosing the anchor.

        The dialog aligns its top edge to this panel rather than the inner
        list, whose top sits below the panel's search box and section label.
        Falls back to the anchor itself when no sidebar ancestor exists.
        """
        from ..widgets import ObjectBrowserSidebar

        widget = self._anchor
        while widget is not None:
            if isinstance(widget, ObjectBrowserSidebar):
                return widget
            widget = widget.parentWidget()
        return self._anchor

    def showEvent(self, event):
        super().showEvent(event)
        self.setFocus(Qt.FocusReason.OtherFocusReason)

        if self._anchor is None or not self._anchor.isVisible():
            return

        right = self._anchor.mapToGlobal(self._anchor.rect().topRight()).x()
        panel = self._panel_ancestor()
        top = panel.mapToGlobal(panel.rect().topLeft()).y()

        screen_geo = self.screen().availableGeometry()
        x = max(
            screen_geo.left(),
            min(right + 10, screen_geo.right() - self.width()),
        )
        y = max(screen_geo.top(), min(top, screen_geo.bottom() - self.height()))
        self.move(x, y)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)

        appearance_group = QGroupBox("Appearance")
        appearance_layout = QVBoxLayout(appearance_group)
        appearance_layout.setSpacing(12)

        point_size_row = QWidget()
        point_size_layout = QHBoxLayout(point_size_row)
        point_size_layout.setContentsMargins(0, 0, 0, 0)
        point_size_layout.setSpacing(12)

        point_size_label = QLabel("Point Size")
        point_size_layout.addWidget(point_size_label)
        point_size_layout.addStretch()

        self.size_spin = create_setting_widget(
            {
                "type": "number",
                "min": 0,
                "max": 50,
                "default": self.initial_properties.get("size", 8),
            }
        )
        self.size_spin.setFixedWidth(80)
        self.size_spin.setToolTip("Size of points in the representation")
        point_size_layout.addWidget(self.size_spin)

        appearance_layout.addWidget(point_size_row)

        self.opacity_slider = SliderRow(
            "Opacity",
            min_val=0.0,
            max_val=1.0,
            default=self.initial_properties.get("opacity", 0.3),
            decimals=2,
        )
        self.opacity_slider.setToolTip(
            "Transparency of the geometry (0 = invisible, 1 = solid)"
        )
        appearance_layout.addWidget(self.opacity_slider)

        self.base_color_picker = ColorPickerRow("Base Color", self.base_color)
        self.base_color_picker.setToolTip("Default color for the geometry")
        appearance_layout.addWidget(self.base_color_picker)

        self.highlight_color_picker = ColorPickerRow(
            "Highlight Color", self.highlight_color
        )
        self.highlight_color_picker.setToolTip("Color when geometry is selected")
        appearance_layout.addWidget(self.highlight_color_picker)

        main_layout.addWidget(appearance_group)

        lighting_group = QGroupBox("Lighting")
        lighting_layout = QVBoxLayout(lighting_group)
        lighting_layout.setSpacing(12)

        self.ambient_slider = SliderRow(
            "Ambient",
            min_val=0.0,
            max_val=1.0,
            default=self.initial_properties.get("ambient", 0.3),
            decimals=2,
        )
        self.ambient_slider.setToolTip(
            "Base illumination independent of light direction"
        )
        lighting_layout.addWidget(self.ambient_slider)

        self.diffuse_slider = SliderRow(
            "Diffuse",
            min_val=0.0,
            max_val=1.0,
            default=self.initial_properties.get("diffuse", 0.3),
            decimals=2,
        )
        self.diffuse_slider.setToolTip(
            "Scattered light reflection for a matte appearance"
        )
        lighting_layout.addWidget(self.diffuse_slider)

        self.specular_slider = SliderRow(
            "Specular",
            min_val=0.0,
            max_val=1.0,
            default=self.initial_properties.get("specular", 0.3),
            decimals=2,
        )
        self.specular_slider.setToolTip("Sharp highlights for a shiny appearance")
        lighting_layout.addWidget(self.specular_slider)

        main_layout.addWidget(lighting_group)

        model_group = QGroupBox("Model")
        model_layout = QVBoxLayout(model_group)
        model_layout.setSpacing(12)

        browse_row = QWidget()
        browse_layout = QHBoxLayout(browse_row)
        browse_layout.setContentsMargins(0, 0, 0, 0)
        browse_layout.setSpacing(8)

        browse_label = QLabel("Map File")
        browse_label.setToolTip("Density map in MRC or CCP4 format")
        browse_layout.addWidget(browse_label)
        browse_layout.addStretch()

        self.browse_button = QPushButton("Browse...")
        self.browse_button.setIcon(icon("ph.folder-open"))
        self.browse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_button.setToolTip("Select a density map file")
        self.browse_button.clicked.connect(self.browse_volume)
        browse_layout.addWidget(self.browse_button)

        self.attach_button = QPushButton("Reattach")
        self.attach_button.setIcon(icon("ph.link"))
        self.attach_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.attach_button.setEnabled(self.volume_path is not None)
        self.attach_button.setToolTip("Recompute isosurface from the density map")
        browse_layout.addWidget(self.attach_button)

        model_layout.addWidget(browse_row)

        scale_row = QWidget()
        scale_layout = QHBoxLayout(scale_row)
        scale_layout.setContentsMargins(0, 0, 0, 0)
        scale_layout.setSpacing(12)

        scale_label = QLabel("Scale")
        scale_layout.addWidget(scale_label)
        scale_layout.addStretch()

        default_idx = 1 if self.initial_properties.get("volume_scale", 0) < 0 else 0
        self.scale_control = SegmentedControl(["Native", "Invert"], default=default_idx)
        self.scale_control.setToolTip("Keep original density contrast or invert it")
        self.scale_control.setEnabled(self.volume_path is not None)
        scale_layout.addWidget(self.scale_control)

        model_layout.addWidget(scale_row)

        self.isovalue_slider = SliderRow(
            "Isovalue",
            min_val=0.0,
            max_val=100.0,
            default=self.initial_properties.get("isovalue_percentile", 99.5),
            decimals=1,
            suffix="%",
            steps=1000,
            exponent=2.0,
        )
        self.isovalue_slider.setToolTip(
            "Density threshold percentile for isosurface extraction"
        )
        self.isovalue_slider.setEnabled(self.volume_path is not None)
        model_layout.addWidget(self.isovalue_slider)

        main_layout.addWidget(model_group)

        sampling_group = QGroupBox("Sampling")
        sampling_rate = self.initial_properties.get("sampling_rate", (1.0, 1.0, 1.0))

        sampling_layout = QHBoxLayout(sampling_group)
        sampling_layout.setSpacing(8)

        base = {"type": "text", "min": 0}

        sampling_tooltip = "Voxel size in Ångström for this axis"

        min_width = 50
        sampling_layout.addWidget(QLabel("X"))
        self.sampling_x = create_setting_widget(base | {"default": sampling_rate[0]})
        self.sampling_x.setMinimumWidth(min_width)
        self.sampling_x.setToolTip(sampling_tooltip)
        sampling_layout.addWidget(self.sampling_x)

        sampling_layout.addWidget(QLabel("Y"))
        self.sampling_y = create_setting_widget(base | {"default": sampling_rate[1]})
        self.sampling_y.setMinimumWidth(min_width)
        self.sampling_y.setToolTip(sampling_tooltip)
        sampling_layout.addWidget(self.sampling_y)

        sampling_layout.addWidget(QLabel("Z"))
        self.sampling_z = create_setting_widget(base | {"default": sampling_rate[2]})
        self.sampling_z.setMinimumWidth(min_width)
        self.sampling_z.setToolTip(sampling_tooltip)
        sampling_layout.addWidget(self.sampling_z)

        main_layout.addWidget(sampling_group)

        footer = DialogFooter(dialog=self, margin=(0, 0, 0, 0))

        self.reset_button = QPushButton("Reset")
        self.reset_button.setIcon(icon("ph.arrow-counter-clockwise"))
        self.reset_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_button.clicked.connect(self._reset_to_defaults)
        footer.layout().insertWidget(0, self.reset_button)
        footer.layout().insertStretch(1)

        main_layout.addWidget(footer)

    def connect_signals(self):
        """Connect all widget signals to update parameters."""
        self._emit_throttle = Throttle(
            lambda *args: self.emit_parameters(), interval_ms=150
        )

        def mark_and_throttle(field):
            return lambda *_: (self._touched.add(field), self._emit_throttle())

        def mark_and_emit(field):
            return lambda *_: (self._touched.add(field), self.emit_parameters())

        self.size_spin.valueChanged.connect(self._on_size_changed)
        self.opacity_slider.valueChanged.connect(mark_and_throttle("opacity"))
        self.ambient_slider.valueChanged.connect(mark_and_throttle("ambient"))
        self.diffuse_slider.valueChanged.connect(mark_and_throttle("diffuse"))
        self.specular_slider.valueChanged.connect(mark_and_throttle("specular"))
        self.isovalue_slider.valueChanged.connect(
            mark_and_throttle("isovalue_percentile")
        )
        self.scale_control.selectionChanged.connect(self._on_scale_changed)
        self.sampling_x.textChanged.connect(self._on_sampling_x_changed)
        self.sampling_y.textChanged.connect(self._on_sampling_y_changed)
        self.sampling_z.textChanged.connect(self._on_sampling_z_changed)
        self.base_color_picker.colorChanged.connect(mark_and_emit("base_color"))
        self.highlight_color_picker.colorChanged.connect(
            mark_and_emit("highlight_color")
        )

        self.attach_button.clicked.connect(self.reattach_emit)

    def _on_size_changed(self, _value):
        if self.size_spin in self._indeterminate_widgets:
            self._indeterminate_widgets.discard(self.size_spin)
            self.size_spin.setSpecialValueText("")
        self._touched.add("size")
        self._emit_throttle()

    def _on_scale_changed(self, _value):
        # A scale toggle requires reloading the volume so the data is actually
        # re-multiplied; bare appearance updates ignore `scale`.
        self._touched.add("scale")
        parameters = self.get_parameters()
        if self.volume_path is not None:
            parameters["volume_path"] = self.volume_path
        self.parametersChanged.emit(parameters)

    def _on_sampling_changed(self, widget, axis_key: str):
        if widget in self._indeterminate_widgets:
            # Programmatic clears send empty text; only the user typing a value
            # should clear the indeterminate state.
            if widget.text() == "":
                return None
            self._indeterminate_widgets.discard(widget)
            widget.setPlaceholderText("")
        self._touched.add(axis_key)
        self._emit_throttle()

    def _on_sampling_x_changed(self, _text):
        self._on_sampling_changed(self.sampling_x, "_sampling_x")

    def _on_sampling_y_changed(self, _text):
        self._on_sampling_changed(self.sampling_y, "_sampling_y")

    def _on_sampling_z_changed(self, _text):
        self._on_sampling_changed(self.sampling_z, "_sampling_z")

    def reattach_emit(self):
        parameters = self.get_parameters()
        if self.volume_path is not None:
            parameters["volume_path"] = self.volume_path
            parameters["reattach_volume"] = True
            parameters["scale"] = (
                -1 if self.scale_control.currentText() == "Invert" else 1
            )
        self.parametersChanged.emit(parameters)

    def emit_parameters(self):
        parameters = self.get_parameters()
        self.parametersChanged.emit(parameters)

    def _reset_to_defaults(self):
        """Reset every widget to its factory default and broadcast to all selected geometries."""
        self.size_spin.setValue(8)
        self.opacity_slider.setValue(1.0)
        self.ambient_slider.setValue(0.3)
        self.diffuse_slider.setValue(0.7)
        self.specular_slider.setValue(0.2)
        self.base_color_picker.set_color(BASE_COLOR)
        self.highlight_color_picker.set_color((0.8, 0.2, 0.2))
        self.isovalue_slider.setValue(99.5)
        self.sampling_x.setText("1.0")
        self.sampling_y.setText("1.0")
        self.sampling_z.setText("1.0")

        self._indeterminate_widgets.clear()
        self.size_spin.setSpecialValueText("")
        self.sampling_x.setPlaceholderText("")
        self.sampling_y.setPlaceholderText("")
        self.sampling_z.setPlaceholderText("")

        self._touched.update(
            {
                "size",
                "opacity",
                "ambient",
                "diffuse",
                "specular",
                "base_color",
                "highlight_color",
                "isovalue_percentile",
                "_sampling_x",
                "_sampling_y",
                "_sampling_z",
            }
        )

        self.emit_parameters()

    def browse_volume(self):
        from ..formats.parser import load_density

        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select Volume File", "", "MRC Files (*.mrc);;All Files (*.*)"
        )
        if not file_name:
            return

        self.volume_path = file_name
        volume = load_density(self.volume_path)

        self.scale_control.setEnabled(True)
        self.isovalue_slider.setEnabled(True)
        self.attach_button.setEnabled(True)

        non_negative = (volume.data > 0).sum()
        invert = non_negative < volume.data.size // 2
        self.scale_control._select(1 if invert else 0)
        self._touched.add("scale")

        parameters = self.get_parameters()
        parameters["volume_path"] = self.volume_path
        parameters["scale"] = -1 if invert else 1
        self.parametersChanged.emit(parameters)

    def get_parameters(self) -> dict:
        """
        Return the partial parameter dict for the current dialog state.

        A field is included only if its widget is determinate and the field
        was either touched by the user or unanimous across selected
        geometries at dialog open.
        """
        out: dict = {}

        def include(field, widget, getter):
            if self._widget_is_indeterminate(widget):
                return
            if field not in self._touched and field not in self._initially_unanimous:
                return
            out[field] = getter()

        include("size", self.size_spin, lambda: get_widget_value(self.size_spin))
        include("opacity", self.opacity_slider, self.opacity_slider.value)
        include("ambient", self.ambient_slider, self.ambient_slider.value)
        include("diffuse", self.diffuse_slider, self.diffuse_slider.value)
        include("specular", self.specular_slider, self.specular_slider.value)
        include("base_color", self.base_color_picker, self.base_color_picker.get_color)
        include(
            "highlight_color",
            self.highlight_color_picker,
            self.highlight_color_picker.get_color,
        )
        include("isovalue_percentile", self.isovalue_slider, self.isovalue_slider.value)

        include(
            "scale",
            self.scale_control,
            lambda: -1 if self.scale_control.currentText() == "Invert" else 1,
        )

        axes = [
            ("_sampling_x", self.sampling_x),
            ("_sampling_y", self.sampling_y),
            ("_sampling_z", self.sampling_z),
        ]
        sampling_values = [get_widget_value(w) for _, w in axes]
        if (
            all(not self._widget_is_indeterminate(w) for _, w in axes)
            and all(v is not None for v in sampling_values)
            and any(
                k in self._touched or k in self._initially_unanimous for k, _ in axes
            )
        ):
            out["sampling_rate"] = tuple(float(v) for v in sampling_values)

        return out
