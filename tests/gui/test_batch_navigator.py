from unittest.mock import Mock

import pytest
from qtpy.QtCore import Qt

from mosaic.formats.session import session_save_path
from mosaic.settings import Settings
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
        cdata.to_file.side_effect = lambda path: path
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
        assert widget._header._action("Auto-save on switch").isChecked()

    def test_header_menu_actions(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        actions = widget._header._menu.actions()
        texts = [a.text() for a in actions if not a.isSeparator()]
        assert texts == [
            "Link tomograms…",
            "Auto-save on switch",
            "Load tomogram on switch",
            "Clear all sessions",
        ]
        assert [a.isSeparator() for a in actions] == [
            False,
            True,
            False,
            False,
            True,
            False,
        ]
        assert not hasattr(widget._header, "_save_btn")

    def test_header_button_order(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        layout = widget._header.layout()
        items = [layout.itemAt(i).widget() for i in range(layout.count())]
        widgets = [w for w in items if w is not None]
        header = widget._header
        assert widgets == [header._add_btn, header._reload_btn, header._menu_btn]
        assert header._add_btn.text() == ""
        assert not header._add_btn.icon().isNull()
        assert header._add_btn.toolTip() == "Add session files"
        assert layout.itemAt(2).spacerItem() is not None
        assert not header._action("Clear all sessions").icon().isNull()

    def test_autosave_action_toggles_flag(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        widget._header._action("Auto-save on switch").trigger()
        assert widget._auto_save is False

    def test_load_tomogram_action_writes_setting(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        Settings.ui.load_linked_tomogram = True
        widget._header._action("Load tomogram on switch").trigger()
        assert Settings.ui.load_linked_tomogram is False

    def test_link_action_emits(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        handler = Mock()
        widget.link_tomograms_requested.connect(handler)
        widget._header._action("Link tomograms…").trigger()
        handler.assert_called_once()

    def test_clear_action_calls_clear_with_prompt(self, qapp, monkeypatch):
        widget = SessionListWidget(cdata=Mock())
        called = []
        monkeypatch.setattr(
            widget, "clear_sessions_with_prompt", lambda: called.append(True)
        )
        widget._header._action("Clear all sessions").trigger()
        assert called == [True]

    def test_checkable_action_keeps_menu_open(self, qapp):
        from qtpy.QtTest import QTest

        widget = SessionListWidget(cdata=Mock())
        menu = widget._header._menu
        auto_save = widget._header._action("Auto-save on switch")
        menu.popup(widget.mapToGlobal(widget.rect().topLeft()))
        QTest.mouseClick(
            menu,
            Qt.MouseButton.LeftButton,
            pos=menu.actionGeometry(auto_save).center(),
        )
        assert menu.isVisible() and widget._auto_save is False

        link = widget._header._action("Link tomograms…")
        widget.link_tomograms_requested.connect(lambda: None)
        QTest.mouseClick(
            menu,
            Qt.MouseButton.LeftButton,
            pos=menu.actionGeometry(link).center(),
        )
        assert not menu.isVisible()

    def test_session_rows_use_item_icon_size(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        widget.set_sessions(["/p/a.mosaic"])
        assert widget._tree.itemDelegate()._icon_size_for(widget._items[0]) == 20


from mosaic.widgets.sidebar import ObjectBrowserSidebar


@pytest.fixture
def app_stylesheet(qapp):
    from mosaic.stylesheets import build_global_stylesheet

    previous = qapp.styleSheet()
    qapp.setStyleSheet(build_global_stylesheet())
    yield
    qapp.setStyleSheet(previous)


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

    def test_header_buttons_fit_at_minimum_width(self, qapp):
        sidebar = ObjectBrowserSidebar()
        session_widget = SessionListWidget(cdata=Mock())
        sidebar.add_widget("Sessions", session_widget)
        sidebar.resize(sidebar.minimumWidth(), 400)
        sidebar.show()
        qapp.processEvents()
        header = session_widget._header
        for button in (header._add_btn, header._reload_btn, header._menu_btn):
            assert button.width() == button.height()
            assert header.rect().contains(button.geometry())
        sidebar.close()

    def test_header_menu_is_opaque(self, qapp, app_stylesheet):
        from qtpy.QtGui import QColor

        from mosaic.stylesheets import Colors

        sidebar = ObjectBrowserSidebar()
        session_widget = SessionListWidget(cdata=Mock())
        sidebar.add_widget("Sessions", session_widget)
        sidebar.show()
        menu = session_widget._header._menu
        menu.popup(sidebar.mapToGlobal(sidebar.rect().topLeft()))
        qapp.processEvents()
        image = menu.grab().toImage()
        menu.close()
        sidebar.close()
        assert QColor(image.pixel(image.width() // 2, 2)) == QColor(Colors.SURFACE)

    def test_filter_objects_filters_sessions(self, qapp):
        sidebar = ObjectBrowserSidebar()
        session_widget = SessionListWidget(cdata=Mock())
        session_widget.set_sessions(["/p/tomo_001.mosaic", "/p/membrane.mosaic"])
        sidebar.add_widget("Sessions", session_widget)
        sidebar._filter_objects("tomo")
        assert session_widget._items[0].isHidden()
        assert not session_widget._items[1].isHidden()


class TestSessionPathRedirect:
    def test_autosave_of_pickle_swaps_entry(self, qapp, tmp_path):
        cdata = Mock()
        cdata.to_file.side_effect = session_save_path
        widget = SessionListWidget(cdata=cdata)
        a, b = str(tmp_path / "a.pickle"), str(tmp_path / "b.mosaic")
        widget.set_sessions([a, b])
        widget.current_index, widget._session_modified = 0, True
        changed = Mock()
        widget.session_path_changed.connect(changed)
        widget.load_requested.connect(lambda _: None)
        widget._on_item_clicked(widget._items[1])
        assert widget.session_files[0] == str(tmp_path / "a.mosaic")
        changed.assert_called_once_with(a, str(tmp_path / "a.mosaic"))

    def test_set_sessions_prefers_mosaic(self, qapp, tmp_path):
        (tmp_path / "a.mosaic").write_bytes(b"")
        widget = SessionListWidget(cdata=Mock())
        widget.set_sessions([str(tmp_path / "a.pickle"), str(tmp_path / "a.mosaic")])
        assert widget.session_files == [str(tmp_path / "a.mosaic")]

    def test_declined_overwrite_keeps_edits_and_does_not_switch(
        self, qapp, tmp_path, monkeypatch
    ):
        (tmp_path / "a.mosaic").write_bytes(b"newer")
        monkeypatch.setattr(
            "mosaic.widgets.container_list.confirm_session_overwrite",
            lambda *_: False,
        )
        cdata = Mock()
        widget = SessionListWidget(cdata=cdata)
        widget.session_files = [str(tmp_path / "a.pickle"), str(tmp_path / "b.mosaic")]
        widget._rebuild_items()
        widget.current_index, widget._session_modified = 0, True
        widget._on_item_clicked(widget._items[1])
        cdata.to_file.assert_not_called()
        assert widget.current_index == 0 and widget._session_modified

    def test_mark_saved_clears_flag(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        widget.set_sessions(["/p/a.mosaic"])
        widget.current_index, widget._session_modified = 0, True
        widget.mark_saved("/p/a.mosaic")
        assert widget._session_modified is False

    def test_replace_paths_keeps_current_session(self, qapp):
        widget = SessionListWidget(cdata=Mock())
        widget.set_sessions(["/p/a.pickle", "/p/b.pickle"])
        widget.current_index = 1
        widget.replace_paths({"/p/b.pickle": "/p/b.mosaic"})
        assert widget.session_files == ["/p/a.pickle", "/p/b.mosaic"]
        assert widget.current_index == 1

    @pytest.mark.parametrize("current, expected", [(1, 0), (2, 1)])
    def test_replace_paths_merges_duplicates(self, qapp, current, expected):
        widget = SessionListWidget(cdata=Mock())
        widget.session_files = ["/p/a.mosaic", "/p/a.pickle", "/p/b.mosaic"]
        widget.current_index = current
        widget.replace_paths({"/p/a.pickle": "/p/a.mosaic"})
        assert widget.session_files == ["/p/a.mosaic", "/p/b.mosaic"]
        assert widget.current_index == expected

    def test_stale_modified_flag_without_current_still_switches(self, qapp):
        cdata = Mock()
        widget = SessionListWidget(cdata=cdata)
        widget.set_sessions(["/p/a.mosaic", "/p/b.mosaic"])
        widget.current_index, widget._session_modified = -1, True
        loaded = Mock()
        widget.load_requested.connect(loaded)
        widget._on_item_clicked(widget._items[1])
        cdata.to_file.assert_not_called()
        loaded.assert_called_once_with("/p/b.mosaic")

    def test_declined_overwrite_aborts_clear(self, qapp, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "mosaic.widgets.container_list.confirm_session_overwrite",
            lambda *_: False,
        )
        widget = SessionListWidget(cdata=Mock())
        widget.session_files = [str(tmp_path / "a.pickle")]
        widget._rebuild_items()
        widget.current_index, widget._session_modified = 0, True
        widget.clear_sessions()
        assert widget.session_files == [str(tmp_path / "a.pickle")]
        assert widget._session_modified
