from functools import partial
from os.path import join, exists

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFileDialog, QMessageBox

from ..geometry import GeometryTrajectory
from ..widgets.ribbon import create_button
from ..parametrization import TriangularMesh
from ..io_utils import import_mesh_trajectory, import_mesh, load_density
from ..meshing import equilibrate_fit, setup_hmff, to_open3d, marching_cubes, mesh_to_cg
from ..dialogs import (
    MeshEquilibrationDialog,
    HMFFDialog,
    ProgressDialog,
    MeshMappingDialog,
)


class FitWorker(QThread):
    finished = pyqtSignal()

    def __init__(self, cdata, **kwargs):
        super().__init__()
        self.cdata = cdata
        self.kwargs = kwargs

    def run(self):
        self.cdata.add_fit(**self.kwargs)
        self.finished.emit()

    def kill(self, timeout=10000):
        self.quit()
        if not self.wait(timeout):
            self.terminate()
            self.wait()


class ModelTab(QWidget):
    def __init__(self, cdata, ribbon):
        super().__init__()
        self.cdata = cdata
        self.ribbon = ribbon

        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ribbon)

    def show_ribbon(self):
        self.ribbon.clear()

        func = self._fit
        fitting_actions = [
            create_button("Sphere", "mdi.circle", self, partial(func, "sphere")),
            create_button("Ellipse", "mdi.ellipse", self, partial(func, "ellipsoid")),
            create_button("Cylinder", "mdi.hexagon", self, partial(func, "cylinder")),
            create_button(
                "RBF", "mdi.grid", self, partial(func, "rbf"), "Fit RBF", RBF_SETTINGS
            ),
            create_button(
                "Mesh", "mdi.vector-polyline", self, func, "Fit Mesh", MESH_SETTINGS
            ),
        ]
        self.ribbon.add_section("Fitting Operations", fitting_actions)

        mesh_actions = [
            create_button(
                "Sample",
                "mdi.chart-scatter-plot",
                self,
                self.cdata.sample_fit,
                "Sample from Fit",
                SAMPLE_SETTINGS,
            ),
            create_button("To Cluster", "mdi.plus", self, self._to_cluster),
            create_button(
                "Remove", "fa5s.trash", self, self.cdata.models.remove_cluster
            ),
        ]
        self.ribbon.add_section("Sampling Operations", mesh_actions)

        mesh_actions = [
            create_button("Import", "mdi.import", self, self._import_meshes),
            create_button("Volume", "mdi.cube-outline", self, self._mesh_volume),
            create_button("Curvature", "mdi.vector-curve", self, self._color_curvature),
        ]
        self.ribbon.add_section("Mesh Operations", mesh_actions)

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

    def _fit(self, method: str, **kwargs):
        _conversion = {
            "Alpha Shape": "convexhull",
            "Ball Pivoting": "mesh",
            "Poisson": "poissonmesh",
        }

        method = _conversion.get(method, method)
        self.fit_worker = FitWorker(self.cdata, method=method, **kwargs)
        self.fit_worker.finished.connect(self._on_fit_complete)
        self.fit_worker.start()

    def _on_fit_complete(self):
        self.fit_worker.deleteLater()
        self.fit_worker = None

        self.cdata.data.render()
        self.cdata.models.render()

    def _to_cluster(self, *args, **kwargs):
        indices = self.cdata.models._get_selected_indices()

        for index in indices:
            if not self.cdata._models._index_ok(index):
                continue

            geometry = self.cdata._models.data[index]

            points = geometry.points
            sampling = geometry._sampling_rate
            normals = geometry._meta.get("fit", None)
            if normals is not None:
                normals = normals.compute_normal(points)

            self.cdata._data.new(points, normals=normals, sampling_rate=sampling)
        self.cdata.data.data_changed.emit()
        self.cdata.data.render()
        return None

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

        ret = setup_hmff(ret, directory, dialog.get_parameters())
        QMessageBox.information(self, "Success", "HMFF directory setup successfully.")
        return ret

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

    def _import_meshes(self):
        filenames, _ = QFileDialog.getOpenFileNames(self, "Select Meshes")
        if not filenames:
            return -1

        progress = ProgressDialog(filenames, title="Importing Meshes", parent=None)
        for filename in progress:
            try:
                vertices, faces = import_mesh(filename)
                fit = TriangularMesh(to_open3d(vertices, faces))

                meta = {
                    "fit": fit,
                    "points": np.asarray(fit.mesh.vertices),
                    "faces": np.asarray(fit.mesh.triangles),
                    "normals": fit.compute_vertex_normals(),
                }
                self.cdata._models.add(
                    points=meta["points"],
                    normals=meta["normals"],
                    meta=meta,
                )
            except Exception as e:
                print(e)

        self.cdata.models.data_changed.emit()
        return self.cdata.models.render()

    def _mesh_volume(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Select Meshes")
        if not filename:
            return -1

        dens = load_density(filename)
        meshes = marching_cubes(dens.data, dens.sampling_rate)
        for mesh in meshes:
            fit = TriangularMesh(mesh)
            meta = {
                "fit": fit,
                "points": np.asarray(fit.mesh.vertices),
                "faces": np.asarray(fit.mesh.triangles),
                "normals": fit.compute_vertex_normals(),
            }

            self.cdata._models.add(
                points=meta["points"],
                normals=meta["normals"],
                meta=meta,
                sampling_rate=dens.sampling_rate,
            )

        self.cdata.models.data_changed.emit()
        return self.cdata.models.render()

    def _color_curvature(self):
        for index in self.cdata.models._get_selected_indices():
            self.cdata._models.data[index].compute_curvature()
        return self.cdata.models.render()

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
        mesh_trajectory = import_mesh_trajectory(directory)
        progress = ProgressDialog(
            mesh_trajectory, title="Importing Trajectory", parent=None
        )
        for index, data in enumerate(progress):
            points, faces, filename = data

            faces = faces.astype(int)
            points = np.divide(np.subtract(points, offset), scale)
            fit = TriangularMesh(to_open3d(points, faces))
            meta = {
                "points": points,
                "faces": faces,
                "fit": fit,
                "normal": fit.compute_normal(points),
                "filename": filename,
            }
            ret.append(meta)

        if len(ret) == 0:
            print(f"No meshes found at: {directory}.")
            return None

        trajectory = GeometryTrajectory(
            points=np.asarray(ret[0]["fit"].mesh.vertices).copy(),
            normals=np.asarray(ret[0]["fit"].mesh.vertices).copy(),
            sampling_rate=1 / scale,
            meta=ret[0].copy(),
            trajectory=ret,
        )
        self.cdata._models.add(trajectory)
        self.cdata.models.data_changed.emit()
        return self.cdata.models.render()


SAMPLE_SETTINGS = {
    "title": "Sample Fit",
    "settings": [
        {
            "label": "Sampling Method",
            "parameter": "sampling_method",
            "type": "select",
            "options": ["Points", "Distance"],
            "default": "Points",
            "notes": "Number of points or average distance between points.",
        },
        {
            "label": "Sampling",
            "parameter": "sampling",
            "type": "float",
            "min": 1,
            "default": 1000,
            "notes": "Numerical value for sampling method.",
        },
        {
            "label": "Offset",
            "parameter": "normal_offset",
            "type": "float",
            "default": 0,
            "notes": "Points are shifted by n times normal vector for particle picking.",
        },
    ],
}

RBF_SETTINGS = {
    "title": "RBF Settings",
    "settings": [
        {
            "label": "Direction",
            "parameter": "direction",
            "type": "select",
            "options": ["xy", "xz", "yz"],
            "default": "xy",
            "description": "Coordinate plane to fit RBF in.",
        },
    ],
}
MESH_SETTINGS = {
    "title": "Mesh Settings",
    "settings": [
        {
            "label": "Method",
            "parameter": "method",
            "type": "select",
            "options": ["Alpha Shape", "Ball Pivoting", "Poisson"],
            "default": "Alpha Shape",
        },
        {
            "label": "Elastic Weight",
            "parameter": "elastic_weight",
            "type": "float",
            "default": 0.0,
            "description": "Control mesh smoothness and elasticity.",
            "notes": "0 - strong anchoring, 1 - no anchoring, > 1 repulsion.",
        },
        {
            "label": "Curvature Weight",
            "parameter": "curvature_weight",
            "type": "float",
            "default": 0.0,
            "description": "Controls propagation of mesh curvature.",
        },
        {
            "label": "Volume Weight",
            "parameter": "volume_weight",
            "type": "float",
            "default": 0.0,
            "description": "Controls internal pressure of mesh.",
        },
        {
            "label": "Boundary Ring",
            "parameter": "boundary_ring",
            "type": "number",
            "default": 0,
            "description": "Also optimize n-ring vertices for ill-defined boundaries.",
        },
    ],
    "method_settings": {
        "Alpha Shape": [
            {
                "label": "Alpha",
                "parameter": "alpha",
                "type": "float",
                "default": 1.0,
                "description": "Alpha-shape parameter.",
                "notes": "Large values yield coarser features.",
            },
        ],
        "Ball Pivoting": [
            {
                "label": "Hole Size",
                "parameter": "hole_size",
                "type": "float",
                "min": -1.0,
                "default": -1.0,
                "description": "Maximum surface area of holes considered for triangulation.",
            },
            {
                "label": "Downsample",
                "parameter": "downsample_input",
                "type": "boolean",
                "default": True,
                "description": "Thin input point cloud to core.",
            },
            {
                "label": "Smoothing Steps",
                "parameter": "smoothing_steps",
                "type": "number",
                "default": 5,
                "description": "Pre-smoothing steps before fairing.",
                "notes": "Improves repair but less impactful for topolgoy than weights.",
            },
        ],
    },
}

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
