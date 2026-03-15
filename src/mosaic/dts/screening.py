"""
DTS parameter screening: template generation, screen management, status.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import json
import shutil
import textwrap
import warnings
from pathlib import Path
from os import makedirs
from datetime import datetime
from itertools import product
from typing import Dict, List, Optional

import numpy as np

from ..parallel import report_progress

__all__ = [
    "generate_screen",
    "extend_screen",
    "get_screen_status",
    "run_status",
    "write_launcher_scripts",
]


def run_status(run_dir: Path) -> str:
    """Return ``"done"`` if energy xvg or .res files exist, else ``"pending"``."""
    if (run_dir / "dts-en.xvg").exists():
        return "done"
    return "done" if list(run_dir.glob("*.res")) else "pending"


def _prepare_volume(
    volume_path: str,
    output_dir: str,
    use_filters: bool = False,
    lowpass_cutoff: Optional[float] = None,
    highpass_cutoff: Optional[float] = None,
    plane_norm: Optional[str] = None,
) -> str:
    """Apply bandpass filtering to volume if requested.

    Parameters
    ----------
    volume_path : str
        Path to input volume.
    output_dir : str
        Directory for filtered output.
    use_filters : bool
        Whether to apply filtering.
    lowpass_cutoff : float
        Lowpass filter cutoff.
    highpass_cutoff : float
        Highpass filter cutoff.
    plane_norm : str
        Axis to normalize along (x/y/z or None).

    Returns
    -------
    str
        Path to (possibly filtered) volume.
    """
    if not use_filters:
        return volume_path

    from tme import Density

    try:
        from tme.filters import BandPassFilter
    except ImportError:
        from tme.filters import BandPassReconstructed as BandPassFilter

    data = Density.from_file(volume_path)
    sampling, origin = data.sampling_rate, data.origin

    bpf = BandPassFilter(
        lowpass=lowpass_cutoff,
        highpass=highpass_cutoff,
        sampling_rate=np.max(sampling),
        use_gaussian=True,
    )
    template_ft = np.fft.rfftn(data.data, s=data.shape)
    mask = bpf(shape=data.shape, return_real_fourier=True)["data"]
    template_ft = np.multiply(template_ft, mask, out=template_ft)
    filtered = np.fft.irfftn(template_ft, s=data.shape).real

    axis_map = {"x": 0, "y": 1, "z": 2}
    axis = axis_map.get(plane_norm, None)
    if axis is not None:
        axis = tuple(i for i in range(filtered.ndim) if i != axis)
        filtered = filtered / filtered.max(axis=axis, keepdims=True)

    volume_path = str(Path(output_dir) / "density.mrc")
    filtered = filtered.astype(np.float32)
    Density(filtered, origin=origin, sampling_rate=sampling).to_file(volume_path)
    return volume_path


def _build_dts_template(
    volume_path: Optional[str],
    mesh_scale: str,
    mesh_offset: str,
    hmff_params: Dict,
    sim_params: Dict,
    extra_config: str = "",
    coupling_params: Optional[Dict] = None,
) -> str:
    """Build a DTS config template with screening placeholders.

    Values that should be screened must be pre-formatted as
    ``{{name:range}}`` strings by the caller (dialog).

    Parameters
    ----------
    volume_path : str or None
        Path to volume file.  When *None* the standard Helfrich
        energy method is used instead of HMFF.
    mesh_scale : str
        Scale factor from mesh.txt.
    mesh_offset : str
        Offset from mesh.txt.
    hmff_params : dict
        Physical parameters: kappa, kappa0 and optionally xi,
        invert_contrast for HMFF.
        Screened values are already ``{{name:range}}`` strings.
    sim_params : dict
        Simulation values: steps, threads, temperature.
    extra_config : str
        Raw DTS config lines appended verbatim.  May contain
        ``{{name:range}}`` placeholders for additional screening.
    coupling_params : dict, optional
        Coupling configurations keyed by coupling name.  Each value
        is ``{"mode": str, "values": list}``.

    Returns
    -------
    str
        DTS config template content.
    """
    kappa = hmff_params.get("kappa", 25.0)
    kappa0 = hmff_params.get("kappa0", 0.0)

    steps = sim_params.get("steps", 50000)
    threads = sim_params.get("threads", 1)
    temperature = sim_params.get("temperature", 1.0)
    min_edge = sim_params.get("min_edge", 1.0)
    max_edge = sim_params.get("max_edge", 5.0)
    output_period = sim_params.get("output_period", 1000)

    integrator = "MetropolisAlgorithm"
    try:
        if int(threads) > 1:
            integrator = "MetropolisAlgorithmOpenMP"
    except (ValueError, TypeError):
        pass

    if volume_path is not None:
        xi = hmff_params.get("xi", 5.0)
        invert_contrast = hmff_params.get("invert_contrast", True)
        invert_flag = (
            int(invert_contrast)
            if isinstance(invert_contrast, bool)
            else invert_contrast
        )
        energy_line = (
            f"EnergyMethod             = FreeDTS1.0_MDFF {volume_path} {xi} 0 "
            f"{mesh_scale} {mesh_offset} {invert_flag} 0"
        )
    else:
        energy_line = "EnergyMethod             = FreeDTS1.0"

    coupling_params = coupling_params or {}
    coupling_lines = ""
    for ckey, dts_keyword in [
        ("vol_coupling", "VolumeCoupling"),
        ("curv_coupling", "GlobalCurvatureCoupling"),
        ("area_coupling", "TotalAreaCoupling"),
    ]:
        cfg = coupling_params.get(ckey)
        if not cfg:
            continue
        mode = cfg["mode"]
        values = " ".join(str(v) for v in cfg["values"])
        coupling_lines += f"{dts_keyword:<25s}= {mode} {values}\n"

    dts_config = textwrap.dedent(
        f"""\
        {energy_line}
        Integrator_Type          = MC_Simulation
        VertexPositionIntegrator = {integrator} 1 1 0.05
        AlexanderMove            = {integrator} 1
        InclusionPoseIntegrator  = MetropolisAlgorithm 1 1
        VisualizationFormat      = VTUFileFormat VTU_F {output_period}
        NonbinaryTrajectory      = TSI TrajTSI {output_period}
        Kappa                    = {kappa} {kappa0} {kappa0}
        Temperature              = {temperature} 0
        Set_Steps                = 1 {steps}
        Min_Max_Lenghts          = {min_edge} {max_edge}
        TimeSeriesData_Period    = {output_period}
        Box_Centering_F          = 0
        """
    )

    if coupling_lines:
        dts_config += coupling_lines

    if extra_config and extra_config.strip():
        dts_config += extra_config.strip() + "\n"

    return dts_config


def _expand_screen(
    screen_dir: Path,
    template_content: str,
    param_values: Dict[str, List],
    existing_runs: Optional[List[Dict]] = None,
) -> List[Dict]:
    """Generate new parameter combinations and create run directories.

    Parameters
    ----------
    screen_dir : Path
        Screen output directory.
    template_content : str
        Processed template with ``{param}`` placeholders.
    param_values : dict
        Parameter names mapped to value lists.
    existing_runs : list of dict, optional
        Already existing runs whose combinations are skipped.

    Returns
    -------
    list of dict
        Newly created run info dicts with ``run_id`` and ``parameters``.
    """
    existing_runs = existing_runs or []
    existing_combos = {tuple(sorted(r["parameters"].items())) for r in existing_runs}

    param_names = sorted(param_values.keys())
    all_values = [param_values[name] for name in param_names]

    new_runs = []
    run_counter = len(existing_runs)

    for combo in product(*all_values):
        params = dict(zip(param_names, combo))
        combo_key = tuple(sorted(params.items()))
        if combo_key in existing_combos:
            continue

        run_counter += 1
        width = max(len(str(run_counter)), 4)
        run_id = f"run_{run_counter:0{width}d}"
        run_dir = screen_dir / run_id
        run_dir.mkdir(exist_ok=True)

        content = template_content
        for pname, pval in params.items():
            content = content.replace(f"{{{pname}}}", str(pval))

        (run_dir / "input.dts").write_text(content, encoding="utf-8")
        with open(run_dir / "params.json", "w") as f:
            json.dump(params, f, indent=2)

        new_runs.append({"run_id": run_id, "parameters": params})

    return new_runs


def _write_summary(
    screen_dir: Path,
    template_file: str,
    parameters: Dict[str, List],
    runs: List[Dict],
) -> Dict:
    """Write ``screen_summary.json``.

    Parameters
    ----------
    screen_dir : Path
        Screen output directory.
    template_file : str
        Path to template file (stored in summary for reference).
    parameters : dict
        Parameter names mapped to value lists.
    runs : list of dict
        All runs (existing + new).

    Returns
    -------
    dict
        The written summary.
    """
    summary = {
        "template_file": template_file,
        "generated_at": datetime.now().isoformat(),
        "total_runs": len(runs),
        "parameters": sorted(parameters.keys()),
        "parameter_ranges": {
            name: {
                "values": values,
                "min": min(values),
                "max": max(values),
                "count": len(values),
            }
            for name, values in parameters.items()
        },
        "runs": [{"run_id": r["run_id"], "parameters": r["parameters"]} for r in runs],
    }
    with open(screen_dir / "screen_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    return summary


def _write_run_script(run_dir: Path, params: Dict) -> None:
    """Write a run.sh script for a single screen run.

    Parameters
    ----------
    run_dir : Path
        Directory for this run (must contain input.dts and topol.top).
    params : dict
        Run parameters (may contain 'steps' and 'threads' overrides).
    """
    cmd = "DTS"
    if shutil.which("dts"):
        cmd = "dts"

    topol = run_dir / "topol.top"
    mesh = ""
    if topol.exists():
        mesh = topol.read_text().split()[0]

    input_file = run_dir / "input.dts"
    steps = int(float(params.get("steps", 50000)))
    threads = int(float(params.get("threads", 1)))

    script = textwrap.dedent(
        f"""\
        #!/bin/bash

        cd {run_dir}
        rm -rf VTU_F TrajTSI
        mkdir -p TrajTSI
        ln -sf {mesh} TrajTSI/dts0.tsi

        {cmd} -in {input_file} \\
            -top {topol} \\
            -e {steps} \\
            -nt {threads} \\
            -seed 76532
        """
    )
    with open(run_dir / "run.sh", "w", encoding="utf-8") as f:
        f.write(script)


def _finalize_runs(
    screen_dir: Path,
    summary: Dict,
    topol_path: Optional[Path] = None,
) -> None:
    """Ensure every run has topol.top and run.sh, then write launcher scripts.

    Parameters
    ----------
    screen_dir : Path
        Screen output directory.
    summary : dict
        Screen summary (as returned by :func:`_write_summary`).
    topol_path : Path, optional
        Source topology file to copy into runs that lack one.
        When *None*, falls back to ``<screen_dir>/topol.top``.
    """
    if topol_path is None:
        topol_path = screen_dir / "topol.top"

    for run_info in summary["runs"]:
        run_dir = screen_dir / run_info["run_id"]
        topol_copy = run_dir / "topol.top"
        if not topol_copy.exists() and topol_path.exists():
            shutil.copy2(topol_path, topol_copy)
        _write_run_script(run_dir, run_info["parameters"])

    write_launcher_scripts(screen_dir, summary)


def generate_screen(
    mesh_conf: Optional[Dict],
    output_dir: str,
    mesh: str,
    volume_path: Optional[str] = None,
    hmff_params: Optional[Dict] = None,
    sim_params: Optional[Dict] = None,
    extra_config: str = "",
    coupling_params: Optional[Dict] = None,
    use_filters: bool = False,
    lowpass_cutoff: Optional[float] = None,
    highpass_cutoff: Optional[float] = None,
    plane_norm: Optional[str] = None,
) -> Dict:
    """Generate a DTS parameter screen.

    Parameters
    ----------
    mesh_conf : dict or None
        Mesh configuration with 'file', 'scale_factor', 'offset' keys.
        When *None*, ``mesh`` is treated as a direct file path and
        scale/offset default to ``1`` / ``0,0,0``.
    output_dir : str
        Base directory for screen output.
    mesh : str
        Selected mesh file from mesh_conf, or a direct path to a
        mesh file when *mesh_conf* is *None*.
    volume_path : str, optional
        Path to density volume.  When *None* a standard Helfrich
        energy method is used instead of HMFF.
    hmff_params : dict, optional
        Physical parameters (kappa, kappa0 and optionally xi,
        invert_contrast).  Screened values should already be
        ``{{name:range}}`` strings.
    sim_params : dict, optional
        Simulation parameters (steps, threads, temperature).
    extra_config : str
        Raw DTS config lines appended verbatim.
    coupling_params : dict, optional
        Coupling configurations keyed by coupling name.
    use_filters : bool
        Whether to apply bandpass filtering.
    lowpass_cutoff : float
        Lowpass filter cutoff.
    highpass_cutoff : float
        Highpass filter cutoff.
    plane_norm : str
        Axis normalization.

    Returns
    -------
    dict
        Summary with run count, parameter names, directory paths.
    """
    from pyfreedts.screen import ParameterParser

    hmff_params = hmff_params or {}
    sim_params = sim_params or {}

    warnings.warn(
        "Setup FreeDTS Screen - Citation: "
        "[1] Pezeshkian, W. et al. (2024) Nat. Commun., "
        "doi.org/10.1038/s41467-024-44819-w."
    )

    screen_dir = Path(output_dir)
    makedirs(screen_dir, exist_ok=True)
    report_progress(message="Preparing inputs", current=1, total=4)

    if mesh_conf is not None:
        mesh_index = mesh_conf["file"].index(mesh)
        mesh_offset = mesh_conf["offset"][mesh_index]
        mesh_scale = mesh_conf["scale_factor"][mesh_index]
    else:
        mesh_offset = "0,0,0"
        mesh_scale = "1"

    if volume_path is not None:
        volume_path = _prepare_volume(
            volume_path=volume_path,
            output_dir=output_dir,
            use_filters=use_filters,
            lowpass_cutoff=lowpass_cutoff,
            highpass_cutoff=highpass_cutoff,
            plane_norm=plane_norm,
        )

    report_progress(message="Building template", current=2, total=4)

    raw_template = _build_dts_template(
        volume_path=volume_path,
        mesh_scale=mesh_scale,
        mesh_offset=mesh_offset,
        hmff_params=hmff_params,
        sim_params=sim_params,
        extra_config=extra_config,
        coupling_params=coupling_params,
    )
    template_content, parameters = ParameterParser.parse_template(raw_template)

    template_path = screen_dir / "template.dts"
    template_path.write_text(template_content, encoding="utf-8")

    topol_path = screen_dir / "topol.top"
    topol_path.write_text(f"{mesh} 1\n", encoding="utf-8")

    report_progress(message="Generating runs", current=3, total=4)

    existing_runs = []
    merged_parameters = dict(parameters)
    summary_path = screen_dir / "screen_summary.json"
    if summary_path.exists():
        with open(summary_path, "r") as f:
            old_summary = json.load(f)
        existing_runs = old_summary["runs"]
        for name, info in old_summary.get("parameter_ranges", {}).items():
            old_vals = set(info.get("values", []))
            new_vals = set(merged_parameters.get(name, []))
            merged_parameters[name] = sorted(old_vals | new_vals)

    new_runs = _expand_screen(screen_dir, template_content, parameters, existing_runs)
    all_runs = existing_runs + new_runs
    summary = _write_summary(
        screen_dir, str(template_path), merged_parameters, all_runs
    )
    _finalize_runs(screen_dir, summary, topol_path)

    report_progress(message="Done", current=4, total=4)

    return {
        "total_runs": summary["total_runs"],
        "new_runs": len(new_runs),
        "parameter_names": summary["parameters"],
        "output_dir": output_dir,
        "summary_path": str(screen_dir / "screen_summary.json"),
    }


def write_launcher_scripts(output_dir: Path, summary: Dict) -> None:
    """Write local and SLURM launcher scripts for a screen.

    Generates ``run_all.sh`` for local execution (sequential, or via
    GNU parallel when available) and ``submit_slurm.sh`` for HPC
    submission as a SLURM array job.  Run scripts are discovered at
    runtime via ``run_*/run.sh`` globs so the launchers stay compact.

    Parameters
    ----------
    output_dir : Path
        Screen output directory containing per-run subdirectories.
    summary : dict
        Screen summary with ``runs`` and ``total_runs`` keys.
    """
    local_script = textwrap.dedent(
        """\
        #!/bin/bash
        set -euo pipefail

        SCREEN_DIR="$(cd "$(dirname "$0")" && pwd)"
        mapfile -t RUNS < <(find "$SCREEN_DIR" -path '*/run_*/run.sh' | sort)

        if command -v parallel &>/dev/null; then
            printf '%s\\n' "${RUNS[@]}" | parallel --bar bash {}
        else
            for script in "${RUNS[@]}"; do
                echo "Running $script"
                bash "$script"
            done
        fi
        """
    )
    local_path = output_dir / "run_all.sh"
    local_path.write_text(local_script, encoding="utf-8")
    local_path.chmod(0o755)

    n_runs = len(summary["runs"])
    if n_runs == 0:
        return
    slurm_script = textwrap.dedent(
        f"""\
        #!/bin/bash
        #SBATCH --job-name=dts_screen
        #SBATCH --array=0-{n_runs - 1}
        #SBATCH --ntasks=1
        #SBATCH --cpus-per-task=1
        #SBATCH --output=slurm_%A_%a.log

        SCREEN_DIR="$(cd "$(dirname "$0")" && pwd)"
        mapfile -t RUNS < <(find "$SCREEN_DIR" -path '*/run_*/run.sh' | sort)

        bash "${{RUNS[$SLURM_ARRAY_TASK_ID]}}"
        """
    )
    slurm_path = output_dir / "submit_slurm.sh"
    slurm_path.write_text(slurm_script, encoding="utf-8")
    slurm_path.chmod(0o755)


def extend_screen(screen_dir: str, new_screen_params: Dict[str, str]) -> Dict:
    """Extend an existing screen with new parameter combinations.

    Parameters
    ----------
    screen_dir : str
        Existing screen directory.
    new_screen_params : dict
        New parameter ranges to add.

    Returns
    -------
    dict
        Updated summary.
    """
    from pyfreedts.screen import ParameterParser

    screen_path = Path(screen_dir)

    with open(screen_path / "screen_summary.json", "r") as f:
        summary = json.load(f)

    template_content = (screen_path / "template.dts").read_text()

    new_values = {}
    for name, range_str in new_screen_params.items():
        _, parsed = ParameterParser.parse_template(f"{{{{placeholder:{range_str}}}}}")
        new_values[name] = parsed.get("placeholder", [])

    new_runs = _expand_screen(
        screen_path, template_content, new_values, summary["runs"]
    )

    all_runs = summary["runs"] + new_runs
    all_parameters = {}
    for name in set(
        list(summary.get("parameter_ranges", {}).keys()) + list(new_values.keys())
    ):
        existing_vals = (
            summary.get("parameter_ranges", {}).get(name, {}).get("values", [])
        )
        merged = sorted(set(existing_vals + new_values.get(name, [])))
        all_parameters[name] = merged

    updated_summary = _write_summary(
        screen_path,
        summary.get("template_file", ""),
        all_parameters,
        all_runs,
    )
    _finalize_runs(screen_path, updated_summary)

    return {
        "new_runs": len(new_runs),
        "total_runs": len(all_runs),
        "parameter_names": sorted(all_parameters.keys()),
    }


def get_screen_status(screen_dir: str) -> List[Dict]:
    """Check status of all runs in a screen directory.

    Parameters
    ----------
    screen_dir : str
        Screen directory path.

    Returns
    -------
    list of dict
        Each dict has run_id, parameters, status.
    """
    summary_path = Path(screen_dir) / "screen_summary.json"
    if not summary_path.exists():
        return []

    with open(summary_path, "r") as f:
        summary = json.load(f)

    results = []
    for run_info in summary["runs"]:
        run_dir = Path(screen_dir) / run_info["run_id"]
        results.append(
            {
                "run_id": run_info["run_id"],
                "parameters": run_info["parameters"],
                "status": run_status(run_dir),
            }
        )

    return results
