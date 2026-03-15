"""
Configure tab widget for DTS parameter screening dialog.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import re
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
)
import pyqtgraph as pg
import qtawesome as qta

from ..widgets import PathSelector, generate_gradient_colors
from ..widgets.settings import create_setting_widget, get_widget_value
from ..stylesheets import Colors

_EXTRA_CONFIG_PLACEHOLDER = (
    "# Fixed:   Kappa = 25.0 0 0\n"
    "# Screen:  Kappa = {{kappa:25.0:35.0:5.0}} 0 0\n"
    "# List:    Set_Steps = 1 {{steps:1000,5000}}"
)

_COUPLING_DEFS = {
    "vol_coupling": {
        "label": "Volume Coupling",
        "dts_keyword": "VolumeCoupling",
        "modes": {
            "SecondOrder": [
                ("delta_p", "\u0394p (pressure)", 0.0, 0.1),
                ("K", "Stiffness", 10000.0, 100.0),
                ("target_v", "Target volume", 0.7, 0.05),
            ],
            "OsmoticPressure": [
                ("gamma", "\u03b3", 1.0, 0.1),
                ("P0", "P\u2080", 0.0, 0.1),
            ],
        },
    },
    "curv_coupling": {
        "label": "Global Curvature",
        "dts_keyword": "GlobalCurvatureCoupling",
        "modes": {
            "HarmonicPotential": [
                ("K", "Stiffness", 180.0, 1.0),
                ("C_g0", "Target curvature", 0.3, 0.05),
            ],
        },
    },
    "area_coupling": {
        "label": "Total Area",
        "dts_keyword": "TotalAreaCoupling",
        "modes": {
            "HarmonicPotential": [
                ("K", "Stiffness", 1000.0, 10.0),
                ("gamma", "Target ratio", 0.34, 0.05),
            ],
        },
    },
}


def _parse_screening_ranges(text: str) -> Dict[str, List]:
    """Extract ``{{name:range}}`` placeholders from text and parse values."""
    result = {}
    for match in re.finditer(r"\{\{(\w+):([^}]+)\}\}", text):
        name, range_str = match.group(1), match.group(2)
        try:
            from pyfreedts.screen import ParameterParser

            _, parsed = ParameterParser.parse_template("{{" + f"p:{range_str}" + "}}")
            result[name] = parsed.get("p", [])
        except Exception:
            pass
    return result


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
        self._mesh_conf = None

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

        input_group = QGroupBox("Input")
        input_form = QFormLayout(input_group)
        input_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._mesh_path = PathSelector(
            placeholder="Input mesh (.tsi, .q)",
            file_filter="TSI Files (*.tsi) Q Files (*.q);;All Files (*.*)",
        )
        input_form.addRow("Mesh:", self._mesh_path)

        self._output_dir = PathSelector(placeholder="Output directory", file_mode=False)
        input_form.addRow("Output:", self._output_dir)

        layout.addWidget(input_group)

        sim_group = QGroupBox("Simulation")
        sim_form = QFormLayout(sim_group)
        sim_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._add_screenable_row(
            sim_form, key="temperature", label="Temperature", default=1.0
        )

        self._param_widgets["edge_range"] = QLineEdit("1 - 5")
        self._param_widgets["edge_range"].setPlaceholderText("min - max")
        self._param_widgets["edge_range"].setToolTip(
            "Min and max edge lengths for mesh refinement (format: min - max)"
        )
        sim_form.addRow("Edge length:", self._param_widgets["edge_range"])

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
            sim_form.addRow(label, self._param_widgets[key])

        layout.addWidget(sim_group)

        phys_group = QGroupBox("Physical Parameters")
        phys_form = QFormLayout(phys_group)
        phys_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._add_screenable_row(
            phys_form, key="kappa", label="Rigidity (\u03ba)", default=25.0
        )
        self._add_screenable_row(
            phys_form,
            key="kappa0",
            label="Spont. curvature (\u03ba\u2080)",
            default=0.0,
        )
        for coupling_key, coupling_def in _COUPLING_DEFS.items():
            self._add_coupling_section(phys_form, coupling_key, coupling_def)

        layout.addWidget(phys_group)

        hmff_group = QGroupBox("HMFF Parameters")
        hmff_form = QFormLayout(hmff_group)
        hmff_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._volume_path = PathSelector(
            placeholder="Volume file (.mrc)",
            file_filter="MRC Files (*.mrc);;All Files (*.*)",
        )
        self._volume_path.path_input.textChanged.connect(self._on_volume_changed)
        hmff_form.addRow("Volume:", self._volume_path)

        self._add_screenable_row(
            hmff_form, key="xi", label="Coupling (\u03be)", default=5.0
        )
        for w in (self._screen_stacks["xi"], self._screen_cbs["xi"]):
            w.setEnabled(False)

        self._hmff_volume_container = QWidget()
        vol_form = QFormLayout(self._hmff_volume_container)
        vol_form.setContentsMargins(0, 2, 0, 2)
        vol_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._param_widgets["invert_contrast"] = create_setting_widget(
            {"type": "boolean", "default": True}
        )
        vol_form.addRow("Invert contrast:", self._param_widgets["invert_contrast"])

        self._scale_file = PathSelector(
            placeholder="Scale file (mesh.txt)",
            file_filter="Text Files (*.txt);;All Files (*.*)",
        )
        self._scale_file.path_input.textChanged.connect(self._on_scale_file_changed)
        vol_form.addRow("Scale file:", self._scale_file)

        self._scale_mesh_combo = QComboBox()
        self._scale_mesh_combo.setVisible(False)
        vol_form.addRow("Scale entry:", self._scale_mesh_combo)

        self._param_widgets["use_filters"] = create_setting_widget(
            {"type": "boolean", "default": False}
        )
        self._param_widgets["use_filters"].stateChanged.connect(
            self._toggle_filter_inputs
        )
        vol_form.addRow("Enable Filters:", self._param_widgets["use_filters"])

        self._filter_container = QWidget()
        filter_form = QFormLayout(self._filter_container)
        filter_form.setContentsMargins(0, 2, 0, 2)
        filter_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

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
            filter_form.addRow(label, self._param_widgets[param_key])

        self._filter_container.setVisible(False)
        vol_form.addRow(self._filter_container)

        hmff_form.addRow(self._hmff_volume_container)
        self._hmff_volume_container.setVisible(False)

        layout.addWidget(hmff_group)

        extra_group = QGroupBox("Extra Parameters")
        extra_layout = QVBoxLayout(extra_group)
        self._extra_config_edit = QPlainTextEdit()
        self._extra_config_edit.setPlaceholderText(_EXTRA_CONFIG_PLACEHOLDER)
        self._extra_config_edit.setMinimumHeight(80)
        self._extra_config_edit.setMaximumHeight(140)
        self._extra_config_edit.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background-color: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER_DARK};
                border-radius: 4px;
                padding: 6px;
                font-size: 12px;
            }}
            QPlainTextEdit:focus {{
                border: 1px solid {Colors.PRIMARY};
            }}
            """
        )
        self._extra_config_edit.textChanged.connect(self._update_combo_summary)
        extra_layout.addWidget(self._extra_config_edit)
        layout.addWidget(extra_group)

        layout.addStretch()

        import shutil

        info_row = QHBoxLayout()
        dts_path = shutil.which("dts") or shutil.which("DTS")
        if dts_path:
            dts_info = QLabel(f"DTS binary: {dts_path}")
        else:
            dts_info = QLabel("DTS binary not found in PATH")
        dts_info.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
        info_row.addWidget(dts_info)

        self._combo_summary = QLabel("")
        self._combo_summary.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 11px;"
        )
        info_row.addStretch()
        info_row.addWidget(self._combo_summary)
        layout.addLayout(info_row)

        self._generate_btn = QPushButton("Generate Screen")
        self._generate_btn.setIcon(qta.icon("ph.play", color=Colors.PRIMARY))
        self._generate_btn.clicked.connect(self._run_screen)
        layout.addWidget(self._generate_btn)

        self.setWidget(content)

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

    def _on_scale_file_changed(self, path: str):
        if not path:
            self._mesh_conf = None
            self._scale_mesh_combo.clear()
            self._scale_mesh_combo.setVisible(False)
            return

        scale_path = Path(path)
        if not scale_path.exists():
            self._mesh_conf = None
            self._scale_mesh_combo.clear()
            self._scale_mesh_combo.setVisible(False)
            return

        with open(scale_path, "r", encoding="utf-8") as f:
            data = [x.strip() for x in f.read().split("\n")]
            data = [x.split("\t") for x in data if len(x)]

        headers = data.pop(0)
        self._mesh_conf = {
            header: list(column) for header, column in zip(headers, zip(*data))
        }

        if not all(k in self._mesh_conf for k in ("file", "scale_factor", "offset")):
            QMessageBox.warning(
                self,
                "Error",
                "Scale file is malformed (missing required columns).",
            )
            self._mesh_conf = None
            return

        self._scale_mesh_combo.clear()
        self._scale_mesh_combo.addItems(self._mesh_conf["file"])
        self._scale_mesh_combo.setVisible(len(self._mesh_conf["file"]) > 1)

    def _toggle_screen_param(self, key: str, state: int):
        screening = bool(state)
        self._screen_stacks[key].setCurrentIndex(1 if screening else 0)
        self._update_combo_summary()

    def _on_volume_changed(self, path: str):
        has_volume = bool(path) and Path(path).exists()
        for w in (self._screen_stacks["xi"], self._screen_cbs["xi"]):
            w.setEnabled(has_volume)
        self._hmff_volume_container.setVisible(has_volume)
        if not has_volume:
            self._param_widgets["use_filters"].setChecked(False)

    def _toggle_filter_inputs(self, state):
        self._filter_container.setVisible(state == Qt.CheckState.Checked.value)

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
            result.update(_parse_screening_ranges(extra_text))
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
        """Return (scale_factor, offset) from the loaded scale file."""
        if self._mesh_conf is None:
            return 1.0, np.array([0.0, 0.0, 0.0])

        try:
            idx = max(self._scale_mesh_combo.currentIndex(), 0)
            scale_factor = float(self._mesh_conf["scale_factor"][idx])
            offset_str = self._mesh_conf["offset"][idx]
            offset = np.array([float(x) for x in offset_str.split(",")])
        except (ValueError, IndexError, KeyError):
            scale_factor = 1.0
            offset = np.array([0.0, 0.0, 0.0])

        return scale_factor, offset

    def get_screen_param_keys(self) -> list:
        """Return all registered screening parameter keys."""
        return list(self._screen_cbs.keys())

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

        for i, name in enumerate(param_names):
            values = [float(v) for v in screened[name]]
            if not values:
                continue

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
            for idx in indices:
                label = pg.TextItem(
                    f"{values[idx]:g}",
                    color=Colors.TEXT_SECONDARY,
                    anchor=(0.5, 0),
                )
                label.setFont(pg.QtGui.QFont("sans-serif", 9))
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

    def _run_screen(self):
        mesh = str(get_widget_value(self._mesh_path) or "")
        if not mesh or not Path(mesh).exists():
            return QMessageBox.warning(self, "Error", "Select a mesh file.")

        output = str(get_widget_value(self._output_dir) or "")
        if not output:
            return QMessageBox.warning(self, "Error", "Select an output directory.")

        screen_params = self._get_screen_params()
        extra_text = self._extra_config_edit.toPlainText().strip()

        if not screen_params and not _parse_screening_ranges(extra_text):
            return QMessageBox.warning(
                self, "Error", "Enable at least one parameter for screening."
            )

        return self._generate_screen(mesh, output, screen_params, extra_text)

    def _generate_screen(self, mesh, output, screen_params, extra_text):
        from ..dts import generate_screen
        from ..parallel import submit_task

        if self._mesh_conf is not None:
            idx = max(self._scale_mesh_combo.currentIndex(), 0)
            mesh_conf = {
                "file": [mesh],
                "scale_factor": [self._mesh_conf["scale_factor"][idx]],
                "offset": [self._mesh_conf["offset"][idx]],
            }
        else:
            mesh_conf = None

        volume = str(get_widget_value(self._volume_path) or "")

        def _screen_or_fixed(key):
            if key in screen_params:
                return "{{" + f"{key}:{screen_params[key]}" + "}}"
            return get_widget_value(self._param_widgets[key])

        use_hmff = volume and Path(volume).exists()
        if "xi" in screen_params and not use_hmff:
            return QMessageBox.warning(
                self, "Error", "HMFF weight screening requires a valid volume file."
            )

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

        use_filters = get_widget_value(self._param_widgets["use_filters"])

        coupling_params = {}
        for ckey, cwidgets in self._coupling_widgets.items():
            if not cwidgets["checkbox"].isChecked():
                continue
            mode = cwidgets["mode_combo"].currentText()
            param_keys = cwidgets["mode_param_keys"][mode]
            values = [_screen_or_fixed(pk) for pk in param_keys]
            coupling_params[ckey] = {"mode": mode, "values": values}

        def _on_done(result):
            if isinstance(result, dict):
                self.screenGenerated.emit(output)

        filter_kwargs = {}
        if use_filters:
            for k in ("lowpass_cutoff", "highpass_cutoff", "plane_norm"):
                filter_kwargs[k] = get_widget_value(self._param_widgets[k])

        submit_task(
            "DTS Screen",
            generate_screen,
            _on_done,
            mesh_conf,
            output_dir=output,
            mesh=mesh,
            volume_path=volume if use_hmff else None,
            hmff_params=hmff_params,
            sim_params=sim_params,
            extra_config=extra_text,
            coupling_params=coupling_params,
            use_filters=use_filters if use_hmff else False,
            **filter_kwargs,
        )
