"""
Tests for lightweight tree-state dataclasses.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from mosaic.tree_state import TreeState, TreeStateData


class TestTreeStateData:

    def test_empty_defaults(self):
        t = TreeStateData()
        assert t.groups == {}
        assert t.group_names == {}
        assert t.root_items == []

    def test_get_all_uuids_ungrouped(self):
        t = TreeStateData()
        t.root_items = ["u1", "u2"]
        assert t.get_all_uuids() == {"u1", "u2"}

    def test_get_all_uuids_grouped(self):
        t = TreeStateData()
        t.root_items = ["g1"]
        t.groups = {"g1": ["u1", "u2"]}
        t.group_names = {"g1": "Group"}
        assert t.get_all_uuids() == {"u1", "u2"}

    def test_get_all_uuids_mixed(self):
        t = TreeStateData()
        t.root_items = ["g1", "u3"]
        t.groups = {"g1": ["u1", "u2"]}
        assert t.get_all_uuids() == {"u1", "u2", "u3"}

    def test_remove_uuid_from_root(self):
        t = TreeStateData()
        t.root_items = ["u1", "u2", "u3"]
        t.remove_uuid("u2")
        assert t.root_items == ["u1", "u3"]

    def test_remove_uuid_from_group_members(self):
        t = TreeStateData()
        t.root_items = ["g1"]
        t.groups = {"g1": ["u1", "u2"]}
        t.group_names = {"g1": "Alpha"}
        t.remove_uuid("u1")
        assert t.groups["g1"] == ["u2"]

    def test_remove_uuid_removes_group_itself(self):
        t = TreeStateData()
        t.root_items = ["g1", "u2"]
        t.groups = {"g1": ["u1"]}
        t.group_names = {"g1": "Alpha"}
        t.remove_uuid("g1")
        assert "g1" not in t.root_items
        assert "g1" not in t.group_names
        assert "g1" not in t.groups

    def test_remove_nonexistent_is_noop(self):
        t = TreeStateData()
        t.root_items = ["u1"]
        t.remove_uuid("u99")
        assert t.root_items == ["u1"]


class TestTreeState:

    def test_get_all_uuids(self):
        t = TreeState()
        t.root_items = ["u1", "u2"]
        t.groups = {"G": ["u3", "u4"]}
        assert t.get_all_uuids() == {"u1", "u2", "u3", "u4"}

    def test_get_all_uuids_empty(self):
        assert TreeState().get_all_uuids() == set()

    def test_to_tree_state_data(self):
        t = TreeState()
        t.root_order = {
            "g1": (0, "GroupA"),
            "u1": (1, None),
        }
        t.groups = {"GroupA": ["m1", "m2"]}
        t.root_items = ["g1", "u1"]

        result = t.to_tree_state_data()
        assert isinstance(result, TreeStateData)
        assert result.root_items == ["g1", "u1"]
        assert result.group_names == {"g1": "GroupA"}
        assert result.groups == {"g1": ["m1", "m2"]}

    def test_to_tree_state_data_empty(self):
        result = TreeState().to_tree_state_data()
        assert result.root_items == []
        assert result.groups == {}
        assert result.group_names == {}
