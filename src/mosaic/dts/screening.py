"""
DTS parameter screening: template generation, screen management, status.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import re
import json
import shutil
import textwrap
import warnings
from pathlib import Path
from os import makedirs
from datetime import datetime
from itertools import product
from typing import Dict, List, Optional, Union

import numpy as np

from ..parallel import report_progress
from ._utils import _ParameterParser

__all__ = ["generate_screen", "extend_screen", "get_screen_status"]


_SENTINEL = ".done"


def run_status(run_dir: Path) -> str:
    """Return ``"available"`` if trajectory output exists, else ``"pending"``."""
    run_dir = Path(run_dir)
    if (run_dir / "dts-en.xvg").exists():
        return "available"
    if (run_dir / "TrajTSI").is_dir() and any((run_dir / "TrajTSI").iterdir()):
        return "available"
    if (run_dir / "VTU_F").is_dir() and any((run_dir / "VTU_F").iterdir()):
        return "available"
    if list(run_dir.glob("*.res")):
        return "available"
    return "pending"


def _filter_single_volume(
    volume_path: str,
    output_path: str,
    lowpass_cutoff: Optional[float],
    highpass_cutoff: Optional[float],
    plane_norm: Optional[str],
) -> str:
    """Apply bandpass filtering to a single volume.

    Parameters
    ----------
    volume_path : str
        Path to input volume.
    output_path : str
        Path for filtered output file.
    lowpass_cutoff : float, optional
        Lowpass filter cutoff.
    highpass_cutoff : float, optional
        Highpass filter cutoff.
    plane_norm : str, optional
        Axis to normalize along (x/y/z or None).

    Returns
    -------
    str
        Path to filtered volume.
    """
    from tme import Density

    try:
        from tme.filters import BandPassFilter
    except ImportError:
        from tme.filters import BandPassReconstructed as BandPassFilter

    data = Density.from_file(volume_path)
    sampling, origin = data.sampling_rate, data.origin

    if lowpass_cutoff is not None and lowpass_cutoff < 0:
        lowpass_cutoff = None
    if highpass_cutoff is not None and highpass_cutoff < 0:
        highpass_cutoff = None

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

    filtered = filtered.astype(np.float32)
    Density(filtered, origin=origin, sampling_rate=sampling).to_file(output_path)
    return output_path


def _prepare_volume(
    volume_path: Union[str, List[str]],
    output_dir: str,
    use_filters: bool = False,
    lowpass_cutoff: Optional[float] = None,
    highpass_cutoff: Optional[float] = None,
    plane_norm: Optional[str] = None,
) -> List[str]:
    """Apply bandpass filtering to volume(s) if requested.

    Parameters
    ----------
    volume_path : str or list of str
        Path(s) to input volume(s).
    output_dir : str
        Directory for filtered output.
    use_filters : bool
        Whether to apply filtering.
    lowpass_cutoff : float, optional
        Lowpass filter cutoff.
    highpass_cutoff : float, optional
        Highpass filter cutoff.
    plane_norm : str, optional
        Axis to normalize along (x/y/z or None).

    Returns
    -------
    list of str
        Path(s) to (possibly filtered) volume(s).
    """
    if not use_filters:
        return volume_path

    if isinstance(volume_path, str):
        volume_path = [volume_path]

    results = []
    for i, vpath in enumerate(volume_path):
        out = str(Path(output_dir) / f"density_{i}.mrc")
        results.append(
            _filter_single_volume(
                vpath, out, lowpass_cutoff, highpass_cutoff, plane_norm
            )
        )
    return results


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
    temperature = sim_params.get("temperature", 1.0)
    min_edge = sim_params.get("min_edge", 1.0)
    max_edge = sim_params.get("max_edge", 5.0)
    output_period = sim_params.get("output_period", 1000)

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
        VertexPositionIntegrator = MetropolisAlgorithmOpenMP 1 1 0.05
        AlexanderMove            = MetropolisAlgorithmOpenMP 1
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
    existing_combo_runs = {
        tuple(sorted(r["parameters"].items())): r["run_id"] for r in existing_runs
    }

    param_names = sorted(param_values.keys())
    all_values = [param_values[name] for name in param_names]

    new_runs = []
    run_counter = len(existing_runs)

    for combo in product(*all_values):
        params = dict(zip(param_names, combo))
        combo_key = tuple(sorted(params.items()))
        existing_id = existing_combo_runs.get(combo_key)
        if existing_id and (screen_dir / existing_id).is_dir():
            continue

        run_counter += 1
        run_id = f"run_{run_counter}"
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
    param_ranges = {}
    for name, values in parameters.items():
        entry = {"values": values, "count": len(values)}
        try:
            entry["min"] = min(values)
            entry["max"] = max(values)
        except TypeError:
            entry["min"] = None
            entry["max"] = None
        param_ranges[name] = entry

    summary = {
        "template_file": template_file,
        "generated_at": datetime.now().isoformat(),
        "total_runs": len(runs),
        "parameters": sorted(parameters.keys()),
        "parameter_ranges": param_ranges,
        "runs": [{"run_id": r["run_id"], "parameters": r["parameters"]} for r in runs],
    }
    with open(screen_dir / "screen_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    return summary


def _finalize_runs(
    screen_dir: Path,
    summary: Dict,
    mesh_name: str = "",
) -> None:
    """Write run.sh for every run, then write launcher scripts.

    Parameters
    ----------
    screen_dir : Path
        Screen output directory.
    summary : dict
        Screen summary (as returned by :func:`_write_summary`).
    mesh_name : str
        Filename of the mesh in the screen root directory.  When empty,
        the name is inferred from ``<screen_dir>/topol.top`` if present.
    """
    if not mesh_name:
        topol_path = screen_dir / "topol.top"
        if topol_path.exists():
            first_word = topol_path.read_text().split()[0]
            if (screen_dir / first_word).is_file():
                mesh_name = first_word

    for run_info in summary["runs"]:
        run_dir = screen_dir / run_info["run_id"]
        run_dir.mkdir(parents=True, exist_ok=True)
        _write_run_script(run_dir, run_info["parameters"], mesh_name=mesh_name)

    _write_launcher_scripts(screen_dir, summary)


def _write_run_script(run_dir: Path, params: Dict, mesh_name: str = "") -> None:
    """Write a run.sh script for a single screen run.

    Parameters
    ----------
    run_dir : Path
        Directory for this run (must contain input.dts).
    params : dict
        Run parameters (may contain 'steps' and 'threads' overrides).
    mesh_name : str
        Filename of the mesh in the screen root directory.
    """
    threads = int(float(params.get("threads", 1)))
    default_cmd = "dts" if shutil.which("dts") else "DTS"

    symlink_line = ""
    if mesh_name:
        symlink_line = f'ln -sf "$(pwd)/../{mesh_name}" TrajTSI/dts0.tsi'

    script = textwrap.dedent(
        f"""\
        #!/bin/bash

        cd "$(dirname "$0")"
        rm -f {_SENTINEL}
        rm -rf VTU_F TrajTSI
        mkdir -p TrajTSI
        {symlink_line}

        DTS_CMD="${{DTS_CMD:-{default_cmd}}}"
        DTS_NT="${{DTS_NT:-{threads}}}"
        $DTS_CMD -in input.dts \\
            -top ../topol.top \\
            -nt $DTS_NT \\
            -seed 76532 \\
            && touch {_SENTINEL}
        """
    )
    with open(run_dir / "run.sh", "w", encoding="utf-8") as f:
        f.write(script)


def _pending_runs_preamble(output_dir: Path) -> str:
    """Shared bash preamble that builds RUNS array from pending run scripts."""
    return textwrap.dedent(
        f"""\
        SCREEN_DIR="{output_dir}"
        mapfile -t ALL < <(find "$SCREEN_DIR" -path '*/run_*/run.sh' | sort)

        RUNS=()
        for script in "${{ALL[@]}}"; do
            [[ -f "$(dirname "$script")/{_SENTINEL}" ]] && continue
            RUNS+=("$script")
        done
    """
    )


def _write_launcher_scripts(output_dir: Path, summary: Dict) -> None:
    """Write local and SLURM launcher scripts for a screen."""
    preamble = _pending_runs_preamble(output_dir)

    local_script = (
        "#!/bin/bash\nset -euo pipefail\n\n"
        "export DTS_NT=${DTS_NT:-1}\n\n"
        + preamble
        + textwrap.dedent(
            """\
        echo "${#RUNS[@]}/${#ALL[@]} runs pending"
        [[ ${#RUNS[@]} -eq 0 ]] && exit 0

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
    )
    local_path = output_dir / "submit_local.sh"
    local_path.write_text(local_script, encoding="utf-8")
    local_path.chmod(0o755)

    n_runs = len(summary["runs"])
    if n_runs == 0:
        return

    slurm_script = (
        textwrap.dedent(
            f"""\
        #!/bin/bash
        #SBATCH --ntasks=1
        #SBATCH --cpus-per-task=1
        #SBATCH --mem=6G
        #SBATCH --time=24:00:00
        #SBATCH --output=slurm_%A_%a.log

        #
        # DTS screen launcher — {n_runs} runs.
        # Set DTS_NT before calling sbatch to control thread count, e.g.
        # DTS_NT=8 sbatch submit_slurm.sh
        #

        export DTS_NT="${{DTS_NT:-1}}"
        MAX_ARRAY=1000

        """
        )
        + preamble
        + textwrap.dedent(
            """\
        N=${#RUNS[@]}

        if [[ -n "${SLURM_ARRAY_TASK_ID:-}" ]]; then
            OFFSET=${SLURM_OFFSET:-0}
            exec bash "${RUNS[$((SLURM_ARRAY_TASK_ID + OFFSET))]}"
        fi

        echo "$N/${#ALL[@]} runs pending"
        [[ $N -eq 0 ]] && exit 0

        for (( START=0; START<N; START+=MAX_ARRAY )); do
            END=$(( START + MAX_ARRAY - 1 ))
            if (( END >= N )); then END=$(( N - 1 )); fi

            ARGS=(--parsable --job-name=dts_$((START / MAX_ARRAY))
                  --cpus-per-task="$DTS_NT"
                  --array=0-$((END - START))
                  --export=ALL,SLURM_OFFSET=$START)
            [[ -n "${JOB:-}" ]] && ARGS+=(--dependency=afterany:$JOB)

            JOB=$(sbatch "${ARGS[@]}" "$0")
            echo "Submitted chunk $((START / MAX_ARRAY)): $JOB (runs $START-$END)"
        done
        """
        )
    )
    slurm_path = output_dir / "submit_slurm.sh"
    slurm_path.write_text(slurm_script, encoding="utf-8")
    slurm_path.chmod(0o755)


def _setup_screen_dir(screen_dir, mesh):
    """Copy mesh into screen directory, return mesh filename."""
    mesh_src = Path(mesh).resolve()
    if not mesh_src.exists():
        raise FileNotFoundError(f"Mesh file not found: {mesh_src}")
    screen_mesh = screen_dir / mesh_src.name
    if not screen_mesh.exists():
        shutil.copy2(mesh_src, screen_mesh)
    return mesh_src.name


def _merge_parameters(old_summary, new_parameters):
    """Merge existing parameter ranges from a summary with new values."""
    merged = dict(new_parameters)
    for name, info in old_summary.get("parameter_ranges", {}).items():
        old_vals = set(info.get("values", []))
        new_vals = set(merged.get(name, []))
        merged[name] = sorted(old_vals | new_vals)
    return merged


def _natural_sort_key(s: str):
    return [int(c) if c.isdigit() else c for c in re.split(r"(\d+)", s)]


def _is_run_directory(path: Path) -> bool:
    """Return True if *path* looks like a DTS run directory."""
    if not path.is_dir():
        return False
    return run_status(path) == "available" or (path / "input.dts").exists()


def _run_info(run_dir: Path) -> Dict:
    """Build a status dict for a single run directory."""
    params = {}
    params_file = run_dir / "params.json"
    if params_file.exists():
        with open(params_file, "r") as f:
            params = json.load(f)

    return {
        "run_id": run_dir.name,
        "parameters": params,
        "status": run_status(run_dir),
    }


def generate_screen(
    output_dir: str,
    mesh: str,
    dts_content: str,
) -> Dict:
    """Generate a DTS parameter screen from a DTS config template.

    Parameters
    ----------
    output_dir : str
        Base directory for screen output.
    mesh : str
        Path to the mesh file.
    dts_content : str
        DTS config template content.  May contain ``{{name:range}}``
        screening placeholders and ``;@filter`` comment directives.
        Volume path(s) are extracted from the content automatically.

    Returns
    -------
    dict
        Summary with run count, parameter names, directory paths.

    Notes
    -----
    The *dts_content* is the canonical input: a DTS config string that
    may contain ``{{name:range}}`` screening placeholders and
    ``;@filter`` directives for volume filtering.
    """
    from ._utils import parse_filter_directives, extract_volume_path

    volume_path = extract_volume_path(dts_content)
    filter_params = parse_filter_directives(dts_content)

    warnings.warn(
        "Setup FreeDTS Screen - Citation: "
        "[1] Pezeshkian, W. et al. (2024) Nat. Commun., "
        "doi.org/10.1038/s41467-024-44819-w."
    )

    screen_dir = Path(output_dir).resolve()
    makedirs(screen_dir, exist_ok=True)
    report_progress(message="Preparing inputs", current=1, total=4)

    mesh_name = _setup_screen_dir(screen_dir, mesh)
    if volume_path is not None and filter_params:
        volume_path = _prepare_volume(
            volume_path=volume_path,
            output_dir=output_dir,
            use_filters=True,
            lowpass_cutoff=filter_params.get("lowpass_cutoff"),
            highpass_cutoff=filter_params.get("highpass_cutoff"),
            plane_norm=filter_params.get("plane_norm"),
        )

    report_progress(message="Building template", current=2, total=4)

    raw_template = "\n".join(
        l for l in dts_content.splitlines() if not l.strip().startswith(";@filter")
    )
    template_content, parameters = _ParameterParser.parse_template(raw_template)

    if isinstance(volume_path, list) and len(volume_path) >= 1:
        original = extract_volume_path(dts_content)
        if isinstance(original, str):
            template_content = template_content.replace(original, volume_path[0])
        else:
            parameters["volume_path"] = volume_path

    (screen_dir / "screen.dts").write_text(dts_content, encoding="utf-8")
    (screen_dir / "topol.top").write_text(
        f"{screen_dir / mesh_name} 1\n", encoding="utf-8"
    )

    report_progress(message="Generating runs", current=3, total=4)

    existing_runs = []
    merged_parameters = dict(parameters)
    summary_path = screen_dir / "screen_summary.json"
    if summary_path.exists():
        with open(summary_path, "r") as f:
            old_summary = json.load(f)
        existing_runs = old_summary["runs"]
        merged_parameters = _merge_parameters(old_summary, parameters)

    new_runs = _expand_screen(screen_dir, template_content, parameters, existing_runs)
    all_runs = existing_runs + new_runs
    summary = _write_summary(screen_dir, "screen.dts", merged_parameters, all_runs)
    _finalize_runs(screen_dir, summary, mesh_name=mesh_name)

    report_progress(message="Done", current=4, total=4)

    return {
        "total_runs": summary["total_runs"],
        "new_runs": len(new_runs),
        "parameter_names": summary["parameters"],
        "output_dir": output_dir,
        "summary_path": str(screen_dir / "screen_summary.json"),
    }


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
    screen_path = Path(screen_dir)

    with open(screen_path / "screen_summary.json", "r") as f:
        summary = json.load(f)

    dts_content = (screen_path / "screen.dts").read_text()
    raw_template = "\n".join(
        l for l in dts_content.splitlines() if not l.strip().startswith(";@filter")
    )
    template_content, _ = _ParameterParser.parse_template(raw_template)

    new_values = {}
    for name, range_str in new_screen_params.items():
        _, parsed = _ParameterParser.parse_template(f"{{{{placeholder:{range_str}}}}}")
        new_values[name] = parsed.get("placeholder", [])

    new_runs = _expand_screen(
        screen_path, template_content, new_values, summary["runs"]
    )

    all_runs = summary["runs"] + new_runs
    all_parameters = _merge_parameters(summary, new_values)

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
    """Check status of all runs in a screen or trajectory directory.

    Parameters
    ----------
    screen_dir : str
        Path to a screen directory, trajectory collection, or single run.

    Returns
    -------
    list of dict
        Each dict has run_id, parameters, status.

    Notes
    -----
    Supports three modes:
    - Screen directory (has ``screen_summary.json``): returns runs with parameters.
    - Directory of trajectories: subdirectories that are DTS runs.
    - Single trajectory: the directory itself is a DTS run.
    """
    root = Path(screen_dir)
    if not root.is_dir() or not root.exists():
        return []

    summary_path = root / "screen_summary.json"
    if summary_path.exists():
        with open(summary_path, "r") as f:
            summary = json.load(f)
        runs = sorted(summary["runs"], key=lambda r: _natural_sort_key(r["run_id"]))
        return [_run_info(root / r["run_id"]) for r in runs]

    if _is_run_directory(root):
        return [_run_info(root)]

    subdirs = sorted(
        [d for d in root.iterdir() if _is_run_directory(d)],
        key=lambda d: _natural_sort_key(d.name),
    )
    return [_run_info(d) for d in subdirs]
