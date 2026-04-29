import shutil
import warnings
import textwrap
from os import makedirs
from typing import Dict
from os.path import join

import numpy as np

from ..parallel import report_progress
from ..formats.writer import write_topology_file
from ..meshing.utils import (
    equilibrate_edges,
    remesh,
    compute_edge_lengths,
    scale,
    compute_scale_factor_lower,
    center_mesh,
)

__all__ = ["equilibrate_fit"]


def equilibrate_fit(geometry, directory: str, parameters: Dict):
    makedirs(directory, exist_ok=True)
    mesh_base = geometry.model.mesh

    mesh_base = mesh_base.remove_duplicated_vertices()
    mesh_base = mesh_base.remove_unreferenced_vertices()
    mesh_base = mesh_base.remove_degenerate_triangles()

    edge_length = float(parameters.get("average_edge_length", 40))
    lower_bound = float(parameters.pop("lower_bound", (1 - 0.25) * edge_length))
    upper_bound = float(parameters.pop("upper_bound", (1 + 0.25) * edge_length))
    etarget = float(parameters.get("scaling_lower", 1.0))

    report_progress(message="Cleanup", current=1, total=4)

    filename = f"{directory}/mesh"
    with open(f"{filename}.txt", mode="w", encoding="utf-8") as ofile:
        ofile.write("file\tscale_factor\toffset\n")

        # Baseline without remeshing
        scale_factor = compute_scale_factor_lower(mesh_base, lower_bound=etarget)
        mesh_scale = scale(mesh_base, scale_factor)
        mesh_data, offset = center_mesh(mesh_scale)
        offset = ",".join([str(-float(x)) for x in offset])

        fname = f"{filename}_base.q"
        write_topology_file(file_path=fname, data=mesh_data)
        ofile.write(f"{fname}\t{scale_factor}\t{offset}\n")
        dist_base = compute_edge_lengths(mesh_scale)

        mesh = remesh(mesh_base, edge_length, n_iter=500)
        scale_factor = compute_scale_factor_lower(mesh, lower_bound=etarget)
        mesh_scale = scale(mesh, scale_factor)
        mesh_data, offset = center_mesh(mesh_scale)
        offset = ",".join([str(-float(x)) for x in offset])

        report_progress(message="Remesh", current=2, total=4)

        fname = f"{filename}_remeshed.q"
        write_topology_file(file_path=fname, data=mesh_data)
        ofile.write(f"{fname}\t{scale_factor}\t{offset}\n")
        dist_remesh = compute_edge_lengths(mesh_scale)

        report_progress(message="Trimem", current=3, total=4)
        ret = equilibrate_edges(
            mesh, lower_bound=lower_bound, upper_bound=upper_bound, **parameters
        )

        scale_factor = compute_scale_factor_lower(ret, lower_bound=etarget)
        mesh_scale = scale(ret, scale_factor)
        mesh_data, offset = center_mesh(mesh_scale)
        offset = ",".join([str(-float(x)) for x in offset])

        fname = f"{filename}_equilibrated.q"
        write_topology_file(file_path=fname, data=mesh_data)
        ofile.write(f"{fname}\t{scale_factor}\t{offset}\n")
        dist_equil = compute_edge_lengths(mesh_scale)
        report_progress(message="Validate", current=4, total=4)

    return dist_base, dist_remesh, dist_equil, filename
