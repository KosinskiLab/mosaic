""" Implements the segmentation GUI tab.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import vtk
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

from ..widgets import HistogramWidget
from ..dialogs import (
    format_tooltip,
    show_parameter_dialog,
    make_param,
    ParameterHandler,
    DistanceStatsDialog,
    DistanceCropDialog,
    DistanceAnalysisDialog,
)
from ..io_utils import import_points
from ..plane_trimmer import PlaneTrimmer


class ClusterTransformer:
    def __init__(self, data):
        self.data = data
        self.transform_widget = None
        self.selected_cluster = None

    def cleanup(self):
        """Remove the transform widget and clean up resources."""
        if self.transform_widget:
            self.data.vtk_widget.GetRenderWindow().GetRenderers().GetFirstRenderer().RemoveViewProp(
                self.transform_widget
            )
            self.transform_widget = None
            self.selected_cluster = None
            self.data.vtk_widget.GetRenderWindow().Render()

    def setup_transform_widget(self):
        """Create and configure the 3D widget for transformations."""
        if self.transform_widget:
            return

        self.transform_widget = vtk.vtkBoxWidget()
        self.transform_widget.SetInteractor(
            self.data.vtk_widget.GetRenderWindow().GetInteractor()
        )
        self.transform_widget.SetRotationEnabled(True)
        self.transform_widget.SetTranslationEnabled(True)
        self.transform_widget.SetScalingEnabled(False)

        # Set up the transform callback
        self.transform_widget.AddObserver("InteractionEvent", self.on_transform)

    def on_transform(self, widget, event):
        """Handle transformation updates."""
        if not self.selected_cluster:
            return

        # Get the transformation matrix
        t = vtk.vtkTransform()
        widget.GetTransform(t)
        matrix = np.array(t.GetMatrix()).reshape(4, 4)

        # Get the cluster points
        points = self.data._get_cluster_points(self.selected_cluster)

        # Apply transformation to points
        homogeneous_points = np.ones((len(points), 4))
        homogeneous_points[:, :3] = points

        # Transform points
        transformed_points = (matrix @ homogeneous_points.T).T[:, :3]

        # Update cluster points
        self.data.data[self.selected_cluster].points = transformed_points
        self.data.render()

    def toggle(self, cluster_index=None):
        """Toggle the transform widget for a specific cluster."""
        if self.transform_widget and cluster_index == self.selected_cluster:
            self.cleanup()
            return

        self.selected_cluster = cluster_index
        self.setup_transform_widget()

        if cluster_index is not None:
            # Get cluster bounds
            points = self.data._get_cluster_points(cluster_index)
            bounds = [
                np.min(points[:, 0]),
                np.max(points[:, 0]),
                np.min(points[:, 1]),
                np.max(points[:, 1]),
                np.min(points[:, 2]),
                np.max(points[:, 2]),
            ]

            # Position the widget around the cluster
            self.transform_widget.PlaceWidget(bounds)
            self.transform_widget.On()
            self.data.vtk_widget.GetRenderWindow().Render()


class ClusterSelectionTab(QWidget):
    def __init__(self, cdata):
        super().__init__()
        self.cdata = cdata
        self.setup_ui()
        self.cdata.data.vtk_widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Handle Escape key to exit trimmer mode."""
        # if not self.plane_trimmer:
        #     return super().eventFilter(obj, event)

        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:

                if self.plane_trimmer is not None:
                    self.plane_trimmer.cleanup()
                    self.plane_trimmer = None

                if hasattr(self, "transform_widget"):
                    self.cleanup_transform_widget()

                return True

            if not self.plane_trimmer:
                return super().eventFilter(obj, event)

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

    # def setup_cluster_operations(self, operations_layout):
    #     self.cluster_buttons = {}
    #     cluster_ops_frame = QFrame()
    #     cluster_ops_frame.setFrameStyle(QFrame.Shape.StyledPanel)
    #     cluster_ops_layout = QVBoxLayout(cluster_ops_frame)
    #     cluster_ops_mapping = [
    #         ("Merge Cluster", self.cdata.data.merge_cluster),
    #         ("Remove Cluster", self.cdata.data.remove_cluster),
    #     ]
    #     for button_text, button_method in cluster_ops_mapping:
    #         button = QPushButton(button_text)
    #         button.clicked.connect(button_method)
    #         cluster_ops_layout.addWidget(button)
    #         self.cluster_buttons[button_text] = button
    #     operations_layout.addWidget(cluster_ops_frame)

    def setup_cluster_operations(self, operations_layout):
        self.cluster_buttons = {}
        cluster_ops_frame = QFrame()
        cluster_ops_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        cluster_ops_layout = QVBoxLayout(cluster_ops_frame)
        cluster_ops_mapping = [
            ("Merge Cluster", self.cdata.data.merge_cluster),
            ("Remove Cluster", self.cdata.data.remove_cluster),
            ("Transform Cluster", self.toggle_transform_mode),
        ]
        for button_text, button_method in cluster_ops_mapping:
            button = QPushButton(button_text)
            button.clicked.connect(button_method)
            cluster_ops_layout.addWidget(button)
            self.cluster_buttons[button_text] = button
        operations_layout.addWidget(cluster_ops_frame)

    def toggle_transform_mode(self):
        """Handle transform mode toggling."""
        selected_items = self.cdata.data.data_list.selectedItems()
        if not selected_items:
            return

        # If widget exists and is enabled, turn it off and clean up
        if hasattr(self, "transform_widget") and self.transform_widget.GetEnabled():
            self.transform_widget.Off()
            self.transform_widget.SetEnabled(0)
            self.cdata.data.vtk_widget.GetRenderWindow().Render()
            return

        cluster_index = self.cdata.data.data_list.row(selected_items[0])
        if not hasattr(self, "transform_widget"):
            self.transform_widget = vtk.vtkBoxWidget()
            self.transform_widget.SetInteractor(
                self.cdata.data.vtk_widget.GetRenderWindow().GetInteractor()
            )
            self.transform_widget.HandlesOn()
            self.transform_widget.SetRotationEnabled(True)
            self.transform_widget.SetTranslationEnabled(True)
            self.transform_widget.SetScalingEnabled(False)

            self.transform_widget.AddObserver("InteractionEvent", self.on_transform)
            self.transform_widget.SetPriority(1.0)

        points = self.cdata._data.data[cluster_index].points
        mins = np.min(points, axis=0)
        maxs = np.max(points, axis=0)

        bounds = []
        padding = np.multiply(maxs - mins, 0.55)
        for min_val, max_val, pad in zip(mins, maxs, padding):
            bounds.extend([min_val - pad, max_val + pad])

        self.transform_widget.PlaceWidget(bounds)
        self.transform_widget.On()
        self.selected_cluster = cluster_index
        self.original_points = points.copy()
        self.cdata.data.render_vtk()

    def on_transform(self, widget, event):
        """Handle transformation updates."""
        if not hasattr(self, "selected_cluster") or not hasattr(
            self, "original_points"
        ):
            return

        t = vtk.vtkTransform()
        widget.GetTransform(t)

        vmatrix = t.GetMatrix()
        matrix = np.eye(4)
        vmatrix.DeepCopy(matrix.ravel(), vmatrix)

        rotation = matrix[:3, :3]
        translation = matrix[:3, 3]

        only_translate = np.allclose(rotation, np.eye(3), rtol=1e-10)

        new_points = self.original_points.copy()
        if not only_translate:
            new_points = np.matmul(new_points, rotation.T, out=new_points)

        new_points = np.add(new_points, translation, out=new_points)

        # Update cluster points and render
        self.cdata._data.data[self.selected_cluster].swap_data(new_points=new_points)
        self.cdata.data.render()

    def cleanup_transform_widget(self):
        """Clean up the transform widget."""
        if hasattr(self, "transform_widget"):
            self.transform_widget.Off()
            self.transform_widget.SetEnabled(0)
            if hasattr(self, "original_points"):
                del self.original_points
            self.cdata.data.vtk_widget.GetRenderWindow().Render()

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
