import time

import numpy as np
from qtpy.QtCore import Qt, QEvent
from qtpy.QtGui import QCursor
from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSpinBox,
    QLabel,
    QMessageBox,
    QFileDialog,
)

from ..widgets.ribbon import create_button


class PerformanceMonitor:
    """Monitor VTK rendering performance"""

    def __init__(self, render_window):
        self.render_window = render_window
        self.frame_times = []
        self.start_time = None

    def start_monitoring(self):
        self.frame_times = []
        self.start_time = time.time()

    def record_frame(self):
        if self.start_time:
            frame_time = time.time() - self.start_time
            self.frame_times.append(frame_time)
            self.start_time = time.time()

    def get_stats(self):
        if not self.frame_times:
            return {}
        frame_times = np.array(self.frame_times)
        fps = 1.0 / np.mean(frame_times) if np.mean(frame_times) > 0 else 0
        return {
            "avg_fps": fps,
            "min_fps": 1.0 / np.max(frame_times) if np.max(frame_times) > 0 else 0,
            "max_fps": 1.0 / np.min(frame_times) if np.min(frame_times) > 0 else 0,
            "avg_frame_time_ms": np.mean(frame_times) * 1000,
            "frame_count": len(frame_times),
        }

    def print_stats(self, label="Performance"):
        stats = self.get_stats()
        if stats:
            print(f"\n=== {label} ===")
            print(f"Average FPS: {stats['avg_fps']:.1f}")
            print(f"Frame time: {stats['avg_frame_time_ms']:.1f}ms")
            print(f"FPS range: {stats['min_fps']:.1f} - {stats['max_fps']:.1f}")
            print(f"Frames measured: {stats['frame_count']}")


_HAS_ANNOTATION = True
try:
    from ..models.slice_viewer import AnnotationOverlayController
    from ..models.dialog import AnnotationDialog
    from ..models.volume import AnnotationVolume
    from ..models.labels import LabelManager
except Exception:
    _HAS_ANNOTATION = False


class DevelopmentTab(QWidget):
    _KEY_TO_TOOL = {
        Qt.Key.Key_V: "navigate",
        Qt.Key.Key_B: "brush",
        Qt.Key.Key_E: "eraser",
        Qt.Key.Key_F: "fill",
    }

    def __init__(self, cdata, ribbon, **kwargs):
        super().__init__()
        self.cdata = cdata
        self.ribbon = ribbon
        self.legend = kwargs.get("legend", None)
        self.volume_viewer = kwargs.get("volume_viewer", None)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ribbon)

        self._offset_x = None
        self._offset_y = None
        self._offset_z = None

        self._overlay = None
        self._tool_panel = None
        self._labels = None
        self._cached_logits = None
        self._prediction_label_id = None

    def _create_offset_spinbox(self):
        spinbox = QSpinBox()
        spinbox.setMinimumWidth(80)
        spinbox.setRange(-100000, 100000)
        spinbox.setSingleStep(1)
        spinbox.setValue(0)
        return spinbox

    def _create_translation_widget(self):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(8)
        layout.addWidget(QLabel("X:"))
        self._offset_x = self._create_offset_spinbox()
        layout.addWidget(self._offset_x)
        layout.addWidget(QLabel("Y:"))
        self._offset_y = self._create_offset_spinbox()
        layout.addWidget(self._offset_y)
        layout.addWidget(QLabel("Z:"))
        self._offset_z = self._create_offset_spinbox()
        layout.addWidget(self._offset_z)
        return container

    def translate_geometries(self, *args):
        if self._offset_x is None:
            return
        offset = np.array(
            [self._offset_x.value(), self._offset_y.value(), self._offset_z.value()],
            dtype=np.float32,
        )
        if np.allclose(offset, 0):
            return
        for geometry in self.cdata.data.get_selected_geometries():
            points = geometry.points.copy()
            points += offset * geometry.sampling_rate
            geometry.points = points
            geometry._data.Modified()
        self.cdata.data.render()

    def _stream_test_zarr(self):
        """Load a preset CZI tomogram via Zarr streaming."""
        if self.volume_viewer is None:
            return
        url = (
            "s3://cryoet-data-portal-public/10473/"
            "210610_Lamela1_Position_35/Reconstructions/"
            "VoxelSpacing5.003/Tomograms/100/"
            "210610_Lamela1_Position_35.zarr"
        )
        try:
            self.volume_viewer.primary.load_volume(url)
        except Exception as e:
            print(f"Zarr streaming error: {e}")

    def show_ribbon(self):
        self.ribbon.clear()
        cluster_actions = [
            create_button(
                "Add", "mdi.plus", self, self.add_cloud, "Add test point cloud"
            ),
            create_button(
                "Test Render",
                "mdi.test-tube",
                self,
                self.test_point_rendering_performance,
                "Benchmark rendering",
            ),
        ]
        self.ribbon.add_section("Base Operations", cluster_actions)

        translation_widget = self._create_translation_widget()
        translate_button = create_button(
            "Translate",
            "mdi.arrow-all",
            self,
            self.translate_geometries,
            "Translate all geometries by offset",
        )
        self.ribbon.add_section("Translation", [translation_widget, translate_button])

        zarr_button = create_button(
            "Stream Zarr",
            "mdi.cloud-download",
            self,
            self._stream_test_zarr,
            "Stream a CZI tomogram via OME-Zarr",
        )
        self.ribbon.add_section("Zarr", [zarr_button])

        if _HAS_ANNOTATION:
            self.ribbon.add_section(
                "AI",
                [
                    create_button(
                        "AI",
                        "ph.brain",
                        self,
                        self._toggle_annotator,
                        "Open annotation and training tools",
                    ),
                ],
            )

    def add_cloud(self, *args):
        num_points = 1000
        points = np.random.rand(num_points, 3) * 100
        self.cdata.data.add(points=points, sampling_rate=2)
        self.cdata.data.render()

    def test_point_rendering_performance(self, *args, **kwargs):
        test_duration = 5.0
        vtk_widget = self.cdata.data.vtk_widget
        render_window = vtk_widget.GetRenderWindow()
        renderer = render_window.GetRenderers().GetFirstRenderer()
        camera = renderer.GetActiveCamera()
        monitor = PerformanceMonitor(render_window)
        monitor.start_monitoring()
        start_time = time.time()
        while (time.time() - start_time) < test_duration:
            camera.Azimuth(1.0)
            monitor.start_time = time.time()
            render_window.Render()
            monitor.record_frame()
            vtk_widget.GetRenderWindow().GetInteractor().ProcessEvents()
        monitor.print_stats()
        return monitor

    def eventFilter(self, obj, event):
        if self._overlay is None or not self._overlay.active:
            return super().eventFilter(obj, event)

        if event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
            is_action = event.type() == QEvent.Type.KeyPress

            if event.key() == Qt.Key.Key_Escape:
                if is_action:
                    self._switch_tool("navigate")
                event.accept()
                return True

            if (
                event.key() == Qt.Key.Key_Z
                and event.modifiers() == Qt.KeyboardModifier.ControlModifier
            ):
                if is_action:
                    self._undo()
                event.accept()
                return True

            tool = self._KEY_TO_TOOL.get(event.key())
            if tool is not None and not event.modifiers():
                if is_action:
                    self._switch_tool(tool)
                event.accept()
                return True

        return super().eventFilter(obj, event)

    def _undo(self):
        if self._overlay is None or self._overlay.annotation is None:
            return
        if self._overlay.annotation.undo():
            self._overlay._refresh_overlay_slice()

    def _switch_tool(self, tool_id):
        if self._tool_panel is not None and tool_id in self._tool_panel._tool_buttons:
            self._tool_panel._tool_buttons[tool_id].setChecked(True)
        self._on_tool_changed(tool_id)

    def _get_volume(self):
        if self.volume_viewer is None:
            return None
        return getattr(self.volume_viewer.primary, "_volume", None)

    def _toggle_annotator(self):
        from ..widgets.dock import create_or_toggle_dock

        if getattr(self, "_tool_dock", None) is not None:
            self._deactivate_overlay()
            create_or_toggle_dock(self, "_tool_dock", None)
            self._tool_panel = None
            return

        if self._labels is None:
            self._labels = LabelManager()

        if self._tool_panel is None:
            self._tool_panel = AnnotationDialog(self._labels, parent=self)
            self._tool_panel.brush_changed.connect(self._on_brush_changed)
            self._tool_panel.tool_changed.connect(self._on_tool_changed)
            self._tool_panel.labels_changed.connect(self._on_labels_changed)
            self._tool_panel.import_btn.clicked.connect(self._import_mask)
            self._tool_panel.export_btn.clicked.connect(self._export_mask)
            self._tool_panel.clear_btn.clicked.connect(self._clear_annotations)
            self._tool_panel.to_cluster_btn.clicked.connect(self._mask_to_clusters)
            self._tool_panel.from_cluster_btn.clicked.connect(self._clusters_to_mask)
            self._tool_panel.train_btn.clicked.connect(self._train_model)
            self._tool_panel.extract_btn.clicked.connect(self._extract_patches)
            self._tool_panel.threshold_slider.valueChanged.connect(
                self._on_threshold_changed
            )
            self._tool_panel.predict_btn.clicked.connect(self._run_inference)

        self._tool_panel.refresh_labels()
        create_or_toggle_dock(self, "_tool_dock", self._tool_panel)

        if self._tool_dock is not None:
            original_close = self._tool_dock.closeEvent

            def _on_dock_close(event):
                self._deactivate_overlay()
                self._tool_panel = None
                original_close(event)

            self._tool_dock.closeEvent = _on_dock_close

        self._activate_overlay()

        if self.volume_viewer is not None:
            self.volume_viewer.primary.data_changed.connect(self._on_volume_loaded)

    def _activate_overlay(self):
        volume = self._get_volume()
        if volume is None or 0 in volume.GetDimensions():
            return

        renderer = (
            self.cdata.data.vtk_widget.GetRenderWindow()
            .GetRenderers()
            .GetFirstRenderer()
        )
        vtk_widget = self.cdata.data.vtk_widget

        if self._overlay is None:
            self._overlay = AnnotationOverlayController(
                renderer, vtk_widget, self.volume_viewer
            )
        dims = volume.GetDimensions()
        if self._overlay.annotation is None or self._overlay.annotation.shape != tuple(
            dims
        ):
            self._overlay.annotation = AnnotationVolume(dims, volume.GetSpacing())

        self._overlay.activate(self._overlay.annotation, self._labels)
        self._overlay.tool_panel = self._tool_panel
        vtk_widget.installEventFilter(self)

    def _deactivate_overlay(self):
        if self._overlay is not None:
            self._overlay.deactivate()
            self._overlay.tool_panel = None
        self.cdata.data.vtk_widget.removeEventFilter(self)
        try:
            if self.volume_viewer is not None:
                self.volume_viewer.primary.data_changed.disconnect(
                    self._on_volume_loaded
                )
        except (TypeError, RuntimeError):
            pass

    def _on_volume_loaded(self):
        self._cached_logits = None
        self._prediction_label_id = None
        if self._overlay is not None and self._overlay.active:
            self._overlay.deactivate()
        self._activate_overlay()

    def _on_threshold_changed(self, value):
        """Re-threshold cached logits and update the overlay."""
        if self._cached_logits is None or self._prediction_label_id is None:
            return
        if self._overlay is None or self._overlay.annotation is None:
            return

        threshold = self._tool_panel.logit_threshold if self._tool_panel else 0.0
        layer = self._overlay.annotation._get_layer(self._prediction_label_id)
        layer[:] = self._cached_logits > threshold
        if self._overlay.active:
            self._overlay._refresh_overlay_slice()

    def _on_brush_changed(self, value):
        if self._overlay is not None:
            self._overlay._brush_radius = float(value)

    def _on_tool_changed(self, tool_id):
        if tool_id != "navigate" and (
            self._overlay is None or not self._overlay.active
        ):
            self._activate_overlay()

        if self._overlay is None:
            return
        self._overlay.active_tool = tool_id
        if not self._overlay.active:
            return
        interactor = self.cdata.data.vtk_widget.GetRenderWindow().GetInteractor()
        if interactor.GetInteractorStyle() is not self._overlay._paint_style:
            interactor.SetInteractorStyle(self._overlay._paint_style)
        self._overlay._paint_style._update_cursor()
        self.cdata.data.vtk_widget.GetRenderWindow().Render()

    def _on_labels_changed(self):
        if self._overlay is not None and self._overlay.active:
            self._overlay.invalidate_lut()
            self._overlay._refresh_overlay_slice()

    def _import_mask(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Annotation Mask", "", "NumPy Files (*.npz);;All Files (*.*)"
        )
        if not path:
            return
        volume = self._get_volume()
        expected_shape = volume.GetDimensions() if volume else None
        expected_spacing = volume.GetSpacing() if volume else None

        try:
            annotation = AnnotationVolume.from_file(
                path,
                expected_shape=expected_shape,
                expected_spacing=expected_spacing,
            )
        except ValueError as e:
            QMessageBox.warning(self, "Shape Mismatch", str(e))
            return

        if hasattr(annotation, "metadata") and annotation.metadata.get("labels"):
            stored_labels = LabelManager.from_dict(annotation.metadata["labels"])
            for label in stored_labels:
                if self._labels.get_label(label.id) is None:
                    self._labels._labels[label.id] = label
                    self._labels._next_id = max(self._labels._next_id, label.id + 1)
            if self._tool_panel is not None:
                self._tool_panel.refresh_labels()

        if self._overlay is not None:
            self._overlay.annotation = annotation
            self._overlay.invalidate_lut()
            if self._overlay.active:
                self._overlay._build_overlay()
                self._overlay._refresh_overlay_slice()

    def _export_mask(self):
        annotation = self._overlay.annotation if self._overlay else None
        if annotation is None:
            QMessageBox.information(self, "No Annotations", "Nothing to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Annotation Mask", "", "NumPy Files (*.npz)"
        )
        if path:
            tomogram_path = getattr(self.volume_viewer.primary, "source_path", None)
            annotation.to_file(
                path,
                labels=self._labels,
                source_path=tomogram_path,
            )

    def _mask_to_clusters(self):
        if self._overlay is None or self._overlay.annotation is None:
            QMessageBox.information(self, "No Annotations", "Nothing to convert.")
            return
        from ..geometry import Geometry

        active = self._labels.active
        if active is None:
            QMessageBox.information(self, "No Label", "Select a label first.")
            return

        annotation = self._overlay.annotation
        sampling = annotation.sampling_rate
        mask = annotation.get_class_mask(active.id)
        coords = np.argwhere(mask > 0).astype(np.float32)
        if len(coords) == 0:
            QMessageBox.information(self, "Empty", "Selected label has no annotations.")
            return
        points = coords * sampling
        geom = Geometry(points=points, sampling_rate=sampling)
        geom._meta["name"] = active.name
        r, g, b = active.color
        geom._appearance["color"] = (r, g, b)
        self.cdata.data.add(geom)
        self.cdata.data.render()

    def _clusters_to_mask(self):
        if self._overlay is None or self._overlay.annotation is None:
            QMessageBox.information(
                self,
                "No Annotation Volume",
                "Start annotation first to create a volume.",
            )
            return
        geometries = self.cdata.data.get_selected_geometries()
        if not geometries:
            QMessageBox.information(self, "No Selection", "Select clusters first.")
            return
        annotation = self._overlay.annotation
        sampling = annotation.sampling_rate
        shape = annotation.shape
        for geom in geometries:
            name = geom._meta.get("name", "Cluster")
            label_id = self._labels.add_label(name)
            voxels = np.round(geom.points / sampling).astype(int)
            valid = (
                (voxels[:, 0] >= 0)
                & (voxels[:, 0] < shape[0])
                & (voxels[:, 1] >= 0)
                & (voxels[:, 1] < shape[1])
                & (voxels[:, 2] >= 0)
                & (voxels[:, 2] < shape[2])
            )
            voxels = voxels[valid]
            layer = annotation._get_layer(label_id)
            layer[voxels[:, 0], voxels[:, 1], voxels[:, 2]] = True
        if self._tool_panel is not None:
            self._tool_panel.refresh_labels()
        if self._overlay.active:
            self._overlay.invalidate_lut()
            self._overlay._refresh_overlay_slice()

    def _clear_annotations(self):
        if self._overlay is None or self._overlay.annotation is None:
            return
        ret = QMessageBox.question(
            self,
            "Clear Annotations",
            "Remove all annotations?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ret == QMessageBox.StandardButton.Yes:
            self._overlay.annotation.clear()
            if self._overlay.active:
                self._overlay._refresh_overlay_slice()

    def _extract_volume_array(self):
        """Extract the tomogram as a numpy array from VTK."""
        from vtkmodules.util import numpy_support

        volume = self._get_volume()
        if volume is None:
            return None
        dims = volume.GetDimensions()
        scalars = numpy_support.vtk_to_numpy(volume.GetPointData().GetScalars())
        return scalars.reshape(dims, order="F").astype(np.float32)

    def _prepare_manifest(self, action="train"):
        """Validate state and build a training manifest.

        Returns ``(manifest, fg_labels, bg_labels, label_name, tmp_dir)``
        or *None* if validation fails (user is notified via dialog).
        """
        import os
        import tempfile

        if self._overlay is None or self._overlay.annotation is None:
            QMessageBox.information(self, "No Annotations", "Annotate slices first.")
            return None

        fg_labels = self._labels.get_foreground_ids()
        bg_labels = self._labels.get_background_ids()
        if not fg_labels:
            active = self._labels.active
            if active is None:
                QMessageBox.information(
                    self, "No Label", f"Select a label to {action}."
                )
                return None
            fg_labels = [active.id]

        tomogram_path = getattr(self.volume_viewer.primary, "source_path", None)
        if not tomogram_path:
            QMessageBox.warning(self, "No Source Path", "Re-load the volume.")
            return None

        output_dir = self._tool_panel.get_output_dir() if self._tool_panel else ""
        if not output_dir:
            QMessageBox.information(self, "No Output", "Set an output directory first.")
            return None

        annotation = self._overlay.annotation
        axis = self._overlay._orientation
        is_3d = self._tool_panel is not None and self._tool_panel.is_3d
        mode = "3d" if is_3d else "2d"

        tmp_dir = tempfile.mkdtemp(prefix=f"mosaic_{action}_")
        annotation_path = os.path.join(tmp_dir, "annotation.npz")
        annotation.to_file(
            annotation_path,
            labels=self._labels,
            source_path=tomogram_path,
        )

        from ..models.dataset import build_manifest

        dense_masks = self._tool_panel is not None and self._tool_panel.dense_masks
        manifest = build_manifest(
            tomogram_path=tomogram_path,
            annotation_path=annotation_path,
            foreground_labels=fg_labels,
            background_labels=bg_labels,
            axis=axis,
            patch_size=annotation.patch_size,
            mode=mode,
            dense_masks=dense_masks,
        )

        fg_names = [
            self._labels.get_label(lid).name
            for lid in fg_labels
            if self._labels.get_label(lid)
        ]
        label_name = "_".join(fg_names) or "model"

        return manifest, fg_labels, bg_labels, label_name, output_dir, tmp_dir

    def _extract_patches(self):
        """Write training patches to disk exactly as the dataloader sees them."""
        import os
        import shutil

        result = self._prepare_manifest(action="extract")
        if result is None:
            return
        manifest, fg_labels, bg_labels, label_name, output_dir, tmp_dir = result

        from ..models.dataset import SegmentationDataset

        dataset = SegmentationDataset(manifest)
        is_3d = manifest.get("mode") == "3d"

        extract_dir = os.path.join(output_dir, f"patches_{label_name}")
        os.makedirs(extract_dir, exist_ok=True)

        for idx in range(len(dataset)):
            img, msk = dataset[idx]
            img_np = img[0].numpy()
            msk_np = msk.numpy()
            if is_3d:
                mid = img_np.shape[0] // 2
                self._save_patch(extract_dir, idx, img_np[mid], msk_np[mid])
            else:
                self._save_patch(extract_dir, idx, img_np, msk_np)

        shutil.rmtree(tmp_dir, ignore_errors=True)

        QMessageBox.information(
            self, "Done", f"Extracted {len(dataset)} patches to:\n{extract_dir}"
        )

    @staticmethod
    def _save_patch(output_dir, idx, img, mask):
        """Save an image/mask pair as PNGs for visual inspection.

        Mask values: 0 (bg) → black, 1 (fg) → white, 2 (ignore) → gray.
        """
        import os
        from PIL import Image

        def to_uint8(arr):
            arr = arr.astype(np.float64)
            lo, hi = arr.min(), arr.max()
            if hi - lo > 0:
                arr = (arr - lo) / (hi - lo) * 255
            return arr.astype(np.uint8)

        lut = np.array([0, 255, 128], dtype=np.uint8)
        mask_vis = lut[np.clip(mask, 0, 2).astype(int)]

        Image.fromarray(to_uint8(img)).save(
            os.path.join(output_dir, f"{idx:04d}_img.png")
        )
        Image.fromarray(mask_vis).save(os.path.join(output_dir, f"{idx:04d}_mask.png"))

    def _train_model(self):
        import os
        import atexit, shutil

        result = self._prepare_manifest(action="train")
        if result is None:
            return
        manifest, fg_labels, bg_labels, label_name, output_dir, tmp_dir = result

        mode = manifest["mode"]
        axis = manifest["axis"]
        config = self._tool_panel.get_training_config() if self._tool_panel else {}

        os.makedirs(output_dir, exist_ok=True)
        save_path = os.path.join(output_dir, f"{label_name}_{mode}.pt")

        def _cleanup_tmp():
            shutil.rmtree(tmp_dir, ignore_errors=True)

        atexit.register(_cleanup_tmp)

        volume = self._get_volume()
        spacing = list(volume.GetSpacing()) if volume else [1, 1, 1]

        from ..models.trainer import train_from_manifest
        from ..parallel import submit_task

        def _on_complete(result):
            import torch, io

            config = result["config"]
            config["label_name"] = label_name
            config["axis"] = axis
            config["source_spacing"] = spacing
            checkpoint = torch.load(
                io.BytesIO(result["model_bytes"]), weights_only=False
            )
            checkpoint["config"] = config
            torch.save(checkpoint, save_path)
            metrics = result["metrics"]
            if self._tool_panel is not None:
                self._tool_panel.predict_status.setText(
                    f"Trained: {label_name} (loss: {metrics['val_loss']:.4f}, "
                    f"epoch {metrics['best_epoch']}/{len(metrics['loss_history'])})"
                )
                self._tool_panel.model_path.set_path(save_path)
                self._tool_panel._last_metrics = metrics

            if self._tool_panel is not None:
                self._tool_panel.stop_loss_monitoring()

            _cleanup_tmp()
            atexit.unregister(_cleanup_tmp)

        # Start live loss monitoring — remove stale log first
        if self._tool_panel is not None:
            log_path = os.path.join(output_dir, "training_log.csv")
            if os.path.exists(log_path):
                os.remove(log_path)
            self._tool_panel.start_loss_monitoring(log_path)

        submit_task(
            f"Train: {label_name}",
            train_from_manifest,
            _on_complete,
            manifest,
            num_classes=2,
            save_dir=output_dir,
            **config,
        )

    def _run_inference(self):
        model_path = self._tool_panel.get_model_path() if self._tool_panel else ""
        if not model_path:
            QMessageBox.information(self, "No Model", "Select a model file.")
            return

        import torch

        try:
            checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)
        except Exception as e:
            QMessageBox.warning(self, "Load Error", str(e))
            return

        if isinstance(checkpoint, dict) and "config" in checkpoint:
            config = checkpoint["config"]
        else:
            QMessageBox.warning(
                self,
                "Invalid Model",
                "File does not contain an embedded config. "
                "Re-train or use a checkpoint saved by this version.",
            )
            return

        volume = self._get_volume()
        if volume is not None and "source_spacing" in config:
            train_sp = np.array(config["source_spacing"])
            curr_sp = np.array(volume.GetSpacing())
            rel_diff = np.abs(train_sp - curr_sp) / np.maximum(train_sp, 1e-8)
            if np.any(rel_diff > 0.2):
                ret = QMessageBox.question(
                    self,
                    "Spacing Mismatch",
                    f"Model trained at {train_sp.tolist()} but volume is "
                    f"{curr_sp.tolist()}. Continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if ret != QMessageBox.StandardButton.Yes:
                    return

        volume_array = self._extract_volume_array()
        if volume_array is None:
            return

        active = self._labels.active
        from ..models.inference import run_inference
        from ..parallel import submit_task

        to_overlay = self._tool_panel is not None and self._tool_panel.output_to_overlay
        threshold = self._tool_panel.logit_threshold if self._tool_panel else 0.0
        pred_name = f"Prediction: {active.name}" if active else "Prediction"

        def _on_complete(logits):
            # Cache logits for interactive re-thresholding
            self._cached_logits = logits

            mask = logits > threshold
            if (
                to_overlay
                and self._overlay is not None
                and self._overlay.annotation is not None
            ):
                pred_label_id = self._labels.add_label(pred_name)
                self._prediction_label_id = pred_label_id
                layer = self._overlay.annotation._get_layer(pred_label_id)
                layer[mask] = True
                if self._tool_panel is not None:
                    self._tool_panel.refresh_labels()
                    self._tool_panel.predict_status.setText("Drag threshold to adjust")
                if not self._overlay.active:
                    self._activate_overlay()
                self._overlay._refresh_overlay_slice()
            else:
                from ..geometry import Geometry

                coords = np.argwhere(mask).astype(np.float32)
                if len(coords) > 0:
                    sampling = (
                        self._overlay.annotation.sampling_rate
                        if self._overlay and self._overlay.annotation
                        else np.ones(3)
                    )
                    geom = Geometry(points=coords * sampling, sampling_rate=sampling)
                    geom._meta["name"] = f"Prediction"
                    self.cdata.data.add(geom)
                    self.cdata.data.render()

        axis = self._overlay._orientation if self._overlay else "Z"
        submit_task(
            "Run Inference",
            run_inference,
            _on_complete,
            volume_array,
            model_path,
            config,
            axis=axis,
        )
