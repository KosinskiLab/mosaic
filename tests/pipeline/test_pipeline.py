"""
Tests for the pipeline module.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import json
from unittest.mock import patch, MagicMock

import pytest

from mosaic.pipeline._utils import (
    strip_filepath,
    natural_sort_key,
    topological_sort,
)
from mosaic.pipeline.executor import generate_runs


class TestStripFilepath:
    """Tests for strip_filepath utility function."""

    def test_simple_filename(self):
        """Test extracting name from simple path."""
        assert strip_filepath("/path/to/file.star") == "file"

    def test_multiple_extensions(self):
        """Test filename with multiple dots."""
        assert strip_filepath("/path/to/file.tar.gz") == "file"

    def test_no_extension(self):
        """Test filename without extension."""
        assert strip_filepath("/path/to/filename") == "filename"

    def test_relative_path(self):
        """Test with relative path."""
        assert strip_filepath("data/sample.mrc") == "sample"

    def test_filename_only(self):
        """Test with just filename."""
        assert strip_filepath("test.xyz") == "test"


class TestNaturalSortKey:
    """Tests for natural_sort_key utility function."""

    def test_numeric_sorting(self):
        """Test natural sorting of numbered files."""
        files = ["file10.txt", "file2.txt", "file1.txt"]
        sorted_files = sorted(files, key=natural_sort_key)
        assert sorted_files == ["file1.txt", "file2.txt", "file10.txt"]

    def test_mixed_content(self):
        """Test sorting with mixed alphanumeric content."""
        files = ["data20_run3.star", "data3_run1.star", "data10_run2.star"]
        sorted_files = sorted(files, key=natural_sort_key)
        assert sorted_files == [
            "data3_run1.star",
            "data10_run2.star",
            "data20_run3.star",
        ]

    def test_case_insensitive(self):
        """Test case insensitivity in sorting."""
        files = ["File1.txt", "file2.txt", "FILE3.txt"]
        sorted_files = sorted(files, key=natural_sort_key)
        assert sorted_files == ["File1.txt", "file2.txt", "FILE3.txt"]

    def test_no_numbers(self):
        """Test sorting files without numbers."""
        files = ["beta.txt", "alpha.txt", "gamma.txt"]
        sorted_files = sorted(files, key=natural_sort_key)
        assert sorted_files == ["alpha.txt", "beta.txt", "gamma.txt"]


class TestTopologicalSort:
    """Tests for topological_sort utility function."""

    def test_linear_pipeline(self):
        """Test simple linear pipeline."""
        nodes = [
            {"id": "a", "inputs": []},
            {"id": "b", "inputs": ["a"]},
            {"id": "c", "inputs": ["b"]},
        ]
        node_map = {n["id"]: n for n in nodes}
        result = topological_sort(nodes, node_map, "a")
        assert result == ["a", "b", "c"]

    def test_branching_pipeline(self):
        """Test pipeline with branches."""
        nodes = [
            {"id": "root", "inputs": []},
            {"id": "branch1", "inputs": ["root"]},
            {"id": "branch2", "inputs": ["root"]},
            {"id": "merge", "inputs": ["branch1", "branch2"]},
        ]
        node_map = {n["id"]: n for n in nodes}
        result = topological_sort(nodes, node_map, "root")

        assert result[0] == "root"
        assert result[-1] == "merge"
        assert set(result) == {"root", "branch1", "branch2", "merge"}

    def test_single_node(self):
        """Test single node pipeline."""
        nodes = [{"id": "only", "inputs": []}]
        node_map = {n["id"]: n for n in nodes}
        result = topological_sort(nodes, node_map, "only")
        assert result == ["only"]

    def test_cycle_detection(self):
        """Test that cycles raise ValueError."""
        # Create a graph where a→b→c but d forms a disconnected node
        # This tests the "disconnected nodes" part of the error
        nodes = [
            {"id": "a", "inputs": []},
            {"id": "b", "inputs": ["a"]},
            {"id": "c", "inputs": ["b"]},
            {"id": "d", "inputs": ["d"]},  # Self-referencing disconnected node
        ]
        node_map = {n["id"]: n for n in nodes}
        with pytest.raises(ValueError, match="cycles or disconnected"):
            topological_sort(nodes, node_map, "a")

    def test_unknown_input_reference(self):
        """Test reference to unknown node."""
        nodes = [
            {"id": "a", "inputs": []},
            {"id": "b", "inputs": ["nonexistent"]},
        ]
        node_map = {n["id"]: n for n in nodes}
        with pytest.raises(ValueError, match="unknown input"):
            topological_sort(nodes, node_map, "a")


class TestGenerateRuns:
    """Tests for generate_runs function."""

    @pytest.fixture
    def minimal_config(self):
        """Minimal valid pipeline configuration."""
        return {
            "version": "2.0",
            "nodes": [
                {
                    "id": "import-1",
                    "name": "Import Files",
                    "operation_id": "import_batch",
                    "category": "input",
                    "inputs": [],
                    "settings": {
                        "input_files": ["/path/to/file1.star"],
                        "file_parameters": {},
                    },
                },
                {
                    "id": "save-1",
                    "name": "Save Session",
                    "operation_id": "save_session",
                    "category": "export",
                    "inputs": ["import-1"],
                    "settings": {"output_dir": "/output"},
                },
            ],
        }

    def test_generate_runs_minimal(self, minimal_config):
        """Test run generation with minimal config."""
        runs = generate_runs(minimal_config)

        assert len(runs) == 1
        assert runs[0]["run_id"] == "file1"
        assert runs[0]["input_file"] == "/path/to/file1.star"
        assert len(runs[0]["operations"]) == 2

    def test_generate_runs_multiple_files(self, minimal_config):
        """Test run generation with multiple input files."""
        minimal_config["nodes"][0]["settings"]["input_files"] = [
            "/path/file1.star",
            "/path/file2.star",
            "/path/file3.star",
        ]

        runs = generate_runs(minimal_config)

        assert len(runs) == 3
        assert [r["run_id"] for r in runs] == ["file1", "file2", "file3"]

    def test_generate_runs_with_file_parameters(self, minimal_config):
        """Test that file-specific parameters are passed through."""
        file_params = {"/path/to/file1.star": {"offset": 10, "scale": 2}}
        minimal_config["nodes"][0]["settings"]["file_parameters"] = file_params

        runs = generate_runs(minimal_config)

        assert runs[0]["input_params"] == {"offset": 10, "scale": 2}

    def test_generate_runs_empty_nodes(self):
        """Test with empty nodes list."""
        config = {"version": "2.0", "nodes": []}
        runs = generate_runs(config)
        assert runs == []

    def test_generate_runs_no_import(self):
        """Test error when no import operation."""
        config = {
            "nodes": [
                {
                    "id": "save-1",
                    "name": "Save Session",
                    "operation_id": "save_session",
                    "inputs": [],
                    "settings": {},
                }
            ]
        }
        with pytest.raises(ValueError, match="must start with an Import"):
            generate_runs(config)

    def test_generate_runs_multiple_imports(self):
        """Test error with multiple import operations."""
        config = {
            "nodes": [
                {
                    "id": "import-1",
                    "operation_id": "import_batch",
                    "inputs": [],
                    "settings": {"input_files": ["/file1.star"]},
                },
                {
                    "id": "import-2",
                    "operation_id": "import_batch",
                    "inputs": [],
                    "settings": {"input_files": ["/file2.star"]},
                },
            ]
        }
        with pytest.raises(ValueError, match="only one Import"):
            generate_runs(config)

    def test_generate_runs_no_input_files(self):
        """Test error when no input files specified."""
        config = {
            "nodes": [
                {
                    "id": "import-1",
                    "operation_id": "import_batch",
                    "inputs": [],
                    "settings": {"input_files": []},
                }
            ]
        }
        with pytest.raises(ValueError, match="No input files"):
            generate_runs(config)

    def test_generate_runs_operation_order(self, minimal_config):
        """Test that operations are ordered correctly."""
        minimal_config["nodes"].insert(
            1,
            {
                "id": "cluster-1",
                "name": "Clustering",
                "operation_id": "cluster",
                "category": "preprocessing",
                "inputs": ["import-1"],
                "settings": {"method": "Connected Components"},
            },
        )
        minimal_config["nodes"][2]["inputs"] = ["cluster-1"]

        runs = generate_runs(minimal_config)
        op_ids = [op["operation_id"] for op in runs[0]["operations"]]

        assert op_ids == ["import_batch", "cluster", "save_session"]

    def test_generate_runs_preserves_settings(self, minimal_config):
        """Test that operation settings are preserved."""
        minimal_config["nodes"].append(
            {
                "id": "downsample-1",
                "name": "Downsampling",
                "operation_id": "downsample",
                "category": "preprocessing",
                "inputs": ["import-1"],
                "settings": {"method": "Radius", "voxel_size": 150.0},
                "save_output": False,
                "visible_output": True,
            }
        )

        runs = generate_runs(minimal_config)
        downsample_op = next(
            op for op in runs[0]["operations"] if op["operation_id"] == "downsample"
        )

        assert downsample_op["settings"]["method"] == "Radius"
        assert downsample_op["settings"]["voxel_size"] == 150.0
        assert downsample_op["save_output"] is False

    def test_generate_runs_metadata(self, minimal_config):
        """Test that run metadata is populated correctly."""
        minimal_config["nodes"][0]["settings"]["input_files"] = [
            "/file1.star",
            "/file2.star",
        ]

        runs = generate_runs(minimal_config)

        assert runs[0]["metadata"]["file_index"] == 0
        assert runs[0]["metadata"]["total_files"] == 2
        assert runs[1]["metadata"]["file_index"] == 1
        assert runs[1]["metadata"]["pipeline_version"] == "2.0"


class TestExecuteRun:
    """Tests for execute_run function."""

    @pytest.fixture
    def simple_run_config(self):
        """Simple run configuration for testing."""
        return {
            "run_id": "test_run",
            "input_file": "/path/to/input.star",
            "input_params": {},
            "operations": [
                {
                    "operation_id": "import_batch",
                    "name": "Import Files",
                    "settings": {"input_file": "/path/to/input.star"},
                    "group_name": "Import_out",
                    "inputs": [],
                    "save_output": True,
                    "visible_output": True,
                    "node_id": "import-1",
                },
                {
                    "operation_id": "save_session",
                    "name": "Save Session",
                    "settings": {"output_dir": "/tmp/test_output"},
                    "group_name": "Save_out",
                    "inputs": ["import-1"],
                    "save_output": True,
                    "visible_output": True,
                    "node_id": "save-1",
                },
            ],
            "metadata": {"file_index": 0, "total_files": 1, "pipeline_version": "2.0"},
        }

    def test_execute_run_skip_complete(self, simple_run_config, tmp_path):
        """Test skip_complete functionality."""
        from mosaic.pipeline.executor import execute_run

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        simple_run_config["operations"][1]["settings"]["output_dir"] = str(output_dir)

        output_file = output_dir / "test_run.pickle"
        output_file.write_bytes(b"dummy")

        result = execute_run(simple_run_config, skip_complete=True)

        assert result is None


class TestCLI:
    """Tests for the pipeline CLI."""

    @pytest.fixture
    def pipeline_config_data(self, tmp_path):
        """Return the raw pipeline config dict for validation."""
        return {
            "version": "2.0",
            "nodes": [
                {
                    "id": "import-1",
                    "name": "Import Files",
                    "operation_id": "import_batch",
                    "category": "input",
                    "inputs": [],
                    "settings": {
                        "input_files": ["/path/to/file1.star", "/path/to/file2.star"],
                        "file_parameters": {},
                    },
                },
                {
                    "id": "save-1",
                    "name": "Save Session",
                    "operation_id": "save_session",
                    "category": "export",
                    "inputs": ["import-1"],
                    "settings": {"output_dir": str(tmp_path)},
                },
            ],
        }

    @pytest.fixture
    def valid_config(self, tmp_path, pipeline_config_data):
        """Create a valid pipeline config file."""
        config_file = tmp_path / "pipeline.json"
        config_file.write_text(json.dumps(pipeline_config_data))
        return config_file

    def test_cli_config_not_found(self, tmp_path):
        """Test CLI with non-existent config file."""
        from mosaic.scripts.pipeline import main
        import sys

        nonexistent = tmp_path / "nonexistent.json"

        with patch.object(sys, "argv", ["mosaic-pipeline", str(nonexistent)]):
            result = main()

        assert result == 1

    def test_cli_dry_run(self, valid_config, pipeline_config_data, capsys):
        """Test CLI dry-run mode lists all runs from config."""
        from mosaic.scripts.pipeline import main
        import sys

        # Derive expected values from config
        import_node = next(
            n
            for n in pipeline_config_data["nodes"]
            if n["operation_id"] == "import_batch"
        )
        input_files = import_node["settings"]["input_files"]
        expected_run_count = len(input_files)
        expected_run_ids = [strip_filepath(f) for f in input_files]

        with patch.object(
            sys, "argv", ["mosaic-pipeline", str(valid_config), "--dry-run"]
        ):
            result = main()

        captured = capsys.readouterr()
        assert result == 0
        assert f"Total runs: {expected_run_count}" in captured.out
        for run_id in expected_run_ids:
            assert run_id in captured.out

    def test_cli_index_out_of_range(self, valid_config, pipeline_config_data):
        """Test CLI with invalid index returns error."""
        from mosaic.scripts.pipeline import main
        import sys

        # Derive the valid range from config
        import_node = next(
            n
            for n in pipeline_config_data["nodes"]
            if n["operation_id"] == "import_batch"
        )
        num_files = len(import_node["settings"]["input_files"])
        invalid_index = num_files + 10

        with patch.object(
            sys,
            "argv",
            ["mosaic-pipeline", str(valid_config), "--index", str(invalid_index)],
        ):
            result = main()

        assert result == 1

    def test_cli_index_valid(self, valid_config, pipeline_config_data, capsys):
        """Test CLI with valid index selects correct run."""
        from mosaic.scripts.pipeline import main
        import sys

        # Get first file's expected run_id
        import_node = next(
            n
            for n in pipeline_config_data["nodes"]
            if n["operation_id"] == "import_batch"
        )
        first_file = import_node["settings"]["input_files"][0]
        expected_run_id = strip_filepath(first_file)

        with patch.object(
            sys,
            "argv",
            ["mosaic-pipeline", str(valid_config), "--index", "0", "--dry-run"],
        ):
            with patch("mosaic.scripts.pipeline.ProcessPoolExecutor"):
                result = main()

        captured = capsys.readouterr()
        assert expected_run_id in captured.out

    def test_cli_invalid_config(self, tmp_path):
        """Test CLI with invalid JSON config raises JSONDecodeError."""
        from mosaic.scripts.pipeline import main
        import json
        import sys

        config_file = tmp_path / "invalid.json"
        config_file.write_text("not valid json {")

        with patch.object(sys, "argv", ["mosaic-pipeline", str(config_file)]):
            with pytest.raises(json.JSONDecodeError):
                main()

    def test_cli_empty_pipeline(self, tmp_path):
        """Test CLI with empty pipeline."""
        from mosaic.scripts.pipeline import main
        import sys

        config = {"version": "2.0", "nodes": []}
        config_file = tmp_path / "empty.json"
        config_file.write_text(json.dumps(config))

        with patch.object(sys, "argv", ["mosaic-pipeline", str(config_file)]):
            result = main()

        assert result == 1

    @patch("mosaic.scripts.pipeline.execute_run")
    @patch("mosaic.scripts.pipeline.ProcessPoolExecutor")
    def test_cli_execution(
        self, mock_executor_class, mock_execute, valid_config, pipeline_config_data
    ):
        """Test CLI executes correct number of runs from config."""
        from mosaic.scripts.pipeline import main
        import sys
        from concurrent.futures import Future

        # Derive expected run count from config
        import_node = next(
            n
            for n in pipeline_config_data["nodes"]
            if n["operation_id"] == "import_batch"
        )
        input_files = import_node["settings"]["input_files"]
        expected_run_count = len(input_files)

        mock_executor = MagicMock()
        mock_executor_class.return_value.__enter__.return_value = mock_executor

        # Create futures for each expected run
        futures = []
        for f in input_files:
            future = Future()
            future.set_result((strip_filepath(f), None))
            futures.append(future)

        mock_executor.submit.side_effect = futures

        with patch.object(
            sys, "argv", ["mosaic-pipeline", str(valid_config), "--workers", "2"]
        ):
            with patch("mosaic.scripts.pipeline.as_completed", return_value=futures):
                result = main()

        assert result == 0
        assert mock_executor.submit.call_count == expected_run_count

    def test_run_wrapper_success(self):
        """Test run_wrapper with successful execution."""
        from mosaic.scripts.pipeline import run_wrapper

        run_config = {"run_id": "test_run"}

        with patch("mosaic.scripts.pipeline.execute_run") as mock_execute:
            mock_execute.return_value = None
            run_id, error = run_wrapper(run_config, skip_complete=False)

        assert run_id == "test_run"
        assert error is None

    def test_run_wrapper_failure(self):
        """Test run_wrapper with failed execution."""
        from mosaic.scripts.pipeline import run_wrapper

        run_config = {"run_id": "test_run"}

        with patch("mosaic.scripts.pipeline.execute_run") as mock_execute:
            mock_execute.side_effect = RuntimeError("Processing failed")
            run_id, error = run_wrapper(run_config, skip_complete=False)

        assert run_id == "test_run"
        assert "Processing failed" in error


class TestOperationCategories:
    """Tests for operation category definitions."""

    def test_all_operations_have_required_fields(self):
        """Test that all operations have required fields."""
        from mosaic.pipeline.operations import OPERATION_CATEGORIES

        required_fields = ["id", "description", "icon", "has_output"]

        for category_name, category_data in OPERATION_CATEGORIES.items():
            assert "title" in category_data
            assert "operations" in category_data

            for op_name, op_data in category_data["operations"].items():
                for field in required_fields:
                    assert field in op_data, f"{op_name} missing {field}"

    def test_operation_types_valid(self):
        """Test that input/output types are valid."""
        from mosaic.pipeline.operations import OPERATION_CATEGORIES

        valid_types = {None, "point", "model", "any"}

        for category_data in OPERATION_CATEGORIES.values():
            for op_name, op_data in category_data["operations"].items():
                input_type = op_data.get("input_type")
                output_type = op_data.get("output_type")

                assert input_type in valid_types, f"{op_name} has invalid input_type"
                assert output_type in valid_types, f"{op_name} has invalid output_type"

    def test_presets_reference_valid_operations(self):
        """Test that presets reference valid operations."""
        from mosaic.pipeline.operations import OPERATION_CATEGORIES, PIPELINE_PRESETS

        valid_ops = set()
        for category_data in OPERATION_CATEGORIES.values():
            valid_ops.update(category_data["operations"].keys())

        for preset_name, preset_ops in PIPELINE_PRESETS.items():
            for op in preset_ops:
                assert (
                    op["name"] in valid_ops
                ), f"Preset {preset_name} references invalid operation {op['name']}"
