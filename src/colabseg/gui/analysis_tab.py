from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QFrame,
    QPushButton,
    QProgressBar,
    QLabel,
    QSizePolicy,
)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt
import numpy as np


class DistanceWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(np.ndarray)
    error = pyqtSignal(str)

    def __init__(self, positions):
        super().__init__()
        self.positions = positions

    def run(self):
        try:
            n = len(self.positions)
            distances = np.zeros(n)

            for i in range(n):
                distances[i] = np.linalg.norm(self.positions[i])
                progress = int((i + 1) * 100 / n)
                self.progress.emit(progress)
                self.msleep(1)

                if self.isInterruptionRequested():
                    return

            self.finished.emit(distances)

        except Exception as e:
            self.error.emit(str(e))


class AnalysisTab(QWidget):
    def __init__(self, cdata):
        super().__init__()
        self.cdata = cdata
        self._parameter_widgets = {}
        self.worker = None
        self.positions = None
        self.setup_ui()

    def setup_ui(self):
        layout_spacing = 5
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(layout_spacing)
        self.setup_protein_operations(main_layout)
        main_layout.addStretch()

    def setup_protein_operations(self, main_layout):
        # Create a fixed-width frame
        protein_frame = QFrame()
        protein_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        protein_frame.setFixedWidth(300)
        protein_layout = QVBoxLayout(protein_frame)
        protein_layout.setSpacing(10)

        # Create fixed-height container for status elements
        status_container = QFrame()
        status_container.setFixedHeight(100)
        status_layout = QVBoxLayout(status_container)
        status_layout.setContentsMargins(0, 0, 0, 0)

        # Create and configure buttons with fixed height
        load_button = QPushButton("Load Positions")
        analyze_button = QPushButton("Analyze Distances")
        self.cancel_button = QPushButton("Cancel Analysis")

        for button in [load_button, analyze_button, self.cancel_button]:
            button.setFixedHeight(30)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Configure progress bar with fixed height
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(30)
        self.progress_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.progress_bar.hide()

        # Configure status label with fixed height
        self.status_label = QLabel()
        self.status_label.setFixedHeight(30)
        self.status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.hide()

        # Set up button connections
        load_button.clicked.connect(self.load_positions)
        analyze_button.clicked.connect(self.start_analysis)
        self.cancel_button.clicked.connect(self.cancel_analysis)
        self.cancel_button.hide()

        # Add buttons to main layout
        protein_layout.addWidget(load_button)
        protein_layout.addWidget(analyze_button)

        # Add status elements to status container
        status_layout.addWidget(self.progress_bar)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.cancel_button)

        # Add status container to main layout
        protein_layout.addWidget(status_container)

        # Add stretch at the bottom
        protein_layout.addStretch()

        # Add frame to main layout
        main_layout.addWidget(protein_frame)

    def show_temporary_message(self, message, duration=3000, is_error=False):
        """Show a message that automatically disappears after duration milliseconds"""
        self.status_label.setText(message)
        if is_error:
            self.status_label.setStyleSheet("color: red")
        else:
            self.status_label.setStyleSheet("color: green")
        self.status_label.show()

        QTimer.singleShot(duration, self.status_label.hide)

    def load_positions(self):
        self.positions = np.random.rand(1000, 3)
        self.show_temporary_message("Positions loaded successfully!")

    def start_analysis(self):
        if self.positions is None:
            self.show_temporary_message("Please load positions first!", is_error=True)
            return

        self.sender().setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.cancel_button.show()

        self.worker = DistanceWorker(self.positions)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.analysis_finished)
        self.worker.error.connect(self.analysis_error)
        self.worker.start()

    def cancel_analysis(self):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait()
            self.cleanup_analysis()
            self.show_temporary_message("Analysis cancelled by user.")

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def analysis_finished(self, distances):
        self.cleanup_analysis()
        self.show_temporary_message(
            f"Analysis complete! Computed {len(distances)} distances."
        )

    def analysis_error(self, error_message):
        self.cleanup_analysis()
        self.show_temporary_message(f"Analysis failed: {error_message}", is_error=True)

    def cleanup_analysis(self):
        self.progress_bar.hide()
        self.cancel_button.hide()
        for button in self.findChildren(QPushButton):
            if button.text() == "Analyze Distances":
                button.setEnabled(True)
