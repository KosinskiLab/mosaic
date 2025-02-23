from qtpy.QtCore import Qt, QLocale
from qtpy.QtGui import QDoubleValidator
from qtpy.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QGridLayout,
    QSizePolicy,
    QLineEdit,
)


class ImportDataDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file_index = 0
        self.filenames = []
        self.file_parameters = {}
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("Import Parameters")
        self.setMinimumWidth(600)
        layout = QVBoxLayout()
        layout.setSpacing(15)

        grid_layout = QGridLayout()
        grid_layout.setVerticalSpacing(10)
        grid_layout.setHorizontalSpacing(10)

        self.progress_label = QLabel("File 0 of 0")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid_layout.addWidget(self.progress_label, 0, 0, 1, 2)

        self.filename_label = QLabel()
        self.filename_label.setWordWrap(True)
        self.filename_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.filename_label.setMinimumWidth(400)
        grid_layout.addWidget(self.filename_label, 1, 0, 1, 2)

        scale_label = QLabel("Scale Factor:")
        self.scale_input = QLineEdit()
        self.scale_input.setToolTip("Scale imported data by points times scale.")
        validator = QDoubleValidator()
        validator.setLocale(QLocale.c())
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        validator.setBottom(1e-6)
        self.scale_input.setValidator(validator)
        self.scale_input.setText(str(1.0))
        self.scale_input.setMinimumWidth(150)
        self.scale_input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        grid_layout.addWidget(scale_label, 2, 0)
        grid_layout.addWidget(self.scale_input, 2, 1)

        offset_label = QLabel("Offset:")
        self.offset_input = QLineEdit()
        self.offset_input.setToolTip("Add offset as (points - offset) * scale.")
        validator = QDoubleValidator()
        validator.setLocale(QLocale.c())
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.offset_input.setValidator(validator)
        self.offset_input.setText(str(0.0))
        self.offset_input.setMinimumWidth(150)
        self.offset_input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        grid_layout.addWidget(offset_label, 3, 0)
        grid_layout.addWidget(self.offset_input, 3, 1)

        sampling_label = QLabel("Sampling Rate:")
        self.sampling_input = QLineEdit()
        self.sampling_input.setToolTip("Set sampling rate of points.")
        validator = QDoubleValidator()
        validator.setLocale(QLocale.c())
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        validator.setBottom(0.0)
        self.sampling_input.setValidator(validator)
        self.sampling_input.setText(str(1.0))
        self.sampling_input.setMinimumWidth(150)
        self.sampling_input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        grid_layout.addWidget(sampling_label, 4, 0)
        grid_layout.addWidget(self.sampling_input, 4, 1)

        frame = QFrame()
        frame.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        frame.setLayout(grid_layout)
        layout.addWidget(frame)

        layout.addStretch()

        button_layout = QHBoxLayout()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        button_layout.addStretch()
        self.prev_button = QPushButton("← Previous")
        self.next_button = QPushButton("Next →")
        self.apply_all_button = QPushButton("Apply to All")
        self.accept_button = QPushButton("Accept")
        self.accept_button.setDefault(True)

        self.prev_button.clicked.connect(self.previous_file)
        self.next_button.clicked.connect(self.next_file)
        self.apply_all_button.clicked.connect(self.apply_to_all_clicked)
        self.accept_button.clicked.connect(self.accept)

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

    def set_files(self, filenames):
        self.filenames = filenames
        self.current_file_index = 0
        self.file_parameters = {}
        self.update_file_display()
        self.update_navigation_buttons()

        for file in filenames:
            self.file_parameters[file] = {
                "scale": float(self.scale_input.text()),
                "offset": float(self.offset_input.text()),
                "sampling_rate": float(self.sampling_input.text()),
            }

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
            self.file_parameters[current_file] = {
                "scale": float(self.scale_input.text()),
                "offset": float(self.offset_input.text()),
                "sampling_rate": float(self.sampling_input.text()),
            }

    def load_file_parameters(self, filename):
        if filename in self.file_parameters:
            params = self.file_parameters[filename]
            self.scale_input.setText(str(params["scale"]))
            self.offset_input.setText(str(params["offset"]))
            self.sampling_input.setText(str(params["sampling_rate"]))

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
        current_scale = float(self.scale_input.text())
        current_offset = float(self.offset_input.text())
        current_sampling_rate = float(self.sampling_input.text())

        for idx in range(self.current_file_index, len(self.filenames)):
            self.file_parameters[self.filenames[idx]] = {
                "scale": current_scale,
                "offset": current_offset,
                "sampling_rate": current_sampling_rate,
            }

    def get_all_parameters(self):
        self.save_current_parameters()
        return self.file_parameters
