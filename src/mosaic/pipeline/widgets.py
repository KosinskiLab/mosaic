"""
UI widgets for pipeline builder.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import uuid
from qtpy.QtGui import QFont
from qtpy.QtCore import Qt, Signal, QTimer

from qtpy.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QWidget,
    QLineEdit,
    QFileDialog,
    QTreeWidget,
    QTreeWidgetItem,
    QSizePolicy,
    QCheckBox,
    QAbstractItemView,
)

from ..dialogs import ImportDataDialog
from ..widgets.settings import (
    create_setting_widget,
    get_widget_value,
    set_widget_value,
    format_tooltip,
)
from ..widgets.container_list import ContainerListWidget, StyledTreeWidgetItem


from ._utils import strip_filepath, natural_sort_key
from ..stylesheets import Colors, Typography

_COLS = 3  # logical parameter columns (actual grid columns = _COLS * 2)


def _make_grid():
    """Create a 6-column grid: label, widget, label, widget, label, widget."""
    grid = QGridLayout()
    grid.setHorizontalSpacing(6)
    grid.setVerticalSpacing(6)
    for i in range(_COLS):
        grid.setColumnStretch(i * 2, 0)
        grid.setColumnStretch(i * 2 + 1, 1)
    return grid


def _add_to_grid(grid, label_text, widget, row, col, wide=False):
    """Add a label: widget pair to the grid at the given logical column."""
    label = QLabel(f"{label_text}:")
    widget.setFixedHeight(Colors.WIDGET_HEIGHT)

    width, gcol = 1, 2 * col
    if wide:
        width = _COLS * 2 - 1

    grid.addWidget(label, row, gcol)
    grid.addWidget(widget, row, gcol + 1, 1, width)


def _pack_settings_into_grid(grid, settings_list, start_row=0):
    """Pack settings into the grid. Returns {param_name: widget}."""
    widgets = {}
    row, col = start_row, 0

    for setting in settings_list:
        wide = setting.get("type") == "PathSelector"
        widget = create_setting_widget(setting)

        if wide or col >= _COLS:
            col, row = 0, row + int(col != 0)

        _add_to_grid(grid, setting["label"], widget, row, col, wide=wide)
        if param_name := setting.get("parameter"):
            widgets[param_name] = widget
        col += 1
    return widgets, row if col == 0 else row + 1


def _clear_grid_from_row(grid, start_row):
    """Remove all items at row >= start_row from a QGridLayout."""
    to_remove = []
    for i in range(grid.count()):
        item = grid.itemAt(i)
        r, _c, _rs, _cs = grid.getItemPosition(i)
        if r >= start_row:
            to_remove.append(item)

    for item in to_remove:
        grid.removeItem(item)
        if item.widget():
            item.widget().deleteLater()


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

        self._collapsed_height = 96
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setup_ui()
        self.setFixedHeight(self._collapsed_height)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_settings()
        super().mousePressEvent(event)

    def setup_ui(self):
        from ..icons import icon

        self.setStyleSheet(
            f"""
            OperationCardWidget {{
                border: 1px solid {Colors.BORDER_DARK};
                border-left: 4px solid {self.category_color};
                border-radius: {Colors.RADIUS}px;
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
            icon(self.operation_info["icon"], color=self.category_color).pixmap(20, 20)
        )
        header_layout.addWidget(icon_label)

        title = QLabel(self.operation_name)
        title_font = QFont()
        title_font.setPixelSize(Typography.BODY)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {self.category_color};")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.expand_btn = QPushButton()
        self.expand_btn.setIcon(icon("ph.caret-down", role="muted"))
        self.expand_btn.setFixedSize(28, 28)
        self.expand_btn.setStyleSheet(
            f"QPushButton {{ border: none}} QPushButton:hover {{ background: {Colors.BG_TERTIARY}; border-radius: 12px; }}"
        )
        self.expand_btn.clicked.connect(self.toggle_settings)
        header_layout.addWidget(self.expand_btn)

        close_btn = QPushButton()
        close_btn.setIcon(icon("ph.x", role="muted"))
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            f"QPushButton {{ border: none}} QPushButton:hover {{ background: {Colors.BG_TERTIARY}; border-radius: 12px; }}"
        )
        close_btn.clicked.connect(lambda: self.removed.emit(self))
        header_layout.addWidget(close_btn)

        layout.addLayout(header_layout)

        self.desc = QLabel(self.operation_info["description"])
        self.desc.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: {Typography.SMALL}px;"
        )
        self.desc.setWordWrap(True)
        layout.addWidget(self.desc)

        self.params_summary = QLabel("No parameters set")
        self.params_summary.setStyleSheet(
            f"color: {Colors.ICON_MUTED}; font-size: {Typography.SMALL}px; font-style: italic;"
        )
        self.params_summary.setWordWrap(True)
        layout.addWidget(self.params_summary)

        self.settings_container = QWidget()
        self.settings_container.setVisible(False)

        settings_outer = QVBoxLayout(self.settings_container)
        settings_outer.setSpacing(8)
        settings_outer.setContentsMargins(0, 0, 0, 4)

        self.settings_grid = _make_grid()
        self._grid_row = 0
        settings_outer.addLayout(self.settings_grid)

        self.save_output, self.visible_output = True, True
        if self.operation_info.get("has_output", False):
            self.group_input = QLineEdit(self.group_name)
            self.group_input.textChanged.connect(
                lambda t: setattr(self, "group_name", t)
            )
            _add_to_grid(
                self.settings_grid,
                "Group Name",
                self.group_input,
                self._grid_row,
                0,
            )

            self.save_output_checkbox = QCheckBox()
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
            _add_to_grid(
                self.settings_grid,
                "Save output",
                self.save_output_checkbox,
                self._grid_row,
                1,
            )

            self.visible_output_checkbox = QCheckBox()
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
            _add_to_grid(
                self.settings_grid,
                "Visible",
                self.visible_output_checkbox,
                self._grid_row,
                2,
            )
            self._grid_row += 1

        settings = self.operation_info.get("settings", {})
        self._add_operation_settings(settings)
        self.update_summary()
        layout.addWidget(self.settings_container)

    def _add_operation_settings(self, settings):
        """Add operation-specific settings widgets."""
        settings_outer = self.settings_container.layout()

        if self.operation_id == "import_batch":
            self.input_files = []

            file_section = QWidget()
            file_layout = QVBoxLayout(file_section)
            file_layout.setContentsMargins(0, 0, 0, 0)
            file_layout.setSpacing(8)

            count_layout = QHBoxLayout()
            count_layout.addWidget(QLabel("Selected:"))
            self.file_count_label = QLabel("0 files")
            self.file_count_label.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; font-weight: 500;"
            )
            count_layout.addWidget(self.file_count_label)
            count_layout.addStretch()
            file_layout.addLayout(count_layout)

            self.file_list = ContainerListWidget()
            self.file_list.setMinimumHeight(150)
            self.file_list.setMaximumHeight(300)
            file_layout.addWidget(self.file_list)

            select_btn = QPushButton("Select Files")
            select_btn.clicked.connect(self._select_input_files)
            file_layout.addWidget(select_btn)

            settings_outer.addWidget(file_section)
            self._settings_widgets["input_files"] = self.file_list

            params_btn = QPushButton("Configure Import Parameters")
            params_btn.clicked.connect(self._configure_parameters)
            params_btn.setEnabled(False)
            self.params_btn = params_btn
            settings_outer.addWidget(params_btn)
            return None

        self._add_base_settings(settings)
        if hasattr(self, "method_settings_config") and self.method_settings_config:
            self._add_method_settings_section()

    def _add_base_settings(self, settings):
        """Add base operation settings to the grid layout."""
        if len(settings) == 0:
            return None

        self.method_combo = None
        base_settings = settings["settings"][0] if settings["settings"] else None

        if base_settings and "options" in base_settings:
            self.method_combo = create_setting_widget(base_settings)
            self.method_combo.currentTextChanged.connect(self._update_method_settings)
            param_name = base_settings.get("parameter", "method")
            self.method_combo.setProperty("parameter", param_name)
            _add_to_grid(
                self.settings_grid,
                base_settings["label"],
                self.method_combo,
                self._grid_row,
                0,
            )
            self._settings_widgets[param_name] = self.method_combo
            self._grid_row += 1

        remaining = settings["settings"][1 if self.method_combo else 0 :]
        if remaining:
            new_widgets, self._grid_row = _pack_settings_into_grid(
                self.settings_grid, remaining, start_row=self._grid_row
            )
            self._settings_widgets.update(new_widgets)

        self.method_settings_config = settings.get("method_settings", {})

    def _add_method_settings_section(self):
        """Mark where method-specific settings start and populate them."""
        self._method_start_row = self._grid_row
        if self.method_combo:
            self._update_method_settings(self.method_combo.currentText())

    def _update_method_settings(self, method):
        """Update method-specific settings based on selected method."""
        if not hasattr(self, "_method_start_row"):
            return None

        # Remove old method parameter widgets from tracking
        if hasattr(self, "_last_method_params"):
            for param in self._last_method_params:
                self._settings_widgets.pop(param, None)

        _clear_grid_from_row(self.settings_grid, self._method_start_row)

        method = self.method_combo.currentText() if self.method_combo else None
        method_settings = self.method_settings_config.get(method, [])
        self._last_method_params = [
            s.get("parameter") for s in method_settings if s.get("parameter")
        ]

        if method_settings:
            # Separator with method name
            separator = QLabel(f" {method} Settings")
            separator.setFixedHeight(Colors.WIDGET_HEIGHT)
            separator.setStyleSheet(
                f"color: {Colors.TEXT_SECONDARY}; font-size: {Typography.SMALL}px;"
                f"border-top: 1px solid {Colors.BORDER_DARK};"
                f"padding-top: 6px;"
            )
            self.settings_grid.addWidget(
                separator, self._method_start_row, 0, 1, _COLS * 2
            )

            new_widgets, _ = _pack_settings_into_grid(
                self.settings_grid,
                method_settings,
                start_row=self._method_start_row + 1,
            )
            self._settings_widgets.update(new_widgets)

        self.settings_changed.emit()
        QTimer.singleShot(0, self._adjust_height)

    def _adjust_height(self):
        if self.expanded:
            self.resize(self.width(), self.sizeHint().height())

    def _select_input_files(self):
        """Open file dialog to select files."""
        files, _ = QFileDialog.getOpenFileNames(self, "Select Input Files")
        if not files:
            return None

        self.input_files = sorted(files, key=natural_sort_key)
        self._update_file_list()

        # Auto populate parameters from file headers
        dialog = ImportDataDialog(self)
        dialog.set_files(self.input_files)
        self.file_parameters = dialog.get_all_parameters()

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
            return None

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
        from ..icons import icon

        self.expanded = not self.expanded
        self.settings_container.setVisible(self.expanded)

        icon_name = "ph.caret-up" if self.expanded else "ph.caret-down"
        self.expand_btn.setIcon(icon(icon_name, role="muted"))

        self.update_summary()
        self.desc.setVisible(not self.expanded)
        self.params_summary.setVisible(not self.expanded)

        if self.expanded:
            self.setMinimumHeight(self._collapsed_height)
            self.setMaximumHeight(16777215)
        else:
            self.setFixedHeight(self._collapsed_height)

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
            "group_name": self.group_name,
            "save_output": self.save_output,
            "visible_output": self.visible_output,
        }

    def set_settings(self, settings):
        """Set operation settings from config."""

        self.node_id = settings.get("id", self.node_id)
        self.input_nodes = settings.get("inputs", [])

        if "group_name" in settings:
            self.group_name = settings["group_name"]
            if hasattr(self, "group_input"):
                self.group_input.setText(self.group_name)

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

        # Restore operation settings, silently dropping unknown parameters
        # that may come from older pipeline configs with renamed/removed params.
        operation_settings = settings.get("settings", {})
        if not isinstance(operation_settings, dict):
            operation_settings = {}

        if self.operation_id == "import_batch":
            self.input_files = operation_settings.get("input_files", [])
            self.file_parameters = operation_settings.get("file_parameters", {})
            if self.input_files:
                self._update_file_list()
        else:
            for k, v in operation_settings.items():
                widget = self._settings_widgets.get(k)
                if widget is not None:
                    try:
                        set_widget_value(widget, v)
                    except Exception:
                        pass
        self.update_summary()


class PipelineTreeWidget(QTreeWidget):
    """Tree widget for linear pipeline operations."""

    pipeline_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(0)
        self.setRootIsDecorated(False)
        self.setDragEnabled(False)
        self.setAcceptDrops(False)

        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(12)
        self.setViewportMargins(0, 0, 6, 0)
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

        self._add_tail_spacer()

    def _add_tail_spacer(self):
        self._tail_spacer = QTreeWidgetItem()
        self.addTopLevelItem(self._tail_spacer)
        spacer = QWidget()
        spacer.setFixedHeight(120)
        spacer.setStyleSheet("background: transparent;")
        self.setItemWidget(self._tail_spacer, 0, spacer)

    def clear(self):
        super().clear()
        self._add_tail_spacer()

    def _insert_before_spacer(self, item):
        idx = self.indexOfTopLevelItem(self._tail_spacer)
        self.insertTopLevelItem(idx, item)

    def add_operation_card(self, card_widget):
        """Add operation card to list."""

        from ..icons import icon_pixmap

        spacer_idx = self.indexOfTopLevelItem(self._tail_spacer)
        if spacer_idx > 0:
            separator_item = QTreeWidgetItem()
            self._insert_before_spacer(separator_item)

            separator = QWidget()
            layout = QHBoxLayout(separator)
            layout.setContentsMargins(0, 4, 0, 4)
            layout.setSpacing(0)

            layout.addStretch()

            icon_label = QLabel()
            icon_label.setPixmap(icon_pixmap("ph.caret-down", 20, role="muted"))
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(icon_label)
            layout.addStretch()

            separator.setFixedHeight(28)

            self.setItemWidget(separator_item, 0, separator)

        item = QTreeWidgetItem()
        self._insert_before_spacer(item)
        self.setItemWidget(item, 0, card_widget)

        card_widget.removed.connect(lambda w: self._remove_card(item))
        card_widget.settings_changed.connect(lambda: self.scheduleDelayedItemsLayout())
        self.pipeline_changed.emit()
        return item

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
            prev_item = self.topLevelItem(card_index - 1)
            if prev_item is not self._tail_spacer:
                prev_widget = self.itemWidget(prev_item, 0)
                if prev_widget and not isinstance(prev_widget, OperationCardWidget):
                    self.takeTopLevelItem(card_index - 1)

        # If this was the first card, also remove the separator connecting to the next
        if card_index == 0:
            next_item = self.topLevelItem(card_index)
            if next_item is not self._tail_spacer:
                next_widget = self.itemWidget(next_item, 0)
                if next_widget and not isinstance(next_widget, OperationCardWidget):
                    self.takeTopLevelItem(card_index)

        self.pipeline_changed.emit()

    def get_pipeline_config(self):
        """Generate pipeline configuration (supports both linear and graph)."""
        nodes = []
        prev_card_widget = None

        for i in range(self.topLevelItemCount()):
            widget = self.itemWidget(self.topLevelItem(i), 0)

            if not isinstance(widget, OperationCardWidget):
                continue

            node_config = widget.get_settings()
            if prev_card_widget is not None and not node_config["inputs"]:
                node_config["inputs"] = [prev_card_widget.node_id]

            nodes.append(node_config)
            prev_card_widget = widget

        return nodes
