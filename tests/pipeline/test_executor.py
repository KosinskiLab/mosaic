"""
Tests for the pipeline executor (compile_run, generate_runs, execute_run).

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import os
import shlex
from unittest.mock import patch, MagicMock

import pytest

from mosaic.pipeline.executor import compile_run, generate_runs, execute_run


def _run(operations, run_id="test", input_file="/data/input.star", input_params=None):
    return {
        "run_id": run_id,
        "input_file": input_file,
        "input_params": input_params or {},
        "operations": operations,
    }


def _import_op(input_file="/data/input.star", save_output=True):
    return {
        "operation_id": "import_batch",
        "settings": {"input_file": input_file},
        "save_output": save_output,
        "visible_output": True,
        "group_name": "",
    }


def _op(op_id, settings=None, save_output=True, visible_output=True, group_name=""):
    return {
        "operation_id": op_id,
        "settings": settings or {},
        "save_output": save_output,
        "visible_output": visible_output,
        "group_name": group_name,
    }


class TestCompileImport:

    def test_open(self):
        steps = compile_run(_run([_import_op()]))
        assert steps[0][1] == "open /data/input.star"

    def test_pickle_uses_open(self):
        path = "/data/session.pickle"
        steps = compile_run(_run([_import_op(path)], input_file=path))
        assert steps[0][1].startswith("open ")

    def test_params_included(self):
        r = _run([_import_op()], input_params={"offset": 10, "scale": 2})
        line = compile_run(r)[0][1]
        assert "offset=10" in line and "scale=2" in line

    def test_default_params_excluded(self):
        r = _run([_import_op()], input_params={"offset": 0, "scale": 1})
        assert "offset" not in compile_run(r)[0][1]

    @pytest.mark.parametrize(
        "path",
        [
            "/path/with spaces/file.star",
            "/path/with 'quotes'/file.star",
            '/path/"double"/file.star',
            "/path/unicode/\u00e4\u00f6\u00fc/file.star",
        ],
    )
    def test_path_quoting_roundtrip(self, path):
        steps = compile_run(_run([_import_op(path)], input_file=path))
        tokens = shlex.split(steps[0][1])
        assert tokens[1] == path


class TestCompileSaveExport:

    def test_save_session_path(self, tmp_path):
        r = _run(
            [_import_op(), _op("save_session", {"output_dir": str(tmp_path)})],
            run_id="my_run",
        )
        line = compile_run(r)[1][1]
        expected = os.path.join(str(tmp_path), "my_run.pickle")
        tokens = shlex.split(line)
        assert tokens == ["save", expected]

    def test_save_session_creates_dir(self, tmp_path):
        out = str(tmp_path / "new_dir")
        compile_run(_run([_import_op(), _op("save_session", {"output_dir": out})]))
        assert os.path.isdir(out)

    @pytest.mark.parametrize("fmt", ["star", "xyz", "obj", "ply", "mrc"])
    def test_export_format(self, tmp_path, fmt):
        r = _run(
            [
                _import_op(),
                _op("export_data", {"output_dir": str(tmp_path), "format": fmt}),
            ]
        )
        line = compile_run(r)[1][1]
        assert f"format={fmt}" in line

    def test_export_filters_method_key(self, tmp_path):
        r = _run(
            [
                _import_op(),
                _op(
                    "export_data",
                    {
                        "output_dir": str(tmp_path),
                        "format": "star",
                        "method": "Point Cloud",
                    },
                ),
            ]
        )
        assert "method=" not in compile_run(r)[1][1]


class TestCompileMeshAnalysis:

    @patch("mosaic.pipeline.executor.MethodRegistry")
    def test_known_method(self, mock_reg):
        m = MagicMock()
        m.internal_name = "mesh_curvature"
        op = MagicMock()
        op.get_method.return_value = m
        mock_reg.get.return_value = op
        steps = compile_run(
            _run(
                [
                    _import_op(),
                    _op("mesh_analysis", {"method": "Curvature", "output_dir": ""}),
                ]
            )
        )
        assert steps[1][1].startswith("measure mesh_curvature @last")

    @patch("mosaic.pipeline.executor.MethodRegistry")
    def test_unknown_method_skipped(self, mock_reg):
        op = MagicMock()
        op.get_method.return_value = None
        mock_reg.get.return_value = op
        steps = compile_run(
            _run([_import_op(), _op("mesh_analysis", {"method": "Nonexistent"})])
        )
        assert len(steps) == 1

    @patch("mosaic.pipeline.executor.MethodRegistry")
    def test_extra_kwargs_appended(self, mock_reg):
        m = MagicMock()
        m.internal_name = "mesh_curvature"
        op = MagicMock()
        op.get_method.return_value = m
        mock_reg.get.return_value = op
        steps = compile_run(
            _run(
                [
                    _import_op(),
                    _op(
                        "mesh_analysis",
                        {"method": "Curvature", "output_dir": "", "radius": 5.0},
                    ),
                ]
            )
        )
        assert "radius=5.0" in steps[1][1]
        assert "method=" not in steps[1][1]


class TestCompileClusterSelect:

    @pytest.mark.parametrize(
        "lower, upper, expected_parts",
        [
            (100, 5000, ["lower=100", "upper=5000"]),
            (500, 0, ["lower=500"]),
            (0, 2000, ["upper=2000"]),
            (0, 0, []),
        ],
    )
    def test_thresholds(self, lower, upper, expected_parts):
        r = _run(
            [
                _import_op(),
                _op(
                    "cluster_select",
                    {"lower_threshold": lower, "upper_threshold": upper},
                ),
            ]
        )
        line = compile_run(r)[1][1]
        assert line.startswith("filter @last property=n_points")
        for part in expected_parts:
            assert part in line


class TestCompileGeneric:

    def test_persist_false(self):
        r = _run(
            [_import_op(), _op("cluster", {"method": "DBSCAN"}, save_output=False)]
        )
        assert "persist=false" in compile_run(r)[1][1]

    def test_visibility_false_adds_step(self):
        r = _run(
            [
                _import_op(),
                _op("downsample", {"method": "Radius"}, visible_output=False),
            ]
        )
        steps = compile_run(r)
        assert any("visibility @last visible=false" in line for _, line in steps)

    @pytest.mark.parametrize(
        "name, expected_suffix",
        [
            ("My Fancy Group", "'My Fancy Group'"),
            ("Simple", "Simple"),
        ],
    )
    def test_group_name(self, name, expected_suffix):
        r = _run([_import_op(), _op("cluster", {"method": "DBSCAN"}, group_name=name)])
        group_lines = [l for _, l in compile_run(r) if l.startswith("group")]
        assert len(group_lines) == 1
        assert group_lines[0] == f"group @last {expected_suffix}"

    def test_group_not_added_when_persist_false(self):
        r = _run(
            [
                _import_op(),
                _op(
                    "cluster", {"method": "DBSCAN"}, save_output=False, group_name="Grp"
                ),
            ]
        )
        assert not any("group" in l for _, l in compile_run(r))

    def test_empty_operations(self):
        assert compile_run(_run([])) == []

    def test_method_with_spaces(self):
        r = _run([_import_op(), _op("cluster", {"method": "Connected Components"})])
        line = compile_run(r)[1][1]
        tokens = shlex.split(line)
        # Display names are resolved to internal names for REPL commands
        assert "connected_components" in tokens


class TestGenerateRuns:

    @staticmethod
    def _pipeline(files, extra_nodes=None):
        import_node = {
            "id": "import_1",
            "operation_id": "import_batch",
            "name": "Import",
            "settings": {"input_files": files, "file_parameters": {}},
            "inputs": [],
            "save_output": True,
            "visible_output": True,
        }
        nodes = [import_node]
        if extra_nodes:
            nodes.extend(extra_nodes)
        return {"nodes": nodes, "version": "2.0"}

    def test_one_file_one_run(self):
        runs = generate_runs(self._pipeline(["/data/a.star"]))
        assert len(runs) == 1
        assert runs[0]["input_file"] == "/data/a.star"
        assert runs[0]["run_id"] == "a"

    def test_multiple_files(self):
        runs = generate_runs(self._pipeline(["/a.star", "/b.star"]))
        assert len(runs) == 2

    def test_operation_sequence(self):
        cluster_node = {
            "id": "cluster_1",
            "operation_id": "cluster",
            "name": "Cluster",
            "settings": {"method": "DBSCAN"},
            "inputs": ["import_1"],
            "save_output": True,
            "visible_output": True,
        }
        runs = generate_runs(self._pipeline(["/a.star"], [cluster_node]))
        ops = [o["operation_id"] for o in runs[0]["operations"]]
        assert ops == ["import_batch", "cluster"]

    def test_empty_nodes(self):
        assert generate_runs({"nodes": []}) == []

    def test_no_import_raises(self):
        cfg = {
            "nodes": [
                {"id": "x", "operation_id": "cluster", "settings": {}, "inputs": []}
            ]
        }
        with pytest.raises(ValueError, match="Import Files"):
            generate_runs(cfg)

    def test_no_input_files_raises(self):
        cfg = self._pipeline([])
        # input_files is empty list
        with pytest.raises(ValueError, match="No input files"):
            generate_runs(cfg)


class TestExecuteRun:

    def test_skip_complete(self, tmp_path):
        """When output already exists and skip_complete=True, execution is skipped."""
        out_file = tmp_path / "test.pickle"
        out_file.write_bytes(b"fake")
        r = _run(
            [
                _import_op(),
                _op("save_session", {"output_dir": str(tmp_path)}),
            ]
        )
        # Should not raise — execution is skipped
        execute_run(r, skip_complete=True)
        # The file should still be the fake content (not overwritten)
        assert out_file.read_bytes() == b"fake"
