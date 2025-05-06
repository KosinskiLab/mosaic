from qtpy.QtCore import Signal
from qtpy.QtWidgets import (
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
)

from mosaic.widgets import create_setting_widget


class AnimationSettings(QGroupBox):
    animationChanged = Signal(dict)

    def __init__(self, parent=None):
        super().__init__("Properties", parent)
        self.animation = None
        self.parameter_widgets = {}
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setMaximumWidth(140)
        self.name_edit.textChanged.connect(lambda x: self.on_change(x, "name"))
        name_layout.addWidget(self.name_edit)

        name_layout.addWidget(QLabel("Enabled:"))
        self.enabled_check = QCheckBox()
        self.enabled_check.setChecked(True)
        self.enabled_check.stateChanged.connect(
            lambda x: self.on_change(x, key="enabled")
        )
        name_layout.addWidget(self.enabled_check)
        main_layout.addLayout(name_layout)

        frame_group = QGroupBox("Frames")
        frame_layout = QGridLayout(frame_group)

        frame_layout.addWidget(QLabel("Global Start:"), 0, 0)
        self.global_start_spin = QSpinBox()
        self.global_start_spin.setRange(0, 2 << 29)
        self.global_start_spin.valueChanged.connect(
            lambda x: self.on_change(x, "global_start_frame")
        )
        frame_layout.addWidget(self.global_start_spin, 0, 1)

        frame_layout.addWidget(QLabel("Stride:"), 1, 0)
        self.stride_spin = QSpinBox()
        self.stride_spin.setRange(1, 2 << 29)
        self.stride_spin.setValue(1)
        self.stride_spin.valueChanged.connect(lambda x: self.on_change(x, "stride"))
        frame_layout.addWidget(self.stride_spin, 1, 1)

        frame_layout.addWidget(QLabel("Local Start:"), 2, 0)
        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 10000)
        self.start_spin.valueChanged.connect(lambda x: self.on_change(x, "start_frame"))
        frame_layout.addWidget(self.start_spin, 2, 1)

        frame_layout.addWidget(QLabel("Local Stop:"), 3, 0)
        self.stop_spin = QSpinBox()
        self.stop_spin.setRange(0, 10000)
        self.stop_spin.valueChanged.connect(lambda x: self.on_change(x, "stop_frame"))
        frame_layout.addWidget(self.stop_spin, 3, 1)

        main_layout.addWidget(frame_group)

        self.params_group = QGroupBox("Parameters")
        self.params_layout = QFormLayout(self.params_group)
        self.params_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.addWidget(self.params_group)

        main_layout.addStretch()

    def set_animation(self, animation):
        self.animation = animation
        self.name_edit.setText(animation.name)
        self.global_start_spin.setValue(animation.global_start_frame)
        self.start_spin.setValue(animation.start_frame)
        self.stop_spin.setValue(animation.stop_frame)
        self.stop_spin.setMaximum(animation.frames)
        self.stride_spin.setValue(animation.stride)
        self.enabled_check.setChecked(animation.enabled)

        while self.params_layout.rowCount() > 0:
            self.params_layout.removeRow(0)
        self.parameter_widgets.clear()

        for widget_settings in animation.get_settings():
            widget = create_setting_widget(widget_settings)
            if isinstance(widget, QComboBox):
                signal = widget.currentTextChanged
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                signal = widget.valueChanged
            elif isinstance(widget, QLineEdit):
                signal = widget.textChanged

            label = widget_settings["label"]
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

        if self.animation.frames != self.stop_spin.maximum():
            self.start_spin.setMaximum(self.animation.frames)
            self.stop_spin.setMaximum(self.animation.frames)

            if self.animation.frames < (2 << 15):
                self.stop_spin.setValue(self.animation.frames)

        self.animationChanged.emit({key: value})


class ExportSettings(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Export Settings", parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QGridLayout(self)

        layout.addWidget(QLabel("Format:"), 0, 0)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["MP4", "AVI", "RGBA"])
        layout.addWidget(self.format_combo, 0, 1)

        layout.addWidget(QLabel("Quality:"), 1, 0)
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(0, 100)
        self.quality_spin.setValue(80)
        self.quality_spin.setSuffix("%")
        layout.addWidget(self.quality_spin, 1, 1)

        layout.addWidget(QLabel("Rate (fps):"), 2, 0)
        self.frame_rate = QSpinBox()
        self.frame_rate.setRange(1, 1000)
        self.frame_rate.setValue(30)
        layout.addWidget(self.frame_rate, 2, 1)

        layout.addWidget(QLabel("Stride:"), 3, 0)
        self.frame_stride = QSpinBox()
        self.frame_stride.setRange(1, 100)
        self.frame_stride.setValue(1)
        layout.addWidget(self.frame_stride, 3, 1)

        layout.addWidget(QLabel("Window:"), 4, 0)
        range_layout = QHBoxLayout()
        self.start_frame = QSpinBox()
        self.start_frame.setFixedWidth(70)
        self.start_frame.setRange(0, 10000)
        self.end_frame = QSpinBox()
        self.end_frame.setFixedWidth(70)
        self.end_frame.setRange(0, 10000)
        self.end_frame.setValue(300)
        range_layout.addWidget(self.start_frame)
        range_layout.addWidget(self.end_frame)
        layout.addLayout(range_layout, 4, 1)
