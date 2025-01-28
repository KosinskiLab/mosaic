import numpy as np

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QDialog,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)


class DistanceStatsDialog(QDialog):
    def __init__(self, cluster_data, parent=None):
        super().__init__(parent)
        self.cluster_data = cluster_data
        self.setWindowTitle("Distance Statistics")
        self.setup_ui()
        self.resize(900, 450)

    def setup_ui(self):
        layout = QVBoxLayout()
        self.table = QTableWidget()

        stats_header = ["Cluster", "Points", "Centroid", "Std", "Min", "Max", "Density"]
        self.table.setColumnCount(len(stats_header))
        self.table.setRowCount(len(self.cluster_data))
        self.table.setHorizontalHeaderLabels(stats_header)

        for row, (name, geometry) in enumerate(self.cluster_data):
            self.table.setItem(row, 0, QTableWidgetItem(name))
            stats = self.calculate_stats(geometry.points)
            for col, value in enumerate(stats, start=1):
                if isinstance(value, tuple):
                    text = f"({value[0]:.2f}, {value[1]:.2f}, {value[2]:.2f})"
                else:
                    text = str(value)
                self.table.setItem(row, col, QTableWidgetItem(text))

        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        export_btn = QPushButton("Export Statistics")
        export_btn.clicked.connect(self.export_stats)
        layout.addWidget(self.table)
        layout.addWidget(export_btn)
        self.setLayout(layout)

    def calculate_stats(self, points):
        mins = np.min(points, axis=0)
        maxs = np.max(points, axis=0)
        volume = np.prod(maxs - mins)
        density = len(points) / volume if volume > 0 else 0
        return [
            len(points),
            tuple(np.mean(points, axis=0)),
            tuple(np.std(points, axis=0)),
            tuple(mins),
            tuple(maxs),
            density,
        ]

    def export_stats(self):
        sep = "\t"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Statistics", "", "TSV Files (*.tsv)"
        )
        if not filename:
            return -1

        rows = []
        headers = [
            self.table.horizontalHeaderItem(i).text()
            for i in range(self.table.columnCount())
        ]
        rows.append(sep.join(headers))

        for row in range(self.table.rowCount()):
            row_data = [
                self.table.item(row, col).text()
                for col in range(self.table.columnCount())
            ]
            rows.append(sep.join(row_data))

        with open(filename, mode="w", encoding="utf-8") as ofile:
            ofile.write("\n".join(rows))
        QMessageBox.information(self, "Success", "Data saved successfully.")
