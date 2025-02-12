import warnings
from os.path import join
from typing import Dict, List

import numpy as np

from . import remesh, center_mesh, compute_scale_factor_lower, scale
from ..formats.writer import write_topology_file
from ..utils import find_closest_points


def mesh_to_cg(
    mesh,
    output_directory: str,
    inclusions: List[Dict],
    edge_length: float = 40.0,
) -> bool:
    mesh = remesh(mesh, edge_length)

    vertex_maps = []
    for protein in inclusions:
        geometry = protein.get("data", None)
        if geometry is None:
            continue

        distances, indices = find_closest_points(
            np.asarray(mesh.vertices), np.asarray(geometry.points)
        )
        vertex_maps.append(set(indices))

    n_inclusions = len(vertex_maps)
    for i in range(n_inclusions):
        for k in range(i + 1, n_inclusions):
            overlap = vertex_maps[i] & vertex_maps[k]
            if len(overlap) == 0:
                continue

            vertex_maps[k] = vertex_maps[k] - vertex_maps[i]
            print(
                f"{inclusions[i]['name']} and {inclusions[k]['name']} collide on "
                f"{len(overlap)} vertices. Consider reducing mesh edge length. "
                f"Continuing but dropping collisions from {inclusions[k]['name']}."
            )

    scale_factor = compute_scale_factor_lower(mesh, lower_bound=1.0)
    mesh_scale = scale(mesh, scale_factor)
    data, offset = center_mesh(mesh_scale)

    inclusion_list, inclusion_map = [], {}
    for index, vertex_map in enumerate(vertex_maps):
        inclusion_map[index] = inclusions[index]["name"]
        inclusion_list.extend([(index, x, 0, 1) for x in vertex_map])

    _inclusions = np.zeros((len(inclusion_list), 5))
    _inclusions[:, 0] = np.arange(_inclusions.shape[0])
    _inclusions[:, 1:5] = np.asarray(inclusion_list)
    data["inclusions"] = _inclusions.astype(int)

    mesh_path = join(output_directory, "mesh.tsi")
    write_topology_file(file_path=mesh_path, data=data, tsi_format=True)

    warnings.warn(
        "Setup TS2CG - Corresponding Citation: "
        "[1] Pezeshkian, W. et al. (2020) Nat. Commun., doi.org/10.1038/s41467-020-16094-y."
    )
    scale_path = join(output_directory, "scales.txt")
    with open(scale_path, mode="w", encoding="utf-8") as ofile:
        ofile.write(f"{mesh_path}\t{scale_factor}\t{offset}\n")

    str_path = join(output_directory, "input.str")
    with open(str_path, mode="w", encoding="utf-8") as ofile:
        for inclusion in inclusions:
            ofile.write(f"include {inclusion['name']}.gro\n")

        ofile.write("[Lipids List]\n")
        ofile.write("Domain 0\n")
        ofile.write("POPC 1 1 0.64\n")
        ofile.write("End\n")

        ofile.write("[Protein List]\n")
        for index, inclusion in enumerate(inclusions):
            ofile.write(f"{inclusion['name']} {index} 0.01 0 0 -2.5\n")
        ofile.write("End Protein\n")

    plm_path = join(output_directory, "plm.sh")
    with open(plm_path, mode="w", encoding="utf-8") as ofile:
        ofile.write("#!/bin/bash\n")
        ofile.write(
            f"TS2CG PLM -TSfile {mesh_path} -bilayerThickness 3.8  -rescalefactor 4 4 4"
        )

    pcg_path = join(output_directory, "pcg.sh")
    with open(pcg_path, mode="w", encoding="utf-8") as ofile:
        ofile.write("#!/bin/bash\n")
        ofile.write(
            f"TS2CG PCG -str {str_path} -Bondlength 0.2 -LLIB Martini3.LIB -defout system"
        )

    return True
