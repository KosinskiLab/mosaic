import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFileDialog

from ..formats import open_file
from ..widgets.ribbon import create_button
from ..segmentation import MEMBRAIN_SETTINGS, run_membrainseg


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
                self._run_membrain,
                "Segment membranes using Membrain-seg",
                MEMBRAIN_SETTINGS,
            ),
        ]
        self.ribbon.add_section("Segmentation Operations", segmentation_actions)

    def _run_membrain(self, **kwargs):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select Tomogram", "", "MRC Files (*.mrc);;All Files (*.*)"
        )
        if not file_name:
            return None

        if kwargs.get("model_path", "") == "":
            print("Missing path to membrain model.")
            return None

        output_name = run_membrainseg(tomogram_path=file_name, **kwargs)
        if output_name is None:
            return None

        container = open_file(output_name)
        for index in range(len(container)):
            data = container[index]
            self.cdata._data.add(
                points=data.vertices, normals=data.normals, sampling_rate=data.sampling
            )
        self.cdata.data.data_changed.emit()
        return self.cdata.data.render()

    def add_cloud(self, *args):
        num_points = 1000
        points = np.random.rand(num_points, 3) * 100
        self.cdata._data.add(points=points, sampling_rate=1)
        self.cdata.data.data_changed.emit()
        self.cdata.data.render()
