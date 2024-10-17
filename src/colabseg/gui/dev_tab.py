import numpy as np
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QSizePolicy,
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
