"""
Batch session navigator for browsing and managing session files.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
    QGroupBox,
    QScrollArea,
    QFileDialog,
    QMessageBox,
    QFrame,
    QSizePolicy,
)
from qtpy.QtCore import Qt, Signal

from ._utils import natural_sort_key, strip_filepath
from ..widgets import SearchWidget
from ..widgets.cards import Card, FlowLayout
from ..stylesheets import Colors, QScrollArea_style

__all__ = ["BatchNavigatorDialog"]

_LIST_ITEM_W = 160
_LIST_ITEM_H = 28
_LIST_R = 5


def _list_item_qss(cls_name):
    return f"""
        {cls_name} {{
            border: 1px solid {Colors.BORDER_DARK};
            border-radius: {_LIST_R}px;
            background: transparent;
        }}
        {cls_name}:hover {{
            border-color: {Colors.BORDER_HOVER};
        }}
    """


def _list_item_qss_current(cls_name):
    return f"""
        {cls_name} {{
            border: 1px solid {Colors.PRIMARY};
            border-radius: {_LIST_R}px;
            background: rgba(79, 70, 229, 0.06);
        }}
    """


class SessionListItem(QFrame):
    """Compact session tile for the list view mode."""

    clicked = Signal(object)

    def __init__(self, filepath, index, is_current=False, parent=None):
        super().__init__(parent)
        from ..icons import icon as _icon

        self.metadata = {"index": index, "filepath": filepath}
        self._is_current = False

        cls = type(self).__name__
        self._qss_normal = _list_item_qss(cls)
        self._qss_current = _list_item_qss_current(cls)

        self.setFixedSize(_LIST_ITEM_W, _LIST_ITEM_H)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(4)

        self._icon = QLabel()
        self._icon.setFixedSize(14, 14)
        lay.addWidget(self._icon)

        self._label = QLabel(strip_filepath(filepath))
        self._label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 11px; border: none;"
            " background: transparent;"
        )
        self._label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        lay.addWidget(self._label, 1)

        self._eye_icon = _icon("ph.eye", role="primary")
        self._file_icon = _icon("ph.file", role="muted")

        self.set_current(is_current)

    def set_current(self, current):
        self._is_current = current
        self._icon.setPixmap(
            (self._eye_icon if current else self._file_icon).pixmap(14, 14)
        )
        self.setStyleSheet(self._qss_current if current else self._qss_normal)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self)
        ev.accept()


_CARD_W = 180
_CARD_THUMB_H = 100
_CARD_TEXT_H = 24


class SessionCard(Card):
    """Compact gallery card for a session file with placeholder thumbnail."""

    clicked = Signal(object)

    def __init__(self, filepath, index, is_current=False, parent=None):
        super().__init__(
            parent, width=_CARD_W, thumb_height=_CARD_THUMB_H, text_height=_CARD_TEXT_H
        )
        self.metadata = {"index": index, "filepath": filepath}
        self._title.setText(strip_filepath(filepath))
        self._title.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 10px; font-weight: 600;"
        )
        self._sub.hide()
        self.set_selected(is_current)

    def set_current(self, current):
        self.set_selected(current)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self)
        ev.accept()


class BatchNavigatorDialog(QWidget):
    """Bottom-docked navigator for browsing batch-created sessions."""

    load_requested = Signal(str)

    _CONTROLS_W = 280

    def __init__(self, cdata, parent=None):
        super().__init__(parent)
        self._cdata = cdata
        self.current_index = -1

        self._session_modified = False
        self._view_mode = "list"
        self._items = []

        self.session_files = []

        self.setup_ui()
        self.setStyleSheet(QScrollArea_style)

        cdata.data.data_changed.connect(self._mark_modified)
        cdata.models.data_changed.connect(self._mark_modified)

    def _mark_modified(self):
        """Mark current session as modified."""
        self._session_modified = True

    def setup_ui(self):
        from ..icons import icon

        self.setMinimumHeight(110)

        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(4, 4, 4, 4)

        group = QGroupBox("Batch Navigator")
        group.setStyleSheet(
            "QGroupBox { margin-top: 4px; padding-top: 12px; }"
            " QGroupBox::title { subcontrol-origin: margin;"
            " left: 7px; padding: 0 4px; }"
        )
        outer.addWidget(group)

        inner = QHBoxLayout(group)
        inner.setSpacing(8)
        inner.setContentsMargins(6, 4, 6, 6)

        controls = QWidget()
        controls.setFixedWidth(self._CONTROLS_W)
        cl = QVBoxLayout(controls)
        cl.setSpacing(6)
        cl.setContentsMargins(0, 0, 0, 0)

        h = Colors.WIDGET_HEIGHT

        row1 = QHBoxLayout()
        row1.setSpacing(4)

        self.search_widget = SearchWidget(placeholder="Search...")
        self.search_widget.searchTextChanged.connect(self._filter_sessions)
        row1.addWidget(self.search_widget, 1)

        self._view_toggle = QPushButton()
        self._view_toggle.setIcon(icon("ph.squares-four", role="muted"))
        self._view_toggle.setToolTip("Toggle list / gallery view")
        self._view_toggle.setFixedSize(h, h)
        self._view_toggle.clicked.connect(self._toggle_view_mode)
        row1.addWidget(self._view_toggle)

        self.add_btn = QPushButton()
        self.add_btn.setIcon(icon("ph.file-arrow-up", role="muted"))
        self.add_btn.setToolTip("Add session files")
        self.add_btn.setFixedSize(h, h)
        self.add_btn.clicked.connect(self._add_sessions)
        row1.addWidget(self.add_btn)

        self.clear_btn = QPushButton()
        self.clear_btn.setIcon(icon("ph.x", role="muted"))
        self.clear_btn.setToolTip("Remove all sessions")
        self.clear_btn.setFixedSize(h, h)
        self.clear_btn.clicked.connect(self._clear_sessions)
        row1.addWidget(self.clear_btn)

        cl.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(4)

        self._auto_save_btn = QPushButton("Auto-save")
        self._auto_save_btn.setCheckable(True)
        self._auto_save_btn.setChecked(True)
        self._auto_save_btn.setIcon(icon("ph.arrows-clockwise", role="primary"))
        self._auto_save_btn.setToolTip("Auto-save when switching sessions")
        self._auto_save_btn.toggled.connect(self._on_auto_save_toggled)
        row2.addWidget(self._auto_save_btn, 1)

        self.discard_btn = QPushButton("Reload")
        self.discard_btn.setIcon(icon("ph.arrow-counter-clockwise", role="muted"))
        self.discard_btn.clicked.connect(self._discard_changes)
        self.discard_btn.setToolTip(
            "Reload current session, discarding unsaved changes"
        )
        row2.addWidget(self.discard_btn, 1)

        self.save_btn = QPushButton("Save")
        self.save_btn.setIcon(icon("ph.floppy-disk", role="muted"))
        self.save_btn.setToolTip("Save current session to disk")
        self.save_btn.clicked.connect(self._save_current)
        row2.addWidget(self.save_btn, 1)

        cl.addStretch(1)
        cl.addLayout(row2)

        inner.addWidget(controls)

        sep_v = QFrame()
        sep_v.setFrameShape(QFrame.Shape.VLine)
        sep_v.setStyleSheet(f"color: {Colors.BORDER_DARK};")
        inner.addWidget(sep_v)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._content = QWidget()
        self._scroll.setWidget(self._content)

        inner.addWidget(self._scroll, 1)

        self._list_flow = FlowLayout(
            self._content,
            card_width=_LIST_ITEM_W,
            card_height=_LIST_ITEM_H,
            margin=0,
            spacing=6,
        )
        self._gallery_flow = FlowLayout(
            self._content,
            card_width=_CARD_W,
            card_height=_CARD_THUMB_H + _CARD_TEXT_H,
            margin=0,
            spacing=6,
        )

        self._populate_session_list()

    def _toggle_view_mode(self):
        from ..icons import icon

        if self._view_mode == "list":
            self._view_mode = "gallery"
            self._view_toggle.setIcon(icon("ph.list-bullets", role="muted"))
        else:
            self._view_mode = "list"
            self._view_toggle.setIcon(icon("ph.squares-four", role="muted"))
        self._populate_session_list()

    def _on_auto_save_toggled(self, checked):
        from ..icons import icon

        color = Colors.PRIMARY if checked else Colors.ICON_MUTED
        self._auto_save_btn.setIcon(icon("ph.arrows-clockwise", color=color))

    def _on_theme_changed(self):
        """Rebuild all persistent button icons after a theme switch."""
        from ..icons import icon

        # Persistent buttons whose icons are set once in setup_ui
        toggle_icon_name = (
            "ph.list-bullets" if self._view_mode == "gallery" else "ph.squares-four"
        )
        self._view_toggle.setIcon(icon(toggle_icon_name, role="muted"))
        self.add_btn.setIcon(icon("ph.file-arrow-up", role="muted"))
        self.clear_btn.setIcon(icon("ph.x", role="muted"))
        self.discard_btn.setIcon(icon("ph.arrow-counter-clockwise", role="muted"))
        self.save_btn.setIcon(icon("ph.floppy-disk", role="muted"))

        # Auto-save button uses a dynamic color based on checked state
        self._on_auto_save_toggled(self._auto_save_btn.isChecked())

        # Session list items hold cached icons; force a rebuild so they pick up
        # the new palette colours on the next display.
        self._populate_session_list()

    def _active_flow(self):
        return self._list_flow if self._view_mode == "list" else self._gallery_flow

    def _compute_list_item_width(self, container_width):
        from qtpy.QtGui import QFontMetrics, QFont

        if not self.session_files:
            return _LIST_ITEM_W

        font = QFont()
        font.setPixelSize(11)
        fm = QFontMetrics(font)
        padding = 30

        widths = sorted(
            fm.horizontalAdvance(strip_filepath(fp)) + padding
            for fp in self.session_files
        )
        p90 = widths[int(len(widths) * 0.9)]
        base = max(100, min(200, p90))

        if container_width > 0:
            sp = self._list_flow._spacing
            cols = max(1, (container_width + sp) // (base + sp))
            base = (container_width - (cols - 1) * sp) // cols

        return max(100, base)

    def _populate_session_list(self):
        """Rebuild session items for the active view mode."""
        for item in self._items:
            item.setParent(None)
            item.deleteLater()
        self._items.clear()
        self._list_flow.clear()
        self._gallery_flow.clear()

        container_w = self._content.width() or self.width()

        if self._view_mode == "list":
            item_w = self._compute_list_item_width(container_w)
            self._list_flow.set_card_size(width=item_w)
        else:
            item_w = _CARD_W

        for i, filepath in enumerate(self.session_files):
            is_current = i == self.current_index
            if self._view_mode == "list":
                item = SessionListItem(filepath, i, is_current, parent=self._content)
                item.setFixedWidth(item_w)
            else:
                item = SessionCard(filepath, i, is_current, parent=self._content)
            item.clicked.connect(self._on_item_clicked)
            self._items.append(item)

        self._active_flow().build(self._items, container_w)

        if self._view_mode == "gallery":
            self._load_gallery_thumbnails()

    def _load_gallery_thumbnails(self):
        from qtpy.QtGui import QPixmap
        from ..formats.session import read_session_section

        for item, filepath in zip(self._items, self.session_files):
            try:
                data = read_session_section(filepath, "thumbnail")
                if data is None:
                    continue
                pixmap = QPixmap()
                pixmap.loadFromData(data)
                if not pixmap.isNull():
                    item.set_thumbnail(pixmap)
            except Exception:
                continue

    def _reset_selection(self):
        self.current_index = -1
        self._update_session_list()

    def _remove_session_at_index(self, index):
        """Remove a session from the list."""
        if not (0 <= index < len(self.session_files)):
            return

        self.session_files.pop(index)

        if index == self.current_index:
            self._reset_selection()
        elif index < self.current_index:
            self.current_index -= 1

        self._populate_session_list()

    def _update_session_list(self):
        """Update current-session highlight on all items."""
        for i, item in enumerate(self._items):
            item.set_current(i == self.current_index)

    def _filter_sessions(self, search_text):
        """Filter items by filename and reflow visible ones."""
        search_text = search_text.lower()

        for item in self._items:
            filename = strip_filepath(item.metadata.get("filepath", "")).lower()
            matches = search_text in filename if search_text else True
            item.setHidden(not matches)

        self._active_flow().reflow_visibility(self._content.width() or self.width())

    def _on_item_clicked(self, item):
        """Handle click on a session item."""
        index = item.metadata.get("index", -1)
        if index >= 0 and index != self.current_index:
            self._switch_to_session(index)

    def _load_session_at_index(self, index):
        """Load a session file at the given index."""
        if not 0 <= index < len(self.session_files):
            return

        filepath = self.session_files[index]
        self.load_requested.emit(filepath)
        self.current_index = index
        self._update_session_list()

    def _switch_to_session(self, new_index):
        """Switch to a different session, auto-saving current one if enabled."""
        if new_index == self.current_index:
            return

        if self._auto_save_btn.isChecked():
            self._save_current()
        self._load_session_at_index(new_index)
        self._session_modified = False

    def _save_current(self):
        """Save the currently loaded session."""
        if self.current_index < 0:
            return None

        if self._session_modified:
            filepath = self.session_files[self.current_index]
            self._cdata.to_file(filepath)

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

    def _clear_sessions(self):
        """Remove all sessions from the list."""
        self._save_current()
        self.session_files.clear()
        self.current_index = -1
        self._populate_session_list()

    def _add_sessions(self):
        """Add session files via file dialog, deduplicating paths."""
        filepaths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Session Files",
            "",
            "Session Files (*.mosaic *.pickle)"
            ";;Mosaic Sessions (*.mosaic)"
            ";;Legacy Pickle (*.pickle)",
        )
        if not filepaths:
            return

        existing = set(self.session_files)
        for fp in filepaths:
            if fp not in existing:
                self.session_files.append(fp)
                existing.add(fp)

        self.session_files.sort(key=natural_sort_key)
        self._populate_session_list()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self._content.width()
        if w <= 0:
            return

        if self._view_mode == "list" and self._items:
            item_w = self._compute_list_item_width(w)
            if item_w != self._list_flow._card_w:
                self._list_flow.set_card_size(width=item_w)
                for item in self._items:
                    item.setFixedWidth(item_w)

        self._active_flow().reflow(w)

    def close(self):
        """Handle widget close, saving current session if auto-save is enabled."""
        self._save_current()
        super().close()
