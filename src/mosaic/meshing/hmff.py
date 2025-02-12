import warnings
import textwrap
from os import makedirs
from typing import Dict
from os.path import join

import numpy as np
import matplotlib.pyplot as plt
from tme import Density
from tme.preprocessing import BandPassFilter

from ..formats.writer import write_topology_file
from ..meshing.utils import (
    equilibrate_edges,
    remesh,
    compute_edge_lengths,
    scale,
    compute_scale_factor_lower,
    center_mesh,
)


def equilibrate_fit(geometry, directory: str, parameters: Dict):
    makedirs(directory, exist_ok=True)
    mesh_base = geometry._meta.get("fit").mesh
    edge_length = float(parameters.get("average_edge_length", 40))
    lower_bound = float(parameters.pop("lower_bound", (1 - 0.25) * edge_length))
    upper_bound = float(parameters.pop("upper_bound", (1 + 0.25) * edge_length))
    etarget = float(parameters.get("scaling_lower", 1.0))

    filename = f"{directory}/mesh"
    with open(f"{filename}.txt", mode="w", encoding="utf-8") as ofile:
        ofile.write("file\tscale_factor\toffset\n")

        # Baseline without remeshing
        scale_factor = compute_scale_factor_lower(mesh_base, lower_bound=etarget)
        mesh_scale = scale(mesh_base, scale_factor)
        mesh_data, offset = center_mesh(mesh_scale)
        fname = f"{filename}_base.q"
        write_topology_file(file_path=fname, data=mesh_data)
        ofile.write(f"{fname}\t{scale_factor}\t{offset}\n")
        dist_base = compute_edge_lengths(mesh_scale)

        # Remeshed
        mesh = remesh(mesh_base, edge_length, n_iter=500)
        scale_factor = compute_scale_factor_lower(mesh, lower_bound=etarget)
        mesh_scale = scale(mesh, scale_factor)
        mesh_data, offset = center_mesh(mesh_scale)
        fname = f"{filename}_remeshed.q"
        write_topology_file(file_path=fname, data=mesh_data)
        ofile.write(f"{fname}\t{scale_factor}\t{offset}\n")
        dist_remesh = compute_edge_lengths(mesh_scale)

        # Equilibrated
        ret = equilibrate_edges(
            mesh, lower_bound=lower_bound, upper_bound=upper_bound, **parameters
        )
        scale_factor = compute_scale_factor_lower(ret, lower_bound=etarget)
        mesh_scale = scale(ret, scale_factor)
        mesh_data, offset = center_mesh(mesh_scale)
        fname = f"{filename}_equilibrated.q"
        write_topology_file(file_path=fname, data=mesh_data)
        ofile.write(f"{fname}\t{scale_factor}\t{offset}\n")
        dist_equil = compute_edge_lengths(mesh_scale)

        plt.style.use("seaborn-v0_8")
        plt.figure(figsize=(10, 6))
        plt.hist(
            dist_base,
            bins=30,
            alpha=0.6,
            color="#1f77b4",
            label="Baseline",
            density=True,
        )
        plt.hist(
            dist_remesh,
            bins=30,
            alpha=0.6,
            color="#2ca02c",
            label="Remeshed",
            density=True,
        )
        plt.hist(
            dist_equil,
            bins=30,
            alpha=0.6,
            color="#ff7f0e",
            label="Equilibrated",
            density=True,
        )

        plt.xlabel("Edge Lengths")
        plt.ylabel("Frequency")
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(
            f"{filename}_edgelength_histogram.png", dpi=300, bbox_inches="tight"
        )
        plt.close()


def setup_hmff(ret, directory, parameters):
    makedirs(directory, exist_ok=True)
    mesh_index = ret["file"].index(parameters["mesh"])
    mesh_offset = -float(ret["offset"][mesh_index])
    mesh_scale = ret["scale_factor"][mesh_index]

    data = Density.from_file(parameters["volume_path"])
    if np.allclose(data.sampling_rate, 1):
        print(
            f"Sampling of {parameters['volume_path']} is 1 along all axes."
            "If thats not intended, please adapt the respective files."
        )

    sampling, origin = data.sampling_rate, data.origin
    bpf = BandPassFilter(
        lowpass=parameters["lowpass_cutoff"],
        highpass=parameters["highpass_cutoff"],
        sampling_rate=np.max(sampling),
        use_gaussian=True,
        shape_is_real_fourier=True,
        return_real_fourier=True,
    )
    template_ft = np.fft.rfftn(data.data, s=data.shape)

    mask = bpf(shape=template_ft.shape)["data"]
    np.multiply(template_ft, mask, out=template_ft)
    data = np.fft.irfftn(template_ft, s=data.shape).real

    dpath = join(directory, "density.mrc")
    Density(data, origin=origin, sampling_rate=sampling).to_file(dpath)

    warnings.warn(
        "Setup FreeDTS - Corresponding Citation: "
        "[1] Pezeshkian, W. et al. (2024) Nat. Commun., doi.org/10.1038/s41467-024-44819-w."
    )
    integrator = "MetropolisAlgorithm"
    if parameters["threads"] != 1:
        integrator = "MetropolisAlgorithmOpenMP"
    dts_config = textwrap.dedent(
        f"""
        EnergyMethod             = FreeDTS1.0_MDFF {parameters['volume_path']} {parameters['xi']} 0 \
        {mesh_scale} {mesh_offset} {int(parameters['invert_contrast'])} \
        {parameters['gradient_step_size']}
        Integrator_Type          = MC_Simulation
        VertexPositionIntegrator = {integrator} 1 1 0.05
        AlexanderMove            = {integrator} 1
        InclusionPoseIntegrator  = MetropolisAlgorithm 1 1
        VisualizationFormat      = VTUFileFormat VTU_F 100
        NonbinaryTrajectory      = TSI TrajTSI 1000
        Kappa                    = {parameters['kappa']} 0 0
        Temperature              = 1 0
        Set_Steps                = 1 5000
        Min_Max_Lenghts          = 1 8
        TimeSeriesData_Period    = 100
        VolumeCoupling           = No SecondOrder 0.0 10000 0.7
        GlobalCurvatureCoupling  = No HarmonicPotential 180 0.3
        TotalAreaCoupling        = No HarmonicPotential 1000 0.34
        Box_Centering_F          = 0
    """
    )

    dts_config_path = join(directory, "input.dts")
    with open(dts_config_path, mode="w", encoding="utf-8") as ofile:
        ofile.write(dts_config.strip() + "\n")

    topol_path = join(directory, "topol.top")
    with open(topol_path, mode="w", encoding="utf-8") as ofile:
        ofile.write(f"{parameters['mesh']} 1\n")

    run_config = textwrap.dedent(
        f"""
        #!/bin/bash
        rm -rf VTU_F TrajTSI
        mkdir -p  {directory}/TrajTSI
        ln -s {parameters['mesh']} {directory}/TrajTSI/dts0.tsi

        DTS -in {dts_config_path} \\
            -top {topol_path} \\
            -e {parameters['steps']} \\
            -nt {parameters['threads']} \\
            -seed 76532
    """
    )

    with open(join(directory, "run.sh"), mode="w", encoding="utf-8") as ofile:
        ofile.write(run_config.strip() + "\n")

    return 0
