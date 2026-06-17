from typing import Dict, List
from os.path import splitext

from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
    QGroupBox,
    QCheckBox,
    QLineEdit,
    QFileDialog,
)
from ..icons import icon as _icon
from ..widgets import DialogFooter, create_setting_widget, get_widget_value
from ..widgets.message_box import MosaicMessageBox
from ..stylesheets import Colors, Typography

LABEL_WIDTH = 80


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

        icon_label = QLabel()
        icon_label.setPixmap(_icon(icon_name).pixmap(icon_size, icon_size))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        if description and not is_compact:
            desc_label = QLabel(description)
            desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            desc_label.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; font-size: {Typography.SMALL}px;"
            )
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)

        self.setMinimumSize(*size)
        self.setCheckable(True)
        self.setStyleSheet(
            f"""
            QPushButton {{
                border: 1px solid {Colors.BORDER_DARK};
                border-radius: 6px;
                text-align: center;
            }}
            QPushButton:checked {{
                border: 1px solid {Colors.PRIMARY};
            }}
            QPushButton:hover:!checked {{
                background: {Colors.BG_HOVER};
                border: 1px solid {Colors.BORDER_HOVER};
            }}
        """
        )


class ExportDialog(QDialog):
    export_requested = Signal(dict)

    def __init__(
        self,
        parent=None,
        parameters={},
        enabled_categories=None,
        names: List[str] = None,
    ):
        super().__init__(parent)

        self.setWindowTitle("Export Data")

        self.names = names or []
        self.file_names = [f"_{i}" for i in range(len(self.names))]

        if enabled_categories is None:
            enabled_categories = ["pointcloud", "mesh", "volume"]
        self.enabled_categories = set(enabled_categories)
        self.format_categories = {
            "pointcloud": {
                "icon": "ph.dots-nine",
                "label": "Point Cloud",
                "description": "Export coordinates and orientations.",
                "formats": ["star", "ndjson", "xyz"],
            },
            "mesh": {
                "icon": "ph.triangle",
                "label": "Mesh",
                "description": "Export as a surface mesh.",
                "formats": ["obj", "ply", "tsi"],
            },
            "volume": {
                "icon": "ph.cube",
                "label": "Volume",
                "description": "Export as a density map.",
                "formats": ["mrc", "em", "h5"],
            },
        }

        self.format_settings_definitions = {
            "mrc": volume_settings,
            "em": volume_settings,
            "h5": volume_settings,
            "xyz": {},
            "star": {
                "relion_5_format": {
                    "type": "boolean",
                    "label": "RELION 5",
                    "description": "Export in RELION 5 format with coordinate transformation",
                    "default": False,
                    "parameter": "relion_5_format",
                },
                "shape": {
                    "type": "text",
                    "label": "Shape",
                    "description": "Volume dimensions for coordinate transformation (RELION 5). Clear to derive from data.",
                    "default": None,
                    "special_text": "Auto",
                    "parameter": "shape",
                    "depends_on": "relion_5_format",
                },
            },
            "tsv": {},
            "ndjson": {},
            "obj": {},
            "ply": {},
            "tsi": {
                "tsi_format": {
                    "type": "boolean",
                    "label": "TSI format",
                    "description": "Use .tsi format with version header (otherwise .q)",
                    "default": True,
                    "parameter": "tsi_format",
                },
            },
        }

        self.selected_category = next(
            (
                cat
                for cat in ["pointcloud", "mesh", "volume"]
                if cat in self.enabled_categories
            ),
            "pointcloud",
        )
        self.selected_format = self.format_categories[self.selected_category][
            "formats"
        ][0]

        # Set parameters before drawing dialog
        self.set_defaults(list(parameters.keys()), list(parameters.values()))

        self.setup_ui()
        self.resize(700, 460)

    def set_defaults(self, keys, values):
        """Update default values for format settings"""
        params = dict(zip(keys, values))

        if params.get("shape") is not None:
            shape = params["shape"]
            shape_str = ", ".join(str(int(x)) for x in shape)
            for settings_dict in self.format_settings_definitions.values():
                if "shape" in settings_dict:
                    settings_dict["shape"]["default"] = shape_str

        for settings_dict in self.format_settings_definitions.values():
            for key, value in params.items():
                if key == "shape" or key not in settings_dict:
                    continue
                settings_dict[key]["default"] = value

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(10)

        export_group = QGroupBox("Export Type")
        self.export_layout = QHBoxLayout(export_group)
        self.setup_group_buttons()
        content_layout.addWidget(export_group)

        format_group = QGroupBox("File Format")
        self.format_layout = QHBoxLayout(format_group)
        self.setup_format_buttons()
        content_layout.addWidget(format_group)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)

        settings_group = QGroupBox("Settings")
        self.settings_layout = QVBoxLayout(settings_group)
        self.settings_layout.setSpacing(6)
        self.update_advanced_settings()
        bottom_row.addWidget(settings_group, 1)

        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout(output_group)
        output_layout.setSpacing(6)

        self.single_file_checkbox = QCheckBox("Single file")
        self.single_file_checkbox.setChecked(True)
        self.single_file_checkbox.setToolTip(
            "Merge all selected geometries into a single output file"
        )
        self.single_file_checkbox.setFixedHeight(Colors.WIDGET_HEIGHT)
        self.single_file_checkbox.toggled.connect(self._on_single_file_toggled)
        output_layout.addWidget(self.single_file_checkbox)

        suffix_row = QHBoxLayout()
        suffix_row.setSpacing(6)
        self.suffix_label = QLabel("Suffix:")
        self.suffix_label.setFixedWidth(LABEL_WIDTH)
        suffix_row.addWidget(self.suffix_label)

        self.pattern_input = QLineEdit("_{i}")
        self.pattern_input.setPlaceholderText("_{i}")
        self.pattern_input.setToolTip("{name} = original name, {i} = sequential number")
        self.pattern_input.setFixedHeight(Colors.WIDGET_HEIGHT)
        self.pattern_input.textChanged.connect(self._apply_pattern)
        suffix_row.addWidget(self.pattern_input)
        output_layout.addLayout(suffix_row)

        output_layout.addStretch()
        bottom_row.addWidget(output_group, 1)

        content_layout.addLayout(bottom_row)

        self._update_output_enabled()

        main_layout.addWidget(content, 1)

        footer = DialogFooter(dialog=self, margin=(10, 0, 10, 10))
        self.export_button = footer.accept_button
        self.export_button.setText("Export")
        self.export_button.setIcon(_icon("ph.download", role="primary"))
        main_layout.addWidget(footer)

    def _set_export_blocked(self, blocked):
        if hasattr(self, "export_button"):
            self.export_button.setEnabled(not blocked)

    def _refresh_export_blocked(self):
        if self.single_file_checkbox.isChecked() or not self.file_names:
            self._set_export_blocked(False)
            return
        has_dupes = len(self.file_names) != len(set(self.file_names))
        self._set_export_blocked(has_dupes)

    def _apply_pattern(self):
        pattern = self.pattern_input.text()
        for i, name in enumerate(self.names):
            try:
                self.file_names[i] = pattern.format(name=name, i=i)
            except (KeyError, IndexError):
                self.file_names[i] = pattern
        self._refresh_export_blocked()

    def _on_single_file_toggled(self, checked):
        self._update_output_enabled()
        self._refresh_export_blocked()

    def _update_output_enabled(self):
        is_single = self.single_file_checkbox.isChecked()
        enabled = not is_single

        self.suffix_label.setEnabled(enabled)
        self.pattern_input.setEnabled(enabled)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())
                item.layout().deleteLater()
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

            is_enabled = cat_id in self.enabled_categories
            btn.setEnabled(is_enabled)
            btn.setChecked(cat_id == self.selected_category and is_enabled)

            if is_enabled:
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
            btn = StyleableButton("ph.file", f".{fmt}", is_compact=True)
            btn.setChecked(fmt == self.selected_format)
            btn.clicked.connect(lambda checked, f=fmt: self.on_format_selected(f))
            self.format_layout.addWidget(btn)
            self.format_buttons[fmt] = btn

    def update_advanced_settings(self):
        self._clear_layout(self.settings_layout)
        self.setting_widgets = {}

        settings_definitions = self.format_settings_definitions.get(
            self.selected_format, {}
        )

        if not settings_definitions:
            no_settings_label = QLabel(
                "No additional settings available for this format."
            )
            no_settings_label.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; font-style: italic;"
            )
            self.settings_layout.addWidget(no_settings_label)
            self.settings_layout.addStretch()
            return None

        dependent_widgets = {}
        checkbox_widgets = {}

        for setting_def in settings_definitions.values():
            widget = create_setting_widget(setting_def)
            parameter = setting_def["parameter"]
            self.setting_widgets[parameter] = widget

            if setting_def["type"] == "boolean":
                widget.setText(setting_def["label"])
                self.settings_layout.addWidget(widget)
                checkbox_widgets[parameter] = widget
            else:
                row = QHBoxLayout()
                row.setSpacing(6)
                label = QLabel(setting_def["label"])
                label.setFixedWidth(LABEL_WIDTH)
                row.addWidget(label)
                row.addWidget(widget, 1)
                self.settings_layout.addLayout(row)
                if "depends_on" in setting_def:
                    dependent_widgets[setting_def["depends_on"]] = (label, widget)

        for param, (label, widget) in dependent_widgets.items():
            if param in checkbox_widgets:
                cb = checkbox_widgets[param]
                label.setEnabled(cb.isChecked())
                widget.setEnabled(cb.isChecked())
                cb.toggled.connect(label.setEnabled)
                cb.toggled.connect(widget.setEnabled)

        self.settings_layout.addStretch()

    def get_current_settings(self) -> Dict:
        """Extract current settings from the setting widgets"""
        settings = {}

        for parameter, widget in getattr(self, "setting_widgets", {}).items():
            settings[parameter] = get_widget_value(widget)

        if (raw := settings.get("shape", None)) is not None:
            try:
                parsed = tuple(int(s.strip()) for s in raw.split(","))
            except ValueError as exc:
                raise ValueError(
                    "Shape must be three comma-separated integers "
                    f"(X, Y, Z). Got: {raw!r}."
                ) from exc
            if len(parsed) != 3:
                raise ValueError(
                    "Shape must be three comma-separated integers "
                    f"(X, Y, Z). Got {len(parsed)} value(s): {raw!r}."
                )
            settings["shape"] = parsed

        return settings

    def on_category_selected(self, category_id):
        if category_id == self.selected_category:
            return None

        if category_id not in self.enabled_categories:
            return None

        for cat_id, btn in self.category_buttons.items():
            btn.setChecked(cat_id == category_id)

        self.selected_category = category_id
        self.selected_format = self.format_categories[category_id]["formats"][0]

        self.setup_format_buttons()
        self.update_advanced_settings()

    def on_format_selected(self, format_id):
        if format_id == self.selected_format:
            return None

        for fmt, btn in self.format_buttons.items():
            btn.setChecked(fmt == format_id)

        self.selected_format = format_id
        self.update_advanced_settings()

    def accept(self):
        try:
            settings = self.get_current_settings()
        except ValueError as exc:
            MosaicMessageBox.warning(self, "Invalid Input", str(exc))
            return None

        ext = self.selected_format
        if ext == "tsi":
            ext = "tsi" if settings.get("tsi_format", True) else "q"
        file_filter = f"{ext.upper()} Files (*.{ext})"
        path, _ = QFileDialog.getSaveFileName(self, "Export", "", file_filter)

        if not path:
            return None

        # This could be clearer for exporting trajectories
        base_path = splitext(path)[0]
        is_single = self.single_file_checkbox.isChecked()

        if is_single or not self.names:
            file_path = f"{base_path}.{ext}"
        else:
            file_path = [f"{base_path}{name}.{ext}" for name in self.file_names]

        export_data = {
            "category": self.selected_category,
            "format": self.selected_format,
            "file_path": file_path,
            **settings,
        }

        self.export_requested.emit(export_data)
        return super().accept()


volume_settings = {
    "shape": {
        "type": "text",
        "label": "Shape",
        "description": "Volume dimensions as X, Y, Z. Clear to derive from data.",
        "default": None,
        "special_text": "Auto",
        "parameter": "shape",
    },
    "sampling": {
        "type": "float",
        "label": "Voxel Size",
        "description": "Voxel Size in \u00c5ngstr\u00f6ms",
        "notes": "Defaults to sampling rate of Geometry object",
        "default": None,
        "special_text": "Auto",
        "step": 0.1,
        "decimals": 8,
        "parameter": "sampling",
    },
}
