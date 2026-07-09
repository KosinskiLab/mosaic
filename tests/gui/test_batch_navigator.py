import pytest
from unittest.mock import Mock
from qtpy.QtCore import Qt

from mosaic.widgets.container_list import SessionListWidget


class TestSessionListWidget:

    def test_initial_state(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        assert widget.session_files == []
        assert widget.current_index == -1

    def test_set_sessions_populates_items(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        files = ["/path/tomo_001.mosaic", "/path/tomo_002.mosaic"]
        widget.set_sessions(files)
        assert widget.session_files == files
        assert len(widget._items) == 2

    def test_set_sessions_natural_sort(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        files = ["/p/tomo_10.mosaic", "/p/tomo_2.mosaic", "/p/tomo_1.mosaic"]
        widget.set_sessions(files)
        assert widget.session_files[0] == "/p/tomo_1.mosaic"
        assert widget.session_files[1] == "/p/tomo_2.mosaic"
        assert widget.session_files[2] == "/p/tomo_10.mosaic"

    def test_click_emits_load_requested(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        widget.set_sessions(["/p/a.mosaic", "/p/b.mosaic"])
        handler = Mock()
        widget.load_requested.connect(handler)
        widget._on_item_clicked(widget._items[1])
        handler.assert_called_once_with("/p/b.mosaic")

    def test_click_updates_current_index(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        widget.set_sessions(["/p/a.mosaic", "/p/b.mosaic"])
        widget.load_requested.connect(lambda _: None)
        widget._on_item_clicked(widget._items[1])
        assert widget.current_index == 1

    def test_click_same_session_does_nothing(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        widget.set_sessions(["/p/a.mosaic", "/p/b.mosaic"])
        widget.current_index = 0
        widget._update_highlight()
        handler = Mock()
        widget.load_requested.connect(handler)
        widget._on_item_clicked(widget._items[0])
        handler.assert_not_called()

    def test_set_current_by_filepath(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        widget.set_sessions(["/p/a.mosaic", "/p/b.mosaic"])
        widget.set_current("/p/b.mosaic")
        assert widget.current_index == 1

    def test_set_current_unknown_path_ignored(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        widget.set_sessions(["/p/a.mosaic"])
        widget.set_current("/p/unknown.mosaic")
        assert widget.current_index == -1

    def test_filter_items_hides_non_matching(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        # After sort: membrane (idx 0), tomo (idx 1)
        widget.set_sessions(["/p/tomo_001.mosaic", "/p/membrane_002.mosaic"])
        widget.filter_items("tomo")
        assert widget._items[0].isHidden()  # membrane hidden
        assert not widget._items[1].isHidden()  # tomo visible

    def test_filter_items_empty_shows_all(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        widget.set_sessions(["/p/tomo_001.mosaic", "/p/membrane_002.mosaic"])
        widget.filter_items("tomo")
        widget.filter_items("")
        assert not widget._items[0].isHidden()
        assert not widget._items[1].isHidden()

    def test_clear_sessions(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        widget.set_sessions(["/p/a.mosaic", "/p/b.mosaic"])
        widget.current_index = 1
        widget.clear_sessions()
        assert widget.session_files == []
        assert widget.current_index == -1
        assert widget._items == []

    def test_prompt_save_proceeds_when_not_modified(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        widget.set_sessions(["/p/a.mosaic"])
        widget.current_index = 0
        widget._session_modified = False
        assert widget._prompt_save_if_needed() is True

    def test_prompt_save_proceeds_when_auto_save_on(self, qapp):
        cdata = Mock()
        widget = SessionListWidget(cdata=cdata)
        widget.set_sessions(["/p/a.mosaic"])
        widget.current_index = 0
        widget._session_modified = True
        widget._auto_save = True
        widget._active = True
        assert widget._prompt_save_if_needed() is True
        cdata.to_file.assert_called_once_with("/p/a.mosaic")

    def test_prompt_save_no_index_proceeds(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        widget._session_modified = True
        widget._auto_save = False
        assert widget._prompt_save_if_needed() is True

    def test_remove_non_active_session(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        widget.set_sessions(["/p/a.mosaic", "/p/b.mosaic", "/p/c.mosaic"])
        widget.current_index = 2
        widget._update_highlight()
        widget.load_requested.connect(lambda _: None)
        widget.remove_session(0)
        assert widget.session_files == ["/p/b.mosaic", "/p/c.mosaic"]
        assert widget.current_index == 1
        assert len(widget._items) == 2

    def test_remove_non_active_after_current_no_shift(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        widget.set_sessions(["/p/a.mosaic", "/p/b.mosaic", "/p/c.mosaic"])
        widget.current_index = 0
        widget._update_highlight()
        widget.load_requested.connect(lambda _: None)
        widget.remove_session(2)
        assert widget.session_files == ["/p/a.mosaic", "/p/b.mosaic"]
        assert widget.current_index == 0

    def test_remove_active_loads_next(self, qapp):
        handler = Mock()
        widget = SessionListWidget(cdata=Mock())
        widget.set_sessions(["/p/a.mosaic", "/p/b.mosaic", "/p/c.mosaic"])
        widget.current_index = 1
        widget._update_highlight()
        widget.load_requested.connect(handler)
        widget.remove_session(1)
        assert widget.session_files == ["/p/a.mosaic", "/p/c.mosaic"]
        assert widget.current_index == 1
        handler.assert_called_once_with("/p/c.mosaic")

    def test_remove_active_last_loads_previous(self, qapp):
        handler = Mock()
        widget = SessionListWidget(cdata=Mock())
        widget.set_sessions(["/p/a.mosaic", "/p/b.mosaic"])
        widget.current_index = 1
        widget._update_highlight()
        widget.load_requested.connect(handler)
        widget.remove_session(1)
        assert widget.session_files == ["/p/a.mosaic"]
        assert widget.current_index == 0
        handler.assert_called_once_with("/p/a.mosaic")

    def test_remove_only_session_resets(self, qapp):
        handler = Mock()
        widget = SessionListWidget(cdata=Mock())
        widget.set_sessions(["/p/a.mosaic"])
        widget.current_index = 0
        widget._update_highlight()
        widget.load_requested.connect(handler)
        widget.remove_session(0)
        assert widget.session_files == []
        assert widget.current_index == -1
        handler.assert_not_called()

    def test_clear_sessions_with_prompt_clears(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        widget.set_sessions(["/p/a.mosaic", "/p/b.mosaic"])
        widget.current_index = 0
        widget._session_modified = False
        widget.clear_sessions_with_prompt()
        assert widget.session_files == []
        assert widget.current_index == -1
        assert widget._items == []

    def test_context_menu_policy_set(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        assert (
            widget._tree.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
        )


class TestSessionHeader:

    def test_header_widget_exists(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        assert widget._header is not None

    def test_auto_save_default_on(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        assert widget._auto_save is True
        assert widget._header._auto_save_toggle.isChecked()

    def test_auto_save_toggle_updates_property(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        widget._header._auto_save_toggle.setChecked(False)
        assert widget._auto_save is False

    def test_header_has_clear_button(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        assert hasattr(widget._header, "_clear_btn")

    def test_header_button_order(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        layout = widget._header.layout()
        widgets = [layout.itemAt(i).widget() for i in range(layout.count())]
        expected = [
            widget._header._add_btn,
            widget._header._save_btn,
            widget._header._reload_btn,
            widget._header._auto_save_toggle,
            widget._header._clear_btn,
        ]
        assert widgets == expected

    def test_clear_button_calls_clear_with_prompt(self, qapp, monkeypatch):
        widget = SessionListWidget(cdata=Mock())
        called = []
        monkeypatch.setattr(
            widget, "clear_sessions_with_prompt", lambda: called.append(True)
        )
        widget._header._clear_btn.click()
        assert called == [True]


from mosaic.widgets.sidebar import ObjectBrowserSidebar


class TestSidebarSessionIntegration:

    def test_add_widget(self, qapp):
        sidebar = ObjectBrowserSidebar()
        session_widget = SessionListWidget(cdata=Mock())
        sidebar.add_widget("Sessions", session_widget)
        assert sidebar._widgets["Sessions"] is session_widget
        assert sidebar._splitter.count() == 1

    def test_remove_widget(self, qapp):
        sidebar = ObjectBrowserSidebar()
        session_widget = SessionListWidget(cdata=Mock())
        sidebar.add_widget("Sessions", session_widget)
        sidebar.remove_widget("Sessions")
        assert "Sessions" not in sidebar._widgets
        assert sidebar._splitter.count() == 0

    def test_add_then_remove_preserves_widget(self, qapp):
        sidebar = ObjectBrowserSidebar()
        session_widget = SessionListWidget(cdata=Mock())
        sidebar.add_widget("Sessions", session_widget)
        sidebar.remove_widget("Sessions")
        assert len(session_widget.session_files) == 0

    def test_filter_objects_filters_sessions(self, qapp):
        sidebar = ObjectBrowserSidebar()
        session_widget = SessionListWidget(cdata=Mock())
        session_widget.set_sessions(["/p/tomo_001.mosaic", "/p/membrane.mosaic"])
        sidebar.add_widget("Sessions", session_widget)
        sidebar._filter_objects("tomo")
        assert session_widget._items[0].isHidden()
        assert not session_widget._items[1].isHidden()
