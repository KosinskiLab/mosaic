from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QFrame,
    QPushButton,
    QComboBox,
    QGridLayout,
    QSpinBox,
    QLabel,
    QDoubleSpinBox,
    QDialog,
    QVBoxLayout,
    QDialogButtonBox,
)


def format_tooltip(title, description, default_value=None, notes=None):
    """Create a formatted HTML tooltip with consistent styling."""
    tooltip = f"""
    <div style='font-family: Arial, sans-serif;'>
        <b style='color: #2c3e50; font-size: 11pt;'>{title}</b>
        <p style='margin: 5px 0; color: #34495e;'>{description}</p>
    """

    if default_value is not None:
        tooltip += f"""
        <p style='margin: 5px 0;'>
            <span style='color: #7f8c8d;'>Default:</span>
            <span style='color: #2980b9;'>{default_value}</span>
        </p>
        """

    if notes:
        tooltip += f"""
        <p style='margin: 5px 0; font-style: italic; color: #95a5a6;'>
            Note: {notes}
        </p>
        """

    tooltip += "</div>"
    return tooltip


class OperationDialog(QDialog):
    def __init__(self, operation_type, parameters, parent=None):
        super().__init__(parent)
        self.operation_type = operation_type
        self.parameters = parameters
        self.parameter_widgets = {}
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle(f"{self.operation_type}")
        layout = QVBoxLayout(self)

        params_layout = QGridLayout()
        for row, param_info in enumerate(self.parameters):
            label, value, min_value, tooltip_info = param_info
            tooltip = format_tooltip(**tooltip_info)

            label_widget = QLabel(label)
            label_widget.setToolTip(tooltip)
            params_layout.addWidget(label_widget, row, 0)

            if isinstance(value, list):
                widget = QComboBox()
                widget.addItems(value)
                widget.setCurrentText(value[0])
            elif isinstance(value, float):
                widget = QDoubleSpinBox()
                widget.setMinimum(min_value)
                widget.setMaximum(float("inf"))
                widget.setDecimals(4)
                widget.setValue(value)
            else:
                widget = QSpinBox()
                widget.setMinimum(min_value)
                widget.setMaximum(2147483647)
                widget.setValue(value)

            widget.setToolTip(tooltip)
            self.parameter_widgets[label] = widget
            params_layout.addWidget(widget, row, 1)

        layout.addLayout(params_layout)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)


class EditingTab(QWidget):
    def __init__(self, cdata):
        super().__init__()
        self.cdata = cdata
        self.setup_ui()

    def setup_ui(self):
        layout_spacing = 5
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(layout_spacing)

        self.setup_clustering_operations(main_layout)
        main_layout.addStretch()

    def setup_clustering_operations(self, main_layout):
        analysis_frame = QFrame()
        analysis_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        analysis_layout = QGridLayout(analysis_frame)

        operations = {
            "Cluster": [
                (
                    "Neighbor Dist:",
                    40,
                    0,
                    {
                        "title": "Neighbor Distance",
                        "description": "Maximum distance between two samples for them to be considered neighbors.",
                        "default_value": "40",
                        "notes": "Larger values create bigger clusters",
                    },
                ),
                (
                    "Min Points:",
                    20,
                    0,
                    {
                        "title": "Minimum Points",
                        "description": "Minimum number of points required to form a dense region.",
                        "default_value": "20",
                        "notes": "Higher values make the algorithm more selective",
                    },
                ),
            ],
            "Outlier": [
                (
                    "Num Neighbors:",
                    100,
                    0,
                    {
                        "title": "Number of Neighbors",
                        "description": "Number of neighboring points to consider when detecting outliers.",
                        "default_value": "100",
                        "notes": "Affects the local density estimation",
                    },
                ),
                (
                    "Std Ratio:",
                    0.2,
                    0.0,
                    {
                        "title": "Standard Deviation Ratio",
                        "description": "Threshold for statistical outlier detection.",
                        "default_value": "0.2",
                        "notes": "Lower values remove more points",
                    },
                ),
            ],
            "Edge Outlier": [
                (
                    "Num Neighbors:",
                    300,
                    0,
                    {
                        "title": "Number of Neighbors",
                        "description": "Number of neighboring points to consider for edge detection.",
                        "default_value": "300",
                        "notes": "Higher values consider larger neighborhoods",
                    },
                ),
                (
                    "Threshold:",
                    0.0,
                    0.0,
                    {
                        "title": "Edge Threshold",
                        "description": "Eigenvalue ratio threshold for edge point detection.",
                        "default_value": "0.0",
                        "notes": "Higher values detect stronger edges",
                    },
                ),
            ],
            "Trim": [
                (
                    "Trim Min:",
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
                    "Trim Max:",
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
                    "Trim Axis:",
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

        operation_tooltips = {
            "Cluster": {
                "title": "DBSCAN Clustering",
                "description": "Cluster points based on density and proximity.",
                "notes": "Effective for finding clusters of arbitrary shape",
            },
            "Outlier": {
                "title": "Statistical Outlier Removal",
                "description": "Remove points that deviate from local point distribution.",
                "notes": "Uses statistical analysis of point neighborhoods",
            },
            "Edge Outlier": {
                "title": "Edge Point Removal",
                "description": "Remove points located on edges of the point cloud.",
                "notes": "Based on local geometric properties",
            },
            "Trim": {
                "title": "Trim Points",
                "description": "Remove points outside specified range along an axis.",
                "notes": "Useful for cropping the point cloud",
            },
        }

        for row, (operation_name, parameters) in enumerate(operations.items()):
            button = QPushButton(operation_name)
            button.clicked.connect(
                lambda checked, op=operation_name, params=parameters: self.show_parameter_dialog(
                    op, params
                )
            )
            button.setToolTip(format_tooltip(**operation_tooltips[operation_name]))
            analysis_layout.addWidget(button, row, 0)

        main_layout.addWidget(analysis_frame)

    def show_parameter_dialog(self, operation_type, parameters):
        dialog = OperationDialog(operation_type, parameters, self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            param_values = {
                label: (
                    widget.currentText()
                    if isinstance(widget, QComboBox)
                    else widget.value()
                )
                for label, widget in dialog.parameter_widgets.items()
            }

            if operation_type == "Trim":
                self.cdata.data.trim(
                    min_value=param_values["Trim Min:"],
                    max_value=param_values["Trim Max:"],
                    axis=param_values["Trim Axis:"],
                )
            elif operation_type == "DBSCAN clustering":
                self.cdata.data.dbscan_cluster(
                    distance=param_values["Neighbor Dist:"],
                    min_points=param_values["Min Points:"],
                )
            elif operation_type == "Outlier removal":
                self.cdata.data.remove_outliers(
                    k_neighbors=param_values["Num Neighbors:"],
                    std_ratio=param_values["Std Ratio:"],
                    method="statistical",
                )
            elif operation_type == "Edge outlier removal":
                self.cdata.data.remove_outliers(
                    k_neighbors=param_values["Num Neighbors:"],
                    thresh=param_values["Threshold:"],
                    method="eigenvalue",
                )
