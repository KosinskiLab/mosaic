from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QScrollArea,
    QFrame,
    QPushButton,
    QGridLayout,
    QDialog,
    QComboBox,
)

from .widgets import HistogramWidget
from .dialog import format_tooltip, OperationDialog


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
        # operations_layout.addStretch()
        self.setup_cluster_editing_operations(operations_layout)
        main_layout.addLayout(operations_layout)

    def setup_points(self, main_layout):
        editing_layout = QVBoxLayout()
        editing_layout.setSpacing(5)

        self.setup_point_operations(editing_layout)
        # editing_layout.addStretch()
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

        button = QPushButton("Split Cluster")
        button.clicked.connect(self.cdata.data.split_cluster)
        analysis_layout.addWidget(button)
        self.cluster_buttons["Split Cluster"] = button

        for row, (operation_name, parameters) in enumerate(CLUSTER_OPERATIONS.items()):
            button = QPushButton(operation_name)
            button.clicked.connect(
                lambda checked, op=operation_name, params=parameters: self.show_parameter_dialog(
                    op, params
                )
            )
            button.setToolTip(
                format_tooltip(**CLUSTER_OPERATION_TOOLTIPS[operation_name])
            )
            analysis_layout.addWidget(button, row + 1, 0)

        main_layout.addWidget(analysis_frame)

    def setup_point_editing_operations(self, main_layout):
        analysis_frame = QFrame()
        analysis_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        analysis_layout = QGridLayout(analysis_frame)

        for row, (operation_name, parameters) in enumerate(POINT_OPERATIONS.items()):
            button = QPushButton(operation_name)
            button.clicked.connect(
                lambda checked, op=operation_name, params=parameters: self.show_parameter_dialog(
                    op, params
                )
            )
            button.setToolTip(
                format_tooltip(**POINT_OPERATION_TOOLTIPS[operation_name])
            )
            analysis_layout.addWidget(button, row, 0)

        main_layout.addWidget(analysis_frame)

    def show_parameter_dialog(self, operation_type, parameters):
        dialog = OperationDialog(operation_type, parameters, self)

        if dialog.exec() == QDialog.DialogCode.Rejected:
            return -1

        params = {
            label: (
                widget.currentText()
                if isinstance(widget, QComboBox)
                else widget.value()
            )
            for label, widget in dialog.parameter_widgets.items()
        }
        _mapping = {
            "Trim Range": self.cdata.data.trim,
            "Recluster": self.cdata.data.dbscan_cluster,
            "Remove Outlier": self.cdata.data.remove_outliers,
        }

        func = _mapping.get(operation_type)
        if func is None:
            print(
                f"Unknown operation {operation_type}. Supported are {_mapping.keys()}."
            )

        return func(**params)


CLUSTER_OPERATIONS = {
    "Recluster": [
        (
            "distance",
            40,
            0,
            {
                "title": "Neighbor Distance",
                "description": "Maximum distance between two neighbors.",
                "default_value": "40",
                "notes": "Larger values create bigger clusters",
            },
        ),
        (
            "min_points",
            20,
            0,
            {
                "title": "Minimum Points",
                "description": "Minimum number of points required to form a cluster.",
                "default_value": "20",
                "notes": "Higher values make the algorithm more selective",
            },
        ),
    ],
}

POINT_OPERATIONS = {
    "Remove Outlier": [
        (
            "k_neighbors",
            100,
            0,
            {
                "title": "Number of Neighbors",
                "description": "k-Neighbors to consider for detecting outliers.",
                "default_value": "100",
                "notes": "Affects the local density estimation",
            },
        ),
        (
            "thresh",
            0.2,
            0.0,
            {
                "title": "Threshold",
                "description": "Threshold for outlier detection.",
                "default_value": "0.2",
                "notes": "Meaning depends on method - Low values remove more points.",
            },
        ),
        (
            "method",
            ["statistical", "eigenvalue"],
            "statistical",
            {
                "title": "Method",
                "description": "Statistical - General outliers. Eigenvalue - Noisy Edges",
                "default_value": "Statistical",
                "notes": "Threshold is standard deviation for statistical, eigenvalue ratio otherwise.",
            },
        ),
    ],
    "Trim Range": [
        (
            "min_value",
            100,
            0,
            {
                "title": "Minimum Value",
                "description": "Minimum value to keep in the selected axis.",
                "default_value": "100",
                "notes": "Points below this value will be removed",
            },
        ),
        (
            "max_value",
            100,
            0,
            {
                "title": "Maximum Value",
                "description": "Maximum value to keep in the selected axis.",
                "default_value": "100",
                "notes": "Points above this value will be removed",
            },
        ),
        (
            "axis",
            ["x", "y", "z"],
            0,
            {
                "title": "Trim Axis",
                "description": "Axis along which to perform the trimming operation.",
                "default_value": "x",
                "notes": "Choose the spatial dimension to trim",
            },
        ),
    ],
}

CLUSTER_OPERATION_TOOLTIPS = {
    "Recluster": {
        "title": "DBSCAN Clustering",
        "description": "Cluster points based on density and proximity.",
        "notes": "Useful for finding clusters of arbitrary shape",
    }
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
