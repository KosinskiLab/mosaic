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
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from .widgets import ProgressButton
from .dialog import show_parameter_dialog
from ..data import AVAILABLE_PARAMETRIZATIONS
from ..interactor import LinkedDataContainerInteractor


class FitWorker(QThread):
    finished = pyqtSignal()

    def __init__(self, cdata, fit_type):
        super().__init__()
        self.cdata = cdata
        self.fit_type = fit_type

    def run(self):
        self.cdata.add_fit(fit_type=self.fit_type)
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

        # Fit row
        self.fit_button = ProgressButton("Fit")
        self.fit_button.clicked.connect(self.add_fit)
        self.param_type_selector = QComboBox()
        self.param_type_selector.addItems(AVAILABLE_PARAMETRIZATIONS.keys())
        grid_layout.addWidget(self.fit_button, 0, 0)
        grid_layout.addWidget(self.param_type_selector, 0, 1)

        # Export row
        export_button = QPushButton("Export")
        export_button.clicked.connect(self.export_fit)
        self.export_format = QComboBox()
        self.export_format.addItems(
            sorted(["txt", "star (relion 4)", "star (relion 5)", "stl", "obj"])
        )
        grid_layout.addWidget(export_button, 2, 0)
        grid_layout.addWidget(self.export_format, 2, 1)

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

        for row, (operation_name, parameters) in enumerate(FIT_OPERATIONS.items()):
            button = QPushButton(operation_name)
            button.clicked.connect(
                lambda checked, op=operation_name, params=parameters: show_parameter_dialog(
                    op, params, self, {"Crop Around Cluster": self.crop_fit}
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
                    op, params, self, operation_mapping
                )
            )
            frame_layout.addWidget(button, row, 0)

        operations_layout.addWidget(frame)

    def add_fit(self):
        self.fit_button.listen(self.cdata.progress)

        self.fit_worker = FitWorker(
            self.cdata, fit_type=self.param_type_selector.currentText()
        )
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

        return self.cdata.export_fit(
            file_path=file_path, file_format=self.export_format.currentText()
        )

    def equilibrate_fit(self):
        indices = self.cdata.models._get_selected_indices()
        if len(indices) != 1:
            print("Can only equilibrate a single mesh at once.")
            return -1
        fit = self.cdata.models.data[indices[0]]

        return -1


FIT_OPERATIONS = {
    "Crop Around Cluster": [
        (
            "distance",
            40,
            0,
            {
                "title": "Distance",
                "description": "Maximum distance between fit and cluster point.",
                "default_value": "40",
            },
        ),
    ],
}

MESH_OPERATIONS = {
    "Equilibrate Mesh": [
        (
            "averge_edge",
            40,
            0,
            {
                "title": "Mean edge length",
                "description": "Average edge length of mesh.",
                "default_value": "35",
            },
        ),
        (
            "lower_bound",
            35,
            0,
            {
                "title": "Lower Bound (lc1)",
                "description": "Minimum edge length of mesh.",
                "default_value": "35",
            },
        ),
        (
            "upper_bound",
            45,
            0,
            {
                "title": "Upper Bound (lc0)",
                "description": "Maximum edge length of mesh.",
                "default_value": "45",
            },
        ),
        (
            "steps",
            5000,
            1,
            {
                "title": "Steps",
                "description": "Maximum number of minimization iterations.",
                "default_value": "5000",
            },
        ),
        (
            "kappa_b",
            300,
            0,
            {
                "title": "Bending Stiffness",
                "description": "Bending energy coefficient (kappa_b).",
                "default_value": "300.0",
            },
        ),
        (
            "kappa_a",
            int(1.0e6),
            0,
            {
                "title": "Area Constraint",
                "description": "Area conservation coefficient (kappa_a).",
                "default_value": "1.0e6",
            },
        ),
        (
            "kappa_v",
            int(1.0e6),
            0,
            {
                "title": "Volume Constraint",
                "description": "Volume conservation coefficient (kappa_v).",
                "default_value": "1.0e6",
            },
        ),
        (
            "kappa_c",
            0.0,
            0,
            {
                "title": "Curvature Energy",
                "description": "Curvature energy coefficient (kappa_c).",
                "default_value": "0.0",
            },
        ),
        (
            "kappa_t",
            int(1.0e5),
            0,
            {
                "title": "Edge Tension",
                "description": "Edge tension coefficient (kappa_t).",
                "default_value": "1.0e5",
            },
        ),
        (
            "kappa_r",
            int(1.0e3),
            0,
            {
                "title": "Repulsion Strength",
                "description": "Surface repulsion coefficient (kappa_r).",
                "default_value": "1.0e3",
            },
        ),
    ],
    "Scale Mesh": [
        (
            "lower_bound",
            1.0,
            0.0,
            {
                "title": "Lower Bound",
                "description": "Lower bound for edge length.",
                "default_value": "1.0",
            },
        ),
        (
            "upper_bound",
            1.7,
            0.0,
            {
                "title": "Upper Bound",
                "description": "Upper bound for edge length.",
                "default_value": "1.7",
            },
        ),
    ],
}
