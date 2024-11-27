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
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from .widgets import ProgressButton
from .dialog import show_parameter_dialog, make_param, ParameterHandler
from ..interactor import LinkedDataContainerInteractor


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
        self.setup_editing(main_layout)
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

        # name = "Fit"
        # self.fit_button = ProgressButton(name)
        # self.fit_button.clicked.connect(
        #     lambda checked, op=name, params=FIT_OPERATIONS: show_parameter_dialog(
        #         op, params, self, {"Fit": self.add_fit}, self.fit_button
        #     )
        # )
        # grid_layout.addWidget(self.fit_button, 0, 0, 1, 2)

        # Create widgets
        self.fit_button = ProgressButton("Fit")
        self.fit_button.clicked.connect(self.add_fit)

        self.fit_selector = QComboBox()
        self.fit_selector.addItems(FIT_OPERATIONS.keys())
        fit_settings = QPushButton()
        fit_settings.setIcon(
            self.style().standardIcon(
                QStyle.StandardPixmap.SP_ToolBarVerticalExtensionButton
            )
        )
        fit_settings.setFixedSize(25, 25)

        self.fit_handler = ParameterHandler(
            FIT_OPERATIONS, fit_settings, self.fit_selector
        )
        self.fit_selector.currentTextChanged.connect(self.fit_handler.update_button)
        fit_settings.clicked.connect(self.fit_handler.show_dialog)

        grid_layout.addWidget(self.fit_button, 0, 0)
        grid_layout.addWidget(self.fit_selector, 0, 1)
        grid_layout.addWidget(fit_settings, 0, 2)

        # Export row
        export_button = QPushButton("Export")
        export_button.clicked.connect(self.export_fit)
        self.export_format = QComboBox()
        self.export_format.addItems(sorted(["txt", "star", "obj", "mrc", "xyz"]))

        export_settings = QPushButton()
        export_settings.setIcon(
            self.style().standardIcon(
                QStyle.StandardPixmap.SP_ToolBarVerticalExtensionButton
            )
        )
        export_settings.setFixedSize(25, 25)

        self.export_handler = ParameterHandler(
            EXPORT_OPERATIONS, export_settings, self.export_format
        )
        self.export_format.currentTextChanged.connect(self.export_handler.update_button)
        export_settings.clicked.connect(self.export_handler.show_dialog)

        grid_layout.addWidget(export_button, 2, 0)
        grid_layout.addWidget(self.export_format, 2, 1)
        grid_layout.addWidget(export_settings, 2, 2)

        # Delete row
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self.cdata.models.remove_cluster)

        grid_layout.addWidget(delete_button, 3, 0, 1, 2)

        operations_layout.addWidget(frame)

    def setup_sampling_frame(self, operations_layout):
        frame = QFrame()
        frame.setFrameStyle(QFrame.Shape.StyledPanel)
        frame_layout = QHBoxLayout(frame)

        frame.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        frame.setMaximumWidth(300)

        alignment = Qt.AlignmentFlag.AlignTop
        sample_button = QPushButton("Sample Fit")
        self.sampling_rate_selector = QComboBox()

        self.sampling_rate_input = QLineEdit()
        sample_button.clicked.connect(self.sample_fit)
        self.sampling_rate_selector.addItems(["N points", "Avg Distance"])
        self.sampling_rate_input.setPlaceholderText("1000")

        frame_layout.addWidget(sample_button, alignment=alignment)
        frame_layout.addWidget(self.sampling_rate_selector, alignment=alignment)
        frame_layout.addWidget(self.sampling_rate_input, alignment=alignment)

        operations_layout.addWidget(frame)

    def setup_editing(self, main_layout):
        operations_layout = QVBoxLayout()
        operations_layout.setSpacing(5)

        self.setup_fit_operations(operations_layout)
        self.setup_equilibration_frame(operations_layout)

        main_layout.addLayout(operations_layout)

    def setup_fit_operations(self, operations_layout):
        frame = QFrame()
        frame.setFrameStyle(QFrame.Shape.StyledPanel)
        frame_layout = QGridLayout(frame)

        to_cluster = QPushButton("To Cluster")
        to_cluster.clicked.connect(self.fit_to_cluster)
        frame_layout.addWidget(to_cluster, 0, 0)

        for row, (name, parameters) in enumerate(CROP_OPERATIONS.items()):
            button = QPushButton(name)
            button.clicked.connect(
                lambda checked, op=name, params=parameters: show_parameter_dialog(
                    op, params, self, {"Crop Around Cluster": self.crop_fit}, button
                )
            )
            frame_layout.addWidget(button, row + 1, 0)

        operations_layout.addWidget(frame)

    def setup_equilibration_frame(self, operations_layout):
        frame = QFrame()
        frame.setFrameStyle(QFrame.Shape.StyledPanel)
        frame_layout = QGridLayout(frame)

        operation_mapping = {
            "Equilibrate Mesh": self.equilibrate_fit,
            "Scale Mesh": self.equilibrate_fit,
        }
        for row, (operation_name, parameters) in enumerate(MESH_OPERATIONS.items()):
            button = QPushButton(operation_name)
            button.clicked.connect(
                lambda checked, op=operation_name, params=parameters: show_parameter_dialog(
                    op, params, self, operation_mapping, button
                )
            )
            frame_layout.addWidget(button, row, 0)

        operations_layout.addWidget(frame)

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
            sampling_method = self.sampling_rate_selector.currentText()
        except Exception:
            return -1

        return self.cdata.models.sample_cluster(
            sampling=sampling,
            method=sampling_method,
        )

    def crop_fit(self, *args, **kwargs):
        return self.cdata.models.crop_cluster(*args, **kwargs)

    def fit_to_cluster(self, *args, **kwargs):
        indices = self.cdata.models._get_selected_indices()

        for index in indices:
            if not self.cdata._models._index_ok(index):
                continue

            points = self.cdata._models.data[index].points
            sampling = self.cdata._models.data[index]._sampling_rate
            self.cdata._data.new(points, sampling_rate=sampling)
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
            print("Can only equilibrate a single mesh at once.")
            return -1
        _ = self.cdata.models.data[indices[0]]

        return -1


CROP_OPERATIONS = {
    "Crop Around Cluster": [
        make_param("distance", 40, 0, "Maximum distance between fit and cluster point.")
    ],
}

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
            "Number of pre-smoothing operations.",
            notes="Pre-smoothing improves repair, but has little influence on "
            "final mesh topology. Consider tuning the fairing weights instead.",
        ),
    ],
    "Hull": [
        make_param(
            "alpha",
            1.0,
            0.0,
            "Alpha-shape parameter - Larger values emphasize coarse features.",
        ),
        make_param("smoothing_steps", 0, 0, "Number of smoothing operations."),
    ],
    "FairHull": [
        make_param(
            "alpha",
            1.0,
            0.0,
            "Alpha-shape parameter - Larger values emphasize coarse features.",
        ),
        make_param(
            "elastic_weight",
            1.0,
            0.0,
            "Controls mesh smoothness and elasticity.",
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
            "Controls propagation of mesh curvature.",
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


MESH_OPERATIONS = {
    "Equilibrate Mesh": [
        make_param("average_edge", 40, 0, "Average edge length of mesh."),
        make_param("lower_bound", 35, 0, "Minimum edge length of mesh (lc1)."),
        make_param("upper_bound", 45, 0, "Maximumg edge length of mesh (lc0)."),
        make_param("steps", 5000, 0, "Number of minimization steps."),
        make_param("kappa_b", 300.0, 0, "Bending energy coefficient (kappa_b)."),
        make_param("kappa_b", 1e6, 0, "Area conservation coefficient (kappa_a)."),
        make_param("kappa_v", 1e6, 0, "Volume conservation coefficient (kappa_v)."),
        make_param("kappa_c", 0.0, 0, "Curvature energy coefficient (kappa_c)."),
        make_param("kappa_t", 1e5, 0, "Edge tension coefficient (kappa_t)."),
        make_param("kappa_r", 1e3, 0, "Surface repulsion coefficient (kappa_r)."),
    ],
    "Scale Mesh": [
        make_param("lower_bound", 1.0, 0, "Lower bound for edge length."),
        make_param("upper_bound", 1.7, 0, "Upper bound for edge length."),
    ],
}
