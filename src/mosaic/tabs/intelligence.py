import functools
from typing import Union
from os.path import exists, basename, normpath

import numpy as np
from qtpy.QtWidgets import QWidget, QVBoxLayout, QApplication, QFileDialog

from ..parallel import submit_task
from ..widgets.ribbon import create_button
from ..widgets import MosaicMessageBox


class IntelligenceTab(QWidget):
    def __init__(self, cdata, ribbon, **kwargs):
        super().__init__()
        self.cdata = cdata
        self.ribbon = ribbon

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ribbon)

    def show_ribbon(self):
        from ..segmentation import MEMBRAIN_SETTINGS

        self.ribbon.clear()

        dts_actions = [
            create_button(
                "Equilibrate",
                "ph.faders",
                self,
                self._equilibrate_fit,
                "Prepare mesh for DTS simulation",
            ),
            create_button(
                "DTS",
                "ph.grid-four",
                self,
                self._screen_parameters,
                "Setup and analyze DTS simulations.",
            ),
            create_button(
                "Trajectory",
                "ph.path",
                self,
                self._import_trajectory,
                "Load DTS simulation trajectory",
                IMPORT_SETTINGS,
            ),
            create_button(
                "Backmapping",
                "ph.atom",
                self,
                self._map_fit,
                "Backmap DTS to Martini representation",
            ),
        ]
        self.ribbon.add_section("DTS Simulation", dts_actions)

        detection_actions = [
            create_button(
                "Template Match",
                "ph.magnifying-glass",
                self,
                self._match_template,
                "Identify proteins by template matching",
            ),
            create_button(
                "Membrane",
                "ph.stack",
                self,
                self._run_membrane_segmentation,
                "Segment membranes using MemBrain",
                MEMBRAIN_SETTINGS,
            ),
        ]
        self.ribbon.add_section("Detection", detection_actions)

    def _match_template(self):
        from qtpy.QtWidgets import QApplication
        from ..dialogs import TemplateMatchingDialog

        dialog = TemplateMatchingDialog(parent=QApplication.activeWindow())
        return dialog.exec_()

    def _equilibrate_fit(self):
        from ..dts.equilibration_dialog import MeshEquilibrationDialog
        from ..meshing import equilibrate_fit

        geometries = self.cdata.models.get_selected_geometries()
        if len(geometries) == 0:
            msg = "A mesh needs for equilibration needs to be selected."
            return MosaicMessageBox.warning(self, "Error", msg)
        elif len(geometries) > 1:
            msg = "Can only equilibrate a single mesh at a time."
            return MosaicMessageBox.warning(self, "Error", msg)

        geometry = geometries[0]
        if not hasattr(geometry.model, "mesh"):
            msg = f"{geometry} is not a triangular mesh."
            return MosaicMessageBox.warning(self, "Error", msg)

        from qtpy.QtWidgets import QApplication

        dialog = MeshEquilibrationDialog(QApplication.activeWindow())
        if not dialog.exec():
            return -1

        submit_task(
            "Equilibrate",
            equilibrate_fit,
            None,
            geometry,
            dialog.get_output_directory(),
            dialog.get_parameters(),
        )

    def _import_trajectory(
        self,
        directory: str = "",
        scale: float = 1.0,
        offset: Union[str, float] = 0.0,
        drop_pbc: bool = False,
        **kwargs,
    ):
        from ..dts._utils import (
            list_trajectory_files,
            build_trajectory_frames,
        )
        from ..parallel import submit_io_task
        from qtpy.QtWidgets import QApplication

        if not directory:
            return MosaicMessageBox.warning(
                QApplication.activeWindow(),
                "Error",
                "Trajectory directory needs to be specified.",
            )

        if isinstance(offset, str):
            try:
                offset = np.array([float(x) for x in offset.split(",")])
            except Exception:
                return MosaicMessageBox.warning(
                    QApplication.activeWindow(),
                    "Error",
                    "Offset should be a single or three comma-separated floats.",
                )

        files = list_trajectory_files(directory)
        if not files:
            return MosaicMessageBox.warning(
                QApplication.activeWindow(),
                "Error",
                f"No meshes found at: {directory}.",
            )

        name = basename(normpath(directory)) or "trajectory"

        submit_io_task(
            "Import trajectory",
            build_trajectory_frames,
            functools.partial(self._on_trajectory_loaded, scale=scale, name=name),
            directory,
            scale,
            offset,
            None,
            drop_pbc,
        )

    def _on_trajectory_loaded(self, frames, scale: float, name: str):
        """GUI-thread callback: construct GeometryTrajectory and add it."""
        if not frames or self.cdata is None:
            return

        from ..geometry import GeometryTrajectory

        trajectory = GeometryTrajectory(
            sampling_rate=1 / scale,
            trajectory=frames,
            model=frames[0]["fit"],
            vertex_properties=frames[0].get("vertex_properties"),
            meta={"name": name},
        )
        trajectory.change_representation("mesh")
        self.cdata.models.add(trajectory)
        self.cdata.models.data_changed.emit()
        self.cdata.models.render()

    def _screen_parameters(self):
        from ..dialogs import DTSScreeningDialog

        from qtpy.QtWidgets import QApplication

        dialog = DTSScreeningDialog(self.cdata, parent=QApplication.activeWindow())
        dialog.show()
        self._screen_dialog = dialog

    def _map_fit(self):
        from ..dialogs import MeshMappingDialog
        from qtpy.QtWidgets import QApplication

        fits = self.cdata.format_datalist("models", mesh_only=True)
        clusters = self.cdata.format_datalist("data")
        dialog = MeshMappingDialog(
            fits=fits, clusters=clusters, parent=QApplication.activeWindow()
        )
        if not dialog.exec():
            return -1

        from ..meshing import mesh_to_cg

        fit, edge_length, mappings, cast_ray, flip = dialog.get_parameters()

        submit_task(
            "Coarse graining",
            mesh_to_cg,
            None,
            fit._geometry_data,
            edge_length=edge_length,
            output_directory=dialog.get_output_directory(),
            inclusions=mappings,
            include_normals=cast_ray,
            flip_normals=flip,
        )

    def _run_membrain(self, *args, **kwargs):
        from ..gui import App
        from ..formats import open_file
        from ..segmentation import run_membrainseg

        def _callback(output_name: str):
            if output_name is None:
                return MosaicMessageBox.warning(
                    None, "Error", "No segmentation was created."
                )

            # Preferred because it also updates viewport
            app = QApplication.instance().activeWindow()
            if isinstance(app, App):
                return app._open_files([output_name])

            container = open_file(output_name)
            for data in container:
                self.cdata.data.add(
                    points=np.multiply(data.vertices, data.sampling),
                    normals=data.normals,
                    sampling_rate=data.sampling,
                )
            self.cdata.data.data_changed.emit()
            self.cdata.data.render()

        submit_task(
            "Membrane Segmentation", run_membrainseg, _callback, *args, **kwargs
        )

    def _run_membrane_segmentation(self, **kwargs):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select volume", "", "MRC Files (*.mrc);;All Files (*.*)"
        )
        if not file_name:
            return None

        if not exists(kwargs.get("model_path", "")):
            return MosaicMessageBox.warning(
                None, "Error", "Missing path to membrain model."
            )

        return self._run_membrain(tomogram_path=file_name, **kwargs)


IMPORT_SETTINGS = {
    "title": "Settings",
    "settings": [
        {
            "label": "Trajectory",
            "parameter": "directory",
            "type": "PathSelector",
            "mode": "directory",
            "description": "Trajectory directory",
        },
        {
            "label": "Scale",
            "parameter": "scale",
            "type": "text",
            "default": 1.0,
            "description": "Scale imported points by 1 / scale.",
        },
        {
            "label": "Offset",
            "parameter": "offset",
            "type": "text",
            "default": "0.0",
            "description": "Add offset as (points - offset) / scale ",
        },
        {
            "label": "Remove PBC",
            "parameter": "drop_pbc",
            "type": "boolean",
            "default": False,
            "description": "Drop triangles arising from periodic boundaries.",
        },
    ],
}
