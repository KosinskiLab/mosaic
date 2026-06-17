"""
Compute panel widget for DTS trajectory analysis.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import Callable, Optional

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QComboBox,
    QSpinBox,
    QCheckBox,
    QPushButton,
    QFormLayout,
    QGroupBox,
)
from ..icons import icon
from ..widgets import MosaicMessageBox


class ComputePanel(QGroupBox):
    """Inline compute controls for DTS trajectory analysis.

    Parameters
    ----------
    cdata : MosaicData or None
        Application data (provides reference models for distance).
    get_mesh_transform : callable
        ``() -> (float, ndarray)`` returning scale and offset.
    get_run_ids : callable
        ``() -> list[str]`` returning run IDs to compute on.
    get_run_dir : callable
        ``(run_id) -> str or None`` returning the run directory path.
    on_complete : callable, optional
        Called after each computation finishes.
    parent : QWidget, optional
        Parent widget.
    """

    def __init__(
        self,
        get_mesh_transform: Callable,
        cdata=None,
        get_run_ids: Optional[Callable] = None,
        get_run_dir: Optional[Callable] = None,
        on_complete: Optional[Callable] = None,
        parent=None,
    ):
        super().__init__("Compute", parent)
        self.cdata = cdata
        self._get_mesh_transform = get_mesh_transform
        self._get_run_ids = get_run_ids or (lambda: [])
        self._get_run_dir = get_run_dir or (lambda _: None)
        self._on_complete = on_complete
        self._option_widgets = {}

        self._build_ui()

    def _build_ui(self):
        self._form = QFormLayout(self)
        self._form.setSpacing(5)
        self._form.setContentsMargins(8, 8, 8, 8)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._type_combo = QComboBox()
        self._type_combo.addItems(
            [
                "Distance",
                "Fluctuation",
                "Area",
                "Volume",
                "HMFF Energy",
                "Bending Energy",
            ]
        )
        self._type_combo.currentTextChanged.connect(self._on_type_changed)
        self._form.addRow("Type:", self._type_combo)

        bottom = QHBoxLayout()
        self._ignore_cache_cb = QCheckBox("Ignore cache")
        bottom.addWidget(self._ignore_cache_cb)
        bottom.addStretch()

        compute_btn = QPushButton("Compute")
        compute_btn.setIcon(icon("ph.computer-tower", role="primary"))
        compute_btn.clicked.connect(self._on_compute)
        bottom.addWidget(compute_btn)

        self._form.addRow(bottom)
        self._on_type_changed(self._type_combo.currentText())

    def _on_type_changed(self, text):
        self._option_widgets.clear()
        form = self._form

        while form.rowCount() > 2:
            form.removeRow(1)

        opts = self._option_widgets
        insert = form.rowCount() - 1

        if text == "Distance":
            ref = QComboBox()
            if self.cdata is not None:
                for label, geom in self.cdata.format_datalist("models", mesh_only=True):
                    ref.addItem(label, geom.uuid)
                for label, geom in self.cdata.format_datalist("data"):
                    ref.addItem(label, geom.uuid)
            form.insertRow(insert, "Reference:", ref)
            opts["ref"] = ref

            invert = QCheckBox()
            invert.setToolTip(
                "Unchecked: per reference point, distance to nearest mesh vertex.\n"
                "Checked: per mesh vertex, distance to nearest reference point."
            )
            form.insertRow(insert + 1, "Invert:", invert)
            opts["invert"] = invert

        elif text == "Fluctuation":
            window = QSpinBox()
            window.setRange(1, 1000)
            window.setValue(5)
            window.setToolTip(
                "Half-window size: each frame uses \u00b1window neighbours"
            )
            form.insertRow(insert, "Window (\u00b1):", window)

            row = QHBoxLayout()
            from_spin = QSpinBox()
            from_spin.setRange(0, 999999)
            from_spin.setSpecialValueText("start")
            row.addWidget(from_spin)
            row.addWidget(QLabel("\u2013"))
            to_spin = QSpinBox()
            to_spin.setRange(0, 999999)
            to_spin.setSpecialValueText("end")
            row.addWidget(to_spin)
            form.insertRow(insert + 1, "Frames:", row)
            opts["window"] = window
            opts["from"] = from_spin
            opts["to"] = to_spin

    def _on_compute(self):
        opts = self._option_widgets
        prop = self._type_combo.currentText()

        if prop == "Distance":
            ref_uuid = opts["ref"].currentData()

            if not ref_uuid or self.cdata is None:
                MosaicMessageBox.warning(self, "Error", "Select a reference model.")
                return

            all_geoms = [
                *self.cdata.format_datalist("models", mesh_only=True),
                *self.cdata.format_datalist("data"),
            ]
            ref_geom = next((g for _, g in all_geoms if g.uuid == ref_uuid), None)

            if ref_geom is None:
                MosaicMessageBox.warning(self, "Error", "Reference geometry not found.")
                return None

            self._submit(
                "Distance",
                "distance",
                reference=ref_geom,
                reference_label=opts["ref"].currentText(),
                invert=opts["invert"].isChecked(),
            )
        elif prop == "Fluctuation":
            self._submit(
                "RMSF",
                "fluctuation",
                window=opts["window"].value(),
                start_frame=opts["from"].value() or None,
                end_frame=opts["to"].value() or None,
            )
        elif prop == "Area":
            self._submit("Area", "mesh_area")
        elif prop == "Volume":
            self._submit("Volume", "mesh_volume")
        elif prop == "HMFF Energy":
            self._submit("HMFF Energy", "hmff_potential")
        elif prop == "Bending Energy":
            self._submit("Bending Energy", "bending_energy")

    def _submit(self, task_label, kind, **kwargs):
        from ..dts import compute
        from ..dts._utils import resolve_trajectory_dir
        from ..parallel import submit_task

        scale, offset = self._get_mesh_transform()
        run_ids = self._get_run_ids()

        if not run_ids:
            return MosaicMessageBox.warning(self, "Error", "No available runs found.")

        force = self._ignore_cache_cb.isChecked()

        for run_id in run_ids:
            run_dir = self._get_run_dir(run_id)
            if not run_dir:
                continue

            traj_dir = resolve_trajectory_dir(run_dir)
            if traj_dir is None:
                continue

            submit_task(
                f"{task_label} ({run_id})",
                compute,
                lambda _, rid=run_id: (
                    self._on_complete(rid) if self._on_complete else None
                ),
                trajectory_dir=str(traj_dir),
                kind=kind,
                scale=scale,
                offset=offset,
                output_dir=run_dir,
                force=force,
                **kwargs,
            )
