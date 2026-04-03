"""
DTS trajectory analysis compute dispatch.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from pathlib import Path
from typing import Dict, Optional

import numpy as np

from ._utils import (
    parse_xvg,
    write_xvg,
    sanitize_label,
    list_trajectory_files,
    iter_frames,
)

__all__ = ["compute"]


def _build_stem(kind, **kwargs):
    """Derive the cache file stem from analysis kind and parameters."""
    if kind == "distance":
        label = sanitize_label(kwargs.get("reference_label", "reference"))
        return f"distance_to_{label}"
    if kind == "fluctuation":
        return f"rmsf_w{kwargs.get('window', 5)}"
    stem = f"prop_{sanitize_label(kind)}"
    for _, v in sorted(kwargs.items()):
        if isinstance(v, (str, int, float)):
            stem += f"_{sanitize_label(str(v))}"
    return stem


def _read_cached(output_dir, stem, force):
    """Read cached scalar + optional per-vertex result if available."""
    if not output_dir or force:
        return None
    result = parse_xvg(str(Path(output_dir) / "mosaic" / f"{stem}.xvg"))
    if result is None:
        return None

    columns, data, metadata = result
    col_name = columns[1] if len(columns) > 1 else "value"

    per_vertex = None
    vert = parse_xvg(str(Path(output_dir) / "mosaic" / f"{stem}_vertices.xvg"))
    if vert is not None:
        per_vertex = vert[1][:, 1:]

    return {
        "frames": data[:, 0],
        "values": data[:, 1],
        "per_vertex": per_vertex,
        "column": col_name,
        "metadata": metadata,
    }


def _write_result(output_dir, stem, result):
    """Write scalar + optional per-vertex XVG files."""
    if not output_dir:
        return None

    mosaic_dir = Path(output_dir) / "mosaic"
    frames = np.asarray(result["frames"], dtype=float)
    metadata = result["metadata"]

    write_xvg(
        str(mosaic_dir / f"{stem}.xvg"),
        ["frame", result["column"]],
        np.column_stack([frames, result["values"]]),
        metadata=metadata,
    )
    if result.get("per_vertex") is not None:
        pv = result["per_vertex"]
        write_xvg(
            str(mosaic_dir / f"{stem}_vertices.xvg"),
            ["frame"] + [f"v{j}" for j in range(pv.shape[1])],
            np.column_stack([frames.reshape(-1, 1), pv]),
            metadata={**metadata, "format": "per_vertex"},
        )


def _build_mesh(points, faces):
    """Build a TriangularMesh from points and faces."""
    from ..meshing import to_open3d
    from ..parametrization import TriangularMesh

    return TriangularMesh(to_open3d(points, faces), repair=False)


def compute(
    trajectory_dir: str,
    kind: str,
    *,
    scale: float,
    offset: np.ndarray,
    output_dir: Optional[str] = None,
    force: bool = False,
    **kwargs,
) -> Dict:
    """Run a trajectory analysis.

    Parameters
    ----------
    trajectory_dir : str
        Path to TrajTSI or VTU_F directory.
    kind : str
        Analysis type: ``"distance"``, ``"fluctuation"``, or a mesh property
        name like ``"mesh_area"`` or ``"mesh_volume"``.
    scale : float
        DTS scale factor.
    offset : np.ndarray
        DTS offset.
    output_dir : str, optional
        Run directory; results cached in ``{output_dir}/mosaic/``.
    force : bool
        Recompute even if cached.
    **kwargs
        Kind-specific parameters (see individual compute functions).

    Returns
    -------
    dict
        ``frames`` (ndarray), ``values`` (ndarray), ``per_vertex``
        (ndarray or None), ``column`` (str), ``metadata`` (dict).
    """
    stem = _build_stem(kind, **kwargs)

    cached = _read_cached(output_dir, stem, force)
    if cached is not None:
        return cached

    if kind == "distance":
        result = _compute_distance(trajectory_dir, scale, offset, **kwargs)
    elif kind == "fluctuation":
        result = _compute_fluctuation(trajectory_dir, scale, offset, **kwargs)
    else:
        result = _compute_property(trajectory_dir, kind, scale, offset, **kwargs)

    _write_result(output_dir, stem, result)
    return result


def _compute_distance(
    trajectory_dir, scale, offset, reference, reference_label="reference"
):
    """Per-frame vertex-to-surface distance to a reference mesh."""
    from ..geometry import Geometry
    from ..parallel import report_progress
    from ..properties import GeometryProperties

    n_frames = len(list_trajectory_files(trajectory_dir))
    reference_pts = Geometry(points=reference.points)

    per_vertex = []
    for i, (pts, faces, _) in enumerate(iter_frames(trajectory_dir, scale, offset)):
        report_progress(current=i, total=n_frames)
        mesh = Geometry(points=pts, model=_build_mesh(pts, faces))
        per_vertex.append(
            GeometryProperties.compute("distance", reference_pts, queries=[mesh])
        )

    per_vertex = np.array(per_vertex)
    return {
        "frames": np.arange(per_vertex.shape[0], dtype=float),
        "values": per_vertex.mean(axis=1),
        "per_vertex": per_vertex,
        "column": "distance",
        "metadata": {
            "computation": "distance",
            "reference": reference_label,
        },
    }


def _compute_fluctuation(
    trajectory_dir, scale, offset, window=5, start_frame=None, end_frame=None
):
    """Per-vertex positional fluctuation via sliding-window surface distance."""
    from ..geometry import Geometry
    from ..parallel import report_progress
    from ..properties import GeometryProperties

    start = start_frame
    end = end_frame

    all_frames = list(iter_frames(trajectory_dir, scale, offset))
    all_frames = all_frames[start or 0 : end or len(all_frames)]
    n_frames = len(all_frames)

    if n_frames < 2:
        n_verts = all_frames[0][0].shape[0] if all_frames else 0
        return {
            "frames": np.array([0.0]),
            "values": np.array([0.0]),
            "per_vertex": np.zeros((max(n_frames, 1), n_verts)),
            "column": "rmsf",
            "metadata": {"computation": "rmsf", "window": str(window)},
        }

    meshes = [Geometry(model=_build_mesh(pts, faces)) for pts, faces, _ in all_frames]

    per_vertex = []
    for t in range(n_frames):
        report_progress(current=t, total=n_frames)
        source = Geometry(points=all_frames[t][0])
        lo = max(0, t - window)
        hi = min(n_frames, t + window + 1)
        dists = [
            GeometryProperties.compute("distance", source, queries=[meshes[i]])
            for i in range(lo, hi)
            if i != t
        ]
        n_verts = all_frames[t][0].shape[0]
        per_vertex.append(np.std(dists, axis=0) if dists else np.zeros(n_verts))

    per_vertex = np.array(per_vertex)
    return {
        "frames": np.arange(n_frames, dtype=float),
        "values": per_vertex.mean(axis=1),
        "per_vertex": per_vertex,
        "column": "rmsf",
        "metadata": {"computation": "rmsf", "window": str(window)},
    }


def _compute_property(trajectory_dir, property_name, scale, offset, **kwargs):
    """Per-frame scalar mesh property (area, volume, etc.)."""
    from ..geometry import Geometry
    from ..parallel import report_progress
    from ..properties import GeometryProperties

    # Properties may return None for degenerate meshes to we track frame indices
    frame_indices, values = [], []
    n_frames = len(list_trajectory_files(trajectory_dir))
    for i, (pts, faces, _) in enumerate(iter_frames(trajectory_dir, scale, offset)):
        report_progress(current=i, total=n_frames)
        mesh = _build_mesh(pts, faces)

        val = GeometryProperties.compute(property_name, Geometry(model=mesh), **kwargs)
        if val is None:
            continue

        if hasattr(val, "__len__"):
            val = float(val[0]) if len(val) == 1 else float(np.mean(val))
        else:
            val = float(val)

        frame_indices.append(i)
        values.append(val)

    return {
        "frames": np.array(frame_indices, dtype=float),
        "values": np.array(values),
        "per_vertex": None,
        "column": property_name,
        "metadata": {
            "computation": property_name,
            **{k: str(v) for k, v in kwargs.items()},
        },
    }
