import numpy as np
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
    QSpinBox,
    QLabel,
    QDoubleSpinBox,
    QFileDialog,
)
from PyQt6.QtCore import Qt

from .data import AVAILABLE_PARAMETRIZATIONS
from .widgets import HistogramWidget
from .selection import LinkedDataContainerInteractor


class ClusterSelectionTab(QWidget):
    def __init__(self, cdata):
        super().__init__()
        self.cdata = cdata
        self.setup_ui()

    def setup_ui(self):
        layout_spacing = 5
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(layout_spacing)

        self.setup_cluster_list(main_layout)
        self.setup_operations(main_layout)
        self.setup_histogram(main_layout)

    def setup_cluster_list(self, main_layout):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFixedWidth(150)

        cluster_list = self.cdata.data.data_list
        cluster_list.setMinimumWidth(130)
        scroll_area.setWidget(cluster_list)

        main_layout.addWidget(scroll_area, 1)

    def setup_operations(self, main_layout):
        operations_layout = QVBoxLayout()
        operations_layout.setSpacing(5)

        self.setup_cluster_operations(operations_layout)
        operations_layout.addStretch()
        self.setup_point_operations(operations_layout)

        main_layout.addLayout(operations_layout)

    def setup_cluster_operations(self, operations_layout):
        self.cluster_buttons = {}
        cluster_ops_frame = QFrame()
        cluster_ops_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        cluster_ops_layout = QVBoxLayout(cluster_ops_frame)
        cluster_ops_mapping = [
            ("Merge Cluster", self.cdata.data.merge_cluster),
            ("Remove Cluster", self.cdata.data.remove_cluster),
            ("Split Cluster", self.cdata.data.split_cluster),
        ]
        for button_text, button_method in cluster_ops_mapping:
            button = QPushButton(button_text)
            button.clicked.connect(button_method)
            cluster_ops_layout.addWidget(button)
            self.cluster_buttons[button_text] = button
        operations_layout.addWidget(cluster_ops_frame)

    def setup_point_operations(self, operations_layout):
        self.point_buttons = {}
        point_ops_frame = QFrame()
        point_ops_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        point_ops_layout = QVBoxLayout(point_ops_frame)
        points_ops_mapping = [
            ("Cluster Points", self.cdata.data.cluster_points),
            ("Remove Points", self.cdata.data.remove_points),
        ]
        for button_text, button_method in points_ops_mapping:
            button = QPushButton(button_text)
            button.clicked.connect(button_method)
            point_ops_layout.addWidget(button)
            self.point_buttons[button_text] = button
        operations_layout.addWidget(point_ops_frame)

    def setup_histogram(self, main_layout):
        histogram_frame = QFrame()
        histogram_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        histogram_layout = QVBoxLayout(histogram_frame)
        self.histogram_widget = HistogramWidget()
        histogram_layout.addWidget(self.histogram_widget)
        main_layout.addWidget(histogram_frame, 1)

        self.cdata._data.data_changed.connect(self.update_histogram)
        self.histogram_widget.cutoff_changed.connect(self.cdata.data._on_cutoff_changed)

    def update_histogram(self):
        self.histogram_widget.update_histogram(self.cdata._data.get_cluster_size())


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
        fit_button = QPushButton("Fit")
        fit_button.clicked.connect(self.add_fit)
        self.param_type_selector = QComboBox()
        self.param_type_selector.addItems(AVAILABLE_PARAMETRIZATIONS.keys())
        grid_layout.addWidget(fit_button, 0, 0)
        grid_layout.addWidget(self.param_type_selector, 0, 1)

        # Crop row
        crop_button = QPushButton("Crop Fit Around Cluster")
        crop_button.clicked.connect(self.crop_fit)
        self.crop_input = QLineEdit()
        self.crop_input.setPlaceholderText("Distance")
        grid_layout.addWidget(crop_button, 1, 0)
        grid_layout.addWidget(self.crop_input, 1, 1)

        # Export row
        export_button = QPushButton("Export Fit")
        export_button.clicked.connect(self.export_fit)
        self.export_format = QComboBox()
        self.export_format.addItems(["txt", "star (relion 4)", "star (relion 5)"])
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

    def add_fit(self):
        self.cdata.add_fit(
            fit_type=self.param_type_selector.currentText(),
        )
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

    def add_cloud(self):
        num_points = 1000
        points = np.random.rand(num_points, 3) * 100
        self.cdata._data.add(points=points)
        self.cdata.data.render()

    def export_fit(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getSaveFileName(self, "Save File")

        return self.cdata.export_fit(
            file_path=file_path, file_format=self.export_format.currentText()
        )


class DevTab(QWidget):
    def __init__(self, cdata):
        super().__init__()
        self.setup_ui()
        self.cdata = cdata

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        add_cloud_layout = QVBoxLayout()
        add_cloud_button = QPushButton("Add Cloud")
        add_cloud_button.clicked.connect(self.add_cloud)
        add_cloud_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        add_cloud_layout.addWidget(add_cloud_button)
        add_cloud_widget = QWidget()
        add_cloud_widget.setLayout(add_cloud_layout)
        main_layout.addWidget(add_cloud_widget)

    def add_cloud(self, *args):
        num_points = 1000
        points = np.random.rand(num_points, 3) * 100
        self.cdata._data.add(points=points)
        self.cdata.data.render()


class AnalysisTab(QWidget):
    def __init__(self, cdata):
        super().__init__()
        self.cdata = cdata
        self._parameter_widgets = {}
        self.setup_ui()

    def setup_ui(self):
        layout_spacing = 5
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(layout_spacing)

        self.setup_protein_operations(main_layout)
        self.setup_open_data(main_layout)
        self.setup_clustering_operations(main_layout)

    def setup_protein_operations(self, main_layout):
        protein_frame = QFrame()
        protein_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        protein_layout = QVBoxLayout(protein_frame)
        protein_buttons = [
            "Load Proteins",
            "Protein Fit Distance",
            "Protein Cluster Distance",
        ]
        for button_text in protein_buttons:
            button = QPushButton(button_text)
            protein_layout.addWidget(button)
        protein_layout.addStretch()
        main_layout.addWidget(protein_frame)

    def setup_open_data(self, main_layout):
        open_data_frame = QFrame()
        open_data_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        open_data_layout = QVBoxLayout(open_data_frame)
        open_data_button = QPushButton("Open Data")
        open_data_layout.addWidget(open_data_button)
        open_data_layout.addStretch()
        main_layout.addWidget(open_data_frame)

    def setup_clustering_operations(self, main_layout):
        analysis_frame = QFrame()
        analysis_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        analysis_layout = QGridLayout(analysis_frame)

        self._create_parameter_widgets(
            analysis_layout,
            0,
            self.dbscan_cluster,
            "DBSCAN clustering",
            [
                ("Neighbor Dist:", 40, 0, QSpinBox),
                ("Min Points:", 20, 0, QSpinBox),
            ],
        )

        self._create_parameter_widgets(
            analysis_layout,
            1,
            self.outlier_removal,
            "Outlier removal",
            [
                ("Num Neighbors:", 100, 0, QSpinBox),
                ("Std Ratio:", 0.2, 0.0, QDoubleSpinBox),
            ],
        )

        self._create_parameter_widgets(
            analysis_layout,
            2,
            self.edge_outlier_removal,
            "Edge outlier removal",
            [
                ("Num Neighbors:", 300, 0, QSpinBox),
                ("Threshold:", 0.0, 0.0, QDoubleSpinBox),
            ],
        )

        self._create_parameter_widgets(
            analysis_layout,
            3,
            self.trim_cluster,
            "Trim",
            [("Trim Min:", 100, 0, QSpinBox), ("Trim Max:", 100, 0, QSpinBox)],
        )

        # Axis selection for trimming
        analysis_layout.addWidget(QLabel("Trim Axis:"), 3, 5)
        self.axis_combo = QComboBox()
        self.axis_combo.addItems(["x", "y", "x"])
        analysis_layout.addWidget(self.axis_combo, 3, 6)

        main_layout.addWidget(analysis_frame)

    def _create_parameter_widgets(self, layout, row, func, button_text, parameters):
        button = QPushButton(button_text)
        button.clicked.connect(func)
        layout.addWidget(button, row, 0)

        self._parameter_widgets[button_text] = []

        for col, (label, value, min_value, widget) in enumerate(parameters, start=1):
            layout.addWidget(QLabel(label), row, col * 2 - 1)
            widget = widget()
            widget.setMinimum(min_value)
            widget.setValue(value)
            if isinstance(widget, QSpinBox):
                widget.setMaximum(2147483647)
            elif isinstance(widget, QDoubleSpinBox):
                widget.setMaximum(float("inf"))
                widget.setDecimals(4)
            self._parameter_widgets[button_text].append(widget)
            layout.addWidget(widget, row, col * 2)

    def trim_cluster(self):
        min_value, max_value, *_ = self._parameter_widgets["DBSCAN clustering"]
        return self.cdata.data.trim(
            min_value=min_value.value(),
            max_value=max_value.value(),
            axis=self.axis_combo.currentText(),
        )

    def dbscan_cluster(self):
        neighbors, min_points, *_ = self._parameter_widgets["DBSCAN clustering"]
        return self.cdata.data.dbscan_cluster(
            distance=neighbors.value(), min_points=min_points.value()
        )

    def outlier_removal(self):
        k_n, thresh, *_ = self._parameter_widgets["Outlier removal"]
        return self.cdata.data.remove_outliers(
            k_neighbors=k_n.value(), std_ratio=thresh.value(), method="statistical"
        )

    def edge_outlier_removal(self):
        k_n, thresh, *_ = self._parameter_widgets["Edge outlier removal"]
        return self.cdata.data.remove_outliers(
            k_neighbors=k_n.value(), thresh=thresh.value(), method="eigenvalue"
        )
