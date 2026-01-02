"""
Distance-based cropping dialog for filtering points by proximity.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
    QVBoxLayout,
    QDialog,
    QLabel,
    QDoubleSpinBox,
    QHBoxLayout,
    QPushButton,
    QTreeWidget,
    QRadioButton,
    QButtonGroup,
    QGroupBox,
    QFrame,
    QMessageBox,
)
import qtawesome as qta

from ..widgets.container_list import ContainerTreeWidget, StyledTreeWidgetItem
from ..stylesheets import (
    QGroupBox_style,
    QPushButton_style,
    QScrollArea_style,
    HelpLabel_style,
    Colors,
)


class DistanceCropDialog(QDialog):
    """Dialog for cropping geometry points based on distance to reference objects.

    This dialog can be displayed as a dock widget for interactive preview
    of points that would be removed/kept by the distance crop operation.

    Parameters
    ----------
    cdata : MosaicData
        Application data manager for accessing geometry containers.
    parent : QWidget, optional
        Parent widget.
    """

    cropApplied = Signal(dict)
    previewRequested = Signal(dict)

    def __init__(self, cdata, parent=None):
        super().__init__(parent)
        self.cdata = cdata
        self._preview_active = False
        self._original_colors = {}
        self._trees = []
        self._tree_labels = []

        self.setWindowTitle("Distance Crop")
        self.setMinimumWidth(320)
        self.setMaximumWidth(420)
        self.setup_ui()
        self.setStyleSheet(
            QGroupBox_style
            + QPushButton_style
            + QScrollArea_style
            + """
            QRadioButton {
                spacing: 5px;
            }
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
            }
            """
        )

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # Crop Target panel - objects to be cropped
        crop_panel = QGroupBox("Crop Target")
        crop_layout = QVBoxLayout(crop_panel)
        crop_layout.setSpacing(6)

        crop_description = QLabel("Objects to crop")
        crop_description.setStyleSheet(HelpLabel_style)
        crop_layout.addWidget(crop_description)

        self.crop_tree = ContainerTreeWidget(border=False)
        self.crop_tree.tree_widget.setSelectionMode(
            QTreeWidget.SelectionMode.ExtendedSelection
        )
        crop_layout.addWidget(self.crop_tree, 1)

        main_layout.addWidget(crop_panel, 1)

        # Distance Reference panel - objects to compute distance to
        ref_panel = QGroupBox("Distance Reference")
        ref_layout = QVBoxLayout(ref_panel)
        ref_layout.setSpacing(6)

        ref_description = QLabel("Compute distance to")
        ref_description.setStyleSheet(HelpLabel_style)
        ref_layout.addWidget(ref_description)

        self.ref_tree = ContainerTreeWidget(border=False)
        self.ref_tree.tree_widget.setSelectionMode(
            QTreeWidget.SelectionMode.ExtendedSelection
        )
        ref_layout.addWidget(self.ref_tree, 1)

        main_layout.addWidget(ref_panel, 1)

        # Settings panel
        settings_group = QGroupBox("Settings")
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.setSpacing(8)

        # Distance input row
        distance_layout = QHBoxLayout()
        distance_label = QLabel("Max Distance:")
        distance_layout.addWidget(distance_label)
        distance_layout.addStretch()

        self.distance_input = QDoubleSpinBox()
        self.distance_input.setValue(40.0)
        self.distance_input.setRange(0.01, 9999.99)
        self.distance_input.setMaximum(float("inf"))
        self.distance_input.setDecimals(2)
        self.distance_input.setSingleStep(1.0)
        self.distance_input.setMinimumWidth(100)
        distance_layout.addWidget(self.distance_input)
        settings_layout.addLayout(distance_layout)

        # Direction radio buttons row
        direction_layout = QHBoxLayout()
        direction_label = QLabel("Keep:")
        direction_layout.addWidget(direction_label)
        direction_layout.addStretch()

        self.comparison_group = QButtonGroup()

        radio_container = QFrame()
        radio_layout = QHBoxLayout(radio_container)
        radio_layout.setContentsMargins(0, 0, 0, 0)
        radio_layout.setSpacing(12)

        self.smaller_radio = QRadioButton("Within")
        self.smaller_radio.setChecked(True)
        self.larger_radio = QRadioButton("Outside")
        self.comparison_group.addButton(self.smaller_radio)
        self.comparison_group.addButton(self.larger_radio)

        radio_layout.addWidget(self.smaller_radio)
        radio_layout.addWidget(self.larger_radio)

        direction_layout.addWidget(radio_container)
        settings_layout.addLayout(direction_layout)

        main_layout.addWidget(settings_group)

        # Footer with Preview, Cancel, and Crop buttons
        footer = QFrame()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 8, 0, 0)

        self.preview_button = QPushButton("Preview")
        self.preview_button.setIcon(qta.icon("ph.eye", color=Colors.ICON))
        self.preview_button.setStyleSheet(QPushButton_style)
        self.preview_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview_button.clicked.connect(self._on_preview)
        footer_layout.addWidget(self.preview_button)

        footer_layout.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setIcon(qta.icon("ph.x", color=Colors.ICON))
        self.cancel_button.setStyleSheet(QPushButton_style)
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.reject)
        footer_layout.addWidget(self.cancel_button)

        self.crop_button = QPushButton("Crop")
        self.crop_button.setIcon(qta.icon("ph.scissors", color=Colors.PRIMARY))
        self.crop_button.setStyleSheet(QPushButton_style)
        self.crop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.crop_button.clicked.connect(self.accept)
        footer_layout.addWidget(self.crop_button)

        main_layout.addWidget(footer)

        self.populate_lists()

    def populate_lists(self):
        """Populate crop and reference trees with available geometry objects."""
        self._populate_crop_tree()
        self._populate_ref_tree()

    def _populate_crop_tree(self):
        """Populate the crop target tree with cluster objects."""
        self.crop_tree.tree_widget.clear()

        clusters = {obj.uuid: obj for _, obj in self.cdata.format_datalist("data")}
        if clusters:
            state = self.cdata.data.data_list.to_state()
            uuid_to_item = {}
            for uuid, obj in clusters.items():
                item = StyledTreeWidgetItem(
                    obj._meta.get("name", "Unknown"),
                    obj.visible,
                    {"object": obj, "data_type": "data", **obj._meta},
                )
                uuid_to_item[uuid] = item

            self.crop_tree.apply_state(state, uuid_to_item)

    def _populate_ref_tree(self):
        """Populate the reference tree with both clusters and models (flat, no groups)."""
        self.ref_tree.tree_widget.clear()

        # Add clusters
        for name, obj in self.cdata.format_datalist("data"):
            item = StyledTreeWidgetItem(name, obj.visible, {"object": obj, **obj._meta})
            self.ref_tree.tree_widget.addTopLevelItem(item)

        # Add models
        for name, obj in self.cdata.format_datalist("models"):
            item = StyledTreeWidgetItem(name, obj.visible, {"object": obj, **obj._meta})
            self.ref_tree.tree_widget.addTopLevelItem(item)

    def _get_crop_parameters(self):
        """Extract current crop parameters from UI state.

        Returns
        -------
        dict or None
            Dictionary with sources, targets, distance, keep_smaller keys,
            or None if validation fails.
        """
        # Get sources from tree widget
        sources = []
        for item in self.crop_tree.selected_items():
            if "object" in item.metadata:
                sources.append(item.metadata["object"])

        # Get targets from reference tree
        targets = []
        for item in self.ref_tree.selected_items():
            if "object" in item.metadata:
                targets.append(item.metadata["object"])

        if not sources:
            QMessageBox.warning(
                self,
                "Selection Required",
                "Please select at least one object to crop.",
            )
            return None

        if not targets:
            QMessageBox.warning(
                self,
                "Selection Required",
                "Please select at least one distance reference.",
            )
            return None

        return {
            "sources": sources,
            "targets": targets,
            "distance": self.distance_input.value(),
            "keep_smaller": self.smaller_radio.isChecked(),
        }

    def _on_preview(self):
        """Handle preview button click."""
        params = self._get_crop_parameters()
        if params is None:
            return

        self._clear_preview()
        self._apply_preview(params)

    def _apply_preview(self, params):
        """Apply preview highlighting to show points that would be removed.

        Parameters
        ----------
        params : dict
            Crop parameters with sources, targets, distance, keep_smaller.
        """
        from ..properties import GeometryProperties
        import numpy as np

        sources = params["sources"]
        targets = params["targets"]
        distance = params["distance"]
        keep_smaller = params["keep_smaller"]

        for source in sources:
            # Store original base color for restoration
            if source.uuid not in self._original_colors:
                base_color = source._appearance.get("base_color", (0.7, 0.7, 0.7))
                self._original_colors[source.uuid] = base_color

            # Compute distances to target references
            dist = GeometryProperties.compute(
                geometry=source,
                property_name="distance",
                queries=targets,
                include_self=True,
            )

            # Determine which points would be kept
            # keep_smaller=True (Within): keep points where dist < distance
            # keep_smaller=False (Outside): keep points where dist >= distance
            if keep_smaller:
                keep_mask = dist < distance
            else:
                keep_mask = dist >= distance

            keep_ids = np.where(keep_mask)[0]

            if len(keep_ids) > 0:
                self.cdata._data.highlight_points(source.uuid, keep_ids, None)

        self._preview_active = True
        self.cdata.data.render_vtk()

    def _clear_preview(self):
        """Clear preview highlighting and restore original colors."""
        if not self._preview_active:
            return

        for uuid, base_color in self._original_colors.items():
            if (geometry := self.cdata._data.get(uuid)) is not None:
                # Reset all points to base color
                geometry.set_color(base_color)

        self._original_colors.clear()
        self._preview_active = False
        self.cdata.data.render_vtk()

    def accept(self):
        """Handle crop button - apply crop but keep dialog open."""
        params = self._get_crop_parameters()
        if params is None:
            return

        self._clear_preview()
        self.cropApplied.emit(params)

    def reject(self):
        """Handle dialog rejection."""
        self._clear_preview()
        return super().reject()

    def closeEvent(self, event):
        """Clean up preview when dialog is closed."""
        self._clear_preview()
        super().closeEvent(event)
