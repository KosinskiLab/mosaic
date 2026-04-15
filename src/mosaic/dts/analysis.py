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
    if kind == "hmff_potential":
        return "hmff_potential"
    if kind == "bending_energy":
        return "bending_energy"
    if kind == "hmff_bending_ratio":
        return "hmff_bending_ratio"
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

    if kind == "fluctuation":
        result = _compute_fluctuation(trajectory_dir, scale, offset, **kwargs)
    elif kind == "hmff_potential":
        result = _compute_hmff(
            trajectory_dir, scale, offset, output_dir=output_dir, **kwargs
        )
    elif kind == "bending_energy":
        result = _compute_bending_energy(
            trajectory_dir, scale, offset, output_dir=output_dir, **kwargs
        )
    elif kind == "hmff_bending_ratio":
        result = _compute_hmff_bending_ratio(
            trajectory_dir, scale, offset, output_dir=output_dir, **kwargs
        )
    else:
        result = _compute_property(trajectory_dir, kind, scale, offset, **kwargs)

    _write_result(output_dir, stem, result)
    return result


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

    per_vertex = np.array(per_vertex, dtype=float)

    # Frames at boundaries have truncated windows and are not comparable
    # to interior frames so we mark them as missing data.
    per_vertex[:window] = np.nan
    per_vertex[-window:] = np.nan

    return {
        "frames": np.arange(n_frames, dtype=float),
        "values": np.nanmean(per_vertex, axis=1),
        "per_vertex": per_vertex,
        "column": "rmsf",
        "metadata": {"computation": "rmsf", "window": str(window)},
    }


def _compute_property(trajectory_dir, property_name, scale, offset, **kwargs):
    """Per-frame mesh property (area, volume, distance, etc.)."""
    from ..geometry import Geometry
    from ..parallel import report_progress
    from ..properties import GeometryProperties

    frame_indices, scalars, per_vertex = [], [], []
    n_frames = len(list_trajectory_files(trajectory_dir))
    for i, (pts, faces, _) in enumerate(iter_frames(trajectory_dir, scale, offset)):
        report_progress(current=i, total=n_frames)
        mesh = _build_mesh(pts, faces)

        val = GeometryProperties.compute(
            property_name, Geometry(points=pts, model=mesh), **kwargs
        )
        if val is None:
            continue

        frame_indices.append(i)
        if hasattr(val, "__len__") and len(val) > 1:
            per_vertex.append(np.asarray(val))
            scalars.append(float(np.mean(val)))
        else:
            scalars.append(float(val[0]) if hasattr(val, "__len__") else float(val))

    return {
        "frames": np.array(frame_indices, dtype=float),
        "values": np.array(scalars),
        "per_vertex": np.array(per_vertex) if per_vertex else None,
        "column": property_name,
        "metadata": {
            "computation": property_name,
            **{k: str(v) for k, v in kwargs.items()},
        },
    }


def _vertex_bending_energy(vertices, triangles, kappa, kappa_g=0.0, c0=0.0):
    """Compute per-vertex Helfrich bending energy.

    Parameters
    ----------
    vertices : np.ndarray
        Vertex positions, shape ``(N, 3)``.
    triangles : np.ndarray
        Triangle connectivity, shape ``(M, 3)``.
    kappa : float
        Bending rigidity (as in the DTS ``Kappa`` line).
    kappa_g : float
        Gaussian bending rigidity.
    c0 : float
        Spontaneous curvature.

    Returns
    -------
    np.ndarray
        Per-vertex bending energy, shape ``(N,)``.
    """
    import igl

    vertices = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(triangles, dtype=np.int32)

    # TODO: Check the useKring interface changes

    # From parametrization.py
    # pd1, pd2, pv1, pv2, bad_vs = igl.principal_curvature(
    #     self.vertices, self.triangles, radius=radius, useKring=use_k_ring
    # )

    _, _, pv1, pv2, _ = igl.principal_curvature(vertices, triangles, radius=5)

    # Barycentric vertex area: each vertex gets 1/3 of each adjacent triangle
    v0 = vertices[triangles[:, 0]]
    v1 = vertices[triangles[:, 1]]
    v2 = vertices[triangles[:, 2]]
    tri_areas = np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1) / 2.0

    vertex_areas = np.zeros(len(vertices))
    for j in range(3):
        np.add.at(vertex_areas, triangles[:, j], tri_areas / 3.0)

    # E_v = A * (kappa/2 * (2H - c0)^2 - kappa_g * K)
    gaus = kappa_g * pv1 * pv2
    mean = (kappa / 2.0) * (pv1 + pv2 - c0) ** 2
    return (mean - gaus) * vertex_areas


def _compute_bending_energy(trajectory_dir, scale, offset, output_dir=None, **kwargs):
    """Per-frame bending energy from DTS config and trajectory meshes."""
    from ..parallel import report_progress
    from ._utils import parse_dts_content

    run_dir = Path(output_dir) if output_dir else Path(trajectory_dir).parent
    dts_file = run_dir / "input.dts"
    if not dts_file.exists():
        raise FileNotFoundError(f"DTS config not found: {dts_file}")

    known, _ = parse_dts_content(dts_file.read_text())
    kappa = float(known.get("kappa", 20.0))
    kappa_g = float(known.get("kappa0", 0.0))
    c0 = float(known.get("c0", 0.0))

    n_frames = len(list_trajectory_files(trajectory_dir))
    frame_indices, scalars, per_vertex = [], [], []

    for i, (points, faces, _) in enumerate(iter_frames(trajectory_dir, scale, offset)):
        report_progress(current=i, total=n_frames)
        pv = _vertex_bending_energy(points, faces, kappa, kappa_g, c0)
        frame_indices.append(i)
        scalars.append(float(pv.sum()))
        per_vertex.append(pv)

    return {
        "frames": np.array(frame_indices, dtype=float),
        "values": np.array(scalars),
        "per_vertex": np.array(per_vertex) if per_vertex else None,
        "column": "bending_energy",
        "metadata": {
            "computation": "bending_energy",
            "kappa": str(kappa),
            "kappa_g": str(kappa_g),
            "c0": str(c0),
        },
    }


def _compute_hmff_bending_ratio(
    trajectory_dir, scale, offset, output_dir=None, **kwargs
):
    """Per-frame ratio of HMFF potential to bending energy.

    Values > 1 indicate regions where the density fit dominates over
    intrinsic membrane elasticity.
    """
    run_dir = Path(output_dir) if output_dir else Path(trajectory_dir).parent

    bend_stem = "bending_energy"
    hmff_stem = "hmff_potential"
    mosaic_dir = run_dir / "mosaic"

    bend_result = parse_xvg(str(mosaic_dir / f"{bend_stem}_vertices.xvg"))
    hmff_result = parse_xvg(str(mosaic_dir / f"{hmff_stem}_vertices.xvg"))

    if bend_result is None or hmff_result is None:
        bend = compute(
            trajectory_dir,
            "bending_energy",
            scale=scale,
            offset=offset,
            output_dir=output_dir,
            **kwargs,
        )
        hmff = compute(
            trajectory_dir,
            "hmff_potential",
            scale=scale,
            offset=offset,
            output_dir=output_dir,
            **kwargs,
        )
        bend_pv = bend["per_vertex"]
        hmff_pv = hmff["per_vertex"]
    else:
        bend_pv = bend_result[1][:, 1:]
        hmff_pv = hmff_result[1][:, 1:]

    n_frames = min(bend_pv.shape[0], hmff_pv.shape[0])
    bend_pv = bend_pv[:n_frames]
    hmff_pv = hmff_pv[:n_frames]

    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(
            np.abs(bend_pv) > 1e-12,
            hmff_pv / bend_pv,
            0.0,
        )

    return {
        "frames": np.arange(n_frames, dtype=float),
        "values": ratio.mean(axis=1),
        "per_vertex": ratio,
        "column": "hmff_bending_ratio",
        "metadata": {"computation": "hmff_bending_ratio"},
    }


def _hmff_potential(
    vertices,
    interpolator,
    xi=5.0,
    theta_min=0.0,
    theta_max=1.0,
    boundary_values=None,
    padding=0.4,
):
    """Evaluate the HMFF potential for a set of vertices.

    Parameters
    ----------
    vertices : np.ndarray
        Vertex positions in voxel coordinates, shape ``(N, 3)``.
    interpolator : RegularGridInterpolator
        Interpolator over the density grid.
    xi : float
        Coupling strength.
    theta_min : float
        Minimum density threshold.
    theta_max : float
        Maximum density threshold.
    boundary_values : np.ndarray, optional
        Min-max normalized per-slice boundary values for out-of-bounds
        vertices (see ``_compute_boundary_values``).
    padding : float
        Scaling factor for boundary fallback values.

    Returns
    -------
    np.ndarray
        Per-vertex HMFF potential.
    """
    theta = interpolator(vertices)

    # Match FreeDTS VertexInScalarFieldPotential.cpp: all out-of-bounds
    # vertices get padding * boundaryValues[z_clamped] * thetaMax,
    # with z clamped to [0, nz - 1].
    mask = np.isnan(theta)
    if mask.any() and boundary_values is not None:
        z_idx = np.clip(vertices[mask, 2].astype(int), 0, len(boundary_values) - 1)
        theta[mask] = padding * boundary_values[z_idx] * theta_max

    theta = np.minimum(theta, theta_max)
    potential = xi * (1 - (theta - theta_min) / (theta_max - theta_min))
    potential[theta < theta_min] = xi
    return potential


def _compute_boundary_values(data):
    """Compute min-max normalized per-slice boundary values.

    Matches the FreeDTS ``HarmonicPotentialCalculator`` constructor:
    per-slice mean of absolute values, smoothed with neighbor averaging,
    then min-max normalized to [0, 1].
    """
    # Per z-slice mean of absolute values
    averages = np.abs(data).mean(axis=(0, 1))

    # Neighbor-weighted smoothing (2-point at edges, 3-point interior)
    smoothed = np.empty_like(averages)
    smoothed[0] = (
        (averages[0] + averages[1]) / 2.0 if len(averages) > 1 else averages[0]
    )
    smoothed[-1] = (
        (averages[-2] + averages[-1]) / 2.0 if len(averages) > 1 else averages[-1]
    )
    for i in range(1, len(averages) - 1):
        smoothed[i] = (averages[i - 1] + averages[i] + averages[i + 1]) / 3.0

    # Min-max normalization
    vmin, vmax = smoothed.min(), smoothed.max()
    if vmax - vmin > 0:
        smoothed = (smoothed - vmin) / (vmax - vmin)
    else:
        smoothed[:] = 0.5

    return smoothed


def _compute_hmff(trajectory_dir, scale, offset, output_dir=None, **kwargs):
    """Per-frame HMFF potential energy from DTS config and density volume.

    Parameters
    ----------
    trajectory_dir : str
        Path to TrajTSI or VTU_F directory.
    scale : float
        DTS scale factor.
    offset : np.ndarray
        DTS offset.
    output_dir : str, optional
        Run directory containing ``input.dts``.
    """
    from scipy.interpolate import RegularGridInterpolator
    from ..formats.parser import load_density
    from ..parallel import report_progress
    from ._utils import parse_dts_content

    run_dir = Path(output_dir) if output_dir else Path(trajectory_dir).parent
    dts_file = run_dir / "input.dts"
    if not dts_file.exists():
        raise FileNotFoundError(f"DTS config not found: {dts_file}")

    known, _ = parse_dts_content(dts_file.read_text())

    volume_path = known.get("volume_path")
    if volume_path is None:
        raise ValueError(
            "No volume path found in DTS config — HMFF requires a density."
        )
    if isinstance(volume_path, list):
        volume_path = volume_path[0]

    volume_path = str((run_dir / volume_path).resolve())

    xi = float(known.get("xi", 5.0))
    invert = known.get("invert_contrast", False)

    if "scale_factor" in known:
        scale = float(known["scale_factor"])
    if "offset" in known:
        offset = np.array([float(x) for x in known["offset"].split(",")])

    density = load_density(volume_path)
    data = density.data.copy()
    if invert:
        data *= -1

    sampling_rate = np.asarray(density.sampling_rate)
    voxel_scale = 1.0 / (sampling_rate * scale)

    theta_max = float(np.quantile(data, q=0.999))
    boundary_values = _compute_boundary_values(data)

    interpolator = RegularGridInterpolator(
        tuple(np.arange(x) for x in data.shape),
        data,
        method="linear",
        bounds_error=False,
        fill_value=np.nan,
    )

    n_frames = len(list_trajectory_files(trajectory_dir))
    frame_indices, scalars, per_vertex = [], [], []

    for i, (points, _, _) in enumerate(iter_frames(trajectory_dir, 1.0, offset)):
        report_progress(current=i, total=n_frames)
        voxel_points = points * voxel_scale
        pv = _hmff_potential(
            voxel_points,
            interpolator,
            xi=xi,
            theta_max=theta_max,
            boundary_values=boundary_values,
        )
        frame_indices.append(i)
        scalars.append(float(pv.sum()))
        per_vertex.append(pv)

    return {
        "frames": np.array(frame_indices, dtype=float),
        "values": np.array(scalars),
        "per_vertex": np.array(per_vertex) if per_vertex else None,
        "column": "hmff_potential",
        "metadata": {
            "computation": "hmff_potential",
            "volume": str(volume_path),
            "xi": str(xi),
        },
    }
