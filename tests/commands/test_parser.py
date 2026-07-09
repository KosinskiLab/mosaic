"""
Tests for the REPL command parser.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import math
import shlex

import pytest
import numpy as np

from mosaic.commands.parser import (
    ParsedCommand,
    parse_command,
    format_value,
    format_kwargs,
    _coerce_value,
    _TARGET_RE,
    _SPECIAL_TARGETS,
)
from mosaic.registry import Param


class TestParseCommand:

    @pytest.mark.parametrize(
        "text, verb, targets, args, kwargs",
        [
            ("list", "list", [], [], {}),
            ("info #0", "info", ["#0"], [], {}),
            ("info #0-2", "info", ["#0-2"], [], {}),
            (
                "visibility #0 visible=false",
                "visibility",
                ["#0"],
                [],
                {"visible": False},
            ),
            ("group #0 TestGroup", "group", ["#0"], ["TestGroup"], {}),
            ("rename #0 s/old/new/", "rename", ["#0"], ["s/old/new/"], {}),
            (
                "cluster @last method=dbscan",
                "cluster",
                ["@last"],
                [],
                {"method": "dbscan"},
            ),
            (
                "downsample * method=radius voxel_size=2.5",
                "downsample",
                ["*"],
                [],
                {"method": "radius", "voxel_size": 2.5},
            ),
            ("open /path/to/file.star", "open", [], ["/path/to/file.star"], {}),
            ("measure n_points #0 #1", "measure", ["#0", "#1"], ["n_points"], {}),
        ],
    )
    def test_parse(self, text, verb, targets, args, kwargs):
        p = parse_command(text)
        assert p.verb == verb
        assert p.targets == targets
        assert p.args == args
        assert p.kwargs == kwargs

    @pytest.mark.parametrize("text", ["", "  ", "# comment", "## also comment"])
    def test_returns_none(self, text):
        assert parse_command(text) is None

    def test_geometry_ref_not_comment(self):
        """#0 is not treated as a comment — it parses (verb becomes '#0')."""
        p = parse_command("#0")
        assert p is not None

    def test_syntax_error(self):
        with pytest.raises(ValueError, match="Syntax error"):
            parse_command("open 'unclosed")


class TestParseCommandEdgeCases:

    def test_empty_string(self):
        assert parse_command("") is None

    def test_only_whitespace(self):
        assert parse_command("   ") is None
        assert parse_command("\t\n") is None

    def test_single_word_verb_only(self):
        result = parse_command("help")
        assert result is not None
        assert result.verb == "help"
        assert result.targets == []
        assert result.args == []
        assert result.kwargs == {}

    def test_verb_is_lowered(self):
        result = parse_command("HELP")
        assert result.verb == "help"

    def test_command_with_only_targets(self):
        result = parse_command("list #0 #1")
        assert result.verb == "list"
        assert result.targets == ["#0", "#1"]
        assert result.args == []
        assert result.kwargs == {}

    def test_command_with_only_kwargs(self):
        result = parse_command("open filepath=/data/test.star")
        assert result.verb == "open"
        assert result.targets == []
        assert result.args == []
        assert result.kwargs == {"filepath": "/data/test.star"}

    def test_command_with_mixed_order_targets_and_kwargs(self):
        result = parse_command("cluster #0 method=dbscan #1")
        assert result.verb == "cluster"
        assert set(result.targets) == {"#0", "#1"}
        assert result.kwargs == {"method": "dbscan"}

    def test_quoted_string_with_spaces(self):
        result = parse_command('group #0 "My Group"')
        assert result.verb == "group"
        assert result.targets == ["#0"]
        assert result.args == ["My Group"]

    def test_quoted_string_with_special_chars(self):
        result = parse_command('open "file (copy).star"')
        assert result.verb == "open"
        assert result.args == ["file (copy).star"]

    def test_equals_in_kwarg_value(self):
        result = parse_command("measure #0 formula=a=b")
        assert result.verb == "measure"
        assert result.kwargs["formula"] == "a=b"

    def test_token_starting_with_equals(self):
        result = parse_command("open =test")
        assert result.verb == "open"
        assert "=test" in result.args
        assert result.kwargs == {}

    def test_comment_line_hash_no_digit(self):
        assert parse_command("# this is a comment") is None

    def test_comment_line_hash_only(self):
        assert parse_command("#") is None

    def test_hash_with_letter(self):
        assert parse_command("#abc") is None

    def test_geometry_ref_as_first_token(self):
        result = parse_command("#0 info")
        assert result is not None
        assert result.verb == "#0"

    def test_unmatched_quote_raises(self):
        with pytest.raises(ValueError, match="Syntax error"):
            parse_command('open "unclosed')

    def test_multiple_kwargs(self):
        result = parse_command("filter #0 property=area min=10 max=100")
        assert result.kwargs == {"property": "area", "min": 10, "max": 100}

    def test_tab_and_extra_whitespace(self):
        result = parse_command("  list   #0    #1  ")
        assert result.verb == "list"
        assert result.targets == ["#0", "#1"]


class TestCoerceValue:

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("true", True),
            ("False", False),
            ("42", 42),
            ("-7", -7),
            ("3.14", 3.14),
            ("hello", "hello"),
        ],
    )
    def test_scalars(self, raw, expected):
        assert _coerce_value(raw) == expected

    def test_comma_array(self):
        result = _coerce_value("1.0,2.0,3.0")
        np.testing.assert_array_almost_equal(result, [1.0, 2.0, 3.0])

    def test_bracket_array(self):
        result = _coerce_value("[1,2,3]")
        np.testing.assert_array_almost_equal(result, [1.0, 2.0, 3.0])


class TestCoerceValueEdgeCases:

    @pytest.mark.parametrize("val", ["true", "True", "TRUE", "tRuE"])
    def test_true_variants(self, val):
        assert _coerce_value(val) is True

    @pytest.mark.parametrize("val", ["false", "False", "FALSE", "fAlSe"])
    def test_false_variants(self, val):
        assert _coerce_value(val) is False

    def test_zero(self):
        assert _coerce_value("0") == 0
        assert isinstance(_coerce_value("0"), int)

    def test_positive_int(self):
        assert _coerce_value("1") == 1
        assert isinstance(_coerce_value("1"), int)

    def test_negative_int(self):
        assert _coerce_value("-1") == -1
        assert isinstance(_coerce_value("-1"), int)

    def test_float_zero(self):
        assert _coerce_value("0.0") == 0.0
        assert isinstance(_coerce_value("0.0"), float)

    def test_scientific_notation(self):
        assert _coerce_value("1e5") == 1e5
        assert isinstance(_coerce_value("1e5"), float)

    def test_negative_scientific(self):
        result = _coerce_value("-1.5e-3")
        assert result == pytest.approx(-1.5e-3)
        assert isinstance(result, float)

    def test_inf(self):
        result = _coerce_value("inf")
        assert result == float("inf")
        assert isinstance(result, float)

    def test_negative_inf(self):
        result = _coerce_value("-inf")
        assert result == float("-inf")
        assert isinstance(result, float)

    def test_nan(self):
        result = _coerce_value("nan")
        assert math.isnan(result)
        assert isinstance(result, float)

    def test_none_string(self):
        assert _coerce_value("None") == "None"

    def test_null_string(self):
        assert _coerce_value("null") == "null"

    def test_nil_string(self):
        assert _coerce_value("nil") == "nil"

    def test_empty_string(self):
        assert _coerce_value("") == ""
        assert isinstance(_coerce_value(""), str)

    def test_plain_string(self):
        assert _coerce_value("hello") == "hello"

    def test_string_with_spaces(self):
        assert _coerce_value("hello world") == "hello world"

    def test_string_that_looks_numeric_but_isnt(self):
        assert _coerce_value("12abc") == "12abc"

    def test_large_int(self):
        assert _coerce_value("999999999999") == 999999999999


class TestFormatValue:

    @pytest.mark.parametrize(
        "value, expected",
        [
            (True, "true"),
            (False, "false"),
            (42, "42"),
            (3.14, "3.14"),
            ("hello", "hello"),
        ],
    )
    def test_scalars(self, value, expected):
        assert format_value(value) == expected

    def test_ndarray(self):
        assert format_value(np.array([1.0, 2.0])) == "1.0,2.0"

    def test_list(self):
        assert format_value([1, 2, 3]) == "1,2,3"


class TestFormatKwargs:

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"method": "RBF"},
            {"workers": 4},
            {"rate": 3.14},
            {"flag": True},
            {"flag": False},
            {"method": "Connected Components"},
            {"a": 1, "b": "x", "verbose": True},
        ],
    )
    def test_roundtrip(self, kwargs):
        formatted = format_kwargs(kwargs)
        tokens = shlex.split(formatted)
        recovered = {}
        for tok in tokens:
            k, _, v = tok.partition("=")
            recovered[k] = _coerce_value(v)
        for key, val in kwargs.items():
            assert recovered[key] == val

    def test_empty_dict(self):
        assert format_kwargs({}) == ""

    def test_none_values_skipped(self):
        assert format_kwargs({"a": None}) == ""

    def test_path_with_spaces(self):
        result = format_kwargs({"path": "/dir with spaces/file"})
        tokens = shlex.split(result)
        _, _, v = tokens[0].partition("=")
        assert v == "/dir with spaces/file"

    @pytest.mark.parametrize(
        "value",
        [
            'has"quote',
            "it's here",
            'say "hello"',
            "C:\\Users\\data",
            "line1\nline2",
            "tab\there",
        ],
    )
    def test_special_chars_roundtrip(self, value):
        result = format_kwargs({"k": value})
        _, _, v = result.partition("=")
        recovered = shlex.split(v)[0]
        assert recovered == value


class TestTargetParsing:

    def test_simple_target(self):
        assert _TARGET_RE.match("#0")
        assert _TARGET_RE.match("#999")

    def test_range_target(self):
        assert _TARGET_RE.match("#0-5")

    def test_reversed_range(self):
        assert _TARGET_RE.match("#5-0")

    def test_special_at_last(self):
        assert "@last" in _SPECIAL_TARGETS

    def test_special_star(self):
        assert "*" in _SPECIAL_TARGETS

    def test_special_targets_in_parse(self):
        result = parse_command("info @last")
        assert result.targets == ["@last"]

    def test_star_target_in_parse(self):
        result = parse_command("list *")
        assert result.targets == ["*"]

    def test_comma_separated_targets_not_handled(self):
        result = parse_command("info #0,#1,#2")
        assert _TARGET_RE.match("#0,#1,#2") is None
        assert "#0,#1,#2" in result.args
        assert result.targets == []

    def test_negative_target_not_matched(self):
        assert _TARGET_RE.match("#-1") is None

    def test_negative_target_goes_to_args(self):
        result = parse_command("info #-1")
        assert result.targets == []
        assert "#-1" in result.args

    def test_double_hash_not_matched(self):
        assert _TARGET_RE.match("##0") is None

    def test_double_hash_treated_as_comment(self):
        result = parse_command("##0")
        assert result is None

    def test_hash_only_no_number(self):
        assert _TARGET_RE.match("#") is None
        result = parse_command("#")
        assert result is None

    def test_incomplete_range(self):
        assert _TARGET_RE.match("#0-") is None

    def test_incomplete_range_in_parse(self):
        result = parse_command("info #0-")
        assert "#0-" in result.args
        assert result.targets == []

    def test_multiple_ranges(self):
        result = parse_command("info #0-3 #5-9")
        assert result.targets == ["#0-3", "#5-9"]

    def test_target_with_leading_zeros(self):
        assert _TARGET_RE.match("#007")
        result = parse_command("info #007")
        assert result.targets == ["#007"]


class TestResolvePositional:

    def test_maps_args_to_params(self):
        p = ParsedCommand(verb="test", args=["radius", "5"])
        p.resolve_positional(["method", "voxel_size"])
        assert p.kwargs == {"method": "radius", "voxel_size": 5}
        assert p.args == []

    def test_skips_existing_kwargs(self):
        p = ParsedCommand(verb="test", args=["10"], kwargs={"method": "radius"})
        p.resolve_positional(["method", "size"])
        assert p.kwargs["size"] == 10
        assert p.kwargs["method"] == "radius"

    def test_with_string_param_names(self):
        cmd = ParsedCommand(verb="test", args=["42", "hello"])
        cmd.resolve_positional(["count", "name"])
        assert cmd.kwargs == {"count": 42, "name": "hello"}
        assert cmd.args == []

    def test_with_param_objects_str_type(self):
        cmd = ParsedCommand(verb="test", args=["42"])
        cmd.resolve_positional([Param(name="label", type="str")])
        assert cmd.kwargs["label"] == "42"
        assert isinstance(cmd.kwargs["label"], str)

    def test_with_param_objects_path_type(self):
        cmd = ParsedCommand(verb="test", args=["/data/test.star"])
        cmd.resolve_positional([Param(name="filepath", type="path")])
        assert cmd.kwargs["filepath"] == "/data/test.star"
        assert isinstance(cmd.kwargs["filepath"], str)

    def test_with_param_objects_int_type(self):
        cmd = ParsedCommand(verb="test", args=["42"])
        cmd.resolve_positional([Param(name="count", type="int")])
        assert cmd.kwargs["count"] == 42
        assert isinstance(cmd.kwargs["count"], int)

    def test_with_param_objects_float_type(self):
        cmd = ParsedCommand(verb="test", args=["3.14"])
        cmd.resolve_positional([Param(name="radius", type="float")])
        assert cmd.kwargs["radius"] == pytest.approx(3.14)
        assert isinstance(cmd.kwargs["radius"], float)

    def test_with_param_objects_bool_type(self):
        cmd = ParsedCommand(verb="test", args=["true"])
        cmd.resolve_positional([Param(name="flag", type="bool")])
        assert cmd.kwargs["flag"] is True

    def test_more_args_than_params(self):
        cmd = ParsedCommand(verb="test", args=["a", "b", "c"])
        cmd.resolve_positional(["first"])
        assert cmd.kwargs == {"first": "a"}
        assert cmd.args == ["b", "c"]

    def test_fewer_args_than_params(self):
        cmd = ParsedCommand(verb="test", args=["hello"])
        cmd.resolve_positional(["name", "extra1", "extra2"])
        assert cmd.kwargs == {"name": "hello"}
        assert cmd.args == []

    def test_no_args(self):
        cmd = ParsedCommand(verb="test", args=[])
        cmd.resolve_positional(["name", "count"])
        assert cmd.kwargs == {}
        assert cmd.args == []

    def test_no_params(self):
        cmd = ParsedCommand(verb="test", args=["a", "b"])
        cmd.resolve_positional([])
        assert cmd.kwargs == {}
        assert cmd.args == ["a", "b"]

    def test_skips_existing_kwargs_with_param_objects(self):
        cmd = ParsedCommand(
            verb="test",
            args=["replacement"],
            kwargs={"filepath": "/original.star"},
        )
        params = [
            Param(name="filepath", type="path"),
            Param(name="method", type="str"),
        ]
        cmd.resolve_positional(params)
        assert cmd.kwargs["filepath"] == "/original.star"
        assert cmd.kwargs["method"] == "replacement"

    def test_coercion_of_numeric_string_with_plain_param(self):
        cmd = ParsedCommand(verb="test", args=["3.14"])
        cmd.resolve_positional(["value"])
        assert cmd.kwargs["value"] == pytest.approx(3.14)
        assert isinstance(cmd.kwargs["value"], float)

    def test_path_value_with_equals_not_coerced(self):
        cmd = ParsedCommand(verb="test", args=["/data/a=b.star"])
        cmd.resolve_positional([Param(name="filepath", type="path")])
        assert cmd.kwargs["filepath"] == "/data/a=b.star"

    def test_resolve_preserves_target_list(self):
        cmd = ParsedCommand(verb="test", targets=["#0", "#1"], args=["val"])
        cmd.resolve_positional(["param1"])
        assert cmd.targets == ["#0", "#1"]
        assert cmd.kwargs == {"param1": "val"}
