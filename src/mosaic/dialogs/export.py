from typing import Tuple

from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGridLayout,
    QCheckBox,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QFrame,
    QScrollArea,
    QWidget,
    QGroupBox,
)
import qtawesome as qta

from ..widgets import DialogFooter
from ..stylesheets import QGroupBox_style, QPushButton_style, QScrollArea_style


class StyleableButton(QPushButton):
    def __init__(
        self, icon_name, title, description=None, is_compact=False, parent=None
    ):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        icon_size = 32
        size = (150, 100)
        margin = 8, 12, 8, 12
        if is_compact:
            icon_size = 24
            size = (70, 70)
            margin = (6, 8, 6, 8)

        layout.setContentsMargins(*margin)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = qta.icon(icon_name, color="#696c6f")
        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(icon_size, icon_size))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        if description and not is_compact:
            desc_label = QLabel(description)
            desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            desc_label.setStyleSheet("color: #696c6f; font-size: 11px;")
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)

        self.setMinimumSize(*size)
        self.setCheckable(True)
        self.setStyleSheet(
            """
            QPushButton {
                border: 1px solid #d1d5db;
                border-radius: 6px;
                text-align: center;
            }
            QPushButton:checked {
                border: 1px solid #4f46e5;
                background-color: #eef2ff;
            }
            QPushButton:hover:!checked {
                background-color: #1a000000;
            }
        """
        )


class ExportDialog(QDialog):
    export_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Export Data")
        self.resize(700, 600)

        # Principal export categories
        self.format_categories = {
            "pointcloud": {
                "icon": "mdi.dots-grid",
                "label": "Point Cloud",
                "description": "Export coordinates and orientations.",
                "formats": ["star", "tsv", "xyz"],
            },
            "mesh": {
                "icon": "mdi.grid",
                "label": "Mesh",
                "description": "Export as a surface mesh.",
                "formats": ["obj", "stl", "ply"],
            },
            "volume": {
                "icon": "mdi.cube-outline",
                "label": "Volume",
                "description": "Export as a density map.",
                "formats": ["mrc", "em", "h5"],
            },
        }

        # Format implementations for principal categories
        self.format_settings = {
            "mrc": {"shape_x": 64, "shape_y": 64, "shape_z": 64, "sampling": 1.0},
            "em": {"shape_x": 64, "shape_y": 64, "shape_z": 64, "sampling": 1.0},
            "map": {"shape_x": 64, "shape_y": 64, "shape_z": 64, "sampling": 1.0},
            "star": {},
            "tsv": {},
            "xyz": {"header": True, "delimiter": "\t"},
            "obj": {},
            "stl": {},
            "ply": {},
        }

        self.selected_category = "pointcloud"
        self.selected_format = "star"
        self.current_settings = self.format_settings["mrc"].copy()
        self.show_advanced = False

        self.setup_ui()
        self.setStyleSheet(QGroupBox_style + QPushButton_style + QScrollArea_style)

    def set_defaults(self, keys, values):
        for k, v in self.format_settings.items():
            for index, key in enumerate(keys):
                if key not in v:
                    continue
                self.format_settings[k][key] = values[index]

    def set_shape(self, shape: Tuple[int]):
        if shape is None:
            return None
        return self.set_defaults(("shape_x", "shape_y", "shape_y"), shape)

    def set_sampling(self, sampling: Tuple[float]):
        if sampling is None:
            return None

        if not isinstance(sampling, Tuple):
            sampling = (sampling,)
        return self.set_defaults(("sampling",), (max(sampling),))

    def setup_ui(self):
        from ..icons import icon_color

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Scroll area for content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        content_widget = QWidget()
        scroll_area.setWidget(content_widget)
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(20)

        # Principal export categories
        export_group = QGroupBox("Export Type")
        self.export_layout = QHBoxLayout(export_group)
        self.setup_group_buttons()
        content_layout.addWidget(export_group)

        # Formats of principal export category
        format_group = QGroupBox("File Format")
        self.format_layout = QHBoxLayout(format_group)
        self.setup_format_buttons()
        content_layout.addWidget(format_group)

        # Settings for format in pricinpal export category
        seettings_group = QGroupBox("Settings")
        self.settings_layout = QVBoxLayout(seettings_group)
        self.update_advanced_settings()
        content_layout.addWidget(seettings_group)

        main_layout.addWidget(scroll_area)

        footer = DialogFooter(dialog=self, margin=(20, 10, 20, 10))
        footer.accept_button.setText("Export")
        footer.accept_button.setIcon(qta.icon("fa5s.download", color=icon_color))
        main_layout.addWidget(footer)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        return layout

    def setup_group_buttons(self):
        self._clear_layout(self.export_layout)
        self.category_buttons = {}
        for i, (cat_id, category) in enumerate(self.format_categories.items()):
            btn = StyleableButton(
                category["icon"],
                category["label"],
                category["description"],
                is_compact=False,
            )
            btn.setChecked(cat_id == self.selected_category)
            btn.clicked.connect(
                lambda checked, cat=cat_id: self.on_category_selected(cat)
            )
            self.export_layout.addWidget(btn)
            self.category_buttons[cat_id] = btn

    def setup_format_buttons(self):
        self._clear_layout(self.format_layout)
        self.format_buttons = {}
        formats = self.format_categories[self.selected_category]["formats"]

        for i, fmt in enumerate(formats):
            btn = StyleableButton("fa5s.file", f".{fmt}", is_compact=True)
            btn.setChecked(fmt == self.selected_format)
            btn.clicked.connect(lambda checked, f=fmt: self.on_format_selected(f))
            self.format_layout.addWidget(btn)
            self.format_buttons[fmt] = btn

    def update_advanced_settings(self):
        self._clear_layout(self.settings_layout)

        settings_widget = QWidget()
        settings_layout = QGridLayout(settings_widget)
        settings_layout.setContentsMargins(10, 10, 10, 10)
        settings_layout.setSpacing(10)

        if self.selected_format in ["mrc", "em", "h5"]:
            # Volume format settings
            shape_x_label = QLabel("Shape X:")
            shape_x_spin = QSpinBox()
            shape_x_spin.setRange(1, 1024)
            shape_x_spin.setValue(self.current_settings.get("shape_x", 64))
            shape_x_spin.valueChanged.connect(
                lambda v: self.update_setting("shape_x", v)
            )

            shape_y_label = QLabel("Shape Y:")
            shape_y_spin = QSpinBox()
            shape_y_spin.setRange(1, 1024)
            shape_y_spin.setValue(self.current_settings.get("shape_y", 64))
            shape_y_spin.valueChanged.connect(
                lambda v: self.update_setting("shape_y", v)
            )

            shape_z_label = QLabel("Shape Z:")
            shape_z_spin = QSpinBox()
            shape_z_spin.setRange(1, 1024)
            shape_z_spin.setValue(self.current_settings.get("shape_z", 64))
            shape_z_spin.valueChanged.connect(
                lambda v: self.update_setting("shape_z", v)
            )

            sampling_label = QLabel("Sampling Rate (Å):")
            sampling_spin = QDoubleSpinBox()
            sampling_spin.setRange(0.1, 100.0)
            sampling_spin.setSingleStep(0.1)
            sampling_spin.setValue(self.current_settings.get("sampling", 1.0))
            sampling_spin.valueChanged.connect(
                lambda v: self.update_setting("sampling", v)
            )

            settings_layout.addWidget(shape_x_label, 0, 0)
            settings_layout.addWidget(shape_x_spin, 0, 1)
            settings_layout.addWidget(shape_y_label, 0, 2)
            settings_layout.addWidget(shape_y_spin, 0, 3)
            settings_layout.addWidget(shape_z_label, 1, 0)
            settings_layout.addWidget(shape_z_spin, 1, 1)
            settings_layout.addWidget(sampling_label, 1, 2)
            settings_layout.addWidget(sampling_spin, 1, 3)

        elif self.selected_format == "xyz":
            header_check = QCheckBox("Include Header")
            header_check.setChecked(self.current_settings.get("header", False))
            header_check.stateChanged.connect(
                lambda state: self.update_setting(
                    "header", state == Qt.CheckState.Checked.value
                )
            )

            delimiter_label = QLabel("Delimiter:")
            delimiter_combo = QComboBox()
            delimiter_combo.addItem("Comma (,)", ",")
            delimiter_combo.addItem("Tab", "\t")
            delimiter_combo.addItem("Space", " ")

            current_delimiter = self.current_settings.get("delimiter", ",")
            delimiter_index = 0
            for i in range(delimiter_combo.count()):
                if delimiter_combo.itemData(i) == current_delimiter:
                    delimiter_index = i
                    break
            delimiter_combo.setCurrentIndex(delimiter_index)

            delimiter_combo.currentIndexChanged.connect(
                lambda idx: self.update_setting(
                    "delimiter", delimiter_combo.itemData(idx)
                )
            )

            settings_layout.addWidget(header_check, 0, 0, 1, 2)
            settings_layout.addWidget(delimiter_label, 1, 0)
            settings_layout.addWidget(delimiter_combo, 1, 1)

        self.settings_layout.addWidget(settings_widget)

    def on_category_selected(self, category_id):
        if category_id == self.selected_category:
            return None

        for cat_id, btn in self.category_buttons.items():
            btn.setChecked(cat_id == category_id)

        self.selected_category = category_id

        self.selected_format = self.format_categories[category_id]["formats"][0]
        self.current_settings = self.format_settings.get(
            self.selected_format, {}
        ).copy()

        self.setup_format_buttons()
        self.update_advanced_settings()

    def on_format_selected(self, format_id):
        if format_id == self.selected_format:
            return None

        for fmt, btn in self.format_buttons.items():
            btn.setChecked(fmt == format_id)

        self.selected_format = format_id
        self.current_settings = self.format_settings.get(format_id, {}).copy()
        self.update_advanced_settings()

    def update_setting(self, key, value):
        self.current_settings[key] = value

    def accept(self):
        export_data = {
            "category": self.selected_category,
            "format": self.selected_format,
            "settings": self.current_settings,
        }

        self.export_requested.emit(export_data)
        return super().accept()
