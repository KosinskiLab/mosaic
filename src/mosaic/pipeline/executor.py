"""
REPL-based pipeline execution engine.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import os
import shlex
from typing import List, Tuple

from ..commands.parser import format_value, format_kwargs
from ..registry import MethodRegistry
from ..parallel import report_progress
from ._utils import topological_sort, strip_filepath


__all__ = ["compile_run", "execute_run", "generate_runs"]


def _known_params(op_name: str) -> set:
    """Return the set of known parameter names for *op_name*.

    Collects names from common params and every registered method so that
    settings from older configs with renamed/removed params are silently
    dropped instead of causing a crash at execution time.
    """
    op = MethodRegistry.get(op_name)
    if op is None:
        return set()
    names = {p.name for p in op.common_params}
    for m in op.methods:
        for p in m.params:
            names.add(p.name)
    return names


def generate_runs(pipeline_config):
    """
    Generate individual run configurations from a pipeline graph.
    For each input file, creates a linear sequence of operations to execute by
    performing topological sort on the dependency graph.

    Parameters
    ----------
    pipeline_config : dict
        Pipeline configuration containing nodes and metadata

    Returns
    -------
    list
        List of run configurations, where each run is a dict containing:
        - run_id: Unique identifier for this run
        - input_file: Path to input file
        - input_params: Import parameters for this file
        - operations: Ordered list of operations to execute

    Raises
    ------
    ValueError
        If pipeline has cycles or missing node references
    """
    nodes = pipeline_config.get("nodes", [])
    if not nodes:
        return []

    node_map = {node["id"]: node for node in nodes}
    root_nodes = [node for node in nodes if not node.get("inputs", [])]
    if not root_nodes:
        raise ValueError("Pipeline has no root nodes - possible cycle detected")

    import_nodes = [
        node for node in root_nodes if node.get("operation_id") == "import_batch"
    ]

    if not import_nodes:
        raise ValueError("Pipeline must start with an Import Files operation")

    if len(import_nodes) > 1:
        raise ValueError("Pipeline currently supports only one Import Files operation")

    import_node = import_nodes[0]
    input_files = import_node["settings"].get("input_files", [])
    file_parameters = import_node["settings"].get("file_parameters", {})

    if not input_files:
        raise ValueError("No input files specified in Import operation")

    runs = []
    operation_sequence = topological_sort(nodes, node_map, import_node["id"])
    for file_idx, input_file in enumerate(input_files):
        run_id = strip_filepath(input_file)

        operations = []
        for node_id in operation_sequence:
            node = node_map[node_id]

            operation = {
                "operation_id": node["operation_id"],
                "name": node["name"],
                "settings": node["settings"].copy(),
                "group_name": node.get(
                    "group_name",
                    node["settings"].get("group_name", f"{node['name']}_out"),
                ),
                "inputs": node.get("inputs", []),
                "save_output": node.get("save_output", True),
                "visible_output": node.get("visible_output", True),
                "node_id": node["id"],
            }

            if node["operation_id"] == "import_batch":
                operation["settings"]["input_file"] = input_file
                operation["settings"]["file_parameters"] = file_parameters.get(
                    input_file, {}
                )

            operations.append(operation)

        run_config = {
            "run_id": run_id,
            "input_file": input_file,
            "input_params": file_parameters.get(input_file, {}),
            "operations": operations,
            "metadata": {
                "file_index": file_idx,
                "total_files": len(input_files),
                "pipeline_version": pipeline_config.get("version", "2.0"),
            },
        }
        runs.append(run_config)

    return runs


def compile_run(run_config: dict) -> List[Tuple[str, str]]:
    """Translate a pipeline run config into ``(op_id, script_line)`` pairs.

    Parameters
    ----------
    run_config : dict
        Single run configuration from :func:`generate_runs`.

    Returns
    -------
    list of (str, str)
        Each element is ``(operation_id, script_line)`` where
        *script_line* is a valid Mosaic REPL command.
    """
    steps: List[Tuple[str, str]] = []

    for op in run_config["operations"]:
        op_id = op["operation_id"]
        settings = op["settings"]
        save_output = op.get("save_output", True)
        visible_output = op.get("visible_output", True)
        group_name = op.get("group_name", "")

        if op_id == "import_batch":
            input_file = settings.get("input_file", run_config["input_file"])
            params = run_config.get("input_params", {})
            if input_file.endswith(".pickle"):
                parts = [f"open {shlex.quote(input_file)}"]
            else:
                parts = [f"open {shlex.quote(input_file)}"]
                for key in ("offset", "scale", "sampling_rate"):
                    if key in params and params[key] not in (0, 1, None):
                        parts.append(f"{key}={format_value(params[key])}")

            if not save_output:
                parts.append("persist=false")
            steps.append((op_id, " ".join(parts)))
            continue

        if op_id == "save_session":
            output_dir = settings.get("output_dir", ".")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"{run_config['run_id']}.pickle")
            steps.append((op_id, f"save {shlex.quote(output_path)}"))
            continue

        if op_id == "export_data":
            output_dir = settings.get("output_dir", ".")
            os.makedirs(output_dir, exist_ok=True)
            fmt = settings.get("format", "star")
            output_path = os.path.join(output_dir, f"{run_config['run_id']}.{fmt}")
            save_kwargs = {
                k: v
                for k, v in settings.items()
                if k not in ("output_dir", "method", "format")
            }
            line = f"save @last {shlex.quote(output_path)} format={fmt}"
            if save_kwargs:
                line += f" {format_kwargs(save_kwargs)}"
            steps.append((op_id, line))
            continue

        if op_id == "mesh_analysis":
            method = settings.get("method", "")
            reg_op = MethodRegistry.get("mesh_analysis")
            m = reg_op.get_method(method) if reg_op else None
            if m is None:
                continue
            property_name = m.internal_name

            measure_kwargs = {
                k: v for k, v in settings.items() if k not in ("method", "output_dir")
            }
            output_dir = settings.get("output_dir", "").strip()
            output_part = ""
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                output_name = method.lower().replace(" ", "_")
                output_path = os.path.join(
                    output_dir, f"{run_config['run_id']}_{output_name}.csv"
                )
                output_part = f" output={shlex.quote(output_path)}"

            line = f"measure {property_name} @last{output_part}"
            if measure_kwargs:
                line += f" {format_kwargs(measure_kwargs)}"
            steps.append((op_id, line))
            continue

        if op_id == "cluster_select":
            parts = ["filter @last property=n_points"]
            lower = settings.get("lower_threshold", -1)
            upper = settings.get("upper_threshold", -1)
            if lower >= 0:
                parts.append(f"lower={lower}")
            if upper >= 0 and upper > lower:
                parts.append(f"upper={upper}")
            steps.append((op_id, " ".join(parts)))
            continue

        method = settings.get("method")
        if method:
            method = MethodRegistry.resolve_method(op_id, method)
        known = _known_params(op_id)
        filtered = {
            k: v
            for k, v in settings.items()
            if k not in ("group_name", "method") and (not known or k in known)
        }
        kwargs = format_kwargs(filtered)

        parts = [op_id]
        if method:
            parts.append(method)
        parts.append("@last")
        if kwargs:
            parts.append(kwargs)
        if not save_output:
            parts.append("persist=false")
        steps.append((op_id, " ".join(parts)))

        if save_output and not visible_output:
            steps.append((op_id, "visibility @last visible=false"))
        if save_output and group_name:
            steps.append((op_id, f"group @last {shlex.quote(group_name)}"))

    return steps


def execute_run(
    run_config: dict, skip_complete: bool = False, verbose: bool = False
) -> None:
    """Execute a pipeline run by compiling to script lines and running via REPL.

    Parameters
    ----------
    run_config : dict
        Run configuration generated by :func:`generate_runs`.
    skip_complete : bool, optional
        If True, skip execution when all output files already exist.
    """
    if skip_complete:
        all_exist, found_export = True, False
        for op in run_config["operations"]:
            if op["operation_id"] not in ("save_session", "export_data"):
                continue
            found_export = True

            settings = op["settings"]
            output_dir = settings.get("output_dir", ".")
            output_path = None

            if op["operation_id"] == "save_session":
                output_path = os.path.join(output_dir, f"{run_config['run_id']}.pickle")
            elif op["operation_id"] == "export_data":
                output_base = os.path.join(output_dir, run_config["run_id"])
                output_path = f"{output_base}.{settings.get('format', 'star')}"

            if output_path is None or not os.path.exists(output_path):
                all_exist = False
                break

        if all_exist and found_export:
            print(
                f"Skipping run {run_config['run_id']}: "
                "all output files already exist"
            )
            return None

    from ..commands.repl import MosaicREPL
    from ..commands.session import Session

    steps = compile_run(run_config)
    repl = MosaicREPL(session=Session(quiet=True))
    for idx, (op_id, line) in enumerate(steps):
        if verbose:
            report_progress(message=op_id, current=idx, total=len(steps))
        repl.execute(line)
