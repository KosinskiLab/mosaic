"""
Pipeline execution engine for generating and running batch operations.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import pickle
from uuid import uuid4
from os import makedirs
from os.path import join, exists


import numpy as np

from ..container import DataContainer
from ..formats.writer import write_geometries
from ._utils import strip_filepath, topological_sort, flatten
from ..widgets.container_list import TreeStateData, TreeState


__all__ = ["generate_runs", "execute_run"]


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
                "group_name": node["settings"].get("group_name", f"{node['name']}_out"),
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


def _get_op_spec(operation_id):
    from .operation import OPERATION_CATEGORIES

    for category_data in OPERATION_CATEGORIES.values():
        for op_data in category_data["operations"].values():
            if op_data["id"] == operation_id:
                return op_data.get("input_type"), op_data.get("output_type")
    return None, None


def _load_session(filepath: str):
    from ..formats import open_session

    session = open_session(filepath)
    keys = ("_data_tree", "_models_tree")
    for key in keys:
        tree = session.get(key)
        if tree is None:
            session[key] = TreeStateData()
        elif isinstance(tree, TreeState):
            session[key] = tree.to_tree_state_data()

    return session


def _create_session(filepath: str, parameters: dict):
    from ..formats import open_file

    offset = parameters.get("offset", 0)
    scale = parameters.get("scale", 1)
    sampling = parameters.get("sampling_rate", 1)

    shape = None

    model_container = DataContainer()
    cluster_container = DataContainer()
    for data in open_file(filepath):
        scale_new = np.divide(scale, data.sampling)

        data.vertices = np.subtract(data.vertices, offset, out=data.vertices)
        data.vertices = np.multiply(data.vertices, scale_new, out=data.vertices)
        if data.faces is None:
            cluster_container.add(
                points=data.vertices, normals=data.normals, sampling_rate=sampling
            )
        else:
            from ..meshing import to_open3d
            from ..parametrization import TriangularMesh

            model_container.add(
                model=TriangularMesh(to_open3d(data.vertices, data.faces)),
                sampling_rate=sampling,
            )

        data_shape = np.divide(data.shape, data.sampling)

        if shape is None:
            shape = data_shape
        shape = np.maximum(shape, data_shape)

    metadata = {"shape": shape, "sampling_rate": sampling}
    cluster_container.metadata = metadata.copy()

    data_tree = TreeStateData()
    data_tree.root_items = [x.uuid for x in cluster_container.data]

    model_tree = TreeStateData()
    model_tree.root_items = [x.uuid for x in model_container.data]

    return {
        "shape": shape,
        "_data": cluster_container,
        "_models": model_container,
        "_data_tree": data_tree,
        "_models_tree": model_tree,
    }


def execute_run(run_config: dict, skip_complete: bool = False) -> None:
    """
    Execute a single run configuration.

    Parameters
    ----------
    run_config : dict
        Run configuration generated by :py:meth:`generate_runs`.
    skip_complete : bool, optional
        If True (default), skip execution if all output files already exist.


    Returns
    -------
    str
        Path to the output session file
    """
    from ..operations import GeometryOperations

    current_data = ()
    if skip_complete:
        all_exist, found_export = True, False
        for op in run_config["operations"]:
            if op["operation_id"] not in ("save_session", "export_data"):
                continue
            found_export = True

            settings = op["settings"]
            output_dir = settings.get("output_dir", ".")

            if op["operation_id"] == "save_session":
                output_path = join(output_dir, f"{run_config['run_id']}.pickle")
            elif op["operation_id"] == "export_data":
                output_base = join(output_dir, f"{run_config['run_id']}")
                output_path = f"{output_base}.{settings.get('format')}"

            if not exists(output_path):
                all_exist = False
                break

        if all_exist and found_export:
            print(
                f"Skipping run {run_config['run_id']}: all output files already exist"
            )
            return None

    for op in run_config["operations"]:
        op_id = op["operation_id"]
        settings = op["settings"]
        group_name = op["group_name"]

        # This function gets too much special treatmet
        if op_id == "import_batch":
            input_file = run_config["input_file"]
            try:
                session = _load_session(input_file)
            except Exception:
                session = _create_session(input_file, run_config["input_params"])

            relevant_data = "_data"
            try:
                input_type, _ = _get_op_spec(
                    run_config["operations"][1]["operation_id"]
                )

                if input_type == "model":
                    relevant_data = "_model"
            except Exception:
                pass

            current_data = session[relevant_data].data

            # i.e. clear the session we just created
            if not op.get("save_output", True):
                current_data = [
                    session[relevant_data].data.pop()
                    for _ in range(len(session[relevant_data].data))
                ]

                for dtype in ("_data", "_models"):
                    metadata = session[dtype].metadata.copy()
                    session[dtype].clear()
                    session[dtype].metadata = metadata

                for dtype in ("_data_tree", "_models_tree"):
                    uuids = session[dtype].get_all_uuids()
                    _ = [session[dtype].remove_uuid(x) for x in uuids]

            # Nothing more to do here
            continue

        if len(current_data) == 0:
            break

        if (func := getattr(GeometryOperations, op_id)) is not None:
            # Save some memory over the speedup from the list comprehension
            for i in range(len(current_data)):
                current_data[i] = func(current_data[i], **settings)

        elif op_id == "cluster_select":
            lower_threshold = settings.get("lower_threshold", -1)
            upper_threshold = settings.get("upper_threshold", -1)

            drop = set()
            container, tree = session["_data"], session["_data_tree"]
            for x in current_data:
                keep = True
                n_points = x.get_number_of_points()
                if lower_threshold > 0:
                    keep = keep and n_points > lower_threshold
                if upper_threshold > 0:
                    keep = keep and n_points < upper_threshold

                if not keep:
                    drop.add(x.uuid)
                    tree.remove_uuid(x.uuid)
                    container.remove(x)

            # Data is already in session we just filtered it
            # We still need to update available data for next pipeline step though
            current_data = [x for x in current_data if x.uuid not in drop]
            continue
        elif op_id == "save_session":
            output_dir = settings.get("output_dir", ".")
            makedirs(output_dir, exist_ok=True)
            output_path = join(output_dir, f"{run_config['run_id']}.pickle")

            with open(output_path, "wb") as ofile:
                pickle.dump(session, ofile, protocol=pickle.HIGHEST_PROTOCOL)

            # Do not add current_data to session again
            continue

        elif op_id == "export_data":
            output_dir = settings.get("output_dir", ".")
            makedirs(output_dir, exist_ok=True)

            export_parameters = settings.copy()
            output_path = join(output_dir, f"{run_config['run_id']}")

            # Best guess for the correct shape
            container = session["_data"]
            if (shape := container.metadata.get("shape")) is not None:
                sampling = container.metadata.get("sampling_rate", 1)
                shape = np.rint(np.divide(shape, sampling)).astype(int)

                for key, val in zip(("shape_x", "shape_y", "shape_z"), shape):
                    if key not in export_parameters:
                        export_parameters[key] = val

            # file path will be adapted to carry the correct extension
            write_geometries(
                geometries=current_data,
                file_path=output_path,
                export_parameters=export_parameters
                | {"single_file": True, "include_header": True},
            )

            # Do not add current_data to session again
            continue

        # Some methods return lists of geometry objects
        current_data = flatten(current_data)

        if not op.get("save_output", True):
            continue

        # Keep session data in sync
        input_type, output_type = _get_op_spec(op_id)
        container, tree = session["_data"], session["_data_tree"]
        if output_type == "model":
            container, tree = session["_models"], session["_models_tree"]
            _ = [x.change_representation("surface") for x in current_data]

        if not op.get("visible_output", True):
            _ = [x.set_visibility(False) for x in current_data]

        _ = [container.add(x) for x in current_data]

        group_id = str(uuid4())
        tree.root_items.append(group_id)
        tree.group_names[group_id] = group_name
        tree.groups[group_id] = [x.uuid for x in current_data]
