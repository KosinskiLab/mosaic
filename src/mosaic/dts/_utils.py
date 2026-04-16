"""
Shared utilities for DTS screening: XVG I/O, trajectory loading, screen results.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import re
import json
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np


def parse_xvg(path: str) -> Optional[Tuple[List[str], np.ndarray, Dict[str, str]]]:
    """Parse an .xvg file into (column_names, data, metadata) or None."""
    xvg_path = Path(path)
    if not xvg_path.exists():
        return None

    column_names, data_lines, metadata = [], [], {}
    with open(xvg_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("##"):
                column_names = line.lstrip("#").strip().split()
            elif line.startswith("#"):
                m = re.match(r"#\s*(\w+)\s*:\s*(.+)", line)
                if m:
                    metadata[m.group(1)] = m.group(2).strip()
            else:
                try:
                    data_lines.append([float(x) for x in line.split()])
                except ValueError:
                    continue

    if not data_lines:
        return None
    data = np.array(data_lines)
    if not column_names:
        column_names = [f"col_{i}" for i in range(data.shape[1])]
    return column_names, data, metadata


def write_xvg(path, columns, data, metadata=None):
    """Write columns + data to an .xvg file with optional metadata header."""
    xvg_path = Path(path)
    xvg_path.parent.mkdir(parents=True, exist_ok=True)
    with open(xvg_path, "w") as f:
        for key, value in (metadata or {}).items():
            f.write(f"# {key}: {value}\n")
        f.write("## " + "  ".join(columns) + "\n")
        for row in data:
            f.write("  ".join(f"{v:g}" for v in row) + "\n")


def sanitize_label(label: str) -> str:
    """Sanitize a label for use in filenames."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", label).strip("_").lower()


def resolve_trajectory_dir(run_dir) -> Optional[Path]:
    """Return the first existing trajectory directory for a DTS run.

    Parses ``input.dts`` (when present) for ``VisualizationFormat`` and
    ``NonbinaryTrajectory`` directory names, falling back to ``TrajTSI``.
    """
    run_path = Path(run_dir)
    dts_file = run_path / "input.dts"
    candidates = []
    if dts_file.exists():
        known, _ = parse_dts_content(dts_file.read_text())
        for name in known.get("trajectory_dirs", []):
            candidates.append(run_path / name)
    candidates.append(run_path / "TrajTSI")

    for path in candidates:
        if path.is_dir() and any(path.iterdir()):
            return path
    return None


def list_trajectory_files(trajectory_dir):
    """Return sorted trajectory mesh file paths from *trajectory_dir*."""
    traj_path = Path(trajectory_dir)
    files = [
        f
        for f in traj_path.iterdir()
        if f.suffix in (".tsi", ".vtu")
        and f.name != "conf-1.vtu"
        and re.search(r"\d+", f.name)
    ]
    return sorted(files, key=lambda f: int(re.findall(r"\d+", f.name)[0]))


def _drop_pbc_faces(points, faces):
    """Remove faces that wrap across periodic boundaries."""
    from ..meshing.utils import _edge_lengths

    points_norm = points - points.min(axis=0)
    box_stop = points_norm.max(axis=0)
    points_pbc = np.mod(points_norm, 0.85 * box_stop)

    dist_regular = _edge_lengths(points_norm, faces)
    dist_pbc = _edge_lengths(points_pbc, faces)

    return faces[np.all(dist_pbc >= dist_regular, axis=-1)]


def iter_frames(trajectory_dir, scale, offset, drop_pbc=False):
    """Yield ``(points, faces, filepath)`` per frame with transform applied."""
    from ..formats import open_file

    for f in list_trajectory_files(trajectory_dir):
        try:
            container = open_file(str(f))[0]
        except Exception as e:
            warnings.warn(f"Encountered exception loading frame {e}.")
            continue
        points = (container.vertices - offset) / scale
        faces = container.faces
        if drop_pbc:
            faces = _drop_pbc_faces(points, faces)
        yield points, faces, str(f)


def build_trajectory_frames(
    trajectory_dir,
    scale,
    offset,
    vertex_props=None,
    drop_pbc=False,
):
    """Build trajectory frame dicts for :class:`~mosaic.geometry.GeometryTrajectory`.

    Parameters
    ----------
    trajectory_dir : str
        Path to trajectory output directory.
    scale : float
        DTS scale factor.
    offset : np.ndarray
        DTS offset.
    vertex_props : dict, optional
        Mapping of property name to ``(n_frames, n_vertices)`` arrays.
        Obtained from :func:`collect_vertex_properties`.
    drop_pbc : bool
        Remove faces that wrap across periodic boundaries.
    """
    from ..meshing import to_open3d
    from ..parametrization import TriangularMesh
    from ..formats.parser import VertexPropertyContainer
    from ..parallel import report_progress

    total = len(list_trajectory_files(trajectory_dir))

    frames = []
    for i, (points, faces, filepath) in enumerate(
        iter_frames(trajectory_dir, scale, offset, drop_pbc=drop_pbc)
    ):
        report_progress(current=i, total=total)
        fit = TriangularMesh(to_open3d(points, faces), repair=False)
        frame = {"fit": fit, "filename": filepath}

        if vertex_props:
            n_verts = fit.vertices.shape[0]
            props = VertexPropertyContainer()
            for name, data in vertex_props.items():
                if i < data.shape[0] and data.shape[1] == n_verts:
                    props.set_property(name, data[i])
            if props.properties:
                frame["vertex_properties"] = props

        frames.append(frame)

    report_progress(current=total, total=total)
    return frames


def parse_time_series(run_dir: str) -> Optional[Tuple[List[str], np.ndarray]]:
    """Parse ``dts-en.xvg`` energy time series from a DTS run directory."""
    result = parse_xvg(str(Path(run_dir) / "dts-en.xvg"))
    if result is None:
        return None
    columns, data, _ = result
    return columns, data


def parse_run_time_series(run_dir: str) -> List[Dict]:
    """Scan a run directory for all .xvg time series files."""
    run_path = Path(run_dir)

    xvg_paths = []
    dts_en = run_path / "dts-en.xvg"
    if dts_en.exists():
        xvg_paths.append(dts_en)
    mosaic_dir = run_path / "mosaic"
    if mosaic_dir.is_dir():
        xvg_paths.extend(sorted(mosaic_dir.glob("*.xvg")))

    series = []
    for xvg_path in xvg_paths:
        result = parse_xvg(str(xvg_path))
        if result is None:
            continue
        columns, data, metadata = result
        source = "dts-en" if xvg_path.name == "dts-en.xvg" else xvg_path.stem
        series.append(
            {
                "source": source,
                "columns": columns,
                "data": data,
                "metadata": metadata,
            }
        )
    return series


def load_screen_results(screen_dir: str) -> Dict:
    """Load all results from a screen, trajectory collection, or single run."""
    from .screening import get_screen_status

    statuses = get_screen_status(screen_dir)
    if not statuses:
        return {"parameter_names": [], "runs": []}

    screen_path = Path(screen_dir)
    summary_path = screen_path / "screen_summary.json"

    parameter_names = []
    if summary_path.exists():
        with open(summary_path, "r") as f:
            summary = json.load(f)
        parameter_names = summary.get("parameters", [])

    runs = []
    for entry in statuses:
        run_id = entry["run_id"]
        run_dir = screen_path / run_id
        if not run_dir.exists():
            run_dir = screen_path

        params = entry.get("parameters", {})
        params_file = run_dir / "params.json"
        if params_file.exists():
            with open(params_file, "r") as f:
                params = json.load(f)

        runs.append(
            {
                "run_id": run_id,
                "params": params,
                "time_series": parse_run_time_series(str(run_dir)),
                "status": entry["status"],
                "run_dir": str(run_dir),
            }
        )

    return {"parameter_names": parameter_names, "runs": runs}


def collect_available_metrics(screen_results) -> list:
    """Return sorted display names for all non-per-vertex metrics in *screen_results*."""
    if not screen_results:
        return []

    col_sources = {}
    for run in screen_results["runs"]:
        for ts in run.get("time_series") or []:
            if (ts.get("metadata") or {}).get("format") == "per_vertex":
                continue
            for col in ts["columns"][1:]:
                col_sources.setdefault(col, set()).add(ts["source"])

    metrics = set()
    for col, sources in col_sources.items():
        if len(sources) > 1:
            metrics.update(f"{src}/{col}" for src in sources)
        else:
            metrics.add(col)
    return sorted(metrics)


def extract_metric_series(screen_results, metric_display, selected_run_ids=None):
    """Extract ``(run_dict, x, y)`` tuples for a given metric display name."""
    if not screen_results or not metric_display:
        return []

    if "/" in metric_display:
        source_filter, col_name = metric_display.split("/", 1)
    else:
        source_filter, col_name = None, metric_display

    series = []
    for run in screen_results["runs"]:
        if selected_run_ids and run["run_id"] not in selected_run_ids:
            continue

        for ts in run.get("time_series") or []:
            if (ts.get("metadata") or {}).get("format") == "per_vertex":
                continue
            if source_filter is not None and ts["source"] != source_filter:
                continue

            try:
                idx = next(
                    j
                    for j, name in enumerate(ts["columns"])
                    if col_name.lower() == name.lower()
                )
            except StopIteration:
                continue

            series.append(
                (run, np.arange(ts["data"].shape[0], dtype=float), ts["data"][:, idx])
            )
            break

    return series


COUPLING_DEFS = {
    "vol_coupling": {
        "label": "Volume Coupling",
        "dts_keyword": "VolumeCoupling",
        "modes": {
            "SecondOrder": [
                ("delta_p", "\u0394p (pressure)", 0.0, 0.1),
                ("K", "Stiffness", 10000.0, 100.0),
                ("target_v", "Target volume", 0.7, 0.05),
            ],
            "OsmoticPressure": [
                ("gamma", "\u03b3", 1.0, 0.1),
                ("P0", "P\u2080", 0.0, 0.1),
            ],
        },
    },
    "curv_coupling": {
        "label": "Global Curvature",
        "dts_keyword": "GlobalCurvatureCoupling",
        "modes": {
            "HarmonicPotential": [
                ("K", "Stiffness", 180.0, 1.0),
                ("C_g0", "Target curvature", 0.3, 0.05),
            ],
        },
    },
    "area_coupling": {
        "label": "Total Area",
        "dts_keyword": "TotalAreaCoupling",
        "modes": {
            "HarmonicPotential": [
                ("K", "Stiffness", 1000.0, 10.0),
                ("gamma", "Target ratio", 0.34, 0.05),
            ],
        },
    },
}


def extract_volume_path(dts_content: str) -> Optional[Union[str, List[str]]]:
    """Extract volume path(s) from DTS config content.

    Checks for a ``{{volume_path:...}}`` screening placeholder first,
    falling back to the literal path in the ``EnergyMethod`` line.

    Parameters
    ----------
    dts_content : str
        Raw DTS configuration text.

    Returns
    -------
    str, list of str, or None
        Extracted path(s), or *None* when no volume is referenced.
    """
    vol_match = re.search(r"\{\{volume_path:([^}]+)\}\}", dts_content)
    if vol_match:
        return vol_match.group(1).split(",")

    em_match = re.search(r"EnergyMethod\s*=\s*\S+\s+(\S+)", dts_content)
    if em_match and not em_match.group(1).startswith("{{"):
        return em_match.group(1)

    return None


def extract_screening_placeholder(value: str):
    """Return ``(name, range_str)`` if *value* is a ``{{name:range}}`` placeholder."""
    match = re.fullmatch(r"\{\{(\w+):([^}]+)\}\}", value.strip())
    if match:
        return match.group(1), match.group(2)
    return None


def parse_screening_ranges(text: str) -> Dict[str, List]:
    """Extract ``{{name:range}}`` placeholders from text and parse values."""
    result = {}
    for match in re.finditer(r"\{\{(\w+):([^}]+)\}\}", text):
        name, range_str = match.group(1), match.group(2)
        try:
            from pyfreedts.screen import ParameterParser

            _, parsed = ParameterParser.parse_template("{{" + f"p:{range_str}" + "}}")
            result[name] = parsed.get("p", [])
        except Exception:
            pass
    return result


_FILTER_KEY_MAP = {
    "lowpass": "lowpass_cutoff",
    "highpass": "highpass_cutoff",
    "plane_norm": "plane_norm",
}


def _parse_filter_line(line: str, known: Dict):
    """Parse a single ``;@filter`` line into *known* under ``_filters``."""
    filters = known.setdefault("_filters", {})
    for token in line[len(";@filter") :].split():
        if "=" not in token:
            continue
        key, _, val = token.partition("=")
        mapped = _FILTER_KEY_MAP.get(key.strip(), key.strip())
        try:
            filters[mapped] = float(val)
        except ValueError:
            filters[mapped] = val.strip()


def parse_filter_directives(dts_content: str) -> Dict[str, float]:
    """Parse ``; @filter`` directives from DTS content."""
    known: Dict = {}
    for line in dts_content.splitlines():
        stripped = line.strip()
        if stripped.startswith(";@filter"):
            _parse_filter_line(stripped, known)
    return known.get("_filters", {})


def parse_dts_content(content: str):
    """Parse DTS config content into known parameters and extra lines.

    Returns
    -------
    tuple of (dict, list)
        Known parameter dict and list of extra config lines.
    """
    known = {}
    extra_lines = []
    tail_lines = []

    if "INCLUSION" in content:
        idx = content.index("INCLUSION")
        tail_lines = content[idx:].strip().split("\n")
        content = content[:idx]

    _SKIP_KEYS = {
        "Integrator_Type",
        "VertexPositionIntegrator",
        "AlexanderMove",
        "InclusionPoseIntegrator",
        "VisualizationFormat",
        "NonbinaryTrajectory",
        "Box_Centering_F",
    }

    for line in content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(";"):
            if line.startswith(";@filter"):
                _parse_filter_line(line, known)
            continue

        if "=" not in line:
            extra_lines.append(line)
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        parts = value.split()

        if not parts:
            continue

        def _parse_val(raw):
            placeholder = extract_screening_placeholder(raw)
            if placeholder:
                name, range_str = placeholder
                known.setdefault("_screen", {})[name] = range_str
                try:
                    from pyfreedts.screen import ParameterParser

                    _, parsed = ParameterParser.parse_template(
                        "{{" + f"p:{range_str}" + "}}"
                    )
                    vals = parsed.get("p", [])
                    return vals[0] if vals else raw
                except Exception:
                    return raw
            return raw

        if key == "EnergyMethod":
            if ("MDFF" in parts[0] or "HMFF" in parts[0]) and len(parts) >= 8:
                vol_raw = parts[1]
                placeholder = extract_screening_placeholder(vol_raw)
                if placeholder:
                    paths = placeholder[1].split(",")
                    known["volume_path"] = paths
                    known.setdefault("_screen", {})["volume_path"] = placeholder[1]
                else:
                    known["volume_path"] = vol_raw
                known["xi"] = float(_parse_val(parts[2]))
                known["scale_factor"] = parts[4]
                known["offset"] = parts[5]
                try:
                    known["invert_contrast"] = bool(int(parts[6]))
                except (ValueError, IndexError):
                    pass
        elif key == "Kappa":
            known["kappa"] = float(_parse_val(parts[0]))
            if len(parts) >= 2:
                known["kappa0"] = float(_parse_val(parts[1]))
            if len(parts) >= 3:
                known["c0"] = float(_parse_val(parts[2]))
        elif key == "Temperature":
            known["temperature"] = float(_parse_val(parts[0]))
        elif key == "Set_Steps" and len(parts) >= 2:
            known["steps"] = int(float(parts[1]))
        elif key == "Min_Max_Lenghts" and len(parts) >= 2:
            known["min_edge"] = float(parts[0])
            known["max_edge"] = float(parts[1])
        elif key == "TimeSeriesData_Period":
            known["output_period"] = int(float(parts[0]))
        elif key == "VolumeCoupling":
            if parts[0] != "No":
                known["vol_coupling"] = {
                    "mode": parts[0],
                    "values": [_parse_val(p) for p in parts[1:]],
                }
        elif key == "GlobalCurvatureCoupling":
            if parts[0] != "No":
                known["curv_coupling"] = {
                    "mode": parts[0],
                    "values": [_parse_val(p) for p in parts[1:]],
                }
        elif key == "TotalAreaCoupling":
            if parts[0] != "No":
                known["area_coupling"] = {
                    "mode": parts[0],
                    "values": [_parse_val(p) for p in parts[1:]],
                }
        elif key == "VisualizationFormat" and len(parts) >= 2:
            known.setdefault("trajectory_dirs", []).append(parts[1])
        elif key == "NonbinaryTrajectory" and len(parts) >= 2:
            known.setdefault("trajectory_dirs", []).append(parts[1])
        elif key in _SKIP_KEYS:
            pass
        else:
            extra_lines.append(line)

    if "OpenMP" in content:
        known["threads"] = 4

    extra_lines.extend(tail_lines)
    return known, extra_lines


def collect_vertex_properties(run_dir: str) -> Dict[str, np.ndarray]:
    """Collect per-frame per-vertex properties from ``{run_dir}/mosaic/``.

    Returns
    -------
    dict of str -> np.ndarray
        Mapping from file stems to arrays of shape ``(n_frames, n_vertices)``.
    """
    mosaic_dir = Path(run_dir) / "mosaic"
    if not mosaic_dir.is_dir():
        return {}

    properties = {}
    for xvg_file in sorted(mosaic_dir.glob("*.xvg")):
        result = parse_xvg(str(xvg_file))
        if result is None:
            continue

        _, data, metadata = result
        if metadata.get("format") != "per_vertex":
            continue

        vertex_data = data[:, 1:]
        if vertex_data.size == 0:
            continue

        name = xvg_file.stem.removesuffix("_vertices")
        properties[name] = vertex_data

    return properties
