from qtpy.QtCore import Signal
from qtpy.QtWidgets import (
    QWidget,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QFormLayout,
    QDoubleSpinBox,
    QGridLayout,
    QPushButton,
    QSizePolicy,
)

from mosaic.widgets import create_setting_widget


class AnimationSettings(QGroupBox):
    animationChanged = Signal(dict)

    def __init__(self, parent=None):
        super().__init__("Track Settings", parent)
        self.animation = None
        self.parameter_widgets = {}
        self.setup_ui()

    def setup_ui(self):
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 14, 10, 10)
        main_layout.setSpacing(10)

        # Name row with enabled checkbox
        name_layout = QHBoxLayout()
        name_layout.setSpacing(8)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Track name")
        self.name_edit.setMinimumWidth(0)
        self.name_edit.textChanged.connect(lambda x: self.on_change(x, "name"))
        name_layout.addWidget(self.name_edit, 1)

        self.enabled_check = QCheckBox("Enabled")
        self.enabled_check.setChecked(True)
        self.enabled_check.stateChanged.connect(
            lambda x: self.on_change(x, key="enabled")
        )
        name_layout.addWidget(self.enabled_check)
        main_layout.addLayout(name_layout)

        # Frame controls in compact grid: Start | Duration | Rate
        frame_layout = QGridLayout()
        frame_layout.setSpacing(4)
        frame_layout.setColumnStretch(1, 1)
        frame_layout.setColumnStretch(3, 1)
        frame_layout.setColumnStretch(5, 1)

        frame_layout.addWidget(QLabel("Start:"), 0, 0)
        self.global_start_spin = QSpinBox()
        self.global_start_spin.setRange(0, 2 << 29)
        self.global_start_spin.setMinimumWidth(0)
        self.global_start_spin.valueChanged.connect(
            lambda x: self.on_change(x, "global_start_frame")
        )
        frame_layout.addWidget(self.global_start_spin, 0, 1)

        frame_layout.addWidget(QLabel("Len:"), 0, 2)
        self.stop_spin = QSpinBox()
        self.stop_spin.setRange(1, 2 << 29)
        self.stop_spin.setMinimumWidth(0)
        self.stop_spin.valueChanged.connect(self._on_duration_changed)
        frame_layout.addWidget(self.stop_spin, 0, 3)

        frame_layout.addWidget(QLabel("Rate:"), 0, 4)
        self.rate_spin = QDoubleSpinBox()
        self.rate_spin.setRange(0.1, 10.0)
        self.rate_spin.setValue(1.0)
        self.rate_spin.setSingleStep(0.1)
        self.rate_spin.setDecimals(1)
        self.rate_spin.setMinimumWidth(0)
        self.rate_spin.valueChanged.connect(self._on_rate_changed)
        frame_layout.addWidget(self.rate_spin, 0, 5)

        self._base_duration = 100  # Reference duration at rate=1.0

        main_layout.addLayout(frame_layout)

        # Separator
        separator = QWidget()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: #d1d5db;")
        main_layout.addWidget(separator)

        # Parameters with better spacing
        params_label = QLabel("Parameters")
        params_label.setStyleSheet("font-weight: 500; color: #6b7280;")
        main_layout.addWidget(params_label)

        self.params_layout = QFormLayout()
        self.params_layout.setContentsMargins(0, 0, 0, 0)
        self.params_layout.setSpacing(8)
        self.params_layout.setHorizontalSpacing(12)
        main_layout.addLayout(self.params_layout)

        main_layout.addStretch()

    def _on_duration_changed(self, value):
        """Handle duration change - update rate to match."""
        if self._base_duration > 0:
            self.rate_spin.blockSignals(True)
            self.rate_spin.setValue(self._base_duration / value)
            self.rate_spin.blockSignals(False)
        self.on_change(value, "stop_frame")

    def _on_rate_changed(self, rate):
        """Handle rate change - update duration accordingly."""
        if rate > 0:
            new_duration = max(1, int(self._base_duration / rate))
            self.stop_spin.blockSignals(True)
            self.stop_spin.setValue(new_duration)
            self.stop_spin.blockSignals(False)
            self.on_change(new_duration, "stop_frame")

    def set_animation(self, animation):
        self.animation = animation

        # Block signals during setup to avoid triggering changes
        for widget in [
            self.name_edit,
            self.global_start_spin,
            self.stop_spin,
            self.enabled_check,
            self.rate_spin,
        ]:
            widget.blockSignals(True)

        self.name_edit.setText(animation.name)
        self.global_start_spin.setValue(animation.global_start_frame)
        self.stop_spin.setValue(animation.stop_frame)
        self.enabled_check.setChecked(animation.enabled)

        # Set base duration and rate
        self._base_duration = animation.stop_frame
        self.rate_spin.setValue(1.0)

        for widget in [
            self.name_edit,
            self.global_start_spin,
            self.stop_spin,
            self.enabled_check,
            self.rate_spin,
        ]:
            widget.blockSignals(False)

        # Clear and rebuild parameters
        while self.params_layout.rowCount() > 0:
            self.params_layout.removeRow(0)
        self.parameter_widgets.clear()

        for widget_settings in animation.get_settings():
            if widget_settings["type"] == "button":
                widget = QPushButton(widget_settings["text"])
                widget.clicked.connect(widget_settings["callback"])
            else:
                widget = create_setting_widget(widget_settings)

            signal = None
            if isinstance(widget, QComboBox):
                signal = widget.currentTextChanged
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                signal = widget.valueChanged
            elif isinstance(widget, QLineEdit):
                signal = widget.textChanged

            label = widget_settings["label"]

            if signal is not None:
                signal.connect(lambda x, lab=label: self.on_change(x, lab))

            label_clean = label.title().replace("_", " ")
            self.params_layout.addRow(f"{label_clean}:", widget)
            self.parameter_widgets[label] = widget

    def on_change(self, value, key):
        if not self.animation:
            return None

        attr = getattr(self.animation, key, None)
        if attr is not None:
            setattr(self.animation, key, value)
        else:
            self.animation.update_parameters(**{key: value})

        self.animationChanged.emit({key: value})


class ExportDialog(QDialog):
    """Dialog for configuring animation export settings."""

    RESOLUTION_PRESETS = {
        "Current": None,
        "720p (HD)": (1280, 720),
        "1080p (Full HD)": (1920, 1080),
        "1440p (2K)": (2560, 1440),
        "2160p (4K)": (3840, 2160),
        "Custom": None,
    }

    def __init__(
        self,
        total_frames: int = 300,
        current_width: int = 1280,
        current_height: int = 720,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Export Animation")
        self.setModal(True)
        self.total_frames = total_frames
        self.current_width = current_width
        self.current_height = current_height
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # === Output Format ===
        format_group = QGroupBox("Output Format")
        format_layout = QGridLayout(format_group)
        format_layout.setSpacing(8)
        format_layout.setColumnStretch(1, 1)

        format_layout.addWidget(QLabel("Format:"), 0, 0)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["MP4", "AVI", "PNG Sequence"])
        self.format_combo.currentTextChanged.connect(self._on_format_changed)
        format_layout.addWidget(self.format_combo, 0, 1)

        format_layout.addWidget(QLabel("Quality:"), 1, 0)
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(10, 100)
        self.quality_spin.setValue(80)
        self.quality_spin.setSuffix("%")
        format_layout.addWidget(self.quality_spin, 1, 1)

        layout.addWidget(format_group)

        # === Resolution ===
        resolution_group = QGroupBox("Resolution")
        resolution_layout = QGridLayout(resolution_group)
        resolution_layout.setSpacing(8)

        resolution_layout.addWidget(QLabel("Preset:"), 0, 0)
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(list(self.RESOLUTION_PRESETS.keys()))
        self.resolution_combo.currentTextChanged.connect(
            self._on_resolution_preset_changed
        )
        resolution_layout.addWidget(self.resolution_combo, 0, 1, 1, 3)

        resolution_layout.addWidget(QLabel("Width:"), 1, 0)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(128, 7680)
        self.width_spin.setValue(self.current_width)
        self.width_spin.setSingleStep(2)
        self.width_spin.valueChanged.connect(self._on_width_changed)
        resolution_layout.addWidget(self.width_spin, 1, 1)

        resolution_layout.addWidget(QLabel("Height:"), 1, 2)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(128, 4320)
        self.height_spin.setValue(self.current_height)
        self.height_spin.setSingleStep(2)
        resolution_layout.addWidget(self.height_spin, 1, 3)

        # Propgate changes
        self._on_resolution_preset_changed(list(self.RESOLUTION_PRESETS.keys())[0])
        layout.addWidget(resolution_group)

        # === Render Quality ===
        quality_group = QGroupBox("Render Quality")
        quality_layout = QGridLayout(quality_group)
        quality_layout.setSpacing(8)

        quality_layout.addWidget(QLabel("Supersampling:"), 0, 0)
        self.magnification_spin = QSpinBox()
        self.magnification_spin.setRange(1, 8)
        self.magnification_spin.setValue(2)
        self.magnification_spin.setToolTip(
            "Render at higher resolution for sharper output"
        )
        quality_layout.addWidget(self.magnification_spin, 0, 1)

        quality_layout.addWidget(QLabel("Multisampling:"), 0, 2)
        self.multisamples_spin = QSpinBox()
        self.multisamples_spin.setRange(0, 16)
        self.multisamples_spin.setValue(8)
        self.multisamples_spin.setToolTip("Anti-aliasing samples (0 = off)")
        quality_layout.addWidget(self.multisamples_spin, 0, 3)

        layout.addWidget(quality_group)

        # === Timing ===
        timing_group = QGroupBox("Timing")
        timing_layout = QGridLayout(timing_group)
        timing_layout.setSpacing(8)

        timing_layout.addWidget(QLabel("Frame Rate:"), 0, 0)
        self.frame_rate = QSpinBox()
        self.frame_rate.setRange(1, 120)
        self.frame_rate.setValue(30)
        self.frame_rate.setSuffix(" fps")
        timing_layout.addWidget(self.frame_rate, 0, 1)

        timing_layout.addWidget(QLabel("Stride:"), 0, 2)
        self.frame_stride = QSpinBox()
        self.frame_stride.setRange(1, 100)
        self.frame_stride.setValue(1)
        self.frame_stride.setToolTip("Export every Nth frame")
        timing_layout.addWidget(self.frame_stride, 0, 3)

        timing_layout.addWidget(QLabel("Start:"), 1, 0)
        self.start_frame = QSpinBox()
        self.start_frame.setRange(0, self.total_frames)
        self.start_frame.setValue(0)
        timing_layout.addWidget(self.start_frame, 1, 1)

        timing_layout.addWidget(QLabel("End:"), 1, 2)
        self.end_frame = QSpinBox()
        self.end_frame.setRange(0, self.total_frames)
        self.end_frame.setValue(self.total_frames)
        timing_layout.addWidget(self.end_frame, 1, 3)

        layout.addWidget(timing_group)

        # === Buttons ===
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        export_btn = QPushButton("Export")
        export_btn.setDefault(True)
        export_btn.clicked.connect(self.accept)
        button_layout.addWidget(export_btn)

        layout.addLayout(button_layout)

        self.setMinimumWidth(340)

    def _on_format_changed(self, format_name: str):
        """Handle format change - disable quality for PNG."""
        is_video = format_name != "PNG Sequence"
        self.quality_spin.setEnabled(is_video)

    def _on_resolution_preset_changed(self, preset: str):
        """Handle resolution preset change."""
        self.width_spin.blockSignals(True)
        self.height_spin.blockSignals(True)
        if preset == "Current":
            self.width_spin.setValue(self.current_width)
            self.height_spin.setValue(self.current_height)
            self.width_spin.setEnabled(False)
            self.height_spin.setEnabled(False)
        elif preset == "Custom":
            self.width_spin.setEnabled(True)
            self.height_spin.setEnabled(True)
        else:
            resolution = self.RESOLUTION_PRESETS.get(preset)
            if resolution:
                self.width_spin.setValue(resolution[0])
                self.height_spin.setValue(resolution[1])
            self.width_spin.setEnabled(False)
            self.height_spin.setEnabled(False)
        self.width_spin.blockSignals(False)
        self.height_spin.blockSignals(False)

    def _on_width_changed(self, width: int):
        """Handle width change - switch to Custom preset."""
        self.resolution_combo.blockSignals(True)
        self.resolution_combo.setCurrentText("Custom")
        self.resolution_combo.blockSignals(False)

    def get_settings(self) -> dict:
        """Return export settings as a dictionary."""
        return {
            "format": self.format_combo.currentText(),
            "quality": self.quality_spin.value(),
            "fps": self.frame_rate.value(),
            "stride": self.frame_stride.value(),
            "start_frame": self.start_frame.value(),
            "end_frame": self.end_frame.value(),
            "width": self.width_spin.value(),
            "height": self.height_spin.value(),
            "magnification": self.magnification_spin.value(),
            "multisamples": self.multisamples_spin.value(),
        }
