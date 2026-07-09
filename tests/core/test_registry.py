"""
Tests for the unified method and parameter registry.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import pytest

from mosaic.registry import (
    Param,
    Method,
    Operation,
    MethodRegistry,
    _UNSET,
    _WIDGET_TYPE,
)


class TestParam:

    def test_defaults(self):
        p = Param(name="depth", type="float")
        assert p.name == "depth"
        assert p.type == "float"
        assert p.default is _UNSET
        assert p.label == ""
        assert p.options is None

    def test_widget_type_from_type(self):
        for py_type, expected in _WIDGET_TYPE.items():
            p = Param(name="x", type=py_type)
            assert p.widget_type == expected

    def test_widget_type_select_when_options(self):
        p = Param(name="method", type="str", options=("a", "b"))
        assert p.widget_type == "select"

    def test_widget_type_unknown_passthrough(self):
        p = Param(name="x", type="custom")
        assert p.widget_type == "custom"

    def test_to_setting_dict_minimal(self):
        p = Param(name="depth", type="float")
        d = p.to_setting_dict()
        assert d["label"] == "Depth"
        assert d["parameter"] == "depth"
        assert d["type"] == "float"
        assert "default" not in d

    def test_to_setting_dict_with_default(self):
        p = Param(name="k", type="int", default=10)
        d = p.to_setting_dict()
        assert d["default"] == 10

    def test_to_setting_dict_with_all_fields(self):
        p = Param(
            name="voxel_size",
            type="float",
            label="Voxel Size",
            default=2.5,
            description="Size of each voxel.",
            notes="Must be positive.",
            min=0.1,
            max=100.0,
            step=0.5,
            decimals=2,
        )
        d = p.to_setting_dict()
        assert d["label"] == "Voxel Size"
        assert d["default"] == 2.5
        assert d["description"] == "Size of each voxel."
        assert d["notes"] == "Must be positive."
        assert d["min"] == 0.1
        assert d["max"] == 100.0
        assert d["step"] == 0.5
        assert d["decimals"] == 2

    def test_to_setting_dict_with_options(self):
        p = Param(name="mode", type="str", options=("fast", "slow"), default="fast")
        d = p.to_setting_dict()
        assert d["type"] == "select"
        assert d["options"] == ["fast", "slow"]
        assert d["default"] == "fast"

    def test_to_setting_dict_path_with_file_mode(self):
        p = Param(
            name="output_dir",
            type="path",
            file_mode=False,
            placeholder="/tmp/output",
        )
        d = p.to_setting_dict()
        assert d["type"] == "PathSelector"
        assert d["file_mode"] is False
        assert d["placeholder"] == "/tmp/output"

    def test_auto_label_from_name(self):
        p = Param(name="voxel_size", type="float")
        d = p.to_setting_dict()
        assert d["label"] == "Voxel Size"

    def test_explicit_label_overrides(self):
        p = Param(name="voxel_size", type="float", label="Custom Label")
        d = p.to_setting_dict()
        assert d["label"] == "Custom Label"

    def test_frozen(self):
        p = Param(name="x", type="int")
        with pytest.raises(AttributeError):
            p.name = "y"


class TestMethod:

    def test_defaults(self):
        m = Method(display_name="DBSCAN", internal_name="dbscan")
        assert m.display_name == "DBSCAN"
        assert m.internal_name == "dbscan"
        assert m.params == ()
        assert m.description == ""
        assert m.gui is True

    def test_with_params(self):
        p = Param(name="eps", type="float", default=0.5)
        m = Method(display_name="DBSCAN", internal_name="dbscan", params=(p,))
        assert len(m.params) == 1
        assert m.params[0].name == "eps"

    def test_gui_false(self):
        m = Method(display_name="Hidden", internal_name="hidden", gui=False)
        assert m.gui is False


class TestOperation:

    @pytest.fixture
    def simple_op(self):
        return Operation(
            name="cluster",
            description="Cluster point cloud.",
            methods=(
                Method(
                    "DBSCAN",
                    "dbscan",
                    params=(Param("distance", "float", default=20.0),),
                ),
                Method(
                    "K-Means", "kmeans", params=(Param("n_clusters", "int", default=2),)
                ),
            ),
            common_params=(Param("drop_noise", "bool", default=True),),
        )

    def test_get_method_by_display_name(self, simple_op):
        m = simple_op.get_method("DBSCAN")
        assert m is not None
        assert m.internal_name == "dbscan"

    def test_get_method_by_internal_name(self, simple_op):
        m = simple_op.get_method("kmeans")
        assert m is not None
        assert m.display_name == "K-Means"

    def test_get_method_case_insensitive(self, simple_op):
        assert simple_op.get_method("dbscan") is not None
        assert simple_op.get_method("DBSCAN") is not None
        assert simple_op.get_method("Dbscan") is not None

    def test_get_method_not_found(self, simple_op):
        assert simple_op.get_method("nonexistent") is None

    def test_display_to_internal(self, simple_op):
        assert simple_op.display_to_internal("DBSCAN") == "dbscan"
        assert simple_op.display_to_internal("K-Means") == "kmeans"

    def test_display_to_internal_passthrough(self, simple_op):
        assert simple_op.display_to_internal("unknown") == "unknown"

    def test_build_usage_no_method(self, simple_op):
        usage = simple_op.build_usage()
        assert usage == "cluster <method> [parameter=value ...] [targets]"

    def test_build_usage_with_method(self, simple_op):
        usage = simple_op.build_usage("dbscan")
        assert usage == "cluster dbscan [parameter=value ...] [targets]"

    def test_build_usage_no_targets(self):
        op = Operation(
            name="open", targets=False, common_params=(Param("filepath", "path"),)
        )
        usage = op.build_usage()
        assert "[targets]" not in usage

    def test_to_settings_dict_structure(self, simple_op):
        d = simple_op.to_settings_dict()
        assert d["title"] == "Settings"
        assert "settings" in d
        assert "method_settings" in d

        method_setting = d["settings"][0]
        assert method_setting["parameter"] == "method"
        assert method_setting["type"] == "select"
        assert method_setting["options"] == ["DBSCAN", "K-Means"]

    def test_to_settings_dict_common_params(self, simple_op):
        d = simple_op.to_settings_dict()
        common = [s for s in d["settings"] if s["parameter"] == "drop_noise"]
        assert len(common) == 1
        assert common[0]["type"] == "boolean"

    def test_to_settings_dict_method_params(self, simple_op):
        d = simple_op.to_settings_dict()
        ms = d["method_settings"]
        assert "DBSCAN" in ms
        assert ms["DBSCAN"][0]["parameter"] == "distance"
        assert "K-Means" in ms
        assert ms["K-Means"][0]["parameter"] == "n_clusters"

    def test_to_settings_dict_excludes_gui_false(self):
        op = Operation(
            name="test",
            methods=(
                Method("Visible", "visible", gui=True),
                Method("Hidden", "hidden", gui=False),
            ),
        )
        d = op.to_settings_dict()
        assert d["settings"][0]["options"] == ["Visible"]
        assert "Hidden" not in d.get("method_settings", {})


class TestMethodRegistry:

    def test_get_registered_operation(self):
        op = MethodRegistry.get("cluster")
        assert op is not None
        assert op.name == "cluster"

    def test_get_missing_returns_none(self):
        assert MethodRegistry.get("nonexistent_op_xyz") is None

    def test_settings_dict(self):
        d = MethodRegistry.settings_dict("cluster")
        assert "settings" in d
        assert "method_settings" in d

    def test_settings_dict_missing_raises(self):
        with pytest.raises(KeyError, match="No operation registered"):
            MethodRegistry.settings_dict("nonexistent_op_xyz")

    def test_resolve_method_display_to_internal(self):
        internal = MethodRegistry.resolve_method("cluster", "DBSCAN")
        assert internal == "dbscan"

    def test_resolve_method_passthrough_for_unknown_op(self):
        assert MethodRegistry.resolve_method("no_such_op", "value") == "value"

    def test_resolve_method_passthrough_for_unknown_method(self):
        assert (
            MethodRegistry.resolve_method("cluster", "no_such_method")
            == "no_such_method"
        )

    def test_all_operations_returns_dict(self):
        ops = MethodRegistry.all_operations()
        assert isinstance(ops, dict)
        assert "cluster" in ops
        assert "measure" in ops
        assert "open" in ops

    def test_well_known_operations_present(self):
        for name in (
            "cluster",
            "downsample",
            "fit",
            "measure",
            "open",
            "save",
            "filter",
        ):
            assert MethodRegistry.get(name) is not None, f"{name} not registered"

    def test_measure_has_methods(self):
        op = MethodRegistry.get("measure")
        assert len(op.methods) > 0
        method_names = {m.internal_name for m in op.methods}
        assert "n_points" in method_names
        assert "height" in method_names
