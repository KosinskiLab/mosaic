from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGridLayout,
    QGroupBox,
)

from ..stylesheets import QPushButton_style
from ..widgets.settings import create_setting_widget


class ImportDataDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file_index = 0
        self.filenames = []
        self.file_parameters = {}
        self.setup_ui()
        self.setStyleSheet(QPushButton_style)

    def setup_ui(self):
        from ..icons import (
            dialog_accept_icon,
            dialog_reject_icon,
            dialog_next_icon,
            dialog_previous_icon,
            dialog_apply_icon,
        )

        self.setWindowTitle("Import Parameters")
        self.setMinimumWidth(600)
        layout = QVBoxLayout()
        layout.setSpacing(15)

        group = QGroupBox()
        grid_layout = QGridLayout(group)
        grid_layout.setVerticalSpacing(10)
        grid_layout.setHorizontalSpacing(10)

        self.progress_label = QLabel("File 0 of 0")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid_layout.addWidget(self.progress_label, 0, 0, 1, 4)

        self.filename_label = QLabel()
        self.filename_label.setWordWrap(True)
        self.filename_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.filename_label.setMinimumWidth(400)
        grid_layout.addWidget(self.filename_label, 1, 0, 1, 4)

        # Column headers for X, Y, Z axes
        param_label = QLabel("")
        param_label.setFixedWidth(100)
        self.x_label = QLabel("X")
        self.y_label = QLabel("Y")
        self.z_label = QLabel("Z")
        self.x_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.y_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.z_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        grid_layout.addWidget(param_label, 2, 0)
        grid_layout.addWidget(self.x_label, 2, 1)
        grid_layout.addWidget(self.y_label, 2, 2)
        grid_layout.addWidget(self.z_label, 2, 3)

        scale_label = QLabel("Scale Factor:")
        scale_input = {
            "label": "Scale Factor",
            "type": "text",
            "min": 0.0,
            "max": 1e32,
            "default": 1.0,
            "description": "Scale imported data by points times scale.",
        }
        self.scale_x = create_setting_widget(scale_input)
        self.scale_y = create_setting_widget(scale_input)
        self.scale_z = create_setting_widget(scale_input)

        grid_layout.addWidget(scale_label, 3, 0)
        grid_layout.addWidget(self.scale_x, 3, 1)
        grid_layout.addWidget(self.scale_y, 3, 2)
        grid_layout.addWidget(self.scale_z, 3, 3)

        # Offset inputs
        offset_label = QLabel("Offset:")
        offset_settings = {
            "label": "Offset",
            "type": "text",
            "min": -1e32,
            "max": 1e32,
            "default": 0.0,
            "description": "Add offset as (points - offset) * scale.",
        }
        self.offset_x = create_setting_widget(offset_settings)
        self.offset_y = create_setting_widget(offset_settings)
        self.offset_z = create_setting_widget(offset_settings)

        grid_layout.addWidget(offset_label, 4, 0)
        grid_layout.addWidget(self.offset_x, 4, 1)
        grid_layout.addWidget(self.offset_y, 4, 2)
        grid_layout.addWidget(self.offset_z, 4, 3)

        # Sampling rate inputs
        sampling_label = QLabel("Sampling Rate:")
        sampling_settings = {
            "label": "Sampling Rate",
            "type": "text",
            "min": 1e-8,
            "max": 1e32,
            "default": 1.0,
            "description": "Set sampling rate of imported data.",
        }
        self.sampling_x = create_setting_widget(sampling_settings)
        self.sampling_y = create_setting_widget(sampling_settings)
        self.sampling_z = create_setting_widget(sampling_settings)

        grid_layout.addWidget(sampling_label, 5, 0)
        grid_layout.addWidget(self.sampling_x, 5, 1)
        grid_layout.addWidget(self.sampling_y, 5, 2)
        grid_layout.addWidget(self.sampling_z, 5, 3)

        axis_label = QLabel("Configure per Axis")
        axis_settings = {
            "label": "Configure per Axis",
            "type": "boolean",
            "default": False,
            "description": "Specify parameters per axis.",
        }
        self.axis_checkbox = create_setting_widget(axis_settings)
        self.axis_checkbox.toggled.connect(self.toggle_per_axis_mode)
        self.axis_checkbox.setChecked(False)

        grid_layout.addWidget(axis_label, 6, 0)
        grid_layout.addWidget(self.axis_checkbox, 6, 1)

        self.scale_x.textChanged.connect(
            lambda text: self._propagate_value(text, self.scale_y, self.scale_z)
        )
        self.offset_x.textChanged.connect(
            lambda text: self._propagate_value(text, self.offset_y, self.offset_z)
        )
        self.sampling_x.textChanged.connect(
            lambda text: self._propagate_value(text, self.sampling_y, self.sampling_z)
        )
        layout.addWidget(group)

        # Button layout
        button_layout = QHBoxLayout()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        button_layout.addStretch()
        self.prev_button = QPushButton("Previous")
        self.next_button = QPushButton("Next")
        self.apply_all_button = QPushButton("Apply to All")
        self.accept_button = QPushButton("Accept")
        self.accept_button.setDefault(True)

        self.prev_button.clicked.connect(self.previous_file)
        self.next_button.clicked.connect(self.next_file)
        self.apply_all_button.clicked.connect(self.apply_to_all_clicked)
        self.accept_button.clicked.connect(self.accept)

        self.cancel_button.setIcon(dialog_reject_icon)
        self.accept_button.setIcon(dialog_accept_icon)
        self.apply_all_button.setIcon(dialog_apply_icon)
        self.prev_button.setIcon(dialog_previous_icon)
        self.next_button.setIcon(dialog_next_icon)

        for button in [
            self.prev_button,
            self.next_button,
            self.apply_all_button,
            self.accept_button,
        ]:
            button.setMinimumWidth(100)
            button_layout.addWidget(button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        # Set fixed widths for labels
        max_label_width = max(
            scale_label.sizeHint().width(),
            offset_label.sizeHint().width(),
            sampling_label.sizeHint().width(),
        )
        scale_label.setFixedWidth(max_label_width)
        offset_label.setFixedWidth(max_label_width)
        sampling_label.setFixedWidth(max_label_width)

        self.toggle_per_axis_mode(False)

    def toggle_per_axis_mode(self, checked):
        self.x_label.setVisible(checked)
        self.y_label.setVisible(checked)
        self.z_label.setVisible(checked)

        self.scale_y.setVisible(checked)
        self.scale_z.setVisible(checked)
        self.offset_y.setVisible(checked)
        self.offset_z.setVisible(checked)
        self.sampling_y.setVisible(checked)
        self.sampling_z.setVisible(checked)

    def _propagate_value(self, text, y_input, z_input):
        y_input.setText(text)
        z_input.setText(text)

    def set_files(self, filenames):
        from ..formats._utils import get_extension
        from ..formats.reader import FORMAT_MAPPING
        from ..formats.parser import load_density, read_volume

        self.filenames = filenames
        self.current_file_index = 0
        self.file_parameters = {}
        self.update_file_display()
        self.update_navigation_buttons()

        for file in filenames:
            extension = get_extension(file)[1:]
            if extension in FORMAT_MAPPING.get(read_volume):
                volume = load_density(file, use_memmap=True)
                self.scale_x.setText(f"{volume.sampling_rate[0]}")
                self.sampling_x.setText(f"{volume.sampling_rate[0]}")

                self.scale_y.setText(f"{volume.sampling_rate[1]}")
                self.sampling_y.setText(f"{volume.sampling_rate[1]}")

                self.scale_z.setText(f"{volume.sampling_rate[2]}")
                self.sampling_z.setText(f"{volume.sampling_rate[2]}")

            self.file_parameters[file] = self._get_current_parameters()

    def update_file_display(self):
        if not self.filenames:
            self.filename_label.setText("No files selected")
            self.progress_label.setText("File 0 of 0")
            return

        filename = self.filenames[self.current_file_index]
        self.filename_label.setText(filename)
        self.progress_label.setText(
            f"File {self.current_file_index + 1} of {len(self.filenames)}"
        )

    def update_navigation_buttons(self):
        self.prev_button.setEnabled(self.current_file_index > 0)
        self.next_button.setEnabled(self.current_file_index < len(self.filenames) - 1)

    def save_current_parameters(self):
        if self.filenames:
            current_file = self.filenames[self.current_file_index]
            self.file_parameters[current_file] = self._get_current_parameters()

    def _get_current_parameters(self):
        return {
            "scale": (
                float(self.scale_x.text()),
                float(self.scale_y.text()),
                float(self.scale_z.text()),
            ),
            "offset": (
                float(self.offset_x.text()),
                float(self.offset_y.text()),
                float(self.offset_z.text()),
            ),
            "sampling_rate": (
                float(self.sampling_x.text()),
                float(self.sampling_y.text()),
                float(self.sampling_z.text()),
            ),
        }

    def load_file_parameters(self, filename):
        if filename not in self.file_parameters:
            return None

        params = self.file_parameters[filename]

        scale = params["scale"]
        offset = params["offset"]
        sampling_rate = params["sampling_rate"]

        self.scale_x.setText(str(scale[0]))
        self.scale_y.setText(str(scale[1]))
        self.scale_z.setText(str(scale[2]))

        self.offset_x.setText(str(offset[0]))
        self.offset_y.setText(str(offset[1]))
        self.offset_z.setText(str(offset[2]))

        self.sampling_x.setText(str(sampling_rate[0]))
        self.sampling_y.setText(str(sampling_rate[1]))
        self.sampling_z.setText(str(sampling_rate[2]))

    def next_file(self):
        self.save_current_parameters()
        if self.current_file_index < len(self.filenames) - 1:
            self.current_file_index += 1
            self.load_file_parameters(self.filenames[self.current_file_index])
            self.update_file_display()
            self.update_navigation_buttons()

    def previous_file(self):
        self.save_current_parameters()
        if self.current_file_index > 0:
            self.current_file_index -= 1
            self.load_file_parameters(self.filenames[self.current_file_index])
            self.update_file_display()
            self.update_navigation_buttons()

    def apply_to_all_clicked(self):
        current_params = self._get_current_parameters()

        for idx in range(len(self.filenames)):
            self.file_parameters[self.filenames[idx]] = current_params

    def get_all_parameters(self):
        self.save_current_parameters()
        return self.file_parameters
