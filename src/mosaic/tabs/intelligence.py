import re
from os import listdir
from os.path import join, exists, basename

import numpy as np
from qtpy.QtWidgets import QWidget, QVBoxLayout, QFileDialog, QMessageBox

from ..formats import open_file
from ..geometry import GeometryTrajectory
from ..widgets.ribbon import create_button
from ..parametrization import TriangularMesh
from ..segmentation import MEMBRAIN_SETTINGS, run_membrainseg
from ..meshing import equilibrate_fit, setup_hmff, to_open3d, mesh_to_cg
from ..dialogs import (
    MeshEquilibrationDialog,
    HMFFDialog,
    ProgressDialog,
    MeshMappingDialog,
)


class IntelligenceTab(QWidget):
    def __init__(self, cdata, ribbon, **kwargs):
        super().__init__()
        self.cdata = cdata
        self.ribbon = ribbon

        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ribbon)

    def show_ribbon(self):
        self.ribbon.clear()

        hmff_actions = [
            create_button("Equilibrate", "mdi.molecule", self, self._equilibrate_fit),
            create_button("Setup", "mdi.export", self, self._setup_hmff),
            create_button(
                "Trajectory",
                "mdi.chart-line-variant",
                self,
                self._import_trajectory,
                "Import Trajectory",
                IMPORT_SETTINGS,
            ),
            create_button("Backmapping", "mdi.set-merge", self, self._map_fit),
        ]
        self.ribbon.add_section("HMFF Operations", hmff_actions)

        segmentation_actions = [
            create_button(
                "Add", "mdi.plus", self, self.add_cloud, "Merge selected clusters"
            ),
            create_button(
                "Membrane",
                "mdi.border-all-variant",
                self,
                self._run_membrain,
                "Segment membranes using Membrain-seg",
                MEMBRAIN_SETTINGS,
            ),
        ]
        self.ribbon.add_section("Segmentation Operations", segmentation_actions)

    def _equilibrate_fit(self):
        indices = self.cdata.models._get_selected_indices()
        if len(indices) != 1:
            print("Can only equilibrate a single mesh at a time.")
            return -1

        index = indices[0]
        geometry = self.cdata._models.data[index]
        if geometry._meta.get("fit", None) is None:
            print(f"No parametrization associated with {index}.")
            return -1

        if not hasattr(geometry._meta.get("fit", None), "mesh"):
            print(f"{index} is not a triangular mesh.")
            return -1

        directory = QFileDialog.getExistingDirectory(
            self,
            "Select or Create Directory",
            options=QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if not directory:
            return -1

        dialog = MeshEquilibrationDialog(None)
        if not dialog.exec():
            return -1

        return equilibrate_fit(geometry, directory, dialog.get_parameters())

    def _setup_hmff(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Directory with Equilibrated Meshes.",
            options=QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if not directory:
            return -1

        mesh_config = join(directory, "mesh.txt")
        if not exists(mesh_config):
            print(
                f"Missing mesh_config at {mesh_config}. Most likely {directory} "
                "is not a valid directory created by Equilibrate Mesh."
            )
            return -1

        with open(mesh_config, mode="r", encoding="utf-8") as infile:
            data = [x.strip() for x in infile.read().split("\n")]
            data = [x.split("\t") for x in data if len(x)]

        headers = data.pop(0)
        ret = {header: list(column) for header, column in zip(headers, zip(*data))}

        if not all(t in ret.keys() for t in ("file", "scale_factor", "offset")):
            print(
                "mesh_config is malformated. Expected file, scale_factor, "
                f"offset columns, got {', '.join(list(ret.keys()))}."
            )
            return -1

        dialog = HMFFDialog(None, mesh_options=ret["file"])
        if not dialog.exec():
            return -1

        ret = setup_hmff(mesh_conf=ret, directory=directory, **dialog.get_parameters())
        QMessageBox.information(self, "Success", "HMFF directory setup successfully.")
        return ret

    def _import_trajectory(self, scale: float = 1.0, offset: float = 0.0, **kwargs):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Directory with Point Cloud Series",
            "",
            QFileDialog.Option.ShowDirsOnly,
        )
        if not directory:
            return -1

        ret = []
        files = [join(directory, x) for x in listdir(directory)]
        files = [
            x
            for x in files
            if x.endswith(".tsi") or x.endswith(".vtu") and x != "conf-1.vtu"
        ]
        files = sorted(files, key=lambda x: int(re.findall(r"\d+", basename(x))[0]))

        with ProgressDialog(files, title="Importing Trajectory", parent=None) as pbar:
            for index, filename in enumerate(pbar):
                container = open_file(filename)[0]
                faces = container.faces.astype(int)
                points = np.divide(np.subtract(container.vertices, offset), scale)

                fit = TriangularMesh(to_open3d(points, faces))
                ret.append({"fit": fit, "filename": filename})

        if len(ret) == 0:
            print(f"No meshes found at: {directory}.")
            return None

        base = ret[0]["fit"]
        trajectory = GeometryTrajectory(
            points=base.vertices.copy(),
            normals=base.compute_vertex_normals().copy(),
            sampling_rate=1 / scale,
            meta=ret[0].copy(),
            trajectory=ret,
        )
        trajectory.change_representation("mesh")
        self.cdata._models.add(trajectory)
        self.cdata.models.data_changed.emit()
        return self.cdata.models.render()

    def _map_fit(self):
        save_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Save Directory",
            "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if not save_dir:
            return -1

        fits = self.cdata.format_datalist("models")
        fits = [x for x in fits if isinstance(x[1]._meta.get("fit"), TriangularMesh)]
        clusters = self.cdata.format_datalist("data")
        dialog = MeshMappingDialog(fits=fits, clusters=clusters)
        if not dialog.exec():
            return -1

        fit, edge_length, mappings = dialog.get_parameters()
        ret = mesh_to_cg(
            mesh=fit._meta["fit"].mesh,
            edge_length=edge_length,
            output_directory=save_dir,
            inclusions=mappings,
        )
        QMessageBox.information(self, "Success", "Export successful.")
        return ret

    def _run_membrain(self, **kwargs):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select Tomogram", "", "MRC Files (*.mrc);;All Files (*.*)"
        )
        if not file_name:
            return None

        if kwargs.get("model_path", "") == "":
            print("Missing path to membrain model.")
            return None

        output_name = run_membrainseg(tomogram_path=file_name, **kwargs)
        if output_name is None:
            return None

        container = open_file(output_name)
        for index in range(len(container)):
            data = container[index]
            self.cdata._data.add(
                points=data.vertices, normals=data.normals, sampling_rate=data.sampling
            )
        self.cdata.data.data_changed.emit()
        return self.cdata.data.render()

    def add_cloud(self, *args):
        num_points = 1000
        points = np.random.rand(num_points, 3) * 100
        self.cdata._data.add(points=points, sampling_rate=1)
        self.cdata.data.data_changed.emit()
        self.cdata.data.render()


IMPORT_SETTINGS = {
    "title": "Trajectory Import",
    "settings": [
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
            "default": 0.0,
            "description": "Add offset as (points - offset) / scale ",
        },
    ],
}
