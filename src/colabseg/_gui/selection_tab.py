""" Implements the segmentation GUI tab.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np
import qtawesome as qta
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QScrollArea,
    QFrame,
    QPushButton,
    QGridLayout,
    QComboBox,
    QFileDialog,
)
from PyQt6.QtCore import Qt, QEvent

from .widgets import HistogramWidget
from .dialog import (
    format_tooltip,
    show_parameter_dialog,
    make_param,
    ParameterHandler,
    DistanceAnalysisDialog,
    DistanceStatsDialog,
    DistanceCropDialog,
)
from ..io_utils import import_points
from ..plane_trimmer import PlaneTrimmer


class ClusterSelectionTab(QWidget):
    def __init__(self, cdata):
        super().__init__()
        self.cdata = cdata
        self.setup_ui()
        self.cdata.data.vtk_widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Handle Escape key to exit trimmer mode."""
        if not self.plane_trimmer:
            return super().eventFilter(obj, event)

        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.plane_trimmer.cleanup()
                self.plane_trimmer = None
                return True

            if key in (Qt.Key.Key_X, Qt.Key.Key_C, Qt.Key.Key_Z):
                axis = {Qt.Key.Key_X: "x", Qt.Key.Key_C: "y", Qt.Key.Key_Z: "z"}[key]

                self.plane_trimmer.align_to_axis(
                    self.plane_trimmer.plane_widget1, f"-{axis}"
                )
                self.plane_trimmer.align_to_axis(
                    self.plane_trimmer.plane_widget2, f"{axis}"
                )
                return True

        return super().eventFilter(obj, event)

    def setup_ui(self):
        layout_spacing = 5
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(layout_spacing)

        self.setup_cluster_list(main_layout)
        self.setup_cluster(main_layout)
        self.setup_points(main_layout)
        self.setup_histogram(main_layout)
        self.setup_distance(main_layout)

    def setup_cluster_list(self, main_layout):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFixedWidth(150)

        cluster_list = self.cdata.data.data_list
        cluster_list.setMinimumWidth(130)
        scroll_area.setWidget(cluster_list)

        main_layout.addWidget(scroll_area, 1)

    def setup_cluster(self, main_layout):
        operations_layout = QVBoxLayout()
        operations_layout.setSpacing(5)

        self.setup_cluster_operations(operations_layout)
        self.setup_cluster_editing_operations(operations_layout)
        main_layout.addLayout(operations_layout)

    def setup_points(self, main_layout):
        editing_layout = QVBoxLayout()
        editing_layout.setSpacing(5)

        self.setup_point_operations(editing_layout)
        self.setup_point_editing_operations(editing_layout)
        main_layout.addLayout(editing_layout)

    def setup_cluster_operations(self, operations_layout):
        self.cluster_buttons = {}
        cluster_ops_frame = QFrame()
        cluster_ops_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        cluster_ops_layout = QVBoxLayout(cluster_ops_frame)
        cluster_ops_mapping = [
            ("Merge Cluster", self.cdata.data.merge_cluster),
            ("Remove Cluster", self.cdata.data.remove_cluster),
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
            ("Merge Points", self.cdata.data.cluster_points),
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

        # TODO: Fix QEventPoint issue on trackpad
        self.cdata.data.data_changed.connect(self.update_histogram)
        self.histogram_widget.cutoff_changed.connect(self.cdata.data._on_cutoff_changed)

    def update_histogram(self):
        self.histogram_widget.update_histogram(self.cdata._data.get_cluster_size())

    def setup_cluster_editing_operations(self, main_layout):
        analysis_frame = QFrame()
        analysis_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        analysis_layout = QGridLayout(analysis_frame)

        name = "Thinning"
        button, params = QPushButton(name), THINNING_OPERATIONS[name]
        button.clicked.connect(
            lambda checked, op=name, params=params: show_parameter_dialog(
                op, params, self, {"Thinning": self.cdata.data.decimate}, button
            )
        )
        analysis_layout.addWidget(button, 0, 0)

        name = "Clustering"
        button = QPushButton(name)
        button.clicked.connect(
            lambda checked, op=name, params=CLUSTER_OPERATIONS: show_parameter_dialog(
                op,
                params,
                self,
                {
                    "Clustering": self.cdata.data.cluster,
                },
                button,
            )
        )
        tooltip = {
            "title": "DBSCAN Clustering",
            "description": "Cluster points based on density and proximity.",
            "notes": "Useful for finding clusters of arbitrary shape",
        }
        button.setToolTip(format_tooltip(**tooltip))
        analysis_layout.addWidget(button, 1, 0)
        main_layout.addWidget(analysis_frame)

    def setup_point_editing_operations(self, main_layout):
        analysis_frame = QFrame()
        analysis_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        analysis_layout = QGridLayout(analysis_frame)

        self.plane_trimmer = None
        plane_trim_button = QPushButton("Trim Range")
        plane_trim_button.clicked.connect(self._toggle_plane_trimmer)
        plane_trim_button.setToolTip("Select points using two adjustable planes")
        analysis_layout.addWidget(plane_trim_button, 0, 0)

        operations_mapping = {
            "Remove Outlier": self.cdata.data.remove_outliers,
        }

        for row, (name, parameters) in enumerate(POINT_OPERATIONS.items()):
            button = QPushButton(name)
            button.clicked.connect(
                lambda checked, op=name, params=parameters: show_parameter_dialog(
                    op, params, self, operations_mapping[name], button
                )
            )
            button.setToolTip(format_tooltip(**POINT_OPERATION_TOOLTIPS[name]))
            analysis_layout.addWidget(button, row + 1, 0)

        main_layout.addWidget(analysis_frame)

    def _toggle_plane_trimmer(self):
        if self.plane_trimmer is not None:
            self.plane_trimmer.toggle(False)
            self.plane_trimmer.cleanup()
            self.plane_trimmer = None
            return True

        self.plane_trimmer = PlaneTrimmer(self.cdata.data)
        self.plane_trimmer.toggle(True)

    def setup_distance(self, main_layout):
        analysis_layout = QVBoxLayout()
        analysis_layout.setSpacing(5)

        self.setup_distance_cropping(analysis_layout)
        self.setup_distance_comparison(analysis_layout)
        main_layout.addLayout(analysis_layout)

    def setup_distance_cropping(self, main_layout):
        operations_layout = QVBoxLayout()

        frame = QFrame()
        frame.setFrameStyle(QFrame.Shape.StyledPanel)
        frame_layout = QGridLayout(frame)

        stats_button = QPushButton("Distance Crop")
        stats_button.clicked.connect(self._distance_crop)
        frame_layout.addWidget(stats_button, 0, 0)

        import_button = QPushButton("Distance Statistics")
        import_button.clicked.connect(self._compute_stats)
        frame_layout.addWidget(import_button, 1, 0)

        operations_layout.addWidget(frame)
        main_layout.addLayout(operations_layout)

    def _format_datalist(self, type="data"):
        interactor, container = self.cdata.data, self.cdata._data
        if type == "models":
            interactor, container = self.cdata.models, self.cdata._models

        ret = []
        for i in range(interactor.data_list.count()):
            list_item = interactor.data_list.item(i)
            ret.append((list_item.text(), container.data[i]))
        return ret

    def _compute_stats(self):
        clusters = self._format_datalist(type="data")
        dialog = DistanceStatsDialog(clusters, self)
        return dialog.show()

    def _distance_crop(self):
        clusters = self._format_datalist(type="data")
        dialog = DistanceCropDialog(clusters, self)
        sources, targets, distance = dialog.get_results()
        if sources is None:
            return -1

        # Build points attribute first to avoid synchronization issues
        for source in sources:
            temp_targets = [x for x in targets if x != source]
            target_points = np.concatenate(
                [self.cdata._data._get_cluster_points(x) for x in temp_targets]
            )
            self.cdata._data.data[source]._meta["points"] = target_points

        for source in sources:
            self.cdata._data.crop(indices=[source], distance=distance)
            _ = self.cdata._data.data[source]._meta.pop("points")
        self.cdata.data.render()

    def setup_distance_comparison(self, main_layout):
        operations_layout = QVBoxLayout()

        frame = QFrame()
        frame.setFrameStyle(QFrame.Shape.StyledPanel)
        frame_layout = QGridLayout(frame)

        import_button = QPushButton("Import Points")
        import_button.clicked.connect(self._import_points)

        selector = QComboBox()
        selector.addItems(IMPORT_OPERATIONS.keys())
        fit_settings = QPushButton()
        fit_settings.setIcon(qta.icon("fa5s.sliders-h", opacity=0.7))
        fit_settings.setFixedSize(25, 25)

        self.import_handler = ParameterHandler(
            IMPORT_OPERATIONS, fit_settings, selector
        )
        fit_settings.clicked.connect(self.import_handler.show_dialog)

        frame_layout.addWidget(import_button, 0, 0)
        frame_layout.addWidget(fit_settings, 0, 1)

        import_button = QPushButton("Analyze Distances")
        import_button.clicked.connect(self._analyze_distances)
        frame_layout.addWidget(import_button, 1, 0, 1, 2)

        operations_layout.addWidget(frame)
        main_layout.addLayout(operations_layout)

    def _import_points(self, **kwargs):
        parameters = self.import_handler.get("Import Points", {})
        parameters.update(kwargs)

        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Point Files",
            "",
            "Point Files (*.xyz *.star *.csv *.tsv);;All Files (*.*)",
        )

        if not filenames:
            return -1

        # from tme import Density
        # from ..geometry import VolumeGeometry

        # filename = filenames[0]
        # # dens = Density.from_file(filename)
        # dens = Density.from_file(
        #     "/home/vmaurer/Documents/hmff/mycoplasma.nosync/matching/emd_17132_resampled.mrc"
        # )
        # points = import_points(filename, **parameters)

        # normals = np.random.randint(low=0, high=360, size=(points[0].shape[0], 3))
        # normals = normals / np.linalg.norm(normals, axis=1)[:, None]

        # volume_geom = VolumeGeometry(
        #     volume=dens.data * -1,
        #     volume_sampling_rate=dens.sampling_rate,
        #     points=points[0].astype(np.float32),
        #     meta={"filename": filename, "density": dens},
        #     normals=normals,
        #     sampling_rate=dens.sampling_rate,
        # )

        # # Add to data structure
        # self.cdata._data.data.append(volume_geom)
        # self.cdata.data.data_changed.emit()
        # self.cdata.data.render()
        # return -1

        for filename in filenames:
            points = import_points(filename, **parameters)
            for point in points:
                self.cdata._data.add(points=point.astype(np.float32))

        self.cdata.data.data_changed.emit()
        self.cdata.data.render()
        return 0

    def _analyze_distances(self):
        fits = self._format_datalist("models")
        clusters = self._format_datalist("data")

        dialog = DistanceAnalysisDialog(clusters, fits=fits, parent=self)
        return dialog.show()


THINNING_OPERATIONS = {
    "Thinning": [
        make_param(
            "method",
            "core",
            ["outer", "core", "inner"],
            "Reduce cluster to outer, core or inner points.",
        ),
    ],
}

CLUSTER_OPERATIONS = {
    "Connected Components": [],
    "DBSCAN": [
        make_param(
            "distance",
            40,
            0,
            "Maximum distance between two neighbors.",
            notes="Larger values create bigger clusters (Only used by DBSCAN).",
        ),
        make_param(
            "min_points", 20, 0, "Minimum number of points required to form a cluster."
        ),
    ],
    "K-Means": [
        make_param("k", 2, 1, "Number of clusters"),
    ],
}

POINT_OPERATIONS = {
    "Remove Outlier": [
        make_param(
            "k_neighbors",
            10,
            0,
            "k-Neighbors to consider for detecting outliers.",
            notes="Affects the local density estimation",
        ),
        make_param(
            "thresh",
            0.02,
            0,
            "Threshold for outlier detection.",
            notes="Threshold is sdev for statistical, eigenvalue ratio otherwise.",
        ),
        make_param(
            "method",
            "statistical",
            ["statistical", "eigenvalue"],
            "Statistical - General outliers. Eigenvalue - Noisy Edges",
        ),
    ],
}

POINT_OPERATION_TOOLTIPS = {
    "Remove Outlier": {
        "title": "Outlier Removal",
        "description": "Remove points that deviate from local distribution.",
        "notes": "Useful for general outliers and noisy edges",
    },
    "Trim Range": {
        "title": "Trim Range",
        "description": "Remove points outside specified range along an axis.",
        "notes": "Useful for trimming lamellas",
    },
}


IMPORT_OPERATIONS = {
    "Import Points": [
        make_param("scale", 1.0, 0.0, "Scale imported points by 1 / scale."),
        make_param("offset", 0.0, -1e32, "Add offset as (points - offset) / scale "),
    ],
}
