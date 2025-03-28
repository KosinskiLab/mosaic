import sys
from qtpy.QtWidgets import (
    QApplication,
    QDialog,
    QTabWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QGroupBox,
    QCheckBox,
    QComboBox,
    QScrollArea,
    QSpinBox,
    QDoubleSpinBox,
    QWidget,
    QGridLayout,
    QFrame,
)
import qtawesome as qta

from mosaic.stylesheets import (
    QGroupBox_style,
    QPushButton_style,
    QScrollArea_style,
    QTabBar_style,
)


class FilePathSelector(QWidget):
    """Reusable component for file path selection with browse button"""

    def __init__(self, label_text, placeholder="", parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Label
        self.label = QLabel(label_text)
        self.label.setStyleSheet("font-weight: 500;")
        self.layout.addWidget(self.label)
        self.label.setFixedWidth(200)

        # Path input and browse button
        self.input_layout = QHBoxLayout()
        self.input_layout.setContentsMargins(0, 0, 0, 0)

        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText(placeholder)

        self.browse_button = QPushButton("Browse")
        self.browse_button.setStyleSheet(QPushButton_style)
        self.browse_button.setFixedWidth(80)

        self.input_layout.addWidget(self.path_input)
        self.input_layout.addWidget(self.browse_button)

        self.layout.addLayout(self.input_layout)

    def get_path(self):
        return self.path_input.text()

    def set_path(self, path):
        self.path_input.setText(path)


class InputDataTab(QWidget):
    """Tab for input data selection"""

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        # Create a scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(12, 12, 12, 12)
        self.scroll_layout.setSpacing(16)

        # Target section
        self.target_group = QGroupBox("Target")
        self.target_layout = QVBoxLayout(self.target_group)
        self.tomogram_selector = FilePathSelector("Tomogram:", "Path to target file")
        self.target_layout.addWidget(self.tomogram_selector)

        self.target_mask_selector = FilePathSelector(
            "Target Mask (Optional):", "Path to target mask"
        )
        self.target_layout.addWidget(self.target_mask_selector)
        self.scroll_layout.addWidget(self.target_group)

        # Templates section
        self.template_group = QGroupBox("Template")
        self.template_layout = QVBoxLayout(self.template_group)
        self.template_selector = FilePathSelector("Template:", "Path to template file")
        self.template_layout.addWidget(self.template_selector)
        self.template_mask_selector = FilePathSelector(
            "Template Mask (Optional):", "Path to template mask"
        )
        self.template_layout.addWidget(self.template_mask_selector)
        self.scroll_layout.addWidget(self.template_group)

        # Orientation Constraints section
        self.orientation_group = QGroupBox("Orientation Constraints")
        self.orientation_layout = QGridLayout(self.orientation_group)

        # Orientations file
        self.orientations_selector = FilePathSelector(
            "Orientations File (Optional):", "Path to orientations file"
        )
        self.orientation_layout.addWidget(self.orientations_selector, 0, 0, 1, 2)

        # Orientations scale
        scale_label = QLabel("Orientations Scale:")
        scale_label.setStyleSheet("font-weight: 500;")
        self.scale_input = QDoubleSpinBox()
        self.scale_input.setValue(1.0)
        self.scale_input.setRange(0.1, 100.0)
        self.scale_input.setSingleStep(0.1)

        self.orientation_layout.addWidget(scale_label, 1, 0)
        self.orientation_layout.addWidget(self.scale_input, 1, 1)

        self.scroll_layout.addWidget(self.orientation_group)

        self.scroll_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area)


class MatchingTab(QWidget):
    """Tab for matching settings"""

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        # Create a scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(12, 12, 12, 12)
        self.scroll_layout.setSpacing(16)

        # Angular Sampling section
        self.angular_group = QGroupBox("Angular Sampling")
        self.angular_layout = QGridLayout(self.angular_group)

        # Angular step
        step_label = QLabel("Angular Step (degrees):")
        step_label.setStyleSheet("font-weight: 500;")
        self.step_input = QSpinBox()
        self.step_input.setValue(30)
        self.step_input.setRange(1, 180)

        # Score function
        score_label = QLabel("Score Function:")
        score_label.setStyleSheet("font-weight: 500;")
        self.score_combo = QComboBox()
        self.score_combo.addItems(["FLCSphericalMask", "FLC"])

        # Cone angle from input data tab
        cone_label = QLabel("Cone Angle (degrees):")
        cone_label.setStyleSheet("font-weight: 500;")
        self.cone_input = QDoubleSpinBox()
        self.cone_input.setValue(15.0)
        self.cone_input.setRange(0.0, 180.0)
        self.cone_input.setSingleStep(0.5)

        self.angular_layout.addWidget(step_label, 0, 0)
        self.angular_layout.addWidget(self.step_input, 0, 1)
        self.angular_layout.addWidget(score_label, 1, 0)
        self.angular_layout.addWidget(self.score_combo, 1, 1)
        self.angular_layout.addWidget(cone_label, 2, 0)
        self.angular_layout.addWidget(self.cone_input, 2, 1)

        self.scroll_layout.addWidget(self.angular_group)

        # Filters section
        self.filters_group = QGroupBox("Filters")
        self.filters_layout = QGridLayout(self.filters_group)

        # Lowpass
        lowpass_label = QLabel("Lowpass (Å):")
        lowpass_label.setStyleSheet("font-weight: 500;")
        self.lowpass_input = QLineEdit()
        self.lowpass_input.setPlaceholderText("e.g., 20")

        # Highpass
        highpass_label = QLabel("Highpass (Å):")
        highpass_label.setStyleSheet("font-weight: 500;")
        self.highpass_input = QLineEdit()
        self.highpass_input.setPlaceholderText("e.g., 200")

        self.filters_layout.addWidget(lowpass_label, 0, 0)
        self.filters_layout.addWidget(self.lowpass_input, 0, 1)
        self.filters_layout.addWidget(highpass_label, 1, 0)
        self.filters_layout.addWidget(self.highpass_input, 1, 1)

        self.scroll_layout.addWidget(self.filters_group)

        # Missing Wedge section
        self.wedge_group = QGroupBox("Missing Wedge")
        self.wedge_layout = QGridLayout(self.wedge_group)

        # Tilt Range
        tilt_label = QLabel("Tilt Range:")
        tilt_label.setStyleSheet("font-weight: 500;")
        self.tilt_input = QLineEdit()
        self.tilt_input.setPlaceholderText("e.g., -60,60")
        tilt_help = QLabel("Format: start,stop:step")
        tilt_help.setStyleSheet("color: #64748b; font-size: 10px;")

        # Wedge Axes
        axes_label = QLabel("Wedge Axes:")
        axes_label.setStyleSheet("font-weight: 500;")
        self.axes_input = QLineEdit()
        self.axes_input.setPlaceholderText("e.g., 2,0")
        axes_help = QLabel("Format: opening,tilt")
        axes_help.setStyleSheet("color: #64748b; font-size: 10px;")

        self.wedge_layout.addWidget(tilt_label, 0, 0)
        self.wedge_layout.addWidget(self.tilt_input, 0, 1)
        self.wedge_layout.addWidget(tilt_help, 1, 1)
        self.wedge_layout.addWidget(axes_label, 2, 0)
        self.wedge_layout.addWidget(self.axes_input, 2, 1)
        self.wedge_layout.addWidget(axes_help, 3, 1)

        self.scroll_layout.addWidget(self.wedge_group)

        # CTF Correction section
        self.ctf_group = QGroupBox("CTF Correction")
        self.ctf_layout = QGridLayout(self.ctf_group)

        # Defocus
        defocus_label = QLabel("Defocus (Å):")
        defocus_label.setStyleSheet("font-weight: 500;")
        self.defocus_input = QLineEdit()
        self.defocus_input.setPlaceholderText("e.g., 15000")

        # Whitening
        self.whitening_check = QCheckBox("Apply spectral whitening")

        self.ctf_layout.addWidget(defocus_label, 0, 0)
        self.ctf_layout.addWidget(self.defocus_input, 0, 1)
        self.ctf_layout.addWidget(self.whitening_check, 1, 0, 1, 2)

        self.scroll_layout.addWidget(self.ctf_group)

        self.scroll_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area)


class PeakCallingTab(QWidget):
    """Tab for peak calling settings"""

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        # Create a scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(12, 12, 12, 12)
        self.scroll_layout.setSpacing(16)

        # Peak Calling Settings section
        self.peak_group = QGroupBox("Peak Calling Settings")
        self.peak_layout = QGridLayout(self.peak_group)

        # Peak Caller
        caller_label = QLabel("Peak Caller:")
        caller_label.setStyleSheet("font-weight: 500;")
        self.caller_combo = QComboBox()
        self.caller_combo.addItems(
            [
                "PeakCallerScipy",
                "PeakCallerMaximumFilter",
                "PeakCallerSort",
                "PeakCallerFast",
            ]
        )

        # Number of Peaks
        peaks_label = QLabel("Number of Peaks:")
        peaks_label.setStyleSheet("font-weight: 500;")
        self.peaks_input = QSpinBox()
        self.peaks_input.setValue(1000)
        self.peaks_input.setRange(1, 100000)

        # Minimum Distance
        distance_label = QLabel("Minimum Distance (voxels):")
        distance_label.setStyleSheet("font-weight: 500;")
        self.distance_input = QSpinBox()
        self.distance_input.setValue(16)
        self.distance_input.setRange(1, 1000)

        self.peak_layout.addWidget(caller_label, 0, 0)
        self.peak_layout.addWidget(self.caller_combo, 0, 1)
        self.peak_layout.addWidget(peaks_label, 1, 0)
        self.peak_layout.addWidget(self.peaks_input, 1, 1)
        self.peak_layout.addWidget(distance_label, 2, 0)
        self.peak_layout.addWidget(self.distance_input, 2, 1)

        self.scroll_layout.addWidget(self.peak_group)

        self.scroll_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area)


class ComputeTab(QWidget):
    """Tab for computation settings"""

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        # Create a scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(12, 12, 12, 12)
        self.scroll_layout.setSpacing(16)

        # Computation Settings section
        self.compute_group = QGroupBox("Computation Settings")
        self.compute_layout = QGridLayout(self.compute_group)

        # CPU Cores
        cores_label = QLabel("CPU Cores:")
        cores_label.setStyleSheet("font-weight: 500;")
        self.cores_input = QSpinBox()
        self.cores_input.setValue(4)
        self.cores_input.setRange(1, 128)

        # Memory Usage
        memory_label = QLabel("Memory Usage:")
        memory_label.setStyleSheet("font-weight: 500;")
        self.memory_input = QLineEdit()
        self.memory_input.setText("85%")
        self.memory_input.setPlaceholderText("e.g., 85% or 16GB")

        # GPU Acceleration
        self.gpu_check = QCheckBox("Use GPU acceleration")

        self.compute_layout.addWidget(cores_label, 0, 0)
        self.compute_layout.addWidget(self.cores_input, 0, 1)
        self.compute_layout.addWidget(memory_label, 1, 0)
        self.compute_layout.addWidget(self.memory_input, 1, 1)
        self.compute_layout.addWidget(self.gpu_check, 2, 0, 1, 2)

        self.scroll_layout.addWidget(self.compute_group)

        # Output Options section
        self.output_group = QGroupBox("Output Options")
        self.output_layout = QVBoxLayout(self.output_group)

        self.output_selector = FilePathSelector(
            "Output Directory:", "Path to output directory"
        )
        self.output_layout.addWidget(self.output_selector)

        self.scroll_layout.addWidget(self.output_group)

        self.scroll_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area)


class TemplateMatchingDialog(QDialog):

    def __init__(self):
        from mosaic.icons import dialog_accept_icon, dialog_reject_icon

        super().__init__()
        self.setWindowTitle("Pytme setup")
        self.resize(750, 600)

        self.layout = QVBoxLayout(self)
        self.tabs = QTabWidget()

        self.input_tab = InputDataTab()
        self.matching_tab = MatchingTab()
        self.peak_tab = PeakCallingTab()
        self.compute_tab = ComputeTab()

        self.tabs.addTab(
            self.input_tab, qta.icon("fa5s.file-import", color="#4f46e5"), "Visualize"
        )
        self.tabs.addTab(
            self.matching_tab, qta.icon("fa5s.sliders-h", color="#4f46e5"), "Matching"
        )
        self.tabs.addTab(
            self.peak_tab, qta.icon("fa5s.search", color="#4f46e5"), "Peak Calling"
        )
        self.tabs.addTab(
            self.compute_tab, qta.icon("fa5s.server", color="#4f46e5"), "Compute"
        )

        self.layout.addWidget(self.tabs)

        self.footer = QFrame()
        self.footer.setStyleSheet("border-top: 1px solid #e5e7eb;")
        self.footer.setContentsMargins(10, 0, 10, 0)

        footer_layout = QHBoxLayout(self.footer)

        self.help_text = QLabel("Define target tomogram and template structures")
        self.help_text.setStyleSheet("border-top: 0px;")
        self.tabs.currentChanged.connect(self.update_help_text)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setIcon(dialog_reject_icon)
        self.cancel_button.clicked.connect(self.reject)

        self.run_button = QPushButton("Done")
        self.run_button.setIcon(dialog_accept_icon)
        self.run_button.clicked.connect(self.accept)

        footer_layout.addWidget(self.help_text)
        footer_layout.addStretch()
        footer_layout.addWidget(self.cancel_button)
        footer_layout.addWidget(self.run_button)

        self.layout.addWidget(self.footer)
        self.setStyleSheet(
            QTabBar_style + QPushButton_style + QScrollArea_style + QGroupBox_style
        )

    def update_help_text(self, index):
        help_texts = [
            "Define target tomogram and template structures",
            "Configure template matching parameters",
            "Set up peak calling for candidate detection",
            "Configure computing resources and output",
        ]
        self.help_text.setText(help_texts[index])


if __name__ == "__main__":
    app = QApplication(sys.argv)
    dialog = TemplateMatchingDialog()

    dialog.show()
    sys.exit(app.exec())
