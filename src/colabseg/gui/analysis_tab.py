from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QFrame,
    QPushButton,
    QComboBox,
    QGridLayout,
    QSpinBox,
    QLabel,
    QDoubleSpinBox,
)


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
