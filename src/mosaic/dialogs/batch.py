"""
Batch processing dialogs for importing and navigating sessions.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from os.path import join, basename, splitext

from qtpy.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QLabel,
    QWidget,
    QGroupBox,
    QCheckBox,
)
from ..stylesheets import QPushButton_style, QGroupBox_style, QScrollArea_style
from ..widgets import ContainerListWidget, StyledTreeWidgetItem, PathSelector, SearchWidget
from .import_data import ImportDataDialog
from .progress import ProgressDialog


class BatchImportDialog(QDialog):
    """Dialog for batch importing segmentation files and creating sessions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.input_files = []
        self.output_dir = None
        self.file_parameters = {}
        self.setup_ui()

        self.setStyleSheet(QPushButton_style + QGroupBox_style + QScrollArea_style)

    def setup_ui(self):
        from ..icons import dialog_accept_icon, dialog_reject_icon

        self.setWindowTitle("Batch Import")
        self.setMinimumWidth(550)
        self.setMinimumHeight(520)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(10, 10, 10, 10)

        # Input files group
        input_group = QGroupBox("Input Files")
        input_layout = QVBoxLayout(input_group)
        input_layout.setSpacing(8)

        # File count label
        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("Selected:"))
        self.file_count_label = QLabel("0 files")
        self.file_count_label.setStyleSheet("color: #6b7280; font-weight: 500;")
        count_layout.addWidget(self.file_count_label)
        count_layout.addStretch()
        input_layout.addLayout(count_layout)

        self.file_list = ContainerListWidget(border=False)
        input_layout.addWidget(self.file_list, 1)

        self.select_files_btn = QPushButton("Select Segmentation Files")
        self.select_files_btn.clicked.connect(self._select_input_files)
        input_layout.addWidget(self.select_files_btn)
        layout.addWidget(input_group, 1)

        # Output directory group
        output_group = QGroupBox("Output Directory")
        output_layout = QVBoxLayout(output_group)
        output_layout.setSpacing(8)

        self.output_selector = PathSelector(
            label_text="",
            placeholder="Select output directory for sessions",
            file_mode=False,
        )
        self.output_selector.path_input.textChanged.connect(
            lambda: self._update_process_button()
        )
        output_layout.addWidget(self.output_selector)

        layout.addWidget(output_group)

        # Action buttons footer
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        button_layout.setContentsMargins(0, 4, 0, 0)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setIcon(dialog_reject_icon)
        self.cancel_btn.clicked.connect(self.reject)

        self.params_btn = QPushButton("Configure Parameters")
        self.params_btn.clicked.connect(self._configure_parameters)
        self.params_btn.setEnabled(False)

        self.process_btn = QPushButton("Process Batch")
        self.process_btn.setIcon(dialog_accept_icon)
        self.process_btn.clicked.connect(self._process_batch)
        self.process_btn.setEnabled(False)
        self.process_btn.setDefault(True)

        button_layout.addWidget(self.cancel_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.params_btn)
        button_layout.addWidget(self.process_btn)

        layout.addLayout(button_layout)

    def _select_input_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Segmentation Files")
        if not files:
            return

        self.input_files = files
        self._update_file_list()
        self.params_btn.setEnabled(True)
        self._update_process_button()

    def _update_file_list(self):
        self.file_list.tree_widget.clear()
        for filepath in self.input_files:
            item = StyledTreeWidgetItem(
                basename(filepath),
                visible=True,
                metadata={"filepath": filepath},
            )
            self.file_list.tree_widget.addTopLevelItem(item)

        count = len(self.input_files)
        self.file_count_label.setText(f"{count} file{'s' if count != 1 else ''}")

    def _update_process_button(self):
        output_path = self.output_selector.get_path()
        can_process = bool(self.input_files) and bool(output_path)
        self.process_btn.setEnabled(can_process)

    def _configure_parameters(self):
        if not self.input_files:
            return

        dialog = ImportDataDialog(self)
        dialog.set_files(self.input_files)

        if dialog.exec():
            self.file_parameters = dialog.get_all_parameters()

    def _process_batch(self):
        self.output_dir = self.output_selector.get_path()

        if not self.file_parameters:
            reply = QMessageBox.question(
                self,
                "No Parameters",
                "Import parameters have not been configured. Use default parameters?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return self._configure_parameters()

            dialog = ImportDataDialog(self)
            dialog.set_files(self.input_files)
            self.file_parameters = dialog.get_all_parameters()

        results = []
        errors = []

        with ProgressDialog(
            self.input_files, title="Creating Sessions", parent=self
        ) as pbar:
            for filepath in pbar:
                try:
                    output_path = self._create_session(filepath)
                    results.append(output_path)
                except Exception as e:
                    errors.append((filepath, str(e)))

        self._show_results(results, errors)

    def _create_session(self, filepath):
        """Create a session from a single file."""
        parameters = self.file_parameters.get(filepath, {})

        self.main_window.close_session(show_warning=False)
        self.main_window._open_file(filepath, parameters)

        base_name = splitext(basename(filepath))[0]
        output_path = join(self.output_dir, f"{base_name}_session.pickle")

        self.main_window.cdata.to_file(output_path)

        return output_path

    def _show_results(self, results, errors):
        """Show batch processing results."""
        total = len(self.input_files)
        success = len(results)
        failed = len(errors)

        msg = "Batch Import Complete\n\n"
        msg += f"Successfully processed: {success}/{total}\n"

        if errors:
            msg += f"Failed: {failed}\n\n"
            msg += "Failed files:\n"
            for filepath, error in errors[:5]:
                msg += f"• {basename(filepath)}: {error}\n"
            if len(errors) > 5:
                msg += f"... and {len(errors) - 5} more"

        QMessageBox.information(self, "Batch Import Complete", msg)

        reply = QMessageBox.question(
            self,
            "Open Navigator",
            "Would you like to open the Batch Navigator to review the sessions?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.accept()
            from ..widgets.dock import create_or_toggle_dock

            widget = BatchNavigatorDialog(results, self.main_window)
            return create_or_toggle_dock(self.main_window, "batch_navigator", widget)
        self.reject()


class BatchNavigatorDialog(QWidget):
    """Widget for navigating through batch-created sessions."""

    def __init__(self, session_files, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.current_index = -1

        self.setWindowTitle("Batch Navigator")
        self.session_files = sorted([f for f in session_files if f.endswith('.pickle')])

        self.setup_ui()
        self.setStyleSheet(QPushButton_style + QGroupBox_style + QScrollArea_style)

        if self.session_files:
            self._load_session_at_index(0)

    def setup_ui(self):
        from ..icons import dialog_accept_icon
        import qtawesome as qta

        self.setMinimumWidth(280)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        count = len(self.session_files)
        sessions_group = QGroupBox(f"{count} Session{'s' if count != 1 else ''}")
        sessions_layout = QVBoxLayout(sessions_group)
        sessions_layout.setSpacing(8)

        self.search_widget = SearchWidget(placeholder="Search sessions...")
        self.search_widget.searchTextChanged.connect(self._filter_sessions)
        sessions_layout.addWidget(self.search_widget)

        self.session_list = ContainerListWidget(border=False)
        self.session_list.tree_widget.setSelectionMode(
            self.session_list.tree_widget.SelectionMode.SingleSelection
        )
        self.session_list.tree_widget.itemClicked.connect(self._on_item_clicked)

        self._populate_session_list()
        sessions_layout.addWidget(self.session_list, 1)

        # Auto-save checkbox
        self.auto_save_checkbox = QCheckBox("Auto-save when switching")
        self.auto_save_checkbox.setChecked(True)
        self.auto_save_checkbox.setToolTip(
            "Automatically save the current session when switching to another"
        )
        sessions_layout.addWidget(self.auto_save_checkbox)

        layout.addWidget(sessions_group, 1)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        self.discard_btn = QPushButton("Discard Changes")
        self.discard_btn.setIcon(qta.icon("mdi.undo-variant", color="#4f46e5"))
        self.discard_btn.clicked.connect(self._discard_changes)
        self.discard_btn.setToolTip("Reload current session, discarding unsaved changes")

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
                basename(filepath),
                visible=(i == self.current_index),
                metadata={"index": i, "filepath": filepath},
            )
            self.session_list.tree_widget.addTopLevelItem(item)

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
            filename = basename(item.metadata.get("filepath", "")).lower()

            # Show item if search text is in filename or if search is empty
            matches = search_text in filename if search_text else True
            item.setHidden(not matches)

    def _on_item_clicked(self, item):
        """Handle single click on session item - load immediately."""
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

        if self.current_index >= 0 and self.auto_save_checkbox.isChecked():
            self._save_current()
        self._load_session_at_index(new_index)

    def _save_current(self):
        """Save the currently loaded session."""
        if self.current_index < 0:
            return

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
        if self.current_index >= 0 and self.auto_save_checkbox.isChecked():
            self._save_current()
        super().close()