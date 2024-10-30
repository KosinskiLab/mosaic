import numpy as np
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QSizePolicy,
    QFileDialog,
    QLineEdit,
    QLabel,
)
from PyQt6.QtGui import QDoubleValidator

from ..io import DataIO


class DevTab(QWidget):
    def __init__(self, cdata):
        super().__init__()
        self.setup_ui()
        self.cdata = cdata

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        buttons_layout = QVBoxLayout()

        add_cloud_button = QPushButton("Add Cloud")
        add_cloud_button.clicked.connect(self.add_cloud)
        add_cloud_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        import_button = QPushButton("Import Cloud")
        import_button.clicked.connect(self.import_cloud)
        import_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        scale_layout = QHBoxLayout()
        scale_label = QLabel("Scale Factor:")
        self.scale_input = QLineEdit()
        self.scale_input.setValidator(QDoubleValidator())
        self.scale_input.setText("0.03777476638012516")
        scale_layout.addWidget(scale_label)
        scale_layout.addWidget(self.scale_input)

        buttons_layout.addWidget(add_cloud_button)
        buttons_layout.addWidget(import_button)
        buttons_layout.addLayout(scale_layout)

        buttons_widget = QWidget()
        buttons_widget.setLayout(buttons_layout)
        main_layout.addWidget(buttons_widget)

    def add_cloud(self, *args):
        num_points = 1000
        points = np.random.rand(num_points, 3) * 100
        self.cdata._data.add(points=points)
        self.cdata.data.render()

    def import_cloud(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Import Point Cloud File",
        )
        if not file_name:
            return -1

        try:
            scale_factor = float(self.scale_input.text())
        except ValueError:
            scale_factor = 0.03777476638012516

        data, shape, sampling = DataIO().open_file(filename=file_name)
        for points in data:
            self.cdata._data.add(
                points=points * 1 / scale_factor, sampling_rate=sampling
            )
        self.cdata.data.render()
