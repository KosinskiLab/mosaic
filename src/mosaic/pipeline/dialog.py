"""
Main pipeline builder dialog.

Copyright (c) 2025 European Molecular Biology Laboratory

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
    QMessageBox,
    QCheckBox,
)
from qtpy.QtCore import Qt, QSize
from qtpy.QtGui import QFont

from .executor import generate_runs
from ._utils import natural_sort_key, strip_filepath
from .operations import OPERATION_CATEGORIES, PIPELINE_PRESETS
from .widgets import OperationCardWidget, PipelineTreeWidget

from ..settings import Settings
from ..widgets.settings import format_tooltip
from ..widgets import SearchWidget, ContainerListWidget
from ..widgets.container_list import StyledTreeWidgetItem
from ..stylesheets import QPushButton_style, QScrollArea_style


__all__ = ["BatchNavigatorDialog", "PipelineBuilderDialog"]


class PipelineBuilderDialog(QDialog):
    """Pipeline builder with tree structure and operation library."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pipeline Builder")
        self.setMinimumSize(1100, 750)
        self.resize(1300, 850)
        self.setup_ui()
        self.setStyleSheet(QScrollArea_style + QPushButton_style)

    def setup_ui(self):
        import qtawesome as qta
        from ..icons import dialog_accept_icon, dialog_reject_icon, icon_color

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(12, 12, 12, 12)

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
        info_label.setStyleSheet("color: #6b7280; font-size: 11px;")
        info_label.setWordWrap(True)
        workflow_layout.addWidget(info_label)

        self.pipeline_tree = PipelineTreeWidget()
        workflow_layout.addWidget(self.pipeline_tree, 1)

        workflow_group.setLayout(workflow_layout)
        content_layout.addWidget(workflow_group, 1)

        main_layout.addWidget(content_splitter, 1)

        settings_row = QHBoxLayout()
        settings_row.setSpacing(12)

        presets_group = QGroupBox("Presets")
        presets_container = QVBoxLayout()
        presets_container.setSpacing(8)

        presets_label = QLabel("Common Workflow Configurations:")
        presets_label.setStyleSheet("font-size: 11px; color: #6b7280;")
        presets_container.addWidget(presets_label)

        presets_layout = QHBoxLayout()

        preset_buttons = [
            ("Clear", "mdi6.close-circle-outline", "#ef4444"),
            ("Import", "mdi6.file-import", "#3b82f6"),
            ("Cleanup", "mdi.auto-fix", "#8b5cf6"),
            ("Meshing", "mdi.triangle-outline", "#10b981"),
            ("Particle Picking", "mdi6.target", "#f59e0b"),
        ]

        self.preset_buttons = {}
        for idx, (name, icon, color) in enumerate(preset_buttons):
            btn = QPushButton(name)
            btn.setIcon(qta.icon(icon, color=color))
            btn.setIconSize(QSize(24, 24))
            btn.setFixedHeight(32)

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

        # Workers section
        workers_vbox = QVBoxLayout()
        workers_vbox.setSpacing(4)
        workers_label = QLabel("Parallel Workers:")
        workers_label.setToolTip(
            format_tooltip(
                label="Parallel Workers",
                description="Number of parallel processes in the pipeline.",
                notes="Depending on the workflow, i.e., number of steps and how many "
                "outputs are saved, calculate approximately 8GB of RAM per worker.",
            )
        )
        workers_label.setStyleSheet("font-size: 11px; color: #6b7280;")
        self.workers_spin = QSpinBox()
        self.workers_spin.setMinimum(1)
        self.workers_spin.setMaximum(Settings.rendering.pipeline_worker)
        self.workers_spin.setValue(
            int(getattr(Settings.rendering, "pipeline_worker", 4))
        )
        self.workers_spin.setFixedWidth(80)
        self.workers_spin.setFixedHeight(32)
        workers_vbox.addWidget(workers_label)
        workers_vbox.addWidget(self.workers_spin)

        skip_vbox = QVBoxLayout()
        skip_vbox.setSpacing(4)
        skip_complete_label = QLabel("Skip Complete:")
        skip_complete_label.setToolTip(
            format_tooltip(
                label="Skip Complete",
                description="Skip runs where output files already exist.",
            )
        )
        skip_complete_label.setStyleSheet("font-size: 11px; color: #6b7280;")
        self.skip_complete = QCheckBox()
        self.skip_complete.setFixedHeight(32)
        skip_vbox.addWidget(skip_complete_label)
        skip_vbox.addWidget(self.skip_complete)

        workers_layout.addLayout(workers_vbox)
        workers_layout.addLayout(skip_vbox)
        workers_layout.addStretch()

        workers_group.setLayout(workers_layout)

        settings_row.addWidget(presets_group, 1)
        settings_row.addWidget(workers_group)
        main_layout.addLayout(settings_row)

        # Footer
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(6)

        load_btn = QPushButton("Load Pipeline")
        load_btn.clicked.connect(self._load_config)
        load_btn.setIcon(qta.icon("mdi.upload", color=icon_color))
        footer_layout.addWidget(load_btn)

        export_btn = QPushButton("Export Pipeline")
        export_btn.clicked.connect(self._export_config)
        export_btn.setIcon(qta.icon("mdi.download", color=icon_color))
        footer_layout.addWidget(export_btn)

        validate_btn = QPushButton("Validate Pipeline")
        validate_btn.clicked.connect(self._validate_pipeline)
        validate_btn.setIcon(qta.icon("mdi.check", color=icon_color))
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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        info_label = QLabel("Select operations to add to your pipeline")
        info_label.setStyleSheet("color: #6b7280; font-size: 11px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        for category_id, category in OPERATION_CATEGORIES.items():
            cat_header = QLabel(category["title"])
            cat_header_font = QFont()
            cat_header_font.setBold(True)
            cat_header_font.setPointSize(11)
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

        layout.addStretch()
        return widget

    def _create_library_button(self, name, info, color):
        """Create compact button for library operation."""
        import qtawesome as qta

        btn = QPushButton()
        btn.setFixedHeight(50)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"""
            QPushButton {{
                border: 1px solid #e5e7eb;
                border-left: 3px solid {color};
                border-radius: 4px;
                text-align: left;
                padding: 6px;
            }}
            QPushButton:hover {{
                background: #f9fafb;
                border-left-color: {color};
                border-left-width: 4px;
            }}
        """
        )

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        btn_layout.setContentsMargins(4, 4, 4, 4)

        icon_label = QLabel()
        icon_label.setPixmap(qta.icon(info["icon"], color=color).pixmap(20, 20))
        btn_layout.addWidget(icon_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        name_label = QLabel(name)
        name_label.setStyleSheet(f"color: {color}; font-weight: 600; font-size: 11px;")
        text_layout.addWidget(name_label)

        desc_label = QLabel(info["description"])
        desc_label.setStyleSheet("color: #6b7280; font-size: 11px;")
        desc_label.setWordWrap(True)

        text_layout.addWidget(desc_label)
        btn_layout.addLayout(text_layout, 1)

        add_icon_label = QLabel()
        add_icon_label.setPixmap(qta.icon("mdi6.plus", color="#9ca3af").pixmap(14, 14))
        btn_layout.addWidget(add_icon_label)

        btn.setLayout(btn_layout)
        return btn

    def _add_card(self, name, info, color, node_id=None, settings=None):
        settings = settings if isinstance(settings, dict) else {}

        if self.pipeline_tree.topLevelItemCount() == 0:
            self._previous_node = None

        previous_node = getattr(self, "_previous_node", None)
        card = OperationCardWidget(name, info, color, node_id=node_id)
        if "inputs" not in settings:
            settings["inputs"] = [previous_node] if previous_node is not None else []

        card.set_settings(settings)
        self._previous_node = card.node_id
        self.pipeline_tree.add_operation_card(card)

    def _load_preset(self, preset_name):
        """Load a predefined preset pipeline."""
        self.pipeline_tree.clear()

        if preset_name not in PIPELINE_PRESETS:
            return None

        for op in PIPELINE_PRESETS[preset_name]:
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
            QMessageBox.warning(
                self, "Load Error", f"Failed to load configuration: {str(e)}"
            )
            return None

        nodes = config["nodes"]
        self.pipeline_tree.clear()
        self._previous_node = None

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
            QMessageBox.information(
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

        try:
            config = self.get_pipeline_config()
            with open(filename, "w") as f:
                json.dump(config, f, indent=2)

            QMessageBox.information(
                self, "Export Success", f"Configuration exported to {filename}"
            )
        except IOError as e:
            QMessageBox.warning(
                self, "Export Error", f"Failed to export configuration: {str(e)}"
            )

    def _validate_pipeline(self):
        """Validate the pipeline configuration."""
        try:
            config = self.get_pipeline_config()
            runs = generate_runs(config)

            QMessageBox.information(
                self,
                "Validation Success",
                f"Pipeline is valid!\n\n"
                f"- {len(config['nodes'])} operations\n"
                f"- {len(runs)} runs will be generated\n"
                f"- No cycles detected",
            )
        except Exception as e:
            QMessageBox.warning(
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
            QMessageBox.warning(
                self, "Pipeline Error", f"Failed to generate runs:\n\n{str(e)}"
            )
            return None

        super().accept()

    def get_pipeline_config(self):
        """Get complete pipeline configuration in graph format."""
        return {
            "version": "2.0",
            "format": "directed_graph",
            "nodes": self.pipeline_tree.get_pipeline_config(),
            "workers": self.workers_spin.value(),
            "skip_complete": self.skip_complete.isChecked(),
            "metadata": {
                "description": "Mosaic batch pipeline configuration",
                "created_with": "Mosaic Pipeline Builder",
            },
        }


class BatchNavigatorDialog(QWidget):
    """Widget for navigating through batch-created sessions."""

    def __init__(self, session_files, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.current_index = -1

        self._session_modified = False
        self.setWindowTitle("Batch Navigator")

        self.session_files = sorted(
            [f for f in session_files if f.endswith(".pickle")], key=natural_sort_key
        )

        self.setup_ui()
        self.setStyleSheet(QPushButton_style + QScrollArea_style)

        if hasattr(main_window, "cdata"):
            main_window.cdata.data.data_changed.connect(self._mark_modified)
            main_window.cdata.models.data_changed.connect(self._mark_modified)

    def _mark_modified(self):
        """Mark current session as modified."""
        self._session_modified = True

    def setup_ui(self):
        from ..icons import dialog_accept_icon
        import qtawesome as qta

        self.setMinimumWidth(280)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        count = len(self.session_files)
        self.sessions_group = QGroupBox(f"{count} Session{'s' if count != 1 else ''}")
        sessions_layout = QVBoxLayout(self.sessions_group)
        sessions_layout.setSpacing(8)

        self.search_widget = SearchWidget(placeholder="Search sessions...")
        self.search_widget.searchTextChanged.connect(self._filter_sessions)

        self.session_list = ContainerListWidget(border=False)
        self.session_list.tree_widget.setSelectionMode(
            self.session_list.tree_widget.SelectionMode.SingleSelection
        )
        self.session_list.tree_widget.itemClicked.connect(self._on_item_clicked)

        self._populate_session_list()

        self.auto_save_checkbox = QCheckBox("Auto-save when switching")
        self.auto_save_checkbox.setChecked(True)
        self.auto_save_checkbox.setToolTip(
            "Automatically save the current session when switching to another"
        )

        sessions_layout.addWidget(self.search_widget)
        sessions_layout.addWidget(self.session_list, 1)
        sessions_layout.addWidget(self.auto_save_checkbox)
        layout.addWidget(self.sessions_group, 1)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        self.discard_btn = QPushButton("Discard Changes")
        self.discard_btn.setIcon(qta.icon("mdi.undo-variant", color="#4f46e5"))
        self.discard_btn.clicked.connect(self._discard_changes)
        self.discard_btn.setToolTip(
            "Reload current session, discarding unsaved changes"
        )

        self.save_btn = QPushButton("Save Current")
        self.save_btn.setIcon(dialog_accept_icon)
        self.save_btn.clicked.connect(self._save_current)

        button_layout.addWidget(self.discard_btn)
        button_layout.addWidget(self.save_btn)
        layout.addLayout(button_layout)

    def _populate_session_list(self):
        """Populate the session list widget."""
        self.session_list.tree_widget.clear()

        for i, filepath in enumerate(self.session_files):
            item = StyledTreeWidgetItem(
                strip_filepath(filepath),
                visible=(i == self.current_index),
                metadata={"index": i, "filepath": filepath},
            )
            self.session_list.tree_widget.addTopLevelItem(item)

        count = len(self.session_files)
        self.sessions_group.setTitle(f"{count} Session{'s' if count != 1 else ''}")

    def _reset_selection(self):
        self.current_index = -1
        self.session_list.tree_widget.clearSelection()
        self._update_session_list()

    def _update_session_list(self):
        """Update visibility state of items in the list."""
        for i in range(self.session_list.tree_widget.topLevelItemCount()):
            item = self.session_list.tree_widget.topLevelItem(i)
            item.set_visible(i == self.current_index)

    def _filter_sessions(self, search_text):
        """Filter session list based on search text."""
        search_text = search_text.lower()

        for i in range(self.session_list.tree_widget.topLevelItemCount()):
            item = self.session_list.tree_widget.topLevelItem(i)
            filename = strip_filepath(item.metadata.get("filepath", "")).lower()

            matches = search_text in filename if search_text else True
            item.setHidden(not matches)

    def _on_item_clicked(self, item):
        """Handle single click on session item"""
        index = item.metadata.get("index", -1)
        if index >= 0 and index != self.current_index:
            self._switch_to_session(index)

    def _load_session_at_index(self, index):
        """Load a session file at the given index."""
        if not 0 <= index < len(self.session_files):
            return

        filepath = self.session_files[index]
        self.main_window._load_session(filepath)
        self.current_index = index

        self._update_session_list()

    def _switch_to_session(self, new_index):
        """Switch to a different session, auto-saving current one if enabled."""
        if new_index == self.current_index:
            return

        if self.auto_save_checkbox.isChecked():
            self._save_current()
        self._load_session_at_index(new_index)
        self._session_modified = False

    def _save_current(self):
        """Save the currently loaded session."""
        if self.current_index < 0:
            return None

        if self._session_modified:
            filepath = self.session_files[self.current_index]
            self.main_window.cdata.to_file(filepath)

    def _discard_changes(self):
        """Discard changes by reloading the current session."""
        if self.current_index < 0:
            return

        reply = QMessageBox.question(
            self,
            "Discard Changes",
            "Reload the current session and discard all unsaved changes?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._load_session_at_index(self.current_index)

    def close(self):
        """Handle widget close, saving current session if auto-save is enabled."""
        self._save_current()
        super().close()
