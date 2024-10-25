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
        # self.setup_equilibration_frame(main_layout)
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
        operations_layout.addStretch()
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

        # Crop row
        crop_button = QPushButton("Crop Around Cluster")
        crop_button.clicked.connect(self.crop_fit)
        self.crop_input = QLineEdit()
        self.crop_input.setPlaceholderText("Distance")
        grid_layout.addWidget(crop_button, 1, 0)
        grid_layout.addWidget(self.crop_input, 1, 1)

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

    def setup_equilibration_frame(self, operations_layout):
        frame = QFrame()
        frame.setFrameStyle(QFrame.Shape.StyledPanel)
        frame_layout = QGridLayout(frame)

        frame.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        frame.setMaximumWidth(150)

        button = QPushButton("Equilibrate Edge Length")

        self.lower_edge_length = QLineEdit()
        self.lower_edge_length.setPlaceholderText("Lower Bound")
        self.upper_edge_length = QLineEdit()
        self.upper_edge_length.setPlaceholderText("Upper Bound")

        frame_layout.addWidget(self.lower_edge_length, 0, 1)
        frame_layout.addWidget(self.upper_edge_length, 0, 2)
        frame_layout.addWidget(button, 1, 1, 1, 2)

        operations_layout.addWidget(frame)

    def add_fit(self):
        self.fit_button.listen(self.cdata.progress)

        self.fit_worker = FitWorker(
            self.cdata,
            fit_type=self.param_type_selector.currentText()
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

    def crop_fit(self):
        try:
            distance = float(self.crop_input.text())
        except Exception:
            return -1

        return self.cdata.models.crop_cluster(distance=distance)

    def export_fit(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getSaveFileName(self, "Save File")
        if not file_path:
            return -1

        return self.cdata.export_fit(
            file_path=file_path, file_format=self.export_format.currentText()
        )

    def equilibrate_fit(self):
        try:
            lower_bound = float(self.lower_edge_length.currentText())
            upper_bound = float(self.upper_edge_length.currentText())
        except Exception:
            return -1
