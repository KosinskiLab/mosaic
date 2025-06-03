import textwrap
import warnings
from typing import Dict, List
from os.path import join, basename

import numpy as np

from ..utils import find_closest_points

from ..parallel import run_in_background
from . import remesh, center_mesh, compute_scale_factor_lower, scale
from ..formats.writer import write_topology_file

__all__ = ["mesh_to_cg"]


@run_in_background("Coarse graining")
def mesh_to_cg(
    mesh,
    output_directory: str,
    inclusions: List[Dict],
    edge_length: float = 40.0,
    include_normals: bool = True,
    flip_normals: bool = True,
) -> bool:
    from ..parametrization import TriangularMesh

    mesh = remesh(mesh, edge_length)

    vertex_maps = []
    for protein in inclusions:
        geometry = protein.get("data", None)
        if geometry is None:
            continue

        if include_normals:
            fit = TriangularMesh(mesh)
            kwargs = {
                "points": geometry.points,
                "normals": geometry.normals * -1 if flip_normals else 1,
                "return_indices": True,
            }
            _, vertex_indices = fit.compute_distance(**kwargs)
        else:
            _, vertex_indices = find_closest_points(mesh.vertices, geometry.points, k=1)

        vertex_indices, incl_indices = np.unique(vertex_indices, return_index=True)

        incl_quat = geometry.quaternions[incl_indices]
        vertex_maps.append([vertex_indices, incl_indices, incl_quat])

    n_inclusions = len(vertex_maps)
    for i in range(n_inclusions):
        for k in range(i + 1, n_inclusions):
            overlap = np.intersect1d(vertex_maps[i][0], vertex_maps[k][0])
            if len(overlap) == 0:
                continue

            keep = np.invert(np.isin(vertex_maps[k][0], overlap))
            for ix in range(len(vertex_maps[k])):
                vertex_maps[k][ix] = vertex_maps[k][ix][keep]

            print(
                f"{inclusions[i]['name']} and {inclusions[k]['name']} collide on "
                f"{len(overlap)} vertices. Consider reducing mesh edge length. "
                f"Continuing but dropping collisions from {inclusions[k]['name']}."
            )

    scale_factor = compute_scale_factor_lower(mesh, lower_bound=1.0)
    mesh_scale = scale(mesh, scale_factor)
    data, offset = center_mesh(mesh_scale)
    offset = ",".join([str(-float(x)) for x in offset])

    inclusion_list, inclusion_quat = [], []
    for index, ret in enumerate(vertex_maps):
        inclusion_list.extend([(index + 1, x, 0, 1) for x in ret[0]])
        inclusion_quat.extend([(index + 1, x, y, *z) for x, y, z in zip(*ret)])

    _inclusions = np.zeros((len(inclusion_list), 5))
    _inclusions[:, 0] = np.arange(_inclusions.shape[0])
    _inclusions[:, 1:5] = np.asarray(inclusion_list)
    data["inclusions"] = _inclusions.astype(int)

    mesh_path = join(output_directory, "mesh.tsi")
    write_topology_file(file_path=mesh_path, data=data, tsi_format=True)

    normal_path = join(output_directory, "inclusion_quaternions.csv")
    inclusion_quat = np.asarray(inclusion_quat)
    np.savetxt(
        normal_path,
        inclusion_quat,
        delimiter=",",
        comments="",
        header="inclusion_type,vertex,inclusion,w,x,y,z",
    )

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
            ofile.write(f"{inclusion['name']} {index + 1} 0.01 0 0 0.0\n")
        ofile.write("End Protein\n")

    # Mosaic assumes angstrom for all spatial units
    mesh_to_nm = 0.1 / scale_factor

    plm_path = join(output_directory, "plm.sh")
    with open(plm_path, mode="w", encoding="utf-8") as ofile:
        plm_script = textwrap.dedent(
            f"""
            #!/bin/bash

            TS2CG PLM \\
                -TSfile {basename(mesh_path)} \\
                -bilayerThickness 3.8 \\
                -rescalefactor {mesh_to_nm} {mesh_to_nm} {mesh_to_nm}
        """
        )
        ofile.write(plm_script.lstrip())

    pcg_path = join(output_directory, "pcg.sh")
    with open(pcg_path, mode="w", encoding="utf-8") as ofile:
        pcg_script = textwrap.dedent(
            f"""
            #!/bin/bash

            TS2CG PCG \\
                -str {basename(str_path)} \\
                -Bondlength 0.1 \\
                -LLIB martini3.LIB \\
                -defout system
        """
        )
        ofile.write(pcg_script.lstrip())

    martinize_path = join(output_directory, "martinize.sh")
    with open(martinize_path, mode="w", encoding="utf-8") as ofile:
        martinize_script = "#!/bin/bash\n"

        martinize_execute = ""
        for inclusion in inclusions:
            inclusion_var = f"{inclusion['name']}_structure".upper()

            martinize_script += f"{inclusion_var}=\n"
            martinize_execute += textwrap.dedent(
                f"""
                martinize2 \\
                    -f ${inclusion_var} \\
                    -x {inclusion['name']}.pdb \\
                    -o {inclusion['name']}.top \\
                    -p backbone \\
                    -elastic \\
                    -maxwarn 2 \\
                    -merge all
            """
            )
        martinize_script += martinize_execute
        ofile.write(martinize_script)

    return True
