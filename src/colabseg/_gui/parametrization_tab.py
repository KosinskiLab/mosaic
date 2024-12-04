""" Implements the Fits GUI tab.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""
import textwrap
from os import makedirs
from os.path import exists, join

import numpy as np
import qtawesome as qta
import matplotlib.pyplot as plt
from tme import Density
from tme.preprocessing import BandPassFilter
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QLocale
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QScrollArea,
    QFrame,
    QPushButton,
    QComboBox,
    QLineEdit,
    QSizePolicy,
    QGridLayout,
    QFileDialog,
    QStyle,
    QSlider,
    QLabel,
    QMessageBox,
)

from .widgets import ProgressButton
from .dialog import HMFFDialog, MeshEquilibrationDialog, make_param, ParameterHandler
from ..parametrization import TriangularMesh
from ..io_utils import import_mesh_trajectory, write_topology_file
from ..meshing.utils import (
    to_open3d,
    equilibrate_edges,
    remesh,
    compute_edge_lengths,
    scale,
    compute_scale_factor_lower,
    center_mesh,
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


class ParametrizationTab(QWidget):
    def __init__(self, cdata):
        from ..interactor import LinkedDataContainerInteractor

        super().__init__()
        self.cdata = cdata
        self.linked_interactor = LinkedDataContainerInteractor(self.cdata.data)
        self.setup_ui()

    def setup_ui(self):
        layout_spacing = 5
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(layout_spacing)

        self.setup_cluster_list(main_layout)
        self.setup_operations(main_layout)
        self.setup_fit_list(main_layout)
        self.setup_trajectory(main_layout)
        main_layout.addStretch()

    def setup_cluster_list(self, main_layout):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFixedWidth(150)

        cluster_list = self.linked_interactor.data_list
        cluster_list.setMinimumWidth(130)
        scroll_area.setWidget(cluster_list)

        main_layout.addWidget(scroll_area, 1)

    def setup_fit_list(self, main_layout):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFixedWidth(150)

        fit_list = self.cdata.models.data_list
        fit_list.setMinimumWidth(130)
        scroll_area.setWidget(fit_list)

        main_layout.addWidget(scroll_area, 1)

    def setup_operations(self, main_layout):
        operations_layout = QVBoxLayout()
        operations_layout.setSpacing(5)

        self.setup_fitting_frame(operations_layout)
        self.setup_sampling_frame(operations_layout)

        main_layout.addLayout(operations_layout)

    def setup_fitting_frame(self, operations_layout):
        frame = QFrame()
        frame.setFrameStyle(QFrame.Shape.StyledPanel)
        grid_layout = QGridLayout(frame)
        grid_layout.setSpacing(8)

        frame.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        frame.setMaximumWidth(300)

        # Create widgets
        self.fit_button = ProgressButton("Fit")
        self.fit_button.clicked.connect(self.add_fit)

        self.fit_selector = QComboBox()
        self.fit_selector.addItems(FIT_OPERATIONS.keys())
        fit_settings = QPushButton()
        fit_settings.setIcon(qta.icon("fa5s.sliders-h", opacity=0.7))
        fit_settings.setFixedSize(25, 25)

        self.fit_handler = ParameterHandler(
            FIT_OPERATIONS, fit_settings, self.fit_selector
        )
        self.fit_selector.currentTextChanged.connect(self.fit_handler.update_button)
        fit_settings.clicked.connect(self.fit_handler.show_dialog)

        grid_layout.addWidget(self.fit_button, 0, 0)
        grid_layout.addWidget(self.fit_selector, 0, 1)
        grid_layout.addWidget(fit_settings, 0, 2)

        # Delete row
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self.cdata.models.remove_cluster)
        grid_layout.addWidget(delete_button, 2, 0, 1, 3)

        operations_layout.addWidget(frame)

    def setup_sampling_frame(self, operations_layout):
        frame = QFrame()
        frame.setFrameStyle(QFrame.Shape.StyledPanel)
        frame_layout = QGridLayout(frame)
        frame_layout.setSpacing(8)

        sample_button = QPushButton("Sample Fit")
        sample_button.clicked.connect(self.sample_fit)
        self.sampling_rate_selector = QComboBox()

        SAMPLING_OPTIONS = {
            "Options": [
                make_param(
                    "Sampling Method",
                    "N points",
                    ["N points", "Avg Distance"],
                    "Sampling method to use. Use Avg Distance for equidistant sampling.",
                )
            ],
        }

        selector = QComboBox()
        selector.addItems(SAMPLING_OPTIONS.keys())
        sampling_settings = QPushButton()
        sampling_settings.setIcon(qta.icon("fa5s.sliders-h", opacity=0.7))
        sampling_settings.setFixedSize(25, 25)
        self.sampling_handler = ParameterHandler(
            SAMPLING_OPTIONS, sampling_settings, selector
        )
        sampling_settings.clicked.connect(self.sampling_handler.show_dialog)

        self.sampling_rate_input = QLineEdit()
        self.sampling_rate_input.setFixedSize(75, 25)
        self.sampling_rate_input.setPlaceholderText("1000")
        validator = QDoubleValidator()
        validator.setLocale(QLocale.c())
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        validator.setBottom(0)
        self.sampling_rate_input.setValidator(validator)

        frame_layout.addWidget(sample_button, 0, 0)
        frame_layout.addWidget(self.sampling_rate_input, 0, 1)
        frame_layout.addWidget(sampling_settings, 0, 2)

        to_cluster = QPushButton("To Cluster")
        to_cluster.clicked.connect(self.fit_to_cluster)
        frame_layout.addWidget(to_cluster, 1, 0, 1, 3)

        operations_layout.addWidget(frame)

    def setup_trajectory(self, main_layout):
        operations_layout = QVBoxLayout()
        operations_layout.setSpacing(5)

        self.setup_trajectory_player(operations_layout)
        self.setup_equilibration_frame(operations_layout)

        main_layout.addLayout(operations_layout)

    def setup_equilibration_frame(self, operations_layout):
        frame = QFrame()
        frame.setFrameStyle(QFrame.Shape.StyledPanel)
        frame.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

        frame_layout = QGridLayout(frame)

        button = QPushButton("Equilibrate Mesh")
        button.clicked.connect(self.equilibrate_fit)
        frame_layout.addWidget(button, 0, 0)

        button = QPushButton("Setup HMFF")
        button.clicked.connect(self.setup_hmff)
        frame_layout.addWidget(button, 1, 0)

        operations_layout.addWidget(frame)

    def setup_trajectory_player(self, main_layout):
        from .selection_tab import IMPORT_OPERATIONS

        frame = QFrame()
        frame.setFrameStyle(QFrame.Shape.StyledPanel)

        frame_layout = QGridLayout(frame)

        self.mesh_trajectory = None
        self.current_frame = 0
        self.playing = False
        self.play_timer = QTimer()
        self.play_timer.timeout.connect(self.next_frame)
        self.play_timer.setInterval(100)

        import_trajectory = QPushButton("Open Trajectory")
        import_trajectory.clicked.connect(self.open_series)

        selector = QComboBox()
        selector.addItems(IMPORT_OPERATIONS.keys())
        import_settings = QPushButton()
        import_settings.setIcon(qta.icon("fa5s.sliders-h", opacity=0.7))
        import_settings.setFixedSize(25, 25)

        self.import_handler = ParameterHandler(
            IMPORT_OPERATIONS, import_settings, selector
        )
        import_settings.clicked.connect(self.import_handler.show_dialog)

        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setEnabled(False)
        self.frame_slider.valueChanged.connect(lambda x: self.display_frame(x))

        playback_layout = QHBoxLayout()
        prev_button = QPushButton()
        prev_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSkipBackward)
        )
        prev_button.clicked.connect(self.prev_frame)

        self.play_button = QPushButton()
        self.play_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        )
        self.play_button.clicked.connect(self.toggle_play)

        next_button = QPushButton()
        next_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward)
        )

        next_button.clicked.connect(self.next_frame)
        self.frame_label = QLabel("Frame: 0/0")
        self.frame_label.setFixedWidth(100)
        playback_layout.addWidget(prev_button)
        playback_layout.addWidget(self.play_button)
        playback_layout.addWidget(next_button)

        frame_layout.addWidget(import_trajectory, 0, 0)
        frame_layout.addWidget(import_settings, 0, 1)
        frame_layout.addLayout(playback_layout, 0, 2)
        frame_layout.addWidget(self.frame_label, 1, 0)
        frame_layout.addWidget(self.frame_slider, 1, 1, 1, 2)

        main_layout.addWidget(frame)

    def open_series(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Directory with Point Cloud Series",
            "",
            QFileDialog.Option.ShowDirsOnly,
        )
        if not directory:
            return

        self.current_geometry = None
        self.mesh_trajectory = import_mesh_trajectory(directory)

        parameters = self.import_handler.get("Import Points", {})
        scale = parameters.get("scale", 1)
        offset = parameters.get("offset", 0)

        for index in range(len(self.mesh_trajectory)):
            faces = self.mesh_trajectory[index][1].astype(int)
            points = (self.mesh_trajectory[index][0] - offset) / scale
            fit = TriangularMesh(to_open3d(points, faces))
            meta = {
                "points": points,
                "faces": faces,
                "fit": fit,
                "normal": fit.compute_normal(points),
            }
            self.mesh_trajectory[index] = (points, meta)

        if len(self.mesh_trajectory) == 0:
            return -1

        self.current_frame = 0
        self.frame_slider.setMinimum(0)
        self.frame_slider.setMaximum(len(self.mesh_trajectory) - 1)
        self.frame_slider.setEnabled(True)
        self.frame_slider.setValue(0)
        self.display_frame(0)

    def display_frame(self, frame_idx: int):
        if not self.mesh_trajectory:
            return -1

        if frame_idx < 0 or frame_idx >= len(self.mesh_trajectory):
            if self.playing:
                self.toggle_play()
            return -1

        self.current_frame = frame_idx
        self.frame_slider.setValue(self.current_frame)

        n_frames = len(self.mesh_trajectory) - 1
        n_digits = len(str(n_frames))
        self.frame_label.setText(f"Frame: {frame_idx:0{n_digits}d}/{n_frames}")

        selected_indices = self.cdata.models._get_selected_indices()
        points, meta = self.mesh_trajectory[frame_idx]
        if self.current_geometry is None:
            index = self.cdata._models.add(points=points)
            self.current_geometry = self.cdata._models.data[index]
            self.cdata.models.render()

        self.current_geometry.swap_data(points)
        self.current_geometry._meta.update(meta)
        if selected_indices:
            return self.cdata.models.set_selection(selected_indices)

        return self.cdata.models.render_vtk()

    def next_frame(self):
        return self.display_frame(self.current_frame + 1)

    def prev_frame(self):
        return self.display_frame(self.current_frame - 1)

    def toggle_play(self):
        if len(self.mesh_trajectory) == 0:
            return -1

        self.playing = not self.playing
        if self.playing:
            if self.current_frame == len(self.mesh_trajectory) - 1:
                self.current_frame = 0
            self.play_button.setIcon(
                self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause)
            )
            self.play_timer.start()
            return None

        self.play_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        )
        self.play_timer.stop()

    def add_fit(self, **kwargs):
        self.fit_button.listen(self.cdata.progress)

        method = self.fit_selector.currentText()
        parameters = self.fit_handler.get(method, {})

        self.fit_worker = FitWorker(self.cdata, method=method, **parameters)
        self.fit_worker.finished.connect(self._on_fit_complete)
        self.fit_button.cancel.connect(self.fit_worker.kill)
        self.fit_worker.start()

    def _on_fit_complete(self):
        self.fit_worker.deleteLater()
        self.fit_worker = None

        self.cdata.data.render()
        self.cdata.models.render()

    def sample_fit(self):
        try:
            sampling = float(self.sampling_rate_input.text())
        except Exception:
            sampling = 1000

        parameters = self.sampling_handler.get("Options", {})
        sampling_method = parameters.get("Sampling Method", "N points")
        return self.cdata.sample_fit(sampling=sampling, method=sampling_method)

    def crop_fit(self, *args, **kwargs):
        return self.cdata.models.crop_cluster(*args, **kwargs)

    def fit_to_cluster(self, *args, **kwargs):
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

    def export_fit(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getSaveFileName(self, "Save File")
        if not file_path:
            return -1

        method = self.export_format.currentText()
        parameters = self.export_handler.get(method, {})

        return self.cdata.export_fit(
            file_path=file_path, file_format=method, **parameters
        )

    def equilibrate_fit(self):
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

        dialog = MeshEquilibrationDialog(None)
        if dialog.exec():
            parameters = dialog.get_parameters()
        else:
            return -1

        directory = QFileDialog.getExistingDirectory(
            self,
            "Select or Create Directory",
            options=QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if not directory:
            return -1

        makedirs(directory, exist_ok=True)

        mesh_base = geometry._meta.get("fit").mesh
        edge_length = parameters.get("average_edge_length", 40)
        lower_bound = parameters.pop("lower_bound", (1 - 0.25) * edge_length)
        upper_bound = parameters.pop("upper_bound", (1 + 0.25) * edge_length)
        etarget = parameters.get("scaling_lower", 1.0)

        filename = f"{directory}/mesh"
        with open(f"{filename}.txt", mode="w", encoding="utf-8") as ofile:
            ofile.write("file\tscale_factor\toffset\n")

            # Baseline without remeshing
            scale_factor = compute_scale_factor_lower(mesh_base, lower_bound=etarget)
            mesh_scale = scale(mesh_base, scale_factor)
            mesh_data, offset = center_mesh(mesh_scale)
            fname = f"{filename}_base.q"
            write_topology_file(file_path=fname, data=mesh_data)
            ofile.write(f"{fname}\t{scale_factor}\t{offset}\n")
            dist_base = compute_edge_lengths(mesh_scale)

            # Remeshed
            mesh = remesh(mesh_base, edge_length, n_iter=500)
            scale_factor = compute_scale_factor_lower(mesh, lower_bound=etarget)
            mesh_scale = scale(mesh, scale_factor)
            mesh_data, offset = center_mesh(mesh_scale)
            fname = f"{filename}_remeshed.q"
            write_topology_file(file_path=fname, data=mesh_data)
            ofile.write(f"{fname}\t{scale_factor}\t{offset}\n")
            dist_remesh = compute_edge_lengths(mesh_scale)

            # Equilibrated
            ret = equilibrate_edges(
                mesh, lower_bound=lower_bound, upper_bound=upper_bound, **parameters
            )
            scale_factor = compute_scale_factor_lower(ret, lower_bound=etarget)
            mesh_scale = scale(ret, scale_factor)
            mesh_data, offset = center_mesh(mesh_scale)
            fname = f"{filename}_equilibrated.q"
            write_topology_file(file_path=fname, data=mesh_data)
            ofile.write(f"{fname}\t{scale_factor}\t{offset}\n")
            dist_equil = compute_edge_lengths(mesh_scale)

            plt.style.use("seaborn-v0_8")
            plt.figure(figsize=(10, 6))
            plt.hist(
                dist_base,
                bins=30,
                alpha=0.6,
                color="#1f77b4",
                label="Baseline",
                density=True,
            )
            plt.hist(
                dist_remesh,
                bins=30,
                alpha=0.6,
                color="#2ca02c",
                label="Remeshed",
                density=True,
            )
            plt.hist(
                dist_equil,
                bins=30,
                alpha=0.6,
                color="#ff7f0e",
                label="Equilibrated",
                density=True,
            )

            plt.xlabel("Edge Lengths")
            plt.ylabel("Frequency")
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(
                f"{filename}_edgelength_histogram.png", dpi=300, bbox_inches="tight"
            )
            plt.close()

        return -1

    def setup_hmff(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select directory with equilibrated meshes.",
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

        p = dialog.get_parameters()

        mesh_index = ret["file"].index(p["mesh"])
        mesh_offset = -float(ret["offset"][mesh_index])
        mesh_scale = ret["scale_factor"][mesh_index]

        data = Density.from_file(p["volume_path"])
        if np.allclose(data.sampling_rate, 1):
            print(
                f"Sampling of {p['volume_path']} is 1 along all axes."
                "If thats not intended, please adapt the respective files."
            )

        sampling, origin = data.sampling_rate, data.origin
        bpf = BandPassFilter(
            lowpass=p["lowpass_cutoff"],
            highpass=p["highpass_cutoff"],
            sampling_rate=np.max(sampling),
            use_gaussian=True,
            shape_is_real_fourier=True,
            return_real_fourier=True,
        )
        template_ft = np.fft.rfftn(data.data, s=data.shape)

        mask = bpf(shape=template_ft.shape)["data"]
        np.multiply(template_ft, mask, out=template_ft)
        data = np.fft.irfftn(template_ft, s=data.shape).real

        dpath = join(directory, "density.mrc")
        Density(data, origin=origin, sampling_rate=sampling).to_file(dpath)

        integrator = "MetropolisAlgorithm"
        if p["threads"] != 1:
            integrator = "MetropolisAlgorithmOpenMP"
        dts_config = textwrap.dedent(
            f"""
            EnergyMethod             = FreeDTS1.0_MDFF {p['volume_path']} {p['xi']} 0 \
            {mesh_scale} {mesh_offset} {int(p['invert_contrast'])} \
            {p['gradient_step_size']}
            Integrator_Type          = MC_Simulation
            VertexPositionIntegrator = {integrator} 1 1 0.05
            AlexanderMove            = {integrator} 1
            InclusionPoseIntegrator  = MetropolisAlgorithm 1 1
            VisualizationFormat      = VTUFileFormat VTU_F 100
            NonbinaryTrajectory      = TSI TrajTSI 1000
            Kappa                    = {p['kappa']} 0 0
            Temperature              = 1 0
            Set_Steps                = 1 5000
            Min_Max_Lenghts          = 1 8
            TimeSeriesData_Period    = 100
            VolumeCoupling           = No SecondOrder 0.0 10000 0.7
            GlobalCurvatureCoupling  = No HarmonicPotential 180 0.3
            TotalAreaCoupling        = No HarmonicPotential 1000 0.34
            Box_Centering_F          = 0
        """
        )

        dts_config_path = join(directory, "input.dts")
        with open(dts_config_path, mode="w", encoding="utf-8") as ofile:
            ofile.write(dts_config.strip() + "\n")

        topol_path = join(directory, "topol.top")
        with open(topol_path, mode="w", encoding="utf-8") as ofile:
            ofile.write(f"{p['mesh']} 1\n")

        run_config = textwrap.dedent(
            f"""
            #!/bin/bash
            rm -rf VTU_F TrajTSI
            mkdir -p  {directory}/TrajTSI
            ln -s {p['mesh']} {directory}/TrajTSI/dts0.tsi

            DTS -in {dts_config_path} \\
                -top {topol_path} \\
                -e {p['steps']} \\
                -nt {p['threads']} \\
                -seed 76532
        """
        )

        with open(join(directory, "run.sh"), mode="w", encoding="utf-8") as ofile:
            ofile.write(run_config.strip() + "\n")

        QMessageBox.information(self, "Success", "HMFF directory setup successfully.")

        return 0


FIT_OPERATIONS = {
    "Sphere": [],
    "Ellipsoid": [],
    "Cylinder": [],
    "Mesh": [
        make_param(
            "elastic_weight",
            1.0,
            0.0,
            "Controls mesh smoothness and elasticity.",
            notes="0 - strong anchoring, 1 - no anchoring, > 1 repulsion.",
        ),
        make_param(
            "curvature_weight",
            0.0,
            0.0,
            "Controls propagation of mesh curvature.",
        ),
        make_param(
            "volume_weight",
            0.0,
            0.0,
            "Controls volume pressure.",
        ),
        make_param(
            "hole_size",
            -1,
            -1,
            "Maximum surface area of holes considered for triangulation.",
            notes="Negative values disable hole size checks - 0 corresponds to no fill.",
        ),
        make_param(
            "downsample_input",
            True,
            [True, False],
            "Thin input point cloud to core. Can be omitted if cluster is thinned.",
        ),
        make_param(
            "smoothing_steps",
            5,
            0,
            "Number of pre-smoothing steps.",
            notes="Pre-smoothing improves repair, but has little influence on "
            "final mesh topology. Consider tuning the fairing weights instead.",
        ),
    ],
    "ConvexHull": [
        make_param(
            "alpha",
            1.0,
            0.0,
            "Alpha-shape parameter - Larger values emphasize coarse features.",
        ),
        make_param(
            "elastic_weight",
            0.0,
            0.0,
            "Controls mesh smoothness and elasticity.",
            notes="0 - strong anchoring, 1 - no anchoring, > 1 repulsion.",
        ),
        make_param(
            "curvature_weight",
            0.0,
            0.0,
            "Controls propagation of mesh curvature.",
        ),
        make_param(
            "volume_weight",
            0.0,
            0.0,
            "Controls volume pressure.",
        ),
        make_param(
            "boundary_ring",
            0,
            0,
            "Also optimize n-ring of boundary vertices.",
            notes="This is useful for large structures with ill-defined boundaries.",
        ),
    ],
    "RBF": [make_param("direction", "xy", ["xy", "xz", "yz"], "Plane to fit RBF in.")],
}


EXPORT_OPERATIONS = {
    "txt": [],
    "star": [
        make_param("center", False, [False, True], "Center coordinates (Relion 5)."),
    ],
    "obj": [],
    "mrc": [],
    "xyz": [],
}
