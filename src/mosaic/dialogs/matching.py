import textwrap
from os import makedirs
from os.path import join, splitext

from qtpy.QtWidgets import (
    QDialog,
    QTabWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QGroupBox,
    QCheckBox,
    QComboBox,
    QScrollArea,
    QSpinBox,
    QDoubleSpinBox,
    QWidget,
    QGridLayout,
    QMessageBox,
)
import qtawesome as qta

from ..widgets import PathSelector, DialogFooter
from ..stylesheets import (
    QPushButton_style,
    QScrollArea_style,
    QTabBar_style,
)


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

        self.output_group = QGroupBox("Working Directory")
        self.output_layout = QVBoxLayout(self.output_group)

        self.output_selector = PathSelector(
            "Output Directory:", "Path to working directory", file_mode=False
        )
        self.output_layout.addWidget(self.output_selector)
        self.scroll_layout.addWidget(self.output_group)

        # Target section
        self.target_group = QGroupBox("Target")
        self.target_layout = QVBoxLayout(self.target_group)
        self.tomogram_selector = PathSelector("Tomogram:", "Path to target")
        self.target_layout.addWidget(self.tomogram_selector)

        self.target_mask_selector = PathSelector(
            "Target Mask (Optional):", "Path to target mask"
        )
        self.target_layout.addWidget(self.target_mask_selector)

        self.scroll_layout.addWidget(self.target_group)

        # Templates section
        self.template_group = QGroupBox("Template")
        self.template_layout = QVBoxLayout(self.template_group)
        self.template_selector = PathSelector("Template:", "Path to template")
        self.template_layout.addWidget(self.template_selector)
        self.template_mask_selector = PathSelector(
            "Template Mask (Optional):", "Path to template mask"
        )
        self.template_layout.addWidget(self.template_mask_selector)
        self.scroll_layout.addWidget(self.template_group)

        self.scroll_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area)

    def get_settings(self):
        return {
            "output_directory": self.output_selector.get_path(),
            "tomogram": self.tomogram_selector.get_path(),
            "target_mask": self.target_mask_selector.get_path(),
            "template": self.template_selector.get_path(),
            "template_mask": self.template_mask_selector.get_path(),
        }


class PreprocessTab(QWidget):
    """Tab for template preprocessing"""

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)

        self.skip_group = QGroupBox("Control")
        self.skip_layout = QVBoxLayout(self.skip_group)
        self.skip_preprocessing_check = QCheckBox(
            "Skip preprocessing (template is already prepared)"
        )
        self.skip_preprocessing_check.setToolTip(
            "Use this option if your template is already correctly prepared"
        )
        self.skip_preprocessing_check.setChecked(False)
        self.skip_preprocessing_check.toggled.connect(self._toggle_options)
        self.skip_layout.addWidget(self.skip_preprocessing_check)
        self.scroll_layout.addWidget(self.skip_group)

        # Filters section
        self.preproc_filters_group = QGroupBox("Filters")
        self.preproc_filters_layout = QGridLayout(self.preproc_filters_group)

        preproc_lowpass_label = QLabel("Lowpass (Å):")
        self.preproc_lowpass_input = QLineEdit()
        self.preproc_lowpass_input.setPlaceholderText("e.g., 20")
        self.preproc_lowpass_input.setToolTip("Low-pass filter cutoff in Angstroms")

        preproc_highpass_label = QLabel("Highpass (Å):")
        self.preproc_highpass_input = QLineEdit()
        self.preproc_highpass_input.setPlaceholderText("e.g., 200")
        self.preproc_highpass_input.setToolTip("High-pass filter cutoff in Angstroms")

        invert_template_label = QLabel("Contrast:")
        self.invert_template_check = QCheckBox("Invert template contrast")
        contrast_help = QLabel("Invert template contrast to match target contrast.")
        contrast_help.setStyleSheet("color: #64748b; font-size: 10px;")

        self.preproc_filters_layout.addWidget(preproc_lowpass_label, 0, 0)
        self.preproc_filters_layout.addWidget(self.preproc_lowpass_input, 0, 1)

        self.preproc_filters_layout.addWidget(preproc_highpass_label, 1, 0)
        self.preproc_filters_layout.addWidget(self.preproc_highpass_input, 1, 1)

        self.preproc_filters_layout.addWidget(invert_template_label, 2, 0)
        self.preproc_filters_layout.addWidget(self.invert_template_check, 2, 1)
        self.preproc_filters_layout.addWidget(contrast_help, 3, 1)
        self.scroll_layout.addWidget(self.preproc_filters_group)

        # Alignment section (for constrained matching)
        self.alignment_group = QGroupBox("Alignment")
        self.alignment_layout = QGridLayout(self.alignment_group)

        align_axis_label = QLabel("Align Template Axis:")
        self.align_axis_combo = QComboBox()
        self.align_axis_combo.addItems(["None", "X", "Y", "Z"])
        self.align_axis_combo.setCurrentIndex(0)
        self.align_axis_combo.setToolTip("Align template along a specific axis")

        align_eigen_label = QLabel("Align Eigenvector:")
        self.align_eigen_combo = QComboBox()
        self.align_eigen_combo.addItems(["0", "1", "2"])
        self.align_eigen_combo.setToolTip("Eigenvector to use for alignment")
        align_help = QLabel(
            "Templates including membrane typically align on eigenvector 2."
        )
        align_help.setStyleSheet("color: #64748b; font-size: 10px;")

        flip_axis_label = QLabel("Flip Template:")
        self.flip_axis_check = QCheckBox("Flip template along alignment axis")
        self.flip_axis_check.setToolTip(
            "Invert template orientation along the alignment axis"
        )

        self.alignment_layout.addWidget(align_axis_label, 0, 0)
        self.alignment_layout.addWidget(self.align_axis_combo, 0, 1)

        self.alignment_layout.addWidget(align_eigen_label, 1, 0)
        self.alignment_layout.addWidget(self.align_eigen_combo, 1, 1)
        self.alignment_layout.addWidget(align_help, 2, 1)

        self.alignment_layout.addWidget(flip_axis_label, 3, 0)
        self.alignment_layout.addWidget(self.flip_axis_check, 3, 1)
        self.scroll_layout.addWidget(self.alignment_group)

        self.scroll_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area)

        self._toggle_options(self.skip_preprocessing_check.isChecked())

    def _toggle_options(self, skip_preprocessing):
        self.preproc_filters_group.setEnabled(not skip_preprocessing)
        self.alignment_group.setEnabled(not skip_preprocessing)

    def get_settings(self):
        return {
            "skip_preprocessing": self.skip_preprocessing_check.isChecked(),
            "lowpass": self.preproc_lowpass_input.text(),
            "highpass": self.preproc_highpass_input.text(),
            "invert_template_contrast": self.invert_template_check.isChecked(),
            "align_axis": self.align_axis_combo.currentText(),
            "align_eigenvector": self.align_eigen_combo.currentText(),
            "flip_template": self.flip_axis_check.isChecked(),
        }


class MatchingTab(QWidget):
    """Tab for matching settings"""

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)

        # Angular Sampling section
        self.angular_group = QGroupBox("Sampling")
        self.angular_layout = QGridLayout(self.angular_group)

        step_label = QLabel("Angular Step (degrees):")
        self.step_input = QSpinBox()
        self.step_input.setValue(5)
        self.step_input.setRange(1, 360)

        score_label = QLabel("Score Function:")
        self.score_combo = QComboBox()
        self.score_combo.addItems(["FLCSphericalMask", "FLC"])

        self.angular_layout.addWidget(step_label, 0, 0)
        self.angular_layout.addWidget(self.step_input, 0, 1)

        self.angular_layout.addWidget(score_label, 1, 0)
        self.angular_layout.addWidget(self.score_combo, 1, 1)
        self.scroll_layout.addWidget(self.angular_group)

        # Constrained template matching
        self.orientation_group = QGroupBox("Constraints")
        self.orientation_layout = QGridLayout(self.orientation_group)

        self.orientations_selector = PathSelector(
            "Orientations File (Optional):", "Path to orientations file"
        )

        scaling_label = QLabel("Scaling:")
        self.orientation_scaling = QDoubleSpinBox()
        self.orientation_scaling.setValue(1.0)
        self.orientation_scaling.setRange(1e-6, 1e12)
        self.orientation_scaling.setSingleStep(0.1)
        scaling_help = QLabel(
            "2 if orientations are at 3 Apx and tomogram is at 6 Apx."
        )
        scaling_help.setStyleSheet("color: #64748b; font-size: 10px;")

        rotational_uncertainty_label = QLabel("Rotational Uncertainty:")
        self.rotational_uncertainty = QLineEdit()
        self.rotational_uncertainty.setPlaceholderText("e.g., 15")
        rotational_uncertainty_help = QLabel(
            "Deviation from seed point normal in degree."
        )
        rotational_uncertainty_help.setStyleSheet("color: #64748b; font-size: 10px;")

        translational_uncertainty_label = QLabel("Translational Uncertainty:")
        self.translational_uncertainty = QLineEdit()
        self.translational_uncertainty.setPlaceholderText("e.g., 10,10,15")
        translational_uncertainty_help = QLabel(
            "x, y, z deviation from seed point in voxel."
        )
        translational_uncertainty_help.setStyleSheet("color: #64748b; font-size: 10px;")

        self.orientation_layout.addWidget(self.orientations_selector, 0, 0, 1, 2)
        self.orientation_layout.addWidget(scaling_label, 1, 0)
        self.orientation_layout.addWidget(self.orientation_scaling, 1, 1)
        self.orientation_layout.addWidget(scaling_help, 2, 1)

        self.orientation_layout.addWidget(rotational_uncertainty_label, 3, 0)
        self.orientation_layout.addWidget(self.rotational_uncertainty, 3, 1)
        self.orientation_layout.addWidget(rotational_uncertainty_help, 4, 1)

        self.orientation_layout.addWidget(translational_uncertainty_label, 5, 0)
        self.orientation_layout.addWidget(self.translational_uncertainty, 5, 1)
        self.orientation_layout.addWidget(translational_uncertainty_help, 6, 1)
        self.scroll_layout.addWidget(self.orientation_group)

        # Filters section
        self.filters_group = QGroupBox("Filters")
        self.filters_layout = QGridLayout(self.filters_group)

        lowpass_label = QLabel("Lowpass (Å):")
        self.lowpass_input = QLineEdit()
        self.lowpass_input.setPlaceholderText("e.g., 20")

        highpass_label = QLabel("Highpass (Å):")
        self.highpass_input = QLineEdit()
        self.highpass_input.setPlaceholderText("e.g., 200")

        tilt_label = QLabel("Tilt Range:")
        self.tilt_input = QLineEdit()
        self.tilt_input.setPlaceholderText("e.g., -60,60")
        tilt_help = QLabel("Format: start_angle,stop_angle")
        tilt_help.setStyleSheet("color: #64748b; font-size: 10px;")

        axes_label = QLabel("Wedge Axes:")
        self.axes_input = QLineEdit()
        self.axes_input.setPlaceholderText("e.g., 2,0")
        axes_help = QLabel("Format: opening_axis,tilt_axis")
        axes_help.setStyleSheet("color: #64748b; font-size: 10px;")

        defocus_label = QLabel("Defocus (Å):")
        self.defocus_input = QLineEdit()
        self.defocus_input.setPlaceholderText("e.g., 30000")

        whitening_label = QLabel("Spectral Whitening:")
        self.whitening_check = QCheckBox("Apply")

        self.filters_layout.addWidget(lowpass_label, 0, 0)
        self.filters_layout.addWidget(self.lowpass_input, 0, 1)
        self.filters_layout.addWidget(highpass_label, 1, 0)
        self.filters_layout.addWidget(self.highpass_input, 1, 1)

        self.filters_layout.addWidget(tilt_label, 2, 0)
        self.filters_layout.addWidget(self.tilt_input, 2, 1)
        self.filters_layout.addWidget(tilt_help, 3, 1)

        self.filters_layout.addWidget(axes_label, 4, 0)
        self.filters_layout.addWidget(self.axes_input, 4, 1)
        self.filters_layout.addWidget(axes_help, 5, 1)

        self.filters_layout.addWidget(defocus_label, 6, 0)
        self.filters_layout.addWidget(self.defocus_input, 6, 1)

        self.filters_layout.addWidget(whitening_label, 7, 0)
        self.filters_layout.addWidget(self.whitening_check, 7, 1)

        self.scroll_layout.addWidget(self.filters_group)

        # Additional Options group
        self.options_group = QGroupBox("Additional Options")
        self.options_layout = QGridLayout(self.options_group)

        # Centering toggle
        centering_label = QLabel("No Centering")
        self.no_centering_check = QCheckBox("Apply")
        self.no_centering_check.setChecked(True)
        axes_help = QLabel("Do not center the template in the box.")
        axes_help.setStyleSheet("color: #64748b; font-size: 10px;")

        self.options_layout.addWidget(centering_label, 0, 0)
        self.options_layout.addWidget(self.no_centering_check, 0, 1)
        self.options_layout.addWidget(axes_help, 1, 1)

        self.scroll_layout.addWidget(self.options_group)

        self.scroll_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area)

    def get_settings(self):
        return {
            "angular_step": self.step_input.value(),
            "score_function": self.score_combo.currentText(),
            "orientations_file": self.orientations_selector.get_path(),
            "orientation_scaling": self.orientation_scaling.value(),
            "rotational_uncertainty": self.rotational_uncertainty.text(),
            "translational_uncertainty": self.translational_uncertainty.text(),
            "lowpass": self.lowpass_input.text(),
            "highpass": self.highpass_input.text(),
            "tilt_range": self.tilt_input.text(),
            "wedge_axes": self.axes_input.text(),
            "defocus": self.defocus_input.text(),
            "whitening": self.whitening_check.isChecked(),
            "no_centering": self.no_centering_check.isChecked(),
        }


class PeakCallingTab(QWidget):
    """Tab for peak calling settings"""

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)

        self.peak_group = QGroupBox("Peak Properties")
        self.peak_layout = QGridLayout(self.peak_group)

        caller_label = QLabel("Peak Caller:")
        self.caller_combo = QComboBox()
        self.caller_combo.addItems(
            [
                "PeakCallerScipy",
                "PeakCallerMaximumFilter",
            ]
        )

        # Number of Peaks
        peaks_label = QLabel("Number of Peaks:")
        self.peaks_input = QSpinBox()
        self.peaks_input.setRange(1, 100000)
        self.peaks_input.setValue(1000)

        # Minimum Distance
        distance_label = QLabel("Minimum Distance (voxels):")
        self.distance_input = QSpinBox()
        self.distance_input.setRange(1, 1000)
        self.distance_input.setValue(10)

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

    def get_settings(self):
        return {
            "peak_caller": self.caller_combo.currentText(),
            "num_peaks": self.peaks_input.value(),
            "min_distance": self.distance_input.value(),
        }


class ComputeTab(QWidget):
    """Tab for computation settings"""

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)

        self.compute_group = QGroupBox("Computation Settings")
        self.compute_layout = QGridLayout(self.compute_group)

        cores_label = QLabel("CPU Cores:")
        self.cores_input = QSpinBox()
        self.cores_input.setValue(4)
        self.cores_input.setRange(1, 128)

        memory_label = QLabel("Memory Usage:")
        self.memory_input = QLineEdit()
        self.memory_input.setPlaceholderText(
            "e.g., 85% to use 85% of available memory."
        )

        backend_label = QLabel("Backend:")
        self.backend_combo = QComboBox()
        self.backend_combo.addItems(["numpy", "cupy"])
        self.backend_combo.setCurrentText("numpy")

        self.compute_layout.addWidget(cores_label, 0, 0)
        self.compute_layout.addWidget(self.cores_input, 0, 1)

        self.compute_layout.addWidget(memory_label, 1, 0)
        self.compute_layout.addWidget(self.memory_input, 1, 1)

        self.compute_layout.addWidget(backend_label, 2, 0)
        self.compute_layout.addWidget(self.backend_combo, 2, 1)

        self.scroll_layout.addWidget(self.compute_group)

        self.scroll_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area)

    def get_settings(self):
        return {
            "cores": self.cores_input.value(),
            "memory": self.memory_input.text(),
            "backend": self.backend_combo.currentText(),
        }


class TemplateMatchingDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pytme Setup")
        self.resize(650, 600)

        self.layout = QVBoxLayout(self)
        self.tabs = QTabWidget()

        self.input_tab = InputDataTab()
        self.preprocess_tab = PreprocessTab()
        self.matching_tab = MatchingTab()
        self.peak_tab = PeakCallingTab()
        self.compute_tab = ComputeTab()

        self.tabs.addTab(
            self.input_tab, qta.icon("fa5s.file-import", color="#4f46e5"), "Data"
        )
        self.tabs.addTab(
            self.preprocess_tab, qta.icon("fa5s.wrench", color="#4f46e5"), "Preprocess"
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

        self.footer = DialogFooter(
            info_text="Define target tomogram and template structures",
            dialog=self,
            margin=(0, 10, 0, 0),
        )
        self.layout.addWidget(self.footer)
        self.setStyleSheet(QTabBar_style + QPushButton_style + QScrollArea_style)

    def update_help_text(self, index):
        help_texts = [
            "Define target tomogram and template structures",
            "Create a template for template matching",
            "Configure template matching parameters",
            "Set up peak calling for candidate detection",
            "Configure computing resources and output",
        ]
        self.help_text.setText(help_texts[index])

    def handle_export(self):
        data = self.input_tab.get_settings()
        preprocess = self.preprocess_tab.get_settings()
        peak_data = self.peak_tab.get_settings()

        # Setup working directory
        directory = data.get("output_directory", "")
        if len(directory) == 0:
            return QMessageBox.warning(
                self, "Error", "Missing working directory specification."
            )

        target_path = data.get("tomogram", "")
        template_path = data.get("template", "")
        if len(target_path) == 0 or len(template_path) == 0:
            return QMessageBox.warning(
                self, "Error", "Missing template or tomogram path specification."
            )

        templates_dir = join(directory, "templates")
        match_dir = join(directory, "match")
        orientations_dir = join(directory, "orientations")
        makedirs(directory, exist_ok=True)
        makedirs(templates_dir, exist_ok=True)
        makedirs(match_dir, exist_ok=True)
        makedirs(orientations_dir, exist_ok=True)

        processed_template = template_path
        if not preprocess["skip_preprocessing"]:
            args = []

            if preprocess["align_axis"] != "None":
                axis_map = {"X": "0", "Y": "1", "Z": "2", "None": ""}
                args.append(f"--align_axis {axis_map[preprocess['align_axis']]}")
                args.append(f"--align_eigenvector {preprocess['align_eigenvector']}")

                if preprocess["flip_template"]:
                    args.append("--flip_axis")

            if preprocess["lowpass"]:
                args.append(f"--lowpass {preprocess['lowpass']}")
            if preprocess["highpass"]:
                args.append(f"--highpass {preprocess['highpass']}")
            if preprocess["invert_template_contrast"]:
                args.append("--invert_contrast")

            args = "\n                    ".join([f"{x} \\" for x in args])
            processed_template = f"{splitext(template_path)[0]}_processed.mrc"
            generate_template = textwrap.dedent(
                f"""
                #!/bin/bash

                # Create symlinks to original data if needed
                mkdir -p {templates_dir}

                # Preprocess the template
                preprocess.py \\
                    -m {data["template"]} \\
                    {args}
                    -o {join(templates_dir, processed_template)}

                echo "Template preprocessing complete."
            """
            )

            script_path = join(directory, "create_template.sh")
            with open(script_path, mode="w", encoding="utf-8") as ofile:
                ofile.write(generate_template.strip() + "\n")

        args = []
        matching = self.matching_tab.get_settings()
        if matching["orientations_file"]:
            args.append(f"--orientations {matching['orientations_file']}")
            args.append(f"--orientations_scaling {matching['orientation_scaling']}")
            args.append(f"--orientations_cone {matching['rotational_uncertainty']}")
            args.append(
                f"--orientations_uncertainty {matching['translational_uncertainty']}"
            )

        if matching["lowpass"]:
            args.append(f"--lowpass {matching['lowpass']}")
        if matching["highpass"]:
            args.append(f"--highpass {matching['highpass']}")
        if matching["wedge_axes"]:
            args.append(f"--wedge_axes {matching['wedge_axes']}")
        if matching["tilt_range"]:
            args.append(f"--tilt_angles {matching['tilt_range']}")
        if matching["defocus"]:
            args.append(f"--defocus {matching['defocus']}")
        if matching["whitening"]:
            args.append("--whitening")
        if matching["no_centering"]:
            args.append("--no_centering")

        compute = self.compute_tab.get_settings()
        if compute["backend"] == "cupy":
            args.append("--use_gpu")
        args.append(f"--backend {compute['backend']}")
        if compute["memory"]:
            args.append(f"--memory {compute['memory']}")
        args.append(f"-m {compute['cores']}")

        output_basename = f"{splitext(target_path)[0]}_{splitext(template_path)[0]}"
        match_output = join(match_dir, f"{output_basename}.pickle")
        if len(target_mask := data.get("target_mask", "")) > 0:
            args.append(f"--target_mask {target_mask}")
        if len(template_mask := data.get("template_mask", "")) > 0:
            args.append(f"--template_mask {template_mask}")

        args = "\n                ".join([f"{x} \\" for x in args])
        match_template = textwrap.dedent(
            f"""
            #!/bin/bash

            match_template.py \\
                -m {data["tomogram"]} \\
                -i {processed_template} \\
                -s {matching["score_function"]} \\
                -a {matching["angular_step"]} \\
                {args}
                -o {match_output}

            echo "Template matching complete. Results saved to {match_output}"
        """
        )

        match_script_path = join(directory, "match.sh")
        with open(match_script_path, mode="w", encoding="utf-8") as ofile:
            ofile.write(match_template.strip() + "\n")

        peak_output_prefix = join(orientations_dir, output_basename)
        extract_matches = textwrap.dedent(
            f"""
            #!/bin/bash

            # Extract peaks from matching results
            postprocess.py \\
              --input_file {match_output} \\
              --peak_caller {peak_data["peak_caller"]} \\
              --num_peaks {peak_data["num_peaks"]} \\
              --min_distance {peak_data["min_distance"]} \\
              --output_format orientations \\
              --output_prefix {peak_output_prefix}

            echo "Peak extraction complete. Results saved with prefix {peak_output_prefix}"
        """
        )

        script_path = join(directory, "extract.sh")
        with open(script_path, mode="w", encoding="utf-8") as ofile:
            ofile.write(extract_matches.strip() + "\n")

        master_script = textwrap.dedent(
            f"""
            #!/bin/bash

            echo "Starting template matching pipeline..."

            # Set up environment - modify as needed
            # source activate your_env

            if [ "{preprocess['skip_preprocessing']}" = "True" ]; then
                echo "Skip preprocessing - using existing template"
            else
                # Step 1: Preprocess template
                echo "Preprocessing template..."
                bash create_template.sh
                echo "Template preprocessing done."
            fi

            echo "Running template matching..."
            bash match.sh
            echo "Template matching done."

            echo "Extracting peaks..."
            bash extract.sh
            echo "Peak extraction done."

            echo "Template matching pipeline complete!"
        """
        )

        script_path = join(directory, "run_pipeline.sh")
        with open(script_path, mode="w", encoding="utf-8") as ofile:
            ofile.write(master_script.strip() + "\n")

        return self.accept()
