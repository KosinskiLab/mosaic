"""
Main pipeline builder dialog.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import json
import uuid
from collections.abc import Callable

from qtpy.QtCore import QSize, Qt
from qtpy.QtGui import QFont
from qtpy.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..settings import Settings
from ..stylesheets import Colors, Typography, _get_resource_path
from ..widgets import DialogFooter, MosaicMessageBox
from ..widgets.dock import style_popup
from ..widgets.settings import format_tooltip
from .executor import generate_runs, run_complete
from .operations import OPERATION_CATEGORIES, PIPELINE_PRESETS
from .widgets import OperationCardWidget, PipelineTreeWidget

__all__ = ["PipelineBuilderDialog"]


class PipelineBuilderDialog(QDialog):
    """Pipeline builder with tree structure and operation library."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Pipeline Builder")
        self.setMinimumSize(1100, 750)
        self.resize(1200, 850)
        self.setup_ui()

    def setup_ui(self):
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

        header = QHBoxLayout()
        header.setSpacing(4)
        header.addWidget(info_label)
        header.addStretch()
        header.addWidget(self._create_presets_button())
        header.addSpacing(4)
        header.addWidget(
            self._create_icon_button(
                "ph.download", "Export pipeline", self._export_config
            )
        )
        header.addWidget(
            self._create_icon_button(
                "ph.trash", "Clear pipeline", lambda: self._load_preset("Clear")
            )
        )
        workflow_layout.addLayout(header)
        workflow_layout.addWidget(self.pipeline_tree, 1)

        workflow_group.setLayout(workflow_layout)
        content_layout.addWidget(workflow_group, 1)

        main_layout.addWidget(content_splitter, 1)

        workers_label = QLabel("Workers")
        workers_label.setToolTip(
            format_tooltip(
                label="Workers",
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
        self.workers_spin.setFixedWidth(64)

        self.skip_complete = QCheckBox("Skip complete")
        self.skip_complete.setChecked(True)
        self.skip_complete.setToolTip(
            format_tooltip(
                label="Skip complete",
                description="Skip runs where output files already exist.",
            )
        )
        self.skip_complete.toggled.connect(self._refresh_summary)

        self.footer = DialogFooter(info_text="", dialog=self, margin=(0, 4, 0, 0))
        self.footer.accept_button.setText("Run Pipeline")
        self.footer.accept_button.setDefault(True)
        footer_layout = self.footer.layout()
        at = footer_layout.indexOf(self.footer.reject_button)
        for offset, widget in enumerate(
            (workers_label, self.workers_spin, self.skip_complete)
        ):
            footer_layout.insertWidget(at + offset, widget)
        footer_layout.insertSpacing(at + 3, 12)
        main_layout.addWidget(self.footer)

        self.pipeline_tree.pipeline_changed.connect(self._refresh_summary)
        self._refresh_summary()

    def _create_presets_button(self):
        """Create the menu button that starts the pipeline from a preset or file."""
        button = QToolButton()
        button.setText("Presets")
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setFixedHeight(Colors.WIDGET_HEIGHT)
        caret = _get_resource_path("spinbox-caret-down.svg")
        button.setStyleSheet(
            f"""
            QToolButton {{ padding-right: 22px; font-size: {Typography.BODY}px; }}
            QToolButton::menu-indicator {{
                image: url('{caret}');
                width: 14px;
                height: 14px;
                subcontrol-origin: padding;
                subcontrol-position: right center;
                right: 4px;
            }}
        """
        )

        menu = style_popup(QMenu(button))
        for name in PIPELINE_PRESETS:
            menu.addAction(name, lambda n=name: self._load_preset(n))
        menu.addSeparator()
        menu.addAction("From file…", self._load_config)
        button.setMenu(menu)
        return button

    def _create_icon_button(self, icon_name: str, tooltip: str, slot: Callable):
        """Create an icon-only button styled like the card buttons."""
        from ..icons import icon

        button = QPushButton()
        button.setIcon(icon(icon_name, role="muted"))
        button.setFixedSize(Colors.WIDGET_HEIGHT, Colors.WIDGET_HEIGHT)
        button.setIconSize(QSize(18, 18))
        button.setToolTip(tooltip)
        button.setStyleSheet(
            f"QPushButton {{ border: none}} QPushButton:hover "
            f"{{ background: {Colors.BG_TERTIARY}; border-radius: 12px; }}"
        )
        button.clicked.connect(slot)
        return button

    def _refresh_summary(self):
        """Show what Run would do, or why it cannot run yet."""
        config = self.get_pipeline_config()
        runnable = False
        if not config["nodes"]:
            text = "Add Import Files to start"
        else:
            try:
                runs = generate_runs(config)
            except ValueError as e:
                text = str(e)
            else:
                runnable = True
                steps, count = len(config["nodes"]), len(runs)
                text = f"{steps} step{'s' * (steps != 1)} · "
                text += f"{count} run{'s' * (count != 1)}"
                if self.skip_complete.isChecked():
                    done = sum(run_complete(run) for run in runs)
                    if done:
                        text += f" · {done} done"

        self.footer.set_info(text)
        self.footer.accept_button.setEnabled(runnable)
        return None

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
            cat_header.setStyleSheet(
                f"color: {Colors.TEXT_SECONDARY}; margin-top: 8px;"
            )
            layout.addWidget(cat_header)

            for op_name, op_info in category["operations"].items():
                op_info["category"] = category_id
                op_btn = self._create_library_button(
                    op_name, op_info, category["color"]
                )
                op_btn.clicked.connect(
                    lambda checked, n=op_name, i=op_info, c=category["color"]: (
                        self._add_card(n, i, c)
                    )
                )
                layout.addWidget(op_btn)
                self._library_buttons[(category_id, op_name)] = op_btn

        layout.addStretch()
        self._update_library_state()
        return widget

    def _create_library_button(self, name: str, info: dict, color: str):
        """Create compact button for library operation."""
        from ..icons import icon, icon_pixmap

        btn = QPushButton()
        btn.setFixedHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(format_tooltip(label=name, description=info["description"]))

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

        name_label = QLabel(name)
        name_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: {Typography.BODY}px;"
        )
        btn_layout.addWidget(name_label, 1)

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

    def _is_operation_valid(self, operation_info: dict):
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

    def _add_card(
        self,
        name: str,
        info: dict,
        color: str,
        node_id: str | None = None,
        settings: dict | None = None,
    ):
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

    def _load_preset(self, preset_name: str):
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
            with open(filename) as f:
                config = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
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
        except OSError as e:
            MosaicMessageBox.warning(
                self, "Export Error", f"Failed to export configuration: {str(e)}"
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
