"""
Main pipeline builder dialog.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import json
import uuid

from qtpy.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
    QGroupBox,
    QScrollArea,
    QSpinBox,
    QFileDialog,
    QCheckBox,
)
from qtpy.QtCore import Qt
from qtpy.QtGui import QFont

from .executor import generate_runs
from .widgets import OperationCardWidget, PipelineTreeWidget
from .operations import OPERATION_CATEGORIES, PIPELINE_PRESETS

from ..settings import Settings
from ..widgets import MosaicMessageBox
from ..widgets.settings import format_tooltip
from ..stylesheets import Colors, Typography


__all__ = ["PipelineBuilderDialog"]


class PipelineBuilderDialog(QDialog):
    """Pipeline builder with tree structure and operation library."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pipeline Builder")
        self.setMinimumSize(1100, 750)
        self.resize(1200, 850)
        self.setup_ui()

    def setup_ui(self):
        from ..icons import dialog_accept_icon, dialog_reject_icon, icon

        self.pipeline_tree = PipelineTreeWidget()
        self.pipeline_tree.pipeline_changed.connect(self._update_library_state)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(10, 10, 10, 10)

        content_splitter = QWidget()
        content_layout = QHBoxLayout(content_splitter)
        content_layout.setSpacing(12)
        content_layout.setContentsMargins(0, 0, 0, 0)

        library_group = QGroupBox("Operation Library")
        library_group.setFixedWidth(280)
        library_layout = QVBoxLayout()
        library_layout.setContentsMargins(8, 8, 8, 8)
        library_layout.setSpacing(0)

        library_scroll = QScrollArea()
        library_scroll.setWidgetResizable(True)
        library_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        library_scroll.verticalScrollBar().setSingleStep(12)

        self.library_widget = self._create_library()
        library_scroll.setWidget(self.library_widget)
        library_layout.addWidget(library_scroll)

        library_group.setLayout(library_layout)
        content_layout.addWidget(library_group)

        workflow_group = QGroupBox("Pipeline Workflow")
        workflow_layout = QVBoxLayout()
        workflow_layout.setContentsMargins(8, 8, 8, 8)
        workflow_layout.setSpacing(8)

        info_label = QLabel("Operations to execute in sequence")
        info_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: {Typography.SMALL}px;"
        )
        info_label.setWordWrap(True)
        workflow_layout.addWidget(info_label)

        workflow_layout.addWidget(self.pipeline_tree, 1)

        workflow_group.setLayout(workflow_layout)
        content_layout.addWidget(workflow_group, 1)

        main_layout.addWidget(content_splitter, 1)

        settings_row = QHBoxLayout()
        settings_row.setSpacing(12)

        presets_group = QGroupBox("Presets")
        presets_container = QVBoxLayout()
        presets_container.setSpacing(8)

        presets_layout = QHBoxLayout()

        preset_buttons = [
            ("Clear", "ph.x-circle"),
            ("Import", "ph.file-arrow-up"),
            ("Cleanup", "ph.wrench"),
            ("Meshing", "ph.triangle"),
            ("Particle Picking", "ph.crosshair"),
        ]

        self.preset_buttons = {}
        for idx, (name, _) in enumerate(preset_buttons):
            btn = QPushButton(name)

            preset_key = name.replace("\n", " ")
            btn.clicked.connect(lambda checked, n=preset_key: self._load_preset(n))
            presets_layout.addWidget(btn, 0)
            self.preset_buttons[preset_key] = btn

        presets_container.addLayout(presets_layout)
        presets_container.addStretch()
        presets_group.setLayout(presets_container)

        workers_group = QGroupBox("Settings")
        workers_layout = QHBoxLayout()
        workers_layout.setSpacing(8)

        workers_label = QLabel("Parallel Workers:")
        workers_label.setToolTip(
            format_tooltip(
                label="Parallel Workers",
                description="Number of parallel processes in the pipeline.",
                notes="Depending on the workflow, i.e., number of steps and how many "
                "outputs are saved, calculate approximately 8GB of RAM per worker.",
            )
        )
        self.workers_spin = QSpinBox()
        self.workers_spin.setMinimum(1)
        self.workers_spin.setMaximum(Settings.rendering.parallel_worker)
        self.workers_spin.setValue(
            int(getattr(Settings.rendering, "parallel_worker", 4))
        )
        self.workers_spin.setFixedWidth(80)
        workers_layout.addWidget(workers_label)
        workers_layout.addWidget(self.workers_spin)

        workers_layout.addSpacing(15)

        skip_complete_label = QLabel("Skip Complete:")
        skip_complete_label.setToolTip(
            format_tooltip(
                label="Skip Complete",
                description="Skip runs where output files already exist.",
            )
        )
        self.skip_complete = QCheckBox()
        workers_layout.addWidget(skip_complete_label)
        workers_layout.addWidget(self.skip_complete)

        workers_layout.addStretch()

        workers_group.setLayout(workers_layout)

        settings_row.addWidget(presets_group, 1)
        settings_row.addWidget(workers_group)
        main_layout.addLayout(settings_row)

        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(6)

        load_btn = QPushButton("Load Pipeline")
        load_btn.clicked.connect(self._load_config)
        load_btn.setIcon(icon("ph.upload", role="primary"))
        footer_layout.addWidget(load_btn)

        export_btn = QPushButton("Export Pipeline")
        export_btn.clicked.connect(self._export_config)
        export_btn.setIcon(icon("ph.download", role="primary"))
        footer_layout.addWidget(export_btn)

        validate_btn = QPushButton("Validate Pipeline")
        validate_btn.clicked.connect(self._validate_pipeline)
        validate_btn.setIcon(icon("ph.check", role="primary"))
        footer_layout.addWidget(validate_btn)

        footer_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setIcon(dialog_reject_icon)
        cancel_btn.clicked.connect(self.reject)
        footer_layout.addWidget(cancel_btn)

        run_btn = QPushButton("Run Pipeline")
        run_btn.clicked.connect(self.accept)
        run_btn.setIcon(dialog_accept_icon)
        run_btn.setDefault(True)
        footer_layout.addWidget(run_btn)

        main_layout.addLayout(footer_layout)

    def _create_library(self):
        """Create operation library widget with categories."""

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(8)

        info_label = QLabel("Select operations to add to your pipeline")
        info_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: {Typography.SMALL}px;"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self._library_buttons = {}
        for category_id, category in OPERATION_CATEGORIES.items():
            cat_header = QLabel(category["title"])
            cat_header_font = QFont()
            cat_header_font.setBold(True)
            cat_header_font.setPixelSize(Typography.SMALL)
            cat_header.setFont(cat_header_font)
            cat_header.setStyleSheet(f"color: {category['color']}; margin-top: 8px;")
            layout.addWidget(cat_header)

            for op_name, op_info in category["operations"].items():
                op_info["category"] = category_id
                op_btn = self._create_library_button(
                    op_name, op_info, category["color"]
                )
                op_btn.clicked.connect(
                    lambda checked, n=op_name, i=op_info, c=category[
                        "color"
                    ]: self._add_card(n, i, c)
                )
                layout.addWidget(op_btn)
                self._library_buttons[(category_id, op_name)] = op_btn

        layout.addStretch()
        self._update_library_state()
        return widget

    def _create_library_button(self, name, info, color):
        """Create compact button for library operation."""
        from ..icons import icon, icon_pixmap

        btn = QPushButton()
        btn.setFixedHeight(50)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        base_style = f"""
            QPushButton {{
                border: 1px solid {Colors.BORDER_DARK};
                border-left: 3px solid {color};
                border-radius: 4px;
                text-align: left;
                padding: 6px;
            }}
            QPushButton:hover {{
                background: {Colors.BG_SECONDARY};
                border-left-color: {color};
            }}
        """
        btn.setStyleSheet(base_style)
        btn.setProperty("base_style", base_style)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        btn_layout.setContentsMargins(4, 4, 4, 4)

        icon_label = QLabel()
        icon_label.setPixmap(icon(info["icon"], color=color).pixmap(20, 20))
        btn_layout.addWidget(icon_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        name_label = QLabel(name)
        name_label.setStyleSheet(
            f"color: {color}; font-weight: 600; font-size: {Typography.SMALL}px;"
        )
        text_layout.addWidget(name_label)

        desc_label = QLabel(info["description"])
        desc_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: {Typography.SMALL}px;"
        )
        desc_label.setWordWrap(True)

        text_layout.addWidget(desc_label)
        btn_layout.addLayout(text_layout, 1)

        add_icon_label = QLabel()
        add_icon_label.setPixmap(icon_pixmap("ph.plus", 14, role="muted"))
        btn_layout.addWidget(add_icon_label)

        btn.setLayout(btn_layout)
        return btn

    def _get_current_output_type(self):
        """Get the output type of the last operation in the pipeline."""
        if self.pipeline_tree.topLevelItemCount() == 0:
            return None

        # Find the last operation card that has an output type
        for i in range(self.pipeline_tree.topLevelItemCount() - 1, -1, -1):
            widget = self.pipeline_tree.itemWidget(
                self.pipeline_tree.topLevelItem(i), 0
            )
            if isinstance(widget, OperationCardWidget):
                output_type = widget.operation_info.get("output_type")
                if output_type is not None:
                    return output_type
        return None

    def _is_operation_valid(self, operation_info):
        """Check if an operation can be added to the current pipeline."""
        current_output = self._get_current_output_type()
        operation_input = operation_info.get("input_type")

        # If pipeline is empty, only allow operations with no input requirement
        if current_output is None:
            return operation_input is None

        # If operation accepts any input
        if operation_input == "any":
            return True

        # If operation has no input requirement (like some export operations)
        if operation_input is None:
            return True

        # If current output is 'any', it should be compatible with 'point' operations
        # since Import Files outputs 'any' and we expect to process point clouds next
        if current_output == "any":
            return True
        return operation_input == current_output

    def _update_library_state(self):
        """Update library buttons to show which operations are valid."""

        if not hasattr(self, "_library_buttons"):
            return None

        for (category_id, op_name), btn in self._library_buttons.items():
            op_info = OPERATION_CATEGORIES[category_id]["operations"][op_name]
            is_valid = self._is_operation_valid(op_info)

            btn.setEnabled(is_valid)

            if not is_valid:
                btn.setStyleSheet(
                    btn.property("base_style")
                    + f"""
                    QPushButton:disabled {{
                        background: {Colors.BG_TERTIARY};
                    }}
                """
                )

    def _add_card(self, name, info, color, node_id=None, settings=None):
        settings = settings if isinstance(settings, dict) else {}

        previous_node = None
        count = self.pipeline_tree.topLevelItemCount()
        if count > 0:
            last_item = self.pipeline_tree.topLevelItem(count - 1)
            last_widget = self.pipeline_tree.itemWidget(last_item, 0)
            if isinstance(last_widget, OperationCardWidget):
                previous_node = last_widget.node_id

        card = OperationCardWidget(name, info, color, node_id=node_id)
        if "inputs" not in settings:
            settings["inputs"] = [previous_node] if previous_node is not None else []

        card.set_settings(settings)
        self.pipeline_tree.add_operation_card(card)

    def _load_preset(self, preset_name):
        """Load a predefined preset pipeline."""
        self.pipeline_tree.clear()

        self._update_library_state()
        if preset_name not in PIPELINE_PRESETS:
            return None

        for op in PIPELINE_PRESETS[preset_name]:
            op = op.copy()
            op_name, op_category = op["name"], op["category"]
            op_info = OPERATION_CATEGORIES[op_category]["operations"][op_name]
            self._add_card(
                op_name,
                op_info,
                OPERATION_CATEGORIES[op_category]["color"],
                settings=op,
            )

    def _load_config(self):
        """Load pipeline configuration from file (supports graph format)."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load Pipeline Configuration", "", "JSON Files (*.json)"
        )

        if not filename:
            return None

        try:
            with open(filename, "r") as f:
                config = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            MosaicMessageBox.warning(
                self, "Load Error", f"Failed to load configuration: {str(e)}"
            )
            return None

        nodes = config["nodes"]
        self.pipeline_tree.clear()

        self._update_library_state()
        total_ops, valid_ops = len(nodes), 0
        for node in nodes:
            category = node.get("category")
            if category not in OPERATION_CATEGORIES:
                continue

            op_name = node.get("name")
            if op_name not in OPERATION_CATEGORIES[category]["operations"]:
                continue

            op_info = OPERATION_CATEGORIES[category]["operations"][op_name]
            node_id = node.get("id", str(uuid.uuid4()))

            self._add_card(
                op_name,
                op_info,
                OPERATION_CATEGORIES[category]["color"],
                node_id=node_id,
                settings=node,
            )
            valid_ops += 1

        if "workers" in config:
            self.workers_spin.setValue(config["workers"])

        if "skip_complete" in config:
            self.skip_complete.setChecked(bool(config["skip_complete"]))

        if total_ops != valid_ops:
            MosaicMessageBox.information(
                self,
                "Import Failed",
                f"Imported {valid_ops} of {total_ops} operations.",
            )

    def _export_config(self):
        """Export current pipeline configuration to file (graph format)."""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Pipeline Configuration", "", "JSON Files (*.json)"
        )

        if not filename:
            return None

        if not filename.endswith(".json"):
            filename += ".json"

        try:
            config = self.get_pipeline_config()
            with open(filename, "w") as f:
                json.dump(config, f, indent=2)

            MosaicMessageBox.information(
                self, "Export Success", f"Configuration exported to {filename}"
            )
        except IOError as e:
            MosaicMessageBox.warning(
                self, "Export Error", f"Failed to export configuration: {str(e)}"
            )

    def _validate_pipeline(self):
        """Validate the pipeline configuration."""
        try:
            config = self.get_pipeline_config()
            runs = generate_runs(config)

            MosaicMessageBox.information(
                self,
                "Validation Success",
                f"Pipeline is valid!\n\n"
                f"- {len(config['nodes'])} operations\n"
                f"- {len(runs)} runs will be generated\n"
                f"- No cycles detected",
            )
        except Exception as e:
            MosaicMessageBox.warning(
                self, "Validation Failed", f"Pipeline validation failed:\n\n{str(e)}"
            )

    def get_settings(self):
        return {
            "runs": getattr(self, "pipeline_runs", []),
            "workers": self.workers_spin.value(),
            "skip_complete": self.skip_complete.isChecked(),
        }

    def accept(self):
        """Execute the pipeline on all input files."""
        try:
            config = self.get_pipeline_config()
            self.pipeline_runs = generate_runs(config)
        except Exception as e:
            MosaicMessageBox.warning(
                self, "Pipeline Error", f"Failed to generate runs:\n\n{str(e)}"
            )
            return None

        super().accept()

    def get_pipeline_config(self):
        """Get complete pipeline configuration in graph format."""
        from ..__version__ import __version__

        return {
            "version": __version__,
            "format": "directed_graph",
            "nodes": self.pipeline_tree.get_pipeline_config(),
            "workers": self.workers_spin.value(),
            "skip_complete": self.skip_complete.isChecked(),
            "metadata": {
                "description": "Mosaic batch pipeline configuration",
                "created_with": "Mosaic Pipeline Builder",
            },
        }
