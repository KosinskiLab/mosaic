"""
DTS screening analysis: time series parsing, trajectory comparison, fluctuations.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import re
import json
from pathlib import Path
from os.path import basename
from typing import Dict, List, Optional, Tuple

import numpy as np

from .screening import run_status

__all__ = [
    "parse_time_series",
    "parse_run_time_series",
    "load_screen_results",
    "compute_trajectory_distance",
    "compute_vertex_fluctuation",
    "compute_trajectory_property",
]


def _parse_xvg(path: str) -> Optional[Tuple[List[str], np.ndarray, Dict[str, str]]]:
    """Parse an .xvg file into columns, data array, and metadata.

    Parameters
    ----------
    path : str
        Path to .xvg file.

    Returns
    -------
    tuple of (list of str, np.ndarray, dict) or None
        Column names, data array, and metadata dict from ``# key: value``
        header lines. Returns None if file not found or empty.
    """
    xvg_path = Path(path)
    if not xvg_path.exists():
        return None

    column_names = []
    data_lines = []
    metadata = {}

    with open(xvg_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("##"):
                column_names = line.lstrip("#").strip().split()
                continue
            if line.startswith("#"):
                # Parse metadata: "# key: value"
                m = re.match(r"#\s*(\w+)\s*:\s*(.+)", line)
                if m:
                    metadata[m.group(1)] = m.group(2).strip()
                continue
            parts = line.split()
            try:
                data_lines.append([float(x) for x in parts])
            except ValueError:
                continue

    if not data_lines:
        return None

    data = np.array(data_lines)
    if not column_names:
        column_names = [f"col_{i}" for i in range(data.shape[1])]

    return column_names, data, metadata


def _write_xvg(
    path: str,
    columns: List[str],
    data: np.ndarray,
    metadata: Optional[Dict[str, str]] = None,
):
    """Write data to an .xvg file.

    Parameters
    ----------
    path : str
        Output file path.
    columns : list of str
        Column header names.
    data : np.ndarray
        Data array (rows x cols).
    metadata : dict, optional
        Key-value pairs written as ``# key: value`` header lines.
    """
    xvg_path = Path(path)
    xvg_path.parent.mkdir(parents=True, exist_ok=True)

    with open(xvg_path, "w") as f:
        if metadata:
            for key, value in metadata.items():
                f.write(f"# {key}: {value}\n")
        f.write("## " + "  ".join(columns) + "\n")
        for row in data:
            f.write("  ".join(f"{v:g}" for v in row) + "\n")


def _sanitize_label(label: str) -> str:
    """Sanitize a label for use in filenames."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", label).strip("_").lower()


def parse_time_series(run_dir: str) -> Optional[Tuple[List[str], np.ndarray]]:
    """Parse ``dts-en.xvg`` energy time series from a DTS run directory.

    Parameters
    ----------
    run_dir : str
        Path to run directory.

    Returns
    -------
    tuple of (list of str, np.ndarray) or None
        Column names and data array, or None if file not found.
    """
    result = _parse_xvg(str(Path(run_dir) / "dts-en.xvg"))
    if result is None:
        return None
    columns, data, _metadata = result
    return columns, data


def parse_run_time_series(run_dir: str) -> List[Dict]:
    """Scan a run directory for all .xvg time series files.

    Reads ``{run_dir}/dts-en.xvg`` and all ``{run_dir}/mosaic/*.xvg`` files.

    Parameters
    ----------
    run_dir : str
        Path to run directory.

    Returns
    -------
    list of dict
        Each entry has ``source`` (file stem), ``columns`` (list of str),
        ``data`` (np.ndarray), and ``metadata`` (dict).
    """
    series = []
    run_path = Path(run_dir)

    dts_en = run_path / "dts-en.xvg"
    if dts_en.exists():
        result = _parse_xvg(str(dts_en))
        if result is not None:
            columns, data, metadata = result
            series.append(
                {
                    "source": "dts-en",
                    "columns": columns,
                    "data": data,
                    "metadata": metadata,
                }
            )

    mosaic_dir = run_path / "mosaic"
    if mosaic_dir.is_dir():
        for xvg_file in sorted(mosaic_dir.iterdir()):
            if not xvg_file.is_file() or xvg_file.suffix != ".xvg":
                continue
            result = _parse_xvg(str(xvg_file))
            if result is not None:
                columns, data, metadata = result
                series.append(
                    {
                        "source": xvg_file.stem,
                        "columns": columns,
                        "data": data,
                        "metadata": metadata,
                    }
                )

    return series


def load_screen_results(screen_dir: str) -> Dict:
    """Load all results from a screen, trajectory collection, or single run.

    Parameters
    ----------
    screen_dir : str
        Path to a screen directory, trajectory collection, or single run.

    Returns
    -------
    dict
        Dictionary with parameter_names, runs list (each with run_id, params,
        time_series as list of series dicts, status).
    """
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

        time_series = parse_run_time_series(str(run_dir))

        runs.append(
            {
                "run_id": run_id,
                "params": params,
                "time_series": time_series,
                "status": entry["status"],
                "run_dir": str(run_dir),
            }
        )

    return {
        "parameter_names": parameter_names,
        "runs": runs,
    }


def _load_trajectory_frames(
    trajectory_dir: str,
) -> List[np.ndarray]:
    """Load mesh frames from a TrajTSI directory.

    Parameters
    ----------
    trajectory_dir : str
        Path to TrajTSI directory.

    Returns
    -------
    list of np.ndarray
        List of vertex position arrays per frame.
    """
    from ..formats import open_file

    traj_path = Path(trajectory_dir)
    files = [
        str(traj_path / x)
        for x in sorted(traj_path.iterdir())
        if x.suffix in (".tsi", ".vtu")
        and x.name != "conf-1.vtu"
        and re.search(r"\d+", x.name)
    ]
    files = sorted(files, key=lambda x: int(re.findall(r"\d+", basename(x))[0]))

    frames = []
    for filepath in files:
        container = open_file(filepath)[0]
        frames.append(container.vertices.copy())

    return frames


def compute_trajectory_distance(
    trajectory_dir: str,
    reference_points: np.ndarray,
    scale_factor: float,
    offset: np.ndarray,
    metric: str = "rmse",
    reference_label: str = "reference",
    output_dir: Optional[str] = None,
    force: bool = False,
) -> Dict:
    """Compute distance between trajectory frames and reference geometry.

    Parameters
    ----------
    trajectory_dir : str
        Path to TrajTSI directory.
    reference_points : np.ndarray
        Reference point cloud (N, 3).
    scale_factor : float
        Scale factor from mesh.txt.
    offset : np.ndarray
        Offset from mesh.txt.
    metric : str
        Distance metric: "rmse", "hausdorff", or "mean_distance".
    reference_label : str
        Human-readable reference name for file naming and metadata.
    output_dir : str, optional
        Run directory for writing cached .xvg files. If provided, writes
        to ``{output_dir}/mosaic/``.
    force : bool
        Recompute even if cached files exist.

    Returns
    -------
    dict
        Dictionary with frame indices and distance values.
    """
    from scipy.spatial import KDTree

    safe_label = _sanitize_label(reference_label)
    scalar_stem = f"distance_{metric}_to_{safe_label}"

    # Check cache
    if output_dir and not force:
        scalar_path = Path(output_dir) / "mosaic" / f"{scalar_stem}.xvg"
        if scalar_path.exists():
            result = _parse_xvg(str(scalar_path))
            if result is not None:
                columns, data, _meta = result
                return {
                    "frames": data[:, 0].astype(int).tolist(),
                    "values": data[:, 1],
                    "metric": metric,
                }

    frames = _load_trajectory_frames(trajectory_dir)
    ref_tree = KDTree(reference_points)

    frame_indices = []
    scalar_values = []
    per_vertex_rows = []

    for i, frame_points in enumerate(frames):
        transformed = np.divide(np.subtract(frame_points, offset), scale_factor)
        distances, _ = ref_tree.query(transformed)

        if metric == "rmse":
            val = np.sqrt(np.mean(distances**2))
        elif metric == "hausdorff":
            rev_tree = KDTree(transformed)
            rev_distances, _ = rev_tree.query(reference_points)
            val = max(np.max(distances), np.max(rev_distances))
        elif metric == "mean_distance":
            val = np.mean(distances)
        else:
            val = np.sqrt(np.mean(distances**2))

        frame_indices.append(i)
        scalar_values.append(val)
        per_vertex_rows.append(distances)

    scalar_arr = np.array(scalar_values)

    if output_dir:
        mosaic_dir = Path(output_dir) / "mosaic"

        # Per-frame scalar
        scalar_data = np.column_stack(
            [np.array(frame_indices, dtype=float), scalar_arr]
        )
        _write_xvg(
            str(mosaic_dir / f"{scalar_stem}.xvg"),
            ["frame", metric],
            scalar_data,
            metadata={
                "computation": "distance",
                "reference": reference_label,
                "metric": metric,
            },
        )

        # Per-vertex per-frame
        if per_vertex_rows:
            n_verts = per_vertex_rows[0].shape[0]
            vertex_cols = ["frame"] + [f"v{j}" for j in range(n_verts)]
            vertex_data = np.column_stack(
                [
                    np.array(frame_indices, dtype=float).reshape(-1, 1),
                    np.array(per_vertex_rows),
                ]
            )
            _write_xvg(
                str(mosaic_dir / f"{scalar_stem}_vertices.xvg"),
                vertex_cols,
                vertex_data,
                metadata={
                    "computation": "distance",
                    "reference": reference_label,
                    "metric": metric,
                    "format": "per_vertex",
                },
            )

    return {
        "frames": frame_indices,
        "values": scalar_arr,
        "metric": metric,
    }


def compute_vertex_fluctuation(
    trajectory_dir: str,
    scale_factor: float,
    offset: np.ndarray,
    window: int = 5,
    start_frame: Optional[int] = None,
    end_frame: Optional[int] = None,
    output_dir: Optional[str] = None,
    force: bool = False,
) -> Dict:
    """Compute per-vertex positional standard deviation in a sliding window.

    For each frame *t*, meshes within ``[t - window, t + window]`` are
    collected as queries. :func:`~mosaic.properties.distance` is called
    with ``aggregation="std"`` to obtain the per-vertex standard deviation
    of nearest-neighbour distances to those window meshes.

    Parameters
    ----------
    trajectory_dir : str
        Path to TrajTSI directory.
    scale_factor : float
        Scale factor from mesh.txt.
    offset : np.ndarray
        Offset from mesh.txt.
    window : int
        Half-window size. Each frame uses ``2 * window + 1`` neighbours
        (clamped at trajectory boundaries).
    start_frame : int, optional
        Start frame index (inclusive).
    end_frame : int, optional
        End frame index (exclusive).
    output_dir : str, optional
        Run directory for writing cached .xvg files.
    force : bool
        Recompute even if cached files exist.

    Returns
    -------
    dict
        Dictionary with ``per_vertex_std`` (n_frames, n_vertices),
        ``mean_fluctuation`` (scalar), and ``per_frame_rmsf`` (n_frames,).
    """
    from ..geometry import Geometry
    from ..properties import distance as geom_distance

    stem = f"rmsf_w{window}"

    # Check cache
    if output_dir and not force:
        scalar_path = Path(output_dir) / "mosaic" / f"{stem}.xvg"
        if scalar_path.exists():
            result = _parse_xvg(str(scalar_path))
            if result is not None:
                _columns, data, _meta = result
                per_frame_rmsf = data[:, 1]

                vert_path = Path(output_dir) / "mosaic" / f"{stem}_vertices.xvg"
                per_vertex_std = np.zeros((len(per_frame_rmsf), 0))
                if vert_path.exists():
                    vresult = _parse_xvg(str(vert_path))
                    if vresult is not None:
                        per_vertex_std = vresult[1][:, 1:]

                return {
                    "per_vertex_std": per_vertex_std,
                    "mean_fluctuation": float(np.mean(per_frame_rmsf)),
                    "per_frame_rmsf": per_frame_rmsf,
                }

    frames = _load_trajectory_frames(trajectory_dir)

    transformed = []
    for frame_points in frames:
        transformed.append(np.divide(np.subtract(frame_points, offset), scale_factor))

    if start_frame is not None or end_frame is not None:
        transformed = transformed[start_frame or 0 : end_frame or len(transformed)]

    n_frames = len(transformed)
    if n_frames < 2:
        n_verts = transformed[0].shape[0] if transformed else 0
        return {
            "per_vertex_std": np.zeros((max(n_frames, 1), n_verts)),
            "mean_fluctuation": 0.0,
            "per_frame_rmsf": np.array([0.0]),
        }

    n_verts = transformed[0].shape[0]
    per_vertex_std = np.empty((n_frames, n_verts), dtype=float)
    per_frame_rmsf = np.empty(n_frames, dtype=float)

    for t in range(n_frames):
        lo = max(0, t - window)
        hi = min(n_frames, t + window + 1)

        geom = Geometry(points=transformed[t])
        dists = []
        for i in range(lo, hi):
            if i == t:
                continue
            d = geom_distance(geom, queries=[transformed[i]])
            if d is not None:
                dists.append(d)

        if dists:
            per_vertex_std[t] = np.std(dists, axis=0)
        else:
            per_vertex_std[t] = np.zeros(n_verts)
        per_frame_rmsf[t] = np.mean(per_vertex_std[t])

    if output_dir:
        mosaic_dir = Path(output_dir) / "mosaic"

        frame_indices = np.arange(n_frames, dtype=float)
        _write_xvg(
            str(mosaic_dir / f"{stem}.xvg"),
            ["frame", "rmsf"],
            np.column_stack([frame_indices, per_frame_rmsf]),
            metadata={"computation": "rmsf", "window": str(window)},
        )

        _write_xvg(
            str(mosaic_dir / f"{stem}_vertices.xvg"),
            ["frame"] + [f"v{j}" for j in range(n_verts)],
            np.column_stack([frame_indices.reshape(-1, 1), per_vertex_std]),
            metadata={
                "computation": "rmsf",
                "window": str(window),
                "format": "per_vertex",
            },
        )

    return {
        "per_vertex_std": per_vertex_std,
        "mean_fluctuation": float(np.mean(per_frame_rmsf)),
        "per_frame_rmsf": per_frame_rmsf,
    }


def compute_trajectory_property(
    trajectory_dir: str,
    property_name: str,
    scale_factor: float,
    offset: np.ndarray,
    output_dir: Optional[str] = None,
    force: bool = False,
    **property_kwargs,
) -> Dict:
    """Compute a scalar mesh property for each frame in a trajectory.

    Loads each frame, builds a :class:`~mosaic.geometry.Geometry` with a
    :class:`~mosaic.parametrization.TriangularMesh` model, and calls
    :meth:`~mosaic.properties.GeometryProperties.compute`.

    Parameters
    ----------
    trajectory_dir : str
        Path to TrajTSI directory.
    property_name : str
        Property key registered in ``GeometryProperties`` (e.g.
        ``"mesh_area"``, ``"mesh_volume"``).
    scale_factor : float
        Scale factor from mesh.txt.
    offset : np.ndarray
        Offset from mesh.txt.
    output_dir : str, optional
        Run directory for writing cached .xvg files.
    force : bool
        Recompute even if cached files exist.
    **property_kwargs
        Extra keyword arguments forwarded to the property calculator.

    Returns
    -------
    dict
        Dictionary with ``frames`` and ``values`` arrays.
    """
    from ..geometry import Geometry
    from ..properties import GeometryProperties
    from ..formats import open_file
    from ..meshing import to_open3d
    from ..parametrization import TriangularMesh

    safe_name = _sanitize_label(property_name)
    for k, v in sorted(property_kwargs.items()):
        safe_name += f"_{_sanitize_label(str(v))}"
    stem = f"prop_{safe_name}"

    if output_dir and not force:
        cached = Path(output_dir) / "mosaic" / f"{stem}.xvg"
        if cached.exists():
            result = _parse_xvg(str(cached))
            if result is not None:
                _cols, data, _meta = result
                return {"frames": data[:, 0].astype(int).tolist(), "values": data[:, 1]}

    traj_path = Path(trajectory_dir)
    files = sorted(
        [
            f
            for f in traj_path.iterdir()
            if f.suffix in (".tsi", ".vtu") and f.name != "conf-1.vtu"
        ],
        key=lambda f: int(re.findall(r"\d+", f.name)[0]),
    )

    frame_indices = []
    values = []
    for i, filepath in enumerate(files):
        container = open_file(str(filepath))[0]
        points = np.divide(np.subtract(container.vertices, offset), scale_factor)
        faces = container.faces.astype(int)
        mesh = to_open3d(points, faces)
        model = TriangularMesh(mesh, repair=False)
        geom = Geometry(points=points, model=model)

        val = GeometryProperties.compute(property_name, geom, **property_kwargs)
        if val is None:
            continue

        if hasattr(val, "__len__") and len(val) == 1:
            val = float(val[0])
        elif hasattr(val, "__len__"):
            val = float(np.mean(val))
        else:
            val = float(val)

        frame_indices.append(i)
        values.append(val)

    values_arr = np.array(values)

    if output_dir:
        mosaic_dir = Path(output_dir) / "mosaic"
        _write_xvg(
            str(mosaic_dir / f"{stem}.xvg"),
            ["frame", property_name],
            np.column_stack([np.array(frame_indices, dtype=float), values_arr]),
            metadata={
                "computation": property_name,
                **{k: str(v) for k, v in property_kwargs.items()},
            },
        )

    return {"frames": frame_indices, "values": values_arr}
