"""
Tests for command registry, dispatch, and built-in command handlers.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np
import pytest

from mosaic.commands.parser import parse_command
from mosaic.commands.registry import (
    CommandRegistry,
    _expand_brace_range,
    _is_target_ref,
    _natsort_key,
    _resolve_kwargs,
)
from mosaic.commands.session import Session
from mosaic.commands.theme import render_to_text as _render
from mosaic.geometry import Geometry


def _geom(n=50, seed=0, name=None):
    rng = np.random.RandomState(seed)
    g = Geometry(points=rng.rand(n, 3).astype(np.float32) * 100)
    if name is not None:
        g._meta["name"] = name
    return g


def _session_with(*geoms):
    s = Session(quiet=True)
    for g in geoms:
        s._data.add(g)
        s._order.append(g)
    return s


def _dispatch(session, text):
    parsed = parse_command(text)
    assert parsed is not None
    return CommandRegistry.dispatch(session, parsed)


class TestExpandBraceRange:

    def test_simple_range(self):
        assert _expand_brace_range("/data/file_{0..3}.star") == [
            "/data/file_0.star",
            "/data/file_1.star",
            "/data/file_2.star",
            "/data/file_3.star",
        ]

    def test_range_with_step(self):
        assert _expand_brace_range("f{0..6..2}.txt") == [
            "f0.txt",
            "f2.txt",
            "f4.txt",
            "f6.txt",
        ]

    def test_zero_padded(self):
        result = _expand_brace_range("f{01..03}.txt")
        assert result == ["f01.txt", "f02.txt", "f03.txt"]

    def test_no_brace_range(self):
        assert _expand_brace_range("/data/file.star") is None

    def test_brace_without_dots(self):
        assert _expand_brace_range("/data/{a,b}.star") is None


class TestNatsortKey:

    def test_numeric_ordering(self):
        paths = ["file_10.star", "file_2.star", "file_1.star"]
        assert sorted(paths, key=_natsort_key) == [
            "file_1.star",
            "file_2.star",
            "file_10.star",
        ]

    def test_alpha_ordering(self):
        paths = ["b.txt", "a.txt", "c.txt"]
        assert sorted(paths, key=_natsort_key) == ["a.txt", "b.txt", "c.txt"]

    def test_mixed(self):
        paths = ["TS_20.star", "TS_3.star", "TS_100.star"]
        assert sorted(paths, key=_natsort_key) == [
            "TS_3.star",
            "TS_20.star",
            "TS_100.star",
        ]


class TestIsTargetRef:

    @pytest.mark.parametrize("val", ["#0", "#0-5", "@last", "*", "#0,#1,#2"])
    def test_positive(self, val):
        assert _is_target_ref(val) is True

    @pytest.mark.parametrize("val", ["hello", "123", "/path/to/file", "method=dbscan"])
    def test_negative(self, val):
        assert _is_target_ref(val) is False


class TestResolveKwargs:

    def test_geometry_ref_resolved(self, make_session):
        session = make_session(n=3)
        result = _resolve_kwargs(session, {"queries": "#0"})
        assert result["queries"] is session._all_geometries()[0]

    def test_multi_ref_resolved(self, make_session):
        session = make_session(n=3)
        result = _resolve_kwargs(session, {"queries": "#0,#1"})
        assert isinstance(result["queries"], list)
        assert len(result["queries"]) == 2

    def test_non_ref_passthrough(self, make_session):
        session = make_session(n=1)
        result = _resolve_kwargs(session, {"method": "dbscan", "eps": 0.5})
        assert result == {"method": "dbscan", "eps": 0.5}

    def test_invalid_ref_raises(self):
        session = Session(quiet=True)
        with pytest.raises(IndexError):
            _resolve_kwargs(session, {"queries": "#99"})


class TestDispatchEdgeCases:

    def test_help_redirect(self, make_session):
        """'measure help' redirects to 'help measure'."""
        session = make_session(n=1)
        result = _dispatch(session, "measure help")
        text = _render(result)
        assert "measure" in text.lower()
        assert "method" in text.lower() or "Method" in text

    def test_method_help_redirect(self, make_session):
        """'measure n_points help' shows help for measure n_points."""
        session = make_session(n=1)
        result = _dispatch(session, "measure n_points help")
        text = _render(result)
        assert "n_points" in text

    def test_registry_defaults_injected(self, make_session):
        session = make_session(n=1, n_points=100)
        result = _dispatch(session, "measure n_points #0")
        text = _render(result)
        assert "100" in text


class TestCmdList:

    def test_list_ids_format(self, make_session):
        session = make_session(n=3)
        result = _dispatch(session, "list format=ids")
        assert "#0" in result and "#1" in result and "#2" in result

    def test_list_name_filter(self, make_session):
        session = make_session(n=3)
        result = _dispatch(session, "list name=cloud_1")
        text = _render(result)
        assert "cloud_1" in text
        assert "1 geometries" in text

    def test_list_name_glob(self, make_session):
        session = make_session(n=3)
        result = _dispatch(session, "list name=cloud_*")
        text = _render(result)
        assert "3 geometries" in text

    def test_list_no_match(self, make_session):
        session = make_session(n=2)
        result = _dispatch(session, "list name=nonexistent")
        text = _render(result)
        assert "no geometries" in text.lower()


class TestCmdInfo:

    def test_info_multiple_geometries(self):
        session = _session_with(_geom(10, name="a"), _geom(20, name="b"))
        result = _dispatch(session, "info #0 #1")
        text = _render(result)
        assert "a" in text and "b" in text

    def test_info_no_targets(self):
        session = _session_with(_geom(10))
        result = _dispatch(session, "info")
        text = _render(result)
        assert "no geometries" in text.lower()

    def test_info_shows_uuid(self):
        g = _geom(10, name="test")
        session = _session_with(g)
        result = _dispatch(session, "info #0")
        text = _render(result)
        assert "UUID" in text


class TestCmdRename:

    def test_rename_regex_global(self):
        g = _geom(10, name="aaa_bbb_aaa")
        session = _session_with(g)
        _dispatch(session, "rename #0 s/aaa/xxx/g")
        assert g._meta["name"] == "xxx_bbb_xxx"

    def test_rename_regex_case_insensitive(self):
        g = _geom(10, name="Cloud_Data")
        session = _session_with(g)
        _dispatch(session, "rename #0 s/cloud/Storm/i")
        assert g._meta["name"] == "Storm_Data"

    def test_rename_regex_no_match(self):
        g = _geom(10, name="original")
        session = _session_with(g)
        result = _dispatch(session, "rename #0 s/zzz/yyy/")
        text = _render(result)
        assert "0" in text
        assert g._meta["name"] == "original"

    def test_rename_invalid_regex(self):
        g = _geom(10, name="test")
        session = _session_with(g)
        result = _dispatch(session, "rename #0 s/[invalid/replacement/")
        text = _render(result)
        assert "error" in text.lower() or "invalid" in text.lower()

    def test_rename_no_args(self):
        session = _session_with(_geom(10))
        result = _dispatch(session, "rename")
        text = _render(result)
        assert "usage" in text.lower() or "rename" in text.lower()

    def test_rename_multiple_targets(self):
        g0, g1 = _geom(10, name="a"), _geom(10, seed=1, name="b")
        session = _session_with(g0, g1)
        _dispatch(session, "rename #0 #1 NewName")
        assert g0._meta["name"] == "NewName"
        assert g1._meta["name"] == "NewName"


class TestCmdVisibility:

    def test_no_targets(self):
        session = _session_with(_geom(10))
        result = _dispatch(session, "visibility")
        text = _render(result)
        assert "no target" in text.lower()


class TestCmdGroup:

    def test_group_no_targets(self):
        session = _session_with(_geom(10))
        result = _dispatch(session, "group")
        text = _render(result)
        assert "usage" in text.lower() or "group" in text.lower()

    def test_group_no_name(self):
        session = _session_with(_geom(10))
        result = _dispatch(session, "group #0")
        text = _render(result)
        assert "error" in text.lower() or "missing" in text.lower()

    def test_ungroup_no_targets(self):
        session = _session_with(_geom(10))
        result = _dispatch(session, "ungroup")
        text = _render(result)
        assert "usage" in text.lower() or "ungroup" in text.lower()


class TestCmdRemove:

    def test_remove_no_targets(self):
        session = _session_with(_geom(10))
        result = _dispatch(session, "remove")
        text = _render(result)
        assert "usage" in text.lower() or "remove" in text.lower()


class TestCmdSave:

    def test_save_no_filepath(self, make_session):
        session = make_session(n=1)
        result = _dispatch(session, "save")
        text = _render(result)
        assert "usage" in text.lower() or "save" in text.lower()

    def test_save_xyz(self, make_session, tmp_path):
        session = make_session(n=1, n_points=20)
        path = str(tmp_path / "out.xyz")
        result = _dispatch(session, f"save #0 filepath={path}")
        text = _render(result)
        assert "saved" in text.lower()
        assert (tmp_path / "out.xyz").exists()

    def test_save_session_file(self, make_session, tmp_path):
        session = make_session(n=2, n_points=10)
        path = str(tmp_path / "test.pickle")
        result = _dispatch(session, f"save filepath={path}")
        text = _render(result)
        assert "session saved" in text.lower()
        assert (tmp_path / "test.pickle").exists()


class TestCmdOpen:

    def test_open_no_filepath(self):
        result = _dispatch(Session(quiet=True), "open")
        text = _render(result)
        assert "usage" in text.lower() or "open" in text.lower()

    def test_open_single_file(self, tmp_path):
        path = tmp_path / "test.xyz"
        pts = np.random.rand(15, 3).astype(np.float32) * 10
        np.savetxt(str(path), pts, delimiter=",", header="x,y,z", comments="")

        session = Session(quiet=True)
        result = _dispatch(session, f"open filepath={path}")
        text = _render(result)
        assert "loaded" in text.lower()
        assert len(session._all_geometries()) == 1
        assert session._all_geometries()[0].get_number_of_points() == 15

    def test_open_session_file(self, make_session, tmp_path):
        original = make_session(n=2, n_points=30)
        path = str(tmp_path / "roundtrip.pickle")
        original.save_session(path)

        loaded = Session(quiet=True)
        result = _dispatch(loaded, f"open filepath={path}")
        text = _render(result)
        assert "session loaded" in text.lower()
        assert len(loaded._all_geometries()) == 2

    def test_open_glob(self, tmp_path):
        for i in range(3):
            pts = np.random.rand(10, 3).astype(np.float32)
            np.savetxt(
                str(tmp_path / f"cloud_{i}.xyz"),
                pts,
                delimiter=",",
                header="x,y,z",
                comments="",
            )

        session = Session(quiet=True)
        pattern = str(tmp_path / "cloud_*.xyz")
        result = _dispatch(session, f'open filepath="{pattern}"')
        text = _render(result)
        assert "3 file(s)" in text
        assert len(session._all_geometries()) == 3

    def test_open_brace_range(self, tmp_path):
        for i in range(3):
            pts = np.random.rand(5, 3).astype(np.float32)
            np.savetxt(
                str(tmp_path / f"scan_{i}.xyz"),
                pts,
                delimiter=",",
                header="x,y,z",
                comments="",
            )

        session = Session(quiet=True)
        pattern = str(tmp_path / "scan_{0..2}.xyz")
        result = _dispatch(session, f'open filepath="{pattern}"')
        text = _render(result)
        assert "3 file(s)" in text

    def test_open_no_match(self):
        session = Session(quiet=True)
        result = _dispatch(session, "open filepath=/nonexistent/path/*.star")
        text = _render(result)
        assert "no files" in text.lower()

    def test_open_persist_false(self, tmp_path):
        path = tmp_path / "temp.xyz"
        pts = np.random.rand(8, 3).astype(np.float32)
        np.savetxt(str(path), pts, delimiter=",", header="x,y,z", comments="")

        session = Session(quiet=True)
        result = _dispatch(session, f"open filepath={path} persist=false")
        text = _render(result)
        assert "@last" in text
        assert len(session._all_geometries()) == 0
        assert len(session._last_results) == 1


class TestCmdHelp:

    def test_help_overview(self):
        result = _dispatch(Session(), "help")
        text = _render(result)
        assert "Commands" in text or "commands" in text

    def test_help_specific_command(self):
        result = _dispatch(Session(), "help list")
        text = _render(result)
        assert "list" in text.lower()

    def test_help_operation_with_methods(self):
        result = _dispatch(Session(), "help cluster")
        text = _render(result)
        assert "dbscan" in text.lower()

    def test_help_specific_method(self):
        result = _dispatch(Session(), "help cluster dbscan")
        text = _render(result)
        assert "dbscan" in text.lower()

    def test_help_operation_without_methods(self):
        result = _dispatch(Session(), "help filter")
        text = _render(result)
        assert "filter" in text.lower()
        assert "property" in text.lower()

    def test_help_unknown_command(self):
        result = _dispatch(Session(), "help nonexistent_xyz")
        text = _render(result)
        assert "unknown" in text.lower()

    def test_help_unknown_method(self):
        result = _dispatch(Session(), "help cluster nonexistent_method")
        text = _render(result)
        assert "unknown" in text.lower()
        assert "available" in text.lower()


class TestCmdHistory:

    def test_history_empty(self):
        result = _dispatch(Session(), "history")
        text = _render(result)
        assert "no commands" in text.lower()

    def test_history_with_entries(self, make_session):
        session = make_session(n=1)
        session.log_command("list")
        session.log_command("info #0")
        result = _dispatch(session, "history")
        text = _render(result)
        assert "list" in text
        assert "info #0" in text


class TestOperationHandler:

    def test_operation_no_method(self, make_session):
        session = make_session(n=1)
        result = _dispatch(session, "cluster")
        text = _render(result)
        assert "method" in text.lower()

    def test_operation_unknown_method(self, make_session):
        session = make_session(n=1)
        result = _dispatch(session, "cluster nonexistent_method #0")
        text = _render(result)
        assert "unknown" in text.lower() or "available" in text.lower()

    def test_operation_no_geometry_targets(self):
        session = Session(quiet=True)
        result = _dispatch(session, "cluster dbscan")
        text = _render(result)
        assert "no target" in text.lower()


class TestCmdFilter:

    def test_filter_no_targets(self):
        session = Session(quiet=True)
        result = _dispatch(session, "filter")
        text = _render(result)
        assert "no target" in text.lower()

    def test_filter_missing_property(self):
        session = _session_with(_geom(20))
        result = _dispatch(session, "filter #0")
        text = _render(result)
        assert "missing" in text.lower() or "property" in text.lower()

    def test_filter_upper_bound(self):
        session = Session(quiet=True)
        for size in [10, 50, 100, 200]:
            g = _geom(size, seed=size, name=f"g{size}")
            session._data.add(g)
            session._order.append(g)
        _dispatch(session, "filter * property=n_points upper=50")
        remaining = session._all_geometries()
        assert len(remaining) == 2
        for g in remaining:
            assert g.get_number_of_points() <= 50


class TestFilterMembership:

    def test_filter_include_categorical(self, make_session):
        session = make_session(n=1, n_points=20)
        g = session._all_geometries()[0]
        labels = np.array(["a", "b", "a", "b", "c"] * 4, dtype=object)
        g.vertex_properties.set_property("label", labels)
        _dispatch(session, "filter #0 property=label include=a,c")
        assert g.get_number_of_points() == 12

    def test_filter_exclude_categorical(self, make_session):
        session = make_session(n=1, n_points=20)
        g = session._all_geometries()[0]
        labels = np.array(["a", "b", "a", "b", "c"] * 4, dtype=object)
        g.vertex_properties.set_property("label", labels)
        _dispatch(session, "filter #0 property=label exclude=b")
        assert g.get_number_of_points() == 12

    def test_filter_include_integer_labels(self, make_session):
        session = make_session(n=1, n_points=15)
        g = session._all_geometries()[0]
        ids = np.array([0, 1, 2] * 5, dtype=np.int32)
        g.vertex_properties.set_property("cluster_id", ids)
        _dispatch(session, "filter #0 property=cluster_id include=1,2")
        assert g.get_number_of_points() == 10

    def test_filter_range_on_string_errors(self, make_session):
        session = make_session(n=1, n_points=5)
        g = session._all_geometries()[0]
        g.vertex_properties.set_property(
            "label", np.array(["a", "b", "c", "a", "b"], dtype=object)
        )
        result = _dispatch(session, "filter #0 property=label lower=0")
        text = _render(result)
        assert "non-numeric" in text or "include" in text


class TestCmdMerge:

    def test_merge_too_few(self):
        session = _session_with(_geom(10))
        result = _dispatch(session, "merge #0")
        text = _render(result)
        assert "at least two" in text.lower()


class TestPropertiesCommand:

    def test_no_targets_defaults_to_all(self, make_session):
        session = make_session(n=2, n_points=10)
        g0, g1 = session._all_geometries()
        g0.vertex_properties.set_property("h", np.arange(10, dtype=np.float32))
        g1.vertex_properties.set_property("k", np.arange(10, dtype=np.int32))
        result = _dispatch(session, "properties")
        text = _render(result)
        assert "h" in text and "k" in text

    def test_explicit_targets(self, make_session):
        session = make_session(n=2, n_points=10)
        g0, g1 = session._all_geometries()
        g0.vertex_properties.set_property("only_on_g0", np.arange(10))
        g1.vertex_properties.set_property("only_on_g1", np.arange(10))
        result = _dispatch(session, "properties #0")
        text = _render(result)
        assert "only_on_g0" in text
        assert "only_on_g1" not in text

    def test_empty_when_no_properties(self, make_session):
        session = make_session(n=1, n_points=10)
        result = _dispatch(session, "properties")
        text = _render(result).lower()
        assert "no vertex propert" in text or "no properties" in text

    def test_reports_dtype_and_shape(self, make_session):
        session = make_session(n=1, n_points=8)
        g = session._all_geometries()[0]
        g.vertex_properties.set_property("flag", np.zeros(8, dtype=bool))
        result = _dispatch(session, "properties")
        text = _render(result)
        assert "bool" in text
        assert "(8,)" in text or "8" in text

    def test_reports_unique_count(self, make_session):
        session = make_session(n=1, n_points=12)
        g = session._all_geometries()[0]
        g.vertex_properties.set_property(
            "cluster_id", np.array([0, 1, 2] * 4, dtype=np.int32)
        )
        result = _dispatch(session, "properties")
        text = _render(result)
        assert "3" in text  # three unique values

    def test_value_display_categorical_strings(self, make_session):
        session = make_session(n=1, n_points=20)
        g = session._all_geometries()[0]
        labels = np.array(["a", "b", "a", "b", "c"] * 4, dtype=object)
        g.vertex_properties.set_property("label", labels)
        result = _dispatch(session, "properties name=label")
        text = _render(result)
        assert "a" in text and "b" in text and "c" in text
        assert "8" in text  # count of 'a'
        assert "40" in text or "20" in text  # percentage column

    def test_value_display_bool(self, make_session):
        session = make_session(n=1, n_points=10)
        g = session._all_geometries()[0]
        g.vertex_properties.set_property(
            "flag", np.array([True, False] * 5, dtype=bool)
        )
        result = _dispatch(session, "properties name=flag")
        text = _render(result)
        assert "True" in text and "False" in text
        assert "5" in text

    def test_value_display_low_cardinality_int(self, make_session):
        session = make_session(n=1, n_points=12)
        g = session._all_geometries()[0]
        g.vertex_properties.set_property(
            "cluster_id", np.array([0, 1, 2] * 4, dtype=np.int32)
        )
        result = _dispatch(session, "properties name=cluster_id")
        text = _render(result)
        assert "0" in text and "1" in text and "2" in text
        assert "4" in text  # count per value

    def test_value_display_aggregates_across_geometries(self, make_session):
        session = make_session(n=2, n_points=10)
        g0, g1 = session._all_geometries()
        g0.vertex_properties.set_property("label", np.array(["a"] * 10, dtype=object))
        g1.vertex_properties.set_property("label", np.array(["b"] * 10, dtype=object))
        result = _dispatch(session, "properties name=label")
        text = _render(result)
        assert "a" in text and "b" in text
        assert "10" in text
        assert "2" in text  # 2 geometries footer

    def test_value_display_property_missing(self, make_session):
        session = make_session(n=1, n_points=10)
        result = _dispatch(session, "properties name=nonexistent")
        text = _render(result).lower()
        assert "not found" in text or "no values" in text

    def test_value_display_numeric_sparkline(self, make_session):
        session = make_session(n=1, n_points=100)
        g = session._all_geometries()[0]
        rng = np.random.RandomState(0)
        g.vertex_properties.set_property("curvature", rng.rand(100).astype(np.float32))
        result = _dispatch(session, "properties name=curvature")
        text = _render(result)
        assert "Min" in text and "Max" in text and "Mean" in text
        assert "Median" in text and "Std" in text
        assert "#0" in text
        assert any(c in text for c in "▁▂▃▄▅▆▇█")

    def test_value_display_numeric_multiple_geoms_share_x_axis(self, make_session):
        """Two geometries with disjoint ranges still get one shared edge set."""
        session = make_session(n=2, n_points=50)
        g0, g1 = session._all_geometries()
        g0.vertex_properties.set_property(
            "v", np.linspace(0.0, 1.0, 50, dtype=np.float32)
        )
        g1.vertex_properties.set_property(
            "v", np.linspace(5.0, 6.0, 50, dtype=np.float32)
        )
        result = _dispatch(session, "properties name=v")
        text = _render(result)
        assert "#0" in text and "#1" in text
        lines = text.splitlines()
        sparkline_lines = [l for l in lines if any(c in l for c in "▁▂▃▄▅▆▇█")]
        assert len(sparkline_lines) >= 2

    def test_value_display_numeric_high_cardinality_int_uses_sparkline(
        self, make_session
    ):
        session = make_session(n=1, n_points=100)
        g = session._all_geometries()[0]
        g.vertex_properties.set_property("rank", np.arange(100, dtype=np.int32))
        result = _dispatch(session, "properties name=rank")
        text = _render(result)
        assert any(c in text for c in "▁▂▃▄▅▆▇█")


class TestMeasureSparkline:

    def test_measure_array_result_has_sparkline_column(self, make_session):
        # height returns a per-vertex array, so this hits the array branch
        session = make_session(n=1, n_points=200)
        result = _dispatch(session, "measure height #0")
        text = _render(result)
        assert "Min" in text and "Max" in text and "Mean" in text
        assert "Median" in text and "Std" in text
        assert "Distribution" in text
        assert any(c in text for c in "▁▂▃▄▅▆▇█")

    def test_measure_array_result_multiple_geoms_share_x_axis(self, make_session):
        session = make_session(n=2, n_points=100)
        result = _dispatch(session, "measure height #0 #1")
        text = _render(result)
        assert "#0" in text and "#1" in text
        sparkline_chars = "▁▂▃▄▅▆▇█"
        sparkline_lines = [
            l for l in text.splitlines() if any(c in l for c in sparkline_chars)
        ]
        assert len(sparkline_lines) >= 2

    def test_measure_scalar_result_unchanged(self, make_session):
        session = make_session(n=2, n_points=77)
        result = _dispatch(session, "measure n_points #0 #1")
        text = _render(result)
        assert "Value" in text
        assert "Distribution" not in text


class TestCommandRegistryAPI:

    def test_get_existing(self):
        cmd = CommandRegistry.get("list")
        assert cmd is not None
        assert cmd.name == "list"

    def test_get_missing(self):
        assert CommandRegistry.get("nonexistent_xyz") is None

    def test_list_commands(self):
        cmds = CommandRegistry.list_commands()
        names = [c.name for c in cmds]
        assert "list" in names
        assert "help" in names
        assert "info" in names
        assert sorted(names) == names


class TestMeasureVertexPropertyBlocked:

    def test_measure_help_does_not_list_vertex_property(self, make_session):
        session = make_session(n=1, n_points=10)
        result = _dispatch(session, "measure help")
        text = _render(result).lower()
        assert "vertex_property" not in text

    def test_measure_vertex_property_returns_redirect(self, make_session):
        session = make_session(n=1, n_points=10)
        g = session._all_geometries()[0]
        g.vertex_properties.set_property("label", np.array(["a"] * 10, dtype=object))
        result = _dispatch(session, "measure vertex_property name=label #0")
        text = _render(result).lower()
        assert "properties" in text and "name=" in text

    def test_calculator_still_callable_from_python(self):
        """The GUI dialog path (GeometryProperties.compute) must keep working."""
        from mosaic.properties import GeometryProperties
        from mosaic.geometry import Geometry

        g = Geometry(points=np.zeros((5, 3), dtype=np.float32))
        g.vertex_properties.set_property("tag", np.array(["x"] * 5, dtype=object))
        result = GeometryProperties.compute("vertex_property", g, name="tag")
        assert result is not None
        assert len(result) == 5
