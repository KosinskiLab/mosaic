import numpy as np
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QScrollArea,
    QFrame,
    QPushButton,
    QGridLayout,
    QComboBox,
    QStyle,
    QFileDialog,
)

from .widgets import HistogramWidget
from ..io import import_points
from .dialog import (
    format_tooltip,
    show_parameter_dialog,
    make_param,
    ParameterHandler,
    DistanceAnalysisDialog,
    DistanceStatsDialog,
    DistanceCropDialog,
)


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

        operations_mapping = {
            "Trim Range": self.cdata.data.trim,
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
            analysis_layout.addWidget(button, row, 0)

        main_layout.addWidget(analysis_frame)

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

    def _format_clusters(self):
        clusters = []
        for i in range(self.cdata.data.data_list.count()):
            list_item = self.cdata.data.data_list.item(i)
            clusters.append((list_item.text(), self.cdata._data._get_cluster_points(i)))
        return clusters

    def _compute_stats(self):
        clusters = self._format_clusters()
        dialog = DistanceStatsDialog(clusters, self)
        return dialog.show()

    def _distance_crop(self):
        clusters = self._format_clusters()
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
        fit_settings.setIcon(
            self.style().standardIcon(
                QStyle.StandardPixmap.SP_ToolBarVerticalExtensionButton
            )
        )
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
            "Point Files (*.xyz *.pts *.csv *.tsv);;All Files (*.*)",
        )

        if not filenames:
            return -1

        for filename in filenames:
            points = import_points(filename, **parameters)
            for point in points:
                self.cdata._data.add(points=point.astype(np.float32))
        self.cdata.data.render()
        return 0

    def _analyze_distances(self):
        clusters = self._format_clusters()

        dialog = DistanceAnalysisDialog(clusters, self)
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
    "Trim Range": [
        make_param("min_value", 50, 0, "Points below this value will be removed."),
        make_param("max_value", 100, 0, "Points above this value will be removed."),
        make_param(
            "axis", "x", ["x", "y", "z"], "Axis along which to perform trimming."
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
