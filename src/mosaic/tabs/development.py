import numpy as np
from qtpy.QtWidgets import QWidget, QVBoxLayout

from ..widgets.ribbon import create_button


def noop(*args, **kwargs):
    return None


class DevelopmentTab(QWidget):
    def __init__(self, cdata, ribbon, **kwargs):
        super().__init__()
        self.cdata = cdata
        self.ribbon = ribbon

        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ribbon)

    def show_ribbon(self):
        self.ribbon.clear()
        cluster_actions = [
            create_button(
                "Add", "mdi.plus", self, self.add_cloud, "Merge selected clusters"
            ),
        ]
        self.ribbon.add_section("Base Operations", cluster_actions)

    def add_cloud(self, *args):
        num_points = 1000
        points = np.random.rand(num_points, 3) * 100
        self.cdata._data.add(points=points, sampling_rate=1)
        self.cdata.data.data_changed.emit()
        self.cdata.data.render()
