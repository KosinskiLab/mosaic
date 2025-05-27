from typing import Tuple, Dict
from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
    QWidget,
    QGroupBox,
    QGridLayout,
)
import qtawesome as qta

from ..widgets import DialogFooter
from ..stylesheets import QGroupBox_style, QPushButton_style, QScrollArea_style
from ..widgets import create_setting_widget, get_widget_value


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
            }
            QPushButton:hover:!checked {
                background-color: #1a000000;
            }
        """
        )


class ExportDialog(QDialog):
    export_requested = Signal(dict)

    def __init__(self, parent=None, parameters={}):
        super().__init__(parent)

        self.setWindowTitle("Export Data")
        self.resize(700, 600)

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

        self.format_settings_definitions = {
            "mrc": volume_settings,
            "em": volume_settings,
            "h5": volume_settings,
            "xyz": {
                "single_file": {
                    "type": "boolean",
                    "label": "Single File",
                    "description": "Export all data to a single file",
                    "default": False,
                    "parameter": "single_file",
                },
                "header": {
                    "type": "boolean",
                    "label": "Include Header",
                    "description": "Include column headers in the exported file",
                    "default": True,
                    "parameter": "header",
                },
            },
            "star": {
                "single_file": {
                    "type": "boolean",
                    "label": "Single File",
                    "description": "Export all data to a single file",
                    "default": False,
                    "parameter": "single_file",
                },
                "relion_5_format": {
                    "type": "boolean",
                    "label": "RELION 5",
                    "description": "Export in RELION 5 format with coordinate transformation",
                    "default": False,
                    "parameter": "relion_5_format",
                },
                "shape_x": {
                    "type": "number",
                    "label": "Shape X",
                    "description": "X voxel for coordinate transformation (RELION 5)",
                    "default": 64,
                    "min": 1,
                    "max": 1024,
                    "parameter": "shape_x",
                },
                "shape_y": {
                    "type": "number",
                    "label": "Shape Y",
                    "description": "Y voxel for coordinate transformation (RELION 5)",
                    "default": 64,
                    "min": 1,
                    "max": 1024,
                    "parameter": "shape_y",
                },
                "shape_z": {
                    "type": "number",
                    "label": "Shape Z",
                    "description": "Z voxel for coordinate transformation (RELION 5)",
                    "default": 64,
                    "min": 1,
                    "max": 1024,
                    "parameter": "shape_z",
                },
            },
            "tsv": {
                "single_file": {
                    "type": "boolean",
                    "label": "Single File",
                    "description": "Export all data to a single file",
                    "default": False,
                    "parameter": "single_file",
                }
            },
            "obj": {},
            "stl": {},
            "ply": {},
        }

        self.selected_category = "pointcloud"
        self.selected_format = "star"
        self.current_settings = {}
        self.show_advanced = False

        self.setup_ui()
        self.setStyleSheet(QGroupBox_style + QPushButton_style + QScrollArea_style)

    def set_defaults(self, keys, values):
        """Update default values for format settings"""
        for format_name, settings_dict in self.format_settings_definitions.items():
            for index, key in enumerate(keys):
                if key in settings_dict:
                    settings_dict[key]["default"] = values[index]

    def set_shape(self, shape: Tuple[int]):
        if shape is None:
            return None
        return self.set_defaults(("shape_x", "shape_y", "shape_z"), shape)

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

        export_group = QGroupBox("Export Type")
        self.export_layout = QHBoxLayout(export_group)
        self.setup_group_buttons()
        content_layout.addWidget(export_group)

        format_group = QGroupBox("File Format")
        self.format_layout = QHBoxLayout(format_group)
        self.setup_format_buttons()
        content_layout.addWidget(format_group)

        settings_group = QGroupBox("Settings")
        self.settings_layout = QVBoxLayout(settings_group)
        self.update_advanced_settings()
        content_layout.addWidget(settings_group)

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

        settings_definitions = self.format_settings_definitions.get(
            self.selected_format, {}
        )

        if not settings_definitions:
            self.settings_grid_layout = None
            no_settings_label = QLabel(
                "No additional settings available for this format."
            )
            no_settings_label.setStyleSheet("color: #6b7280; font-style: italic;")
            self.settings_layout.addWidget(no_settings_label)
            return

        settings_widget = QWidget()
        grid_layout = QGridLayout(settings_widget)
        grid_layout.setContentsMargins(10, 10, 10, 10)
        grid_layout.setSpacing(10)

        row = 0
        col = 0
        for setting_key, setting_def in settings_definitions.items():
            widget = create_setting_widget(setting_def)

            label = QLabel(setting_def["label"])
            grid_layout.addWidget(label, row, col * 2)
            grid_layout.addWidget(widget, row, col * 2 + 1)

            col = 1 - col
            if col == 0:
                row += 1

        self.settings_layout.addWidget(settings_widget)
        self.settings_grid_layout = grid_layout

    def get_current_settings(self) -> Dict:
        """Extract current settings from the grid widgets"""
        settings = {}

        if getattr(self, "settings_grid_layout", None) is None:
            return settings

        # Collect values from all widgets in the grid
        for i in range(self.settings_grid_layout.count()):
            item = self.settings_grid_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                parameter = widget.property("parameter")
                if not parameter:
                    continue
                settings[parameter] = get_widget_value(widget)

        return settings

    def on_category_selected(self, category_id):
        if category_id == self.selected_category:
            return None

        for cat_id, btn in self.category_buttons.items():
            btn.setChecked(cat_id == category_id)

        self.selected_category = category_id
        self.selected_format = self.format_categories[category_id]["formats"][0]
        self.current_settings = {}

        self.setup_format_buttons()
        self.update_advanced_settings()

    def on_format_selected(self, format_id):
        if format_id == self.selected_format:
            return None

        for fmt, btn in self.format_buttons.items():
            btn.setChecked(fmt == format_id)

        self.selected_format = format_id
        self.current_settings = {}
        self.update_advanced_settings()

    def accept(self):
        export_data = {
            "category": self.selected_category,
            "format": self.selected_format,
            **self.get_current_settings(),
        }

        self.export_requested.emit(export_data)
        return super().accept()


volume_settings = {
    "shape_x": {
        "type": "number",
        "label": "Shape X",
        "description": "X dimension of the volume",
        "default": 64,
        "min": 1,
        "max": 1024,
        "parameter": "shape_x",
    },
    "shape_y": {
        "type": "number",
        "label": "Shape Y",
        "description": "Y dimension of the volume",
        "default": 64,
        "min": 1,
        "max": 1024,
        "parameter": "shape_y",
    },
    "shape_z": {
        "type": "number",
        "label": "Shape Z",
        "description": "Z dimension of the volume",
        "default": 64,
        "min": 1,
        "max": 1024,
        "parameter": "shape_z",
    },
    "sampling": {
        "type": "float",
        "label": "Sampling Rate",
        "description": "Sampling rate in Ångströms",
        "default": 1.0,
        "min": 0.1,
        "max": 100.0,
        "step": 0.1,
        "parameter": "sampling",
    },
}
