"""
Utility functions for pipeline module.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from os.path import basename
from re import split as re_split


def strip_filepath(path: str) -> str:
    """
    Extract base filename without extension.

    Parameters
    ----------
    path : str
        Full file path

    Returns
    -------
    str
        Filename without extension
    """
    return basename(path).split(".")[0]


def natural_sort_key(path):
    """
    Natural sorting key for filenames with numbers.

    Sorts files like: file1.txt, file2.txt, file10.txt
    instead of: file1.txt, file10.txt, file2.txt

    Parameters
    ----------
    path : str
        File path

    Returns
    -------
    list
        Sort key with integers properly ordered
    """
    filename = basename(path)
    parts = re_split(r"(\d+)", filename)
    return [int(part) if part.isdigit() else part.lower() for part in parts]


def flatten(nested_list):
    """
    Flatten a nested list of arbitrary depth.

    Parameters
    -----------
    nested_list: list
        A list that may contain nested lists at any level

    Returns:
        A flat list containing all non-list elements
    """
    result = []
    for item in nested_list:
        if isinstance(item, list):
            result.extend(flatten(item))
        else:
            result.append(item)
    return result


def topological_sort(nodes, node_map, start_node_id):
    """
    Perform topological sort starting from a given node.

    Parameters
    ----------
    nodes : list
        List of all nodes in the graph
    node_map : dict
        Mapping from node_id to node
    start_node_id : str
        ID of the starting node (import node)

    Returns
    -------
    list
        Ordered list of node IDs in topological order

    Raises
    ------
    ValueError
        If graph contains cycles
    """
    children, in_degree = {}, {}
    for node in nodes:
        node_id = node["id"]
        children[node_id] = []
        in_degree[node_id] = len(node.get("inputs", []))

    for node in nodes:
        node_id = node["id"]
        for parent_id in node.get("inputs", []):
            if parent_id not in node_map:
                raise ValueError(f"Node {node_id} references unknown input {parent_id}")
            children[parent_id].append(node_id)

    # Kahns algorithm for topological sort
    result, visited, queue = [], set(), [start_node_id]
    while queue:
        current = queue.pop(0)

        if current in visited:
            continue

        visited.add(current)
        result.append(current)

        for child_id in children.get(current, []):
            in_degree[child_id] -= 1
            if in_degree[child_id] == 0:
                queue.append(child_id)

    if len(result) != len(nodes):
        raise ValueError("Pipeline contains cycles or disconnected nodes")
    return result
