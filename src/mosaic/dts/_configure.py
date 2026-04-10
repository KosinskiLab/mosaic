"""
Configure tab widget for DTS parameter screening dialog.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from pathlib import Path
from typing import Dict, List

import numpy as np
from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QCheckBox,
    QPushButton,
    QFormLayout,
    QWidget,
    QMessageBox,
    QGroupBox,
    QScrollArea,
    QLineEdit,
    QPlainTextEdit,
    QStackedWidget,
    QFileDialog,
)
import pyqtgraph as pg
import qtawesome as qta

from ..widgets import PathSelector, generate_gradient_colors
from ..widgets.settings import create_setting_widget, get_widget_value, set_widget_value
from ..stylesheets import Colors

from ._utils import (
    COUPLING_DEFS as _COUPLING_DEFS,
    parse_screening_ranges,
    parse_dts_content,
)


_EXTRA_CONFIG_PLACEHOLDER = (
    "# Fixed:   Kappa = 25.0 0 0\n"
    "# Screen:  Kappa = {{kappa:25.0:35.0:5.0}} 0 0\n"
    "# List:    Set_Steps = 1 {{steps:1000,5000}}"
)


class ConfigurePanel(QScrollArea):
    """Configure tab: parameter groups with screening toggle + preview plot.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget.
    """

    screenGenerated = Signal(str)
    """Emitted with the output directory path after a screen is generated."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._param_widgets = {}
        self._screen_cbs = {}
        self._screen_ranges = {}
        self._screen_stacks = {}
        self._coupling_widgets = {}

        self._preview_items = []
        self._preview_visible = False

        self._build_ui()

    def _build_ui(self):
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("scrollContentWidget")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(self._build_input_group())
        layout.addWidget(self._build_simulation_group())
        layout.addWidget(self._build_physics_group())
        layout.addWidget(self._build_hmff_group())
        layout.addWidget(self._build_extra_group())
        layout.addStretch()
        layout.addLayout(self._build_footer())

        self.setWidget(content)

    def _build_input_group(self):
        group = QGroupBox("Input")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._mesh_path = PathSelector(
            placeholder="Input mesh (.tsi, .q)",
            file_filter="TSI Files (*.tsi) Q Files (*.q);;All Files (*.*)",
        )
        form.addRow("Mesh:", self._mesh_path)

        self._output_dir = PathSelector(
            placeholder="Output directory", mode="directory"
        )
        form.addRow("Output:", self._output_dir)

        self._dts_file = PathSelector(
            placeholder="(Optional) populate from dts config",
            file_filter="DTS Files (*.dts);;All Files (*.*)",
        )
        self._dts_file.path_input.textChanged.connect(self._load_dts_file)
        form.addRow("DTS:", self._dts_file)

        return group

    def _build_simulation_group(self):
        group = QGroupBox("Simulation")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._add_screenable_row(
            form, key="temperature", label="Temperature", default=1.0
        )

        self._param_widgets["edge_range"] = QLineEdit("1 - 5")
        self._param_widgets["edge_range"].setPlaceholderText("min - max")
        self._param_widgets["edge_range"].setToolTip(
            "Min and max edge lengths for mesh refinement (format: min - max)"
        )
        form.addRow("Edge length:", self._param_widgets["edge_range"])

        for key, label, cfg in (
            (
                "steps",
                "Steps:",
                {"type": "number", "min": 0, "max": 1000000000, "default": 150000},
            ),
            (
                "output_period",
                "Output period:",
                {"type": "number", "min": 1, "max": 1000000, "default": 1000},
            ),
            (
                "threads",
                "Threads:",
                {"type": "number", "min": 1, "max": 128, "default": 1},
            ),
        ):
            self._param_widgets[key] = create_setting_widget(cfg)
            form.addRow(label, self._param_widgets[key])

        return group

    def _build_physics_group(self):
        group = QGroupBox("Physical Parameters")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._add_screenable_row(
            form, key="kappa", label="Rigidity (\u03ba)", default=25.0
        )
        self._add_screenable_row(
            form,
            key="kappa0",
            label="Spont. curvature (\u03ba\u2080)",
            default=0.0,
        )
        for coupling_key, coupling_def in _COUPLING_DEFS.items():
            self._add_coupling_section(form, coupling_key, coupling_def)

        return group

    def _build_hmff_group(self):
        group = QGroupBox("HMFF Parameters")
        self._hmff_form = QFormLayout(group)
        self._hmff_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        vol_row = QWidget()
        vol_layout = QHBoxLayout(vol_row)
        vol_layout.setContentsMargins(0, 0, 0, 0)
        vol_layout.setSpacing(6)

        self._volume_path = PathSelector(
            placeholder="Volume file (.mrc)",
            file_filter="MRC Files (*.mrc);;All Files (*.*)",
        )
        self._volume_path.path_input.textChanged.connect(self._on_volume_changed)
        vol_layout.addWidget(self._volume_path)

        self._volume_screen_cb = QCheckBox("Screen")
        self._volume_screen_cb.setToolTip(
            "Enable screening: select multiple volume files"
        )
        self._volume_screen_cb.stateChanged.connect(self._toggle_volume_screening)
        vol_layout.addWidget(self._volume_screen_cb)

        self._hmff_form.addRow("Volume:", vol_row)

        self._add_screenable_row(
            self._hmff_form, key="xi", label="Coupling (\u03be)", default=5.0
        )
        for w in (self._screen_stacks["xi"], self._screen_cbs["xi"]):
            w.setEnabled(False)

        self._hmff_dep_widgets = []
        self._filter_dep_widgets = []

        self._param_widgets["invert_contrast"] = create_setting_widget(
            {"type": "boolean", "default": True}
        )
        self._hmff_form.addRow(
            "Invert contrast:", self._param_widgets["invert_contrast"]
        )
        self._hmff_dep_widgets.append(self._param_widgets["invert_contrast"])

        self._param_widgets["scale_factor"] = create_setting_widget(
            {
                "type": "float",
                "min": 0.0,
                "max": 1e6,
                "default": 1.0,
                "step": 0.01,
                "decimals": 6,
            }
        )
        self._param_widgets["scale_factor"].setToolTip(
            "Converts mesh coordinates to DTS units (nm)."
        )
        self._hmff_form.addRow("Scale factor:", self._param_widgets["scale_factor"])
        self._hmff_dep_widgets.append(self._param_widgets["scale_factor"])

        self._param_widgets["offset"] = QLineEdit("0,0,0")
        self._param_widgets["offset"].setPlaceholderText("x,y,z")
        self._param_widgets["offset"].setToolTip(
            "Translation to center the scaled mesh\n"
            "in the simulation box in DTS units (nm)."
        )
        self._hmff_form.addRow("Offset:", self._param_widgets["offset"])
        self._hmff_dep_widgets.append(self._param_widgets["offset"])

        self._param_widgets["use_filters"] = create_setting_widget(
            {"type": "boolean", "default": False}
        )
        self._param_widgets["use_filters"].stateChanged.connect(
            self._toggle_filter_inputs
        )
        self._hmff_form.addRow("Enable Filters:", self._param_widgets["use_filters"])
        self._hmff_dep_widgets.append(self._param_widgets["use_filters"])

        for param_key, label, cfg in (
            (
                "lowpass_cutoff",
                "Lowpass:",
                {
                    "type": "float",
                    "min": 0.0,
                    "max": 10000.0,
                    "default": 140.0,
                    "step": 1.0,
                },
            ),
            (
                "highpass_cutoff",
                "Highpass:",
                {
                    "type": "float",
                    "min": 0.0,
                    "max": 10000.0,
                    "default": 900.0,
                    "step": 1.0,
                },
            ),
            (
                "plane_norm",
                "Normalize axis:",
                {"type": "select", "options": ["", "x", "y", "z"], "default": ""},
            ),
        ):
            self._param_widgets[param_key] = create_setting_widget(cfg)
            self._hmff_form.addRow(label, self._param_widgets[param_key])
            self._hmff_dep_widgets.append(self._param_widgets[param_key])
            self._filter_dep_widgets.append(self._param_widgets[param_key])

        self._set_hmff_volume_visible(False)
        return group

    def _build_extra_group(self):
        group = QGroupBox("Extra Parameters")
        layout = QVBoxLayout(group)
        self._extra_config_edit = QPlainTextEdit()
        self._extra_config_edit.setPlaceholderText(_EXTRA_CONFIG_PLACEHOLDER)
        self._extra_config_edit.setMinimumHeight(80)
        self._extra_config_edit.setMaximumHeight(140)
        self._extra_config_edit.setStyleSheet("QPlainTextEdit { font-size: 12px; }")
        self._extra_config_edit.textChanged.connect(self._update_combo_summary)
        layout.addWidget(self._extra_config_edit)
        return group

    def _build_footer(self):
        import shutil

        info_row = QHBoxLayout()
        dts_path = shutil.which("dts") or shutil.which("DTS")
        dts_info = QLabel(
            f"DTS binary: {dts_path}" if dts_path else "DTS binary not found in PATH"
        )
        dts_info.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
        info_row.addWidget(dts_info)

        self._combo_summary = QLabel("")
        self._combo_summary.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 11px;"
        )
        info_row.addStretch()
        info_row.addWidget(self._combo_summary)

        outer = QVBoxLayout()
        outer.addLayout(info_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._generate_btn = QPushButton("Setup")
        self._generate_btn.setIcon(qta.icon("ph.play", color=Colors.PRIMARY))
        self._generate_btn.clicked.connect(self._run_screen)
        btn_row.addWidget(self._generate_btn)

        self._save_dts_btn = QPushButton()
        self._save_dts_btn.setIcon(qta.icon("ph.floppy-disk", color=Colors.ICON))
        self._save_dts_btn.setFixedSize(28, 28)
        self._save_dts_btn.setToolTip("Save screen input.dts only")
        self._save_dts_btn.clicked.connect(self._save_dts)
        btn_row.addWidget(self._save_dts_btn)

        outer.addLayout(btn_row)
        return outer

    def set_preview_widgets(self, plot_widget, plot_item, placeholder):
        """Receive preview plot widgets owned by the parent dialog."""
        self._preview_plot = plot_widget
        self._preview_plot_item = plot_item
        self._preview_placeholder = placeholder

    def _add_screenable_row(self, form, key, label, default=0.0, step=0.1):
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        fixed_w = create_setting_widget(
            {"type": "float", "min": 0.0, "max": 1e6, "default": default, "step": step}
        )
        fixed_w.setMinimumWidth(90)
        self._param_widgets[key] = fixed_w

        range_input = QLineEdit()
        range_input.setPlaceholderText("start:end:step  or  v1,v2,v3")
        range_input.textChanged.connect(self._update_combo_summary)
        self._screen_ranges[key] = range_input

        stack = QStackedWidget()
        stack.addWidget(fixed_w)
        stack.addWidget(range_input)
        stack.setCurrentIndex(0)
        self._screen_stacks[key] = stack
        row_layout.addWidget(stack)

        screen_cb = QCheckBox("Screen")
        screen_cb.setToolTip(f"Enable screening for {label}")
        self._screen_cbs[key] = screen_cb
        row_layout.addWidget(screen_cb)

        screen_cb.stateChanged.connect(
            lambda state, k=key: self._toggle_screen_param(k, state)
        )

        form.addRow(f"{label}:", row)

    def _add_coupling_section(self, parent_form, coupling_key, coupling_def):
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        cb = QCheckBox()
        cb.setToolTip(f"Enable {coupling_def['label']}")
        header_layout.addWidget(cb)

        mode_combo = QComboBox()
        mode_combo.addItems(list(coupling_def["modes"].keys()))
        mode_combo.setEnabled(False)
        header_layout.addWidget(mode_combo)

        parent_form.addRow(f"{coupling_def['label']}:", header)

        mode_stack = QStackedWidget()
        mode_param_keys = {}

        for mode_name, params in coupling_def["modes"].items():
            page = QWidget()
            page_form = QFormLayout(page)
            page_form.setContentsMargins(50, 2, 0, 2)
            page_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

            keys = []
            for param_name, label, default, step in params:
                full_key = f"{coupling_key}__{param_name}"
                self._add_screenable_row(page_form, full_key, label, default, step)
                keys.append(full_key)

            mode_param_keys[mode_name] = keys
            mode_stack.addWidget(page)

        parent_form.addRow(mode_stack)
        mode_stack.setVisible(False)

        def _on_checkbox(state, mc=mode_combo, mpk=mode_param_keys):
            enabled = bool(state)
            mc.setEnabled(enabled)
            mode_stack.setVisible(enabled)
            if not enabled:
                for keys in mpk.values():
                    for k in keys:
                        if k in self._screen_cbs:
                            self._screen_cbs[k].setChecked(False)
            self._update_combo_summary()

        cb.stateChanged.connect(_on_checkbox)

        def _on_mode_switch(idx, mpk=mode_param_keys):
            mode_stack.setCurrentIndex(idx)
            for mode, keys in mpk.items():
                if mode != mode_combo.currentText():
                    for k in keys:
                        if k in self._screen_cbs:
                            self._screen_cbs[k].setChecked(False)
            self._update_combo_summary()

        mode_combo.currentIndexChanged.connect(_on_mode_switch)

        self._coupling_widgets[coupling_key] = {
            "checkbox": cb,
            "mode_combo": mode_combo,
            "mode_param_keys": mode_param_keys,
        }

    def _set_hmff_volume_visible(self, visible):
        """Show/hide HMFF volume-dependent form rows."""
        for widget in self._hmff_dep_widgets:
            widget.setVisible(visible)
            label = self._hmff_form.labelForField(widget)
            if label is not None:
                label.setVisible(visible)
        if visible:
            self._toggle_filter_inputs(
                self._param_widgets["use_filters"].checkState().value
            )

    def _reset_fields(self):
        """Reset all dialog fields to their defaults."""
        for widget in self._param_widgets.values():
            widget.blockSignals(True)
            if isinstance(widget, QCheckBox):
                widget.setChecked(False)
            elif isinstance(widget, QLineEdit):
                widget.clear()
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(0)
            elif hasattr(widget, "setValue"):
                widget.setValue(widget.minimum())
            widget.blockSignals(False)

        self._volume_screen_cb.blockSignals(True)
        self._volume_screen_cb.setChecked(False)
        self._volume_screen_cb.blockSignals(False)
        self._volume_path.set_path("")

        for cb in self._screen_cbs.values():
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        for rng in self._screen_ranges.values():
            rng.blockSignals(True)
            rng.clear()
            rng.blockSignals(False)

        for widgets in self._coupling_widgets.values():
            widgets["checkbox"].blockSignals(True)
            widgets["checkbox"].setChecked(False)
            widgets["checkbox"].blockSignals(False)

        self._extra_config_edit.clear()
        self._set_hmff_volume_visible(False)

    def _load_dts_file(self, path: str):
        """Parse an existing DTS file and populate dialog fields."""
        if not path or not Path(path).exists():
            return

        self._reset_fields()

        content = Path(path).read_text(encoding="utf-8")
        known, extra_lines = parse_dts_content(content)

        filter_params = known.pop("_filters", {})
        if filter_params:
            set_widget_value(self._param_widgets["use_filters"], True)
            for full_key, val in filter_params.items():
                if full_key in self._param_widgets:
                    set_widget_value(self._param_widgets[full_key], val)

        for key in ("temperature", "kappa", "kappa0", "xi"):
            if key in known:
                set_widget_value(self._param_widgets[key], float(known[key]))

        for key in ("steps", "output_period"):
            if key in known:
                set_widget_value(self._param_widgets[key], int(known[key]))

        if "min_edge" in known and "max_edge" in known:
            self._param_widgets["edge_range"].setText(
                f"{known['min_edge']} - {known['max_edge']}"
            )

        if "threads" in known:
            set_widget_value(self._param_widgets["threads"], known["threads"])

        if "volume_path" in known:
            vol = known["volume_path"]
            self._volume_screen_cb.blockSignals(True)
            if isinstance(vol, list):
                self._volume_screen_cb.setChecked(True)
                self._volume_path.set_mode("files")
            self._volume_screen_cb.blockSignals(False)
            self._volume_path.set_path(vol)
        if "invert_contrast" in known:
            set_widget_value(
                self._param_widgets["invert_contrast"], known["invert_contrast"]
            )
        if "scale_factor" in known:
            set_widget_value(
                self._param_widgets["scale_factor"], float(known["scale_factor"])
            )
        if "offset" in known:
            self._param_widgets["offset"].setText(str(known["offset"]))

        for coupling_key in ("vol_coupling", "curv_coupling", "area_coupling"):
            if coupling_key not in known:
                continue
            cfg = known[coupling_key]
            widgets = self._coupling_widgets[coupling_key]
            widgets["checkbox"].setChecked(True)
            widgets["mode_combo"].setCurrentText(cfg["mode"])
            mode_keys = widgets["mode_param_keys"].get(cfg["mode"], [])
            for i, key in enumerate(mode_keys):
                if i < len(cfg["values"]):
                    try:
                        set_widget_value(
                            self._param_widgets[key], float(cfg["values"][i])
                        )
                    except (ValueError, KeyError):
                        pass

        if extra_lines:
            self._extra_config_edit.setPlainText("\n".join(extra_lines))

        # Restore screening checkboxes and range inputs
        screen_info = known.get("_screen", {})
        for key, range_str in screen_info.items():
            if key in self._screen_cbs:
                self._screen_cbs[key].setChecked(True)
                self._screen_ranges[key].setText(range_str)

    def _toggle_screen_param(self, key: str, state: int):
        screening = bool(state)
        self._screen_stacks[key].setCurrentIndex(1 if screening else 0)
        self._update_combo_summary()

    def _toggle_volume_screening(self, state: int):
        screening = bool(state)
        if screening:
            self._volume_path.set_mode("files")
            self._volume_path.path_input.setPlaceholderText("Volume files (.mrc)")
        else:
            self._volume_path.set_mode("file")
            self._volume_path.path_input.setPlaceholderText("Volume file (.mrc)")
        self._on_volume_changed("")

    def _get_volume_state(self):
        """Return (volume, use_hmff) from the current volume path widget."""
        volume_value = get_widget_value(self._volume_path)
        if isinstance(volume_value, list):
            volumes = [v for v in volume_value if v]
            volume = volumes if len(volumes) > 1 else (volumes[0] if volumes else "")
        else:
            volume = str(volume_value or "")
        return volume, bool(volume)

    def _on_volume_changed(self, _text: str):
        has_volume = bool(self._volume_path.get_path())
        for w in (self._screen_stacks["xi"], self._screen_cbs["xi"]):
            w.setEnabled(has_volume)
        self._set_hmff_volume_visible(has_volume)
        if not has_volume:
            self._param_widgets["use_filters"].setChecked(False)
        self._update_combo_summary()

    def _toggle_filter_inputs(self, state):
        show = state == Qt.CheckState.Checked.value
        for widget in self._filter_dep_widgets:
            widget.setVisible(show)
            label = self._hmff_form.labelForField(widget)
            if label is not None:
                label.setVisible(show)

    def _get_screen_params(self) -> Dict[str, str]:
        params = {}
        for key, cb in self._screen_cbs.items():
            if cb.isChecked():
                text = self._screen_ranges[key].text().strip()
                if text:
                    params[key] = text
        return params

    def _get_all_screened_values(self) -> Dict[str, List]:
        result = {}
        for key, range_str in self._get_screen_params().items():
            try:
                from pyfreedts.screen import ParameterParser

                _, parsed = ParameterParser.parse_template(
                    "{{" + f"p:{range_str}" + "}}"
                )
                result[key] = parsed.get("p", [])
            except Exception:
                pass

        extra_text = self._extra_config_edit.toPlainText()
        if extra_text:
            result.update(parse_screening_ranges(extra_text))

        volumes = self._volume_path.get_path()
        if isinstance(volumes, list) and len(volumes) > 1:
            result["volume_path"] = list(volumes)

        return result

    def _update_combo_summary(self, *_args):
        screened = self._get_all_screened_values()
        if not screened:
            self._combo_summary.setText("")
            self.update_preview_plot()
            return

        total = 1
        for values in screened.values():
            total *= max(len(values), 1)

        self._combo_summary.setText(f"{total} combination{'s' if total != 1 else ''}")
        self.update_preview_plot()

    def get_mesh_transform(self):
        """Return (scale_factor, offset) from the scaling parameters."""
        try:
            scale_factor = float(get_widget_value(self._param_widgets["scale_factor"]))
            offset_str = self._param_widgets["offset"].text().strip()
            offset = np.array([float(x) for x in offset_str.split(",")])
        except (ValueError, IndexError):
            scale_factor = 1.0
            offset = np.array([0.0, 0.0, 0.0])

        return scale_factor, offset

    def update_preview_plot(self, *_args):
        """Redraw the parameter-space preview scatter plot."""
        screened = self._get_all_screened_values()
        param_names = sorted(screened.keys())
        has_params = bool(param_names)

        if has_params != self._preview_visible:
            self._preview_visible = has_params
            self._preview_placeholder.setVisible(not has_params)
            self._preview_plot.setVisible(has_params)

        plot = self._preview_plot_item
        for item in self._preview_items:
            plot.removeItem(item)
        self._preview_items.clear()

        if not has_params:
            return

        n_params = len(param_names)
        colors = generate_gradient_colors("Set2", max(n_params, 2))
        max_labels = 5

        _SHORT_NAMES = {
            "temperature": "T",
            "kappa": "\u03ba",
            "kappa0": "\u03ba\u2080",
            "xi": "\u03be",
            "output_period": "out\u2009period",
            "delta_p": "\u0394p",
            "target_v": "V\u2080",
            "C_g0": "C\u2080",
        }

        def _short(key):
            if "__" in key:
                key = key.rsplit("__", 1)[-1]
            return _SHORT_NAMES.get(key, key)

        # Build volume filename labels for preview if screening volumes
        volumes = self._volume_path.get_path()
        volume_labels = None
        if isinstance(volumes, list) and len(volumes) > 1:
            volume_labels = [Path(p).name for p in volumes]

        for i, name in enumerate(param_names):
            raw_values = screened[name]
            if not raw_values:
                continue

            try:
                values = [float(v) for v in raw_values]
            except (ValueError, TypeError):
                values = list(range(len(raw_values)))
            vmin, vmax = min(values), max(values)
            if vmax > vmin:
                normed = [(v - vmin) / (vmax - vmin) for v in values]
            else:
                normed = [0.5] * len(values)

            guide = pg.PlotCurveItem(
                x=[0.0, 1.0],
                y=[i, i],
                pen=pg.mkPen(Colors.BORDER_DARK, width=1, style=Qt.PenStyle.DashLine),
            )
            plot.addItem(guide)
            self._preview_items.append(guide)

            color = colors[i % len(colors)]
            scatter = pg.ScatterPlotItem(
                x=normed,
                y=[i] * len(normed),
                size=12,
                pen=pg.mkPen(Colors.BORDER_DARK, width=1),
                brush=pg.mkBrush(color.red(), color.green(), color.blue(), 220),
            )
            plot.addItem(scatter)
            self._preview_items.append(scatter)

            n_vals = len(values)
            if n_vals <= max_labels:
                indices = list(range(n_vals))
            else:
                indices = [
                    round(j * (n_vals - 1) / (max_labels - 1))
                    for j in range(max_labels)
                ]

            font = pg.QtGui.QFont()
            font.setPixelSize(9)

            use_volume_labels = name == "volume_path" and volume_labels is not None
            for idx in indices:
                if use_volume_labels:
                    label_text = volume_labels[idx]
                else:
                    label_text = f"{values[idx]:g}"
                label = pg.TextItem(
                    label_text,
                    color=Colors.TEXT_SECONDARY,
                    anchor=(0.5, 0),
                )
                label.setFont(font)
                label.setPos(normed[idx], i - 0.25)
                plot.addItem(label)
                self._preview_items.append(label)

        left_axis = plot.getAxis("left")
        left_axis.setTicks([[(i, _short(n)) for i, n in enumerate(param_names)]])
        left_axis.setStyle(showValues=True)
        left_axis.setPen(pg.mkPen(None))

        bottom_axis = plot.getAxis("bottom")
        bottom_axis.setStyle(showValues=False)
        bottom_axis.setTicks([])
        bottom_axis.setPen(pg.mkPen(None))

        plot.setXRange(-0.1, 1.1, padding=0)
        plot.setYRange(-0.5, n_params - 0.5, padding=0)
        plot.invertY(True)

    def _build_dts_content(self) -> str:
        """Build DTS config content from the current widget state.

        Returns the raw DTS template string with ``{{name:range}}``
        screening placeholders for screened parameters, fixed values
        for others, and ``;@filter`` directives when filters are
        enabled.
        """
        from .screening import _build_dts_template

        screen_params = self._get_screen_params()

        def _screen_or_fixed(key):
            if key in screen_params:
                return "{{" + f"{key}:{screen_params[key]}" + "}}"
            return get_widget_value(self._param_widgets[key])

        volume, use_hmff = self._get_volume_state()
        multi_volume = isinstance(volume, list) and len(volume) > 1

        if multi_volume:
            template_volume = "{{volume_path:" + ",".join(volume) + "}}"
        elif isinstance(volume, list):
            template_volume = volume[0] if volume else None
        else:
            template_volume = volume if use_hmff else None

        hmff_params = {
            "kappa": _screen_or_fixed("kappa"),
            "kappa0": _screen_or_fixed("kappa0"),
        }
        if use_hmff:
            hmff_params["xi"] = _screen_or_fixed("xi")
            hmff_params["invert_contrast"] = get_widget_value(
                self._param_widgets["invert_contrast"]
            )

        edge_text = self._param_widgets["edge_range"].text().strip()
        try:
            parts = [float(x) for x in edge_text.replace("-", " ").split()]
            min_edge, max_edge = (
                (parts[0], parts[1]) if len(parts) >= 2 else (parts[0], parts[0])
            )
        except (ValueError, IndexError):
            min_edge, max_edge = 1.0, 5.0

        sim_params = {
            "steps": get_widget_value(self._param_widgets["steps"]),
            "threads": get_widget_value(self._param_widgets["threads"]),
            "temperature": _screen_or_fixed("temperature"),
            "min_edge": min_edge,
            "max_edge": max_edge,
            "output_period": get_widget_value(self._param_widgets["output_period"]),
        }

        coupling_params = {}
        for ckey, cwidgets in self._coupling_widgets.items():
            if not cwidgets["checkbox"].isChecked():
                continue
            mode = cwidgets["mode_combo"].currentText()
            param_keys = cwidgets["mode_param_keys"][mode]
            values = [_screen_or_fixed(pk) for pk in param_keys]
            coupling_params[ckey] = {"mode": mode, "values": values}

        extra_text = self._extra_config_edit.toPlainText().strip()
        scale_factor = str(get_widget_value(self._param_widgets["scale_factor"]))
        offset = self._param_widgets["offset"].text().strip() or "0,0,0"

        content = _build_dts_template(
            volume_path=template_volume,
            mesh_scale=scale_factor,
            mesh_offset=offset,
            hmff_params=hmff_params,
            sim_params=sim_params,
            extra_config=extra_text,
            coupling_params=coupling_params,
        )

        use_filters = get_widget_value(self._param_widgets["use_filters"])
        if use_hmff and use_filters:
            parts = []
            for k, short in (
                ("lowpass_cutoff", "lowpass"),
                ("highpass_cutoff", "highpass"),
                ("plane_norm", "plane_norm"),
            ):
                val = get_widget_value(self._param_widgets[k])
                if val is not None and str(val).strip():
                    parts.append(f"{short}={val}")
            if parts:
                content = ";@filter " + " ".join(parts) + "\n" + content

        return content

    def _save_dts(self):
        content = self._build_dts_content()
        output = str(get_widget_value(self._output_dir) or "")

        dialog = QFileDialog(self.window() or self)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setNameFilter("DTS Files (*.dts);;All Files (*.*)")
        dialog.setDirectory(str(Path(output)) if output else "")
        dialog.selectFile("input.dts")
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        def on_accepted():
            files = dialog.selectedFiles()
            if files:
                Path(files[0]).write_text(content, encoding="utf-8")

        dialog.accepted.connect(on_accepted)
        dialog.open()

    def _run_screen(self):
        mesh = str(get_widget_value(self._mesh_path) or "")
        if not mesh or not Path(mesh).exists():
            return QMessageBox.warning(self, "Error", "Select a mesh file.")

        output = str(get_widget_value(self._output_dir) or "")
        if not output:
            return QMessageBox.warning(self, "Error", "Select an output directory.")

        return self._generate_screen(mesh, output)

    def _generate_screen(self, mesh, output):
        from ..dts import generate_screen
        from ..parallel import submit_task

        dts_content = self._build_dts_content()

        def _on_done(result):
            if isinstance(result, dict):
                self.screenGenerated.emit(output)

        submit_task(
            "DTS Screen",
            generate_screen,
            _on_done,
            output_dir=output,
            mesh=mesh,
            dts_content=dts_content,
        )
