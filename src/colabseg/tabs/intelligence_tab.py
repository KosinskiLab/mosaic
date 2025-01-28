import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout

from ..widgets.ribbon import create_button
from ..segmentation import MEMBRAIN_SETTINGS


def noop(*args, **kwargs):
    return None


class IntelligenceTab(QWidget):
    def __init__(self, cdata, ribbon):
        super().__init__()
        self.cdata = cdata
        self.ribbon = ribbon

        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ribbon)

    def show_ribbon(self):
        self.ribbon.clear()

        segmentation_actions = [
            create_button(
                "Add", "mdi.plus", self, self.add_cloud, "Merge selected clusters"
            ),
            create_button(
                "Membrane",
                "mdi.border-all-variant",
                self,
                self.add_cloud,
                "Segment membranes using Membrain-seg",
                MEMBRAIN_SETTINGS,
            ),
        ]
        self.ribbon.add_section("Segmentation Operations", segmentation_actions)

    def add_cloud(self, *args):
        num_points = 1000
        points = np.random.rand(num_points, 3) * 100
        self.cdata._data.add(points=points, sampling_rate=1)
        self.cdata.data.data_changed.emit()
        self.cdata.data.render()
