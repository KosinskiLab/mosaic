"""
UI widgets for pipeline builder.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import uuid
from qtpy.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
    QFormLayout,
    QLineEdit,
    QFileDialog,
    QTreeWidget,
    QTreeWidgetItem,
    QSizePolicy,
    QCheckBox,
)
from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QFont

from ..dialogs import ImportDataDialog
from ..widgets.settings import (
    create_setting_widget,
    get_widget_value,
    set_widget_value,
    format_tooltip,
)
from ..widgets.container_list import ContainerListWidget, StyledTreeWidgetItem


from ._utils import strip_filepath, natural_sort_key


class OperationCardWidget(QFrame):
    """Expandable card widget for displaying operation in tree."""

    removed = Signal(object)
    settings_changed = Signal()

    def __init__(
        self, operation_name, operation_info, category_color, parent=None, node_id=None
    ):
        super().__init__(parent)
        self.operation_name = operation_name
        self.operation_id = operation_info["id"]
        self.operation_info = operation_info.copy()

        self.category_color = category_color
        self.category_name = self.operation_info.pop("category", None)

        # Graph orientation
        self.input_nodes: list[str] = []
        self.node_id = node_id or str(uuid.uuid4())

        self.expanded = False
        self._settings_widgets = {}

        self.group_name = operation_name
        self.remove_previous_output = False

        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setup_ui()

    def setup_ui(self):
        import qtawesome as qta

        self.setStyleSheet(
            f"""
            OperationCardWidget {{
                border-left: 4px solid {self.category_color};
                border-radius: 6px;
                background-color: transparent;
            }}
        """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        icon_label = QLabel()
        icon_label.setPixmap(
            qta.icon(self.operation_info["icon"], color=self.category_color).pixmap(
                20, 20
            )
        )
        header_layout.addWidget(icon_label)

        title = QLabel(self.operation_name)
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {self.category_color};")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.expand_btn = QPushButton()
        self.expand_btn.setIcon(qta.icon("mdi6.chevron-down", color="#6b7280"))
        self.expand_btn.setFixedSize(28, 28)
        self.expand_btn.setStyleSheet(
            "QPushButton { border: none} QPushButton:hover { background: #f3f4f6; border-radius: 12px; }"
        )
        self.expand_btn.clicked.connect(self.toggle_settings)
        header_layout.addWidget(self.expand_btn)

        close_btn = QPushButton()
        close_btn.setIcon(qta.icon("mdi6.close", color="#6b7280"))
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            "QPushButton { border: none} QPushButton:hover { background: #f3f4f6; border-radius: 12px; }"
        )
        close_btn.clicked.connect(lambda: self.removed.emit(self))
        header_layout.addWidget(close_btn)

        layout.addLayout(header_layout)

        desc = QLabel(self.operation_info["description"])
        desc.setStyleSheet("color: #6b7280; font-size: 11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.params_summary = QLabel("No parameters set")
        self.params_summary.setStyleSheet(
            "color: #9ca3af; font-size: 11px; font-style: italic;"
        )
        self.params_summary.setWordWrap(True)
        layout.addWidget(self.params_summary)
        layout.addStretch()

        self.settings_container = QWidget()
        self.settings_container.setVisible(False)

        settings_layout = QFormLayout(self.settings_container)
        settings_layout.setSpacing(12)
        settings_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        settings_layout.setContentsMargins(0, 12, 0, 12)

        group_layout = QHBoxLayout()
        group_layout.setSpacing(8)

        self.save_output, self.visible_output = True, True
        if self.operation_info.get("has_output", False):
            self.group_input = QLineEdit(self.group_name)
            self.group_input.setMinimumWidth(150)
            self.group_input.textChanged.connect(
                lambda t: setattr(self, "group_name", t)
            )

            self.save_output_checkbox = QCheckBox("Save output")
            self.save_output_checkbox.setChecked(True)
            self.save_output_checkbox.setToolTip(
                format_tooltip(
                    label="Save Output",
                    description="Save this operation's output to the session. "
                    "Uncheck to use as temporary input for next operation only.",
                )
            )
            self.save_output_checkbox.stateChanged.connect(
                lambda state: setattr(
                    self, "save_output", state == Qt.CheckState.Checked
                )
            )

            self.visible_output_checkbox = QCheckBox("Visible")
            self.visible_output_checkbox.setChecked(True)
            self.visible_output_checkbox.setToolTip(
                format_tooltip(
                    label="Visible",
                    description="Should potentially created objects be visible",
                )
            )
            self.visible_output_checkbox.stateChanged.connect(
                lambda state: setattr(
                    self, "visible_output", state == Qt.CheckState.Checked
                )
            )

            group_layout.addWidget(self.group_input)
            group_layout.addWidget(self.save_output_checkbox)
            group_layout.addWidget(self.visible_output_checkbox)

            group_layout.addStretch()
            settings_layout.addRow("Group Name:", group_layout)

        settings = self.operation_info.get("settings", {})
        self._add_operation_settings(settings_layout, settings)
        self.update_summary()
        layout.addWidget(self.settings_container)

    def _add_operation_settings(self, form_layout, settings):
        """Add operation-specific settings widgets."""

        if self.operation_id == "import_batch":
            self.input_files = []

            file_section = QWidget()
            file_layout = QVBoxLayout(file_section)
            file_layout.setContentsMargins(0, 0, 0, 0)
            file_layout.setSpacing(8)

            count_layout = QHBoxLayout()
            count_layout.addWidget(QLabel("Selected:"))
            self.file_count_label = QLabel("0 files")
            self.file_count_label.setStyleSheet("color: #6b7280; font-weight: 500;")
            count_layout.addWidget(self.file_count_label)
            count_layout.addStretch()
            file_layout.addLayout(count_layout)

            self.file_list = ContainerListWidget(border=False)
            self.file_list.setMinimumHeight(150)
            self.file_list.setMaximumHeight(300)
            file_layout.addWidget(self.file_list)

            select_btn = QPushButton("Select Files")
            select_btn.clicked.connect(self._select_input_files)
            file_layout.addWidget(select_btn)

            form_layout.addRow(file_section)
            self._settings_widgets["input_files"] = self.file_list

            params_btn = QPushButton("Configure Import Parameters")
            params_btn.clicked.connect(self._configure_parameters)
            params_btn.setEnabled(False)
            self.params_btn = params_btn
            form_layout.addRow(params_btn)
        else:
            if len(settings) == 0:
                return None

            self._add_base_settings(form_layout, settings)
            if hasattr(self, "method_settings_config") and self.method_settings_config:
                self._add_method_settings_section(form_layout)

    def _add_base_settings(self, form_layout, settings):
        """Add base operation settings including method selector."""
        offset = 0
        self.method_combo = None
        base_settings = settings["settings"][0] if settings["settings"] else None

        if base_settings and "options" in base_settings:
            offset = 1
            self.method_combo = create_setting_widget(base_settings)
            self.method_combo.currentTextChanged.connect(self._update_method_settings)
            param_name = base_settings.get("parameter", "method")
            self.method_combo.setProperty("parameter", param_name)
            form_layout.addRow(f"{base_settings['label']}:", self.method_combo)
            self._settings_widgets[param_name] = self.method_combo

        # Add remaining base settings
        for setting in settings["settings"][offset:]:
            widget = create_setting_widget(setting)
            widget_param = setting.get("parameter")
            if widget_param:
                self._settings_widgets[widget_param] = widget
            form_layout.addRow(f"{setting['label']}:", widget)

        self.method_settings_config = settings.get("method_settings", {})

    def _add_method_settings_section(self, form_layout):
        """Add separator and initial method-specific settings."""
        # Store where method rows start for dynamic updates
        self.method_row_start = form_layout.rowCount()

        separator = QFrame()
        separator.setFixedHeight(2)
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("background-color: #e5e7eb;")
        form_layout.addRow(separator)

        if self.method_combo:
            self._update_method_settings(self.method_combo.currentText())

    def _update_method_settings(self, method):
        """Update method-specific settings based on selected method."""
        if not hasattr(self, "method_row_start"):
            return

        form_layout = self.settings_container.layout()

        # Remove existing method-specific widgets
        if hasattr(self, "_last_method_params"):
            for param in self._last_method_params:
                self._settings_widgets.pop(param, None)

        # Remove rows from form layout
        while form_layout.rowCount() > self.method_row_start + 1:
            form_layout.removeRow(self.method_row_start + 1)

        # Track current method parameters for next update
        method = self.method_combo.currentText() if self.method_combo else None
        method_settings = self.method_settings_config.get(method, [])
        self._last_method_params = [
            s.get("parameter") for s in method_settings if s.get("parameter")
        ]

        # Add new method-specific widgets
        method_settings = self.method_settings_config.get(method, [])
        for setting in method_settings:
            widget = create_setting_widget(setting)
            if param_name := setting.get("parameter"):
                self._settings_widgets[param_name] = widget
            form_layout.addRow(f"{setting['label']}:", widget)

        self.settings_changed.emit()

    def _select_input_files(self):
        """Open file dialog to select files."""
        files, _ = QFileDialog.getOpenFileNames(self, "Select Input Files")
        if not files:
            return

        self.input_files = sorted(files, key=natural_sort_key)
        self._update_file_list()
        self.update_summary()

    def _update_file_list(self):
        """Update the file list widget with selected files."""
        self.input_files = sorted(self.input_files, key=natural_sort_key)

        self.file_list.tree_widget.clear()
        for filepath in self.input_files:
            item = StyledTreeWidgetItem(
                strip_filepath(filepath),
                visible=True,
                metadata={"filepath": filepath},
            )
            self.file_list.tree_widget.addTopLevelItem(item)

        count = len(self.input_files)
        self.file_count_label.setText(f"{count} file{'s' if count != 1 else ''}")

        self.params_btn.setEnabled(True)

    def _configure_parameters(self):
        """Open dialog to configure import parameters for each file."""
        if not self.input_files:
            return

        dialog = ImportDataDialog(self)
        dialog.set_files(self.input_files)

        if dialog.exec():
            self.file_parameters = dialog.get_all_parameters()
            self.update_summary()

    def update_summary(self):
        """Update the parameter summary text."""
        parts = [
            f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v}"
            for k, v in self.get_settings()["settings"].items()
        ]
        summary = ", ".join(parts) if parts else "No parameters set"

        self.params_summary.setText(
            summary[:80] + "..." if len(summary) > 80 else summary
        )

    def toggle_settings(self):
        """Expand/collapse settings panel."""
        import qtawesome as qta

        self.expanded = not self.expanded
        self.settings_container.setVisible(self.expanded)

        icon = "mdi6.chevron-up" if self.expanded else "mdi6.chevron-down"
        self.expand_btn.setIcon(qta.icon(icon, color="#6b7280"))

        self.update_summary()
        self.params_summary.setVisible(not self.expanded)
        self.settings_changed.emit()

    def get_settings(self):
        """Get operation settings including graph metadata."""
        settings = {k: get_widget_value(v) for k, v in self._settings_widgets.items()}

        if self.operation_id == "import_batch":
            settings = {
                "input_files": self.input_files,
                "file_parameters": getattr(self, "file_parameters", {}),
            }

        return {
            "id": self.node_id,
            "name": self.operation_name,
            "operation_id": self.operation_id,
            "category": self.category_name,
            "settings": settings,
            "inputs": self.input_nodes,
            "save_output": self.save_output,
            "visible_output": self.visible_output,
        }

    def set_settings(self, settings):
        """Set operation settings from config."""

        # Restore graph metadata
        self.node_id = settings.get("id", self.node_id)
        self.input_nodes = settings.get("inputs", [])

        try:
            set_widget_value(
                self.save_output_checkbox, settings.get("save_output", True)
            )
        except Exception:
            pass

        try:
            set_widget_value(
                self.visible_output_checkbox, settings.get("visible_output", True)
            )
        except Exception:
            pass

        # Restore operation settings
        operation_settings = settings.get("settings", {})
        if self.operation_id == "import_batch":
            self.input_files = operation_settings.get("input_files", [])
            self.file_parameters = operation_settings.get("file_parameters", {})
            if self.input_files:
                self._update_file_list()
        else:
            for k, v in operation_settings.items():
                if k in self._settings_widgets:
                    set_widget_value(self._settings_widgets[k], v)
        self.update_summary()


class PipelineTreeWidget(QTreeWidget):
    """Tree widget for linear pipeline operations."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(0)
        self.setRootIsDecorated(False)
        self.setDragEnabled(False)
        self.setAcceptDrops(False)

        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setStyleSheet(
            """
            QTreeWidget {
                border: none;
                background-color: transparent;
                outline: none;
                padding: 4px;
            }
            QTreeWidget::item {
                border: none;
                padding: 2px 0px;
                margin: 2px 0px;
            }
        """
        )

    def add_operation_card(self, card_widget):
        """Add operation card to list."""

        import qtawesome as qta

        if self.topLevelItemCount() > 0:
            separator_item = QTreeWidgetItem()
            self.addTopLevelItem(separator_item)

            separator = QWidget()
            layout = QHBoxLayout(separator)
            layout.setContentsMargins(0, 4, 0, 4)
            layout.setSpacing(0)

            layout.addStretch()

            icon_label = QLabel()
            icon_label.setPixmap(
                qta.icon("mdi6.chevron-down", color="#9ca3af").pixmap(20, 20)
            )
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(icon_label)
            layout.addStretch()

            separator.setFixedHeight(28)

            self.setItemWidget(separator_item, 0, separator)

        item = QTreeWidgetItem()
        self.addTopLevelItem(item)
        self.setItemWidget(item, 0, card_widget)

        card_widget.removed.connect(lambda w: self._remove_card(item))
        card_widget.settings_changed.connect(lambda: self.scheduleDelayedItemsLayout())
        return item

    def _remove_card(self, card_item):
        """Remove card and its preceding separator if it exists."""
        card_index = self.indexOfTopLevelItem(card_item)

        self.takeTopLevelItem(card_index)
        if card_index > 0:
            prev_index = card_index - 1
            prev_widget = self.itemWidget(self.topLevelItem(prev_index), 0)

            if prev_widget and not isinstance(prev_widget, OperationCardWidget):
                self.takeTopLevelItem(prev_index)

    def _remove_card(self, card_item):
        """Remove card and update graph connectivity."""
        card_index = self.indexOfTopLevelItem(card_item)

        removed_widget = self.itemWidget(card_item, 0)
        if not isinstance(removed_widget, OperationCardWidget):
            return

        removed_node_id = removed_widget.node_id
        removed_inputs = removed_widget.input_nodes.copy()

        # Update all downstream cards that depend on this card
        for i in range(self.topLevelItemCount()):
            widget = self.itemWidget(self.topLevelItem(i), 0)
            if not isinstance(widget, OperationCardWidget):
                continue

            if removed_node_id not in widget.input_nodes:
                continue

            # Remove deleted node as inputs of other cards
            widget.input_nodes.remove(removed_node_id)

            # Add the removed cards inputs to maintain connectivity
            # i.e. Card -> RemovedCard -> Card2 becomes Card -> Card2
            for input_id in removed_inputs:
                if input_id not in widget.input_nodes:
                    widget.input_nodes.append(input_id)

        self.takeTopLevelItem(card_index)

        # Remove preceding separator if it exists
        if card_index > 0:
            prev_index = card_index - 1
            prev_widget = self.itemWidget(self.topLevelItem(prev_index), 0)
            if prev_widget and not isinstance(prev_widget, OperationCardWidget):
                self.takeTopLevelItem(prev_index)

    def get_pipeline_config(self):
        """Generate pipeline configuration (supports both linear and graph)."""
        nodes = []
        prev_card_widget = None

        for i in range(self.topLevelItemCount()):
            widget = self.itemWidget(self.topLevelItem(i), 0)

            # Skip separator widgets
            if not isinstance(widget, OperationCardWidget):
                continue

            node_config = widget.get_settings()
            if prev_card_widget is not None and not node_config["inputs"]:
                node_config["inputs"] = [prev_card_widget.node_id]

            nodes.append(node_config)
            prev_card_widget = widget

        return nodes
