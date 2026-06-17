import json
from typing import Dict, List

import numpy as np

from ._utils import write_star_header
from .records import GeometryData


def _coerce_records(geometries) -> List[GeometryData]:
    """Build per-geometry records for the writers.

    Parameters
    ----------
    geometries : list of Geometry
        Source geometries.

    Returns
    -------
    list of GeometryData
        One record per geometry.
    """
    records = []
    for geometry in geometries:
        points, normals, quaternions = geometry.get_point_data()
        records.append(
            GeometryData(
                vertices=points,
                normals=normals,
                quaternions=quaternions,
                sampling=geometry.sampling_rate,
                vertex_properties=geometry.vertex_properties,
                model=geometry.model,
            )
        )
    return records


def _prepare_oriented_points(records, sampling):
    """Scale, synthesize quaternions, and concatenate records for STAR/TSV.

    Parameters
    ----------
    records : list of GeometryData
        Source records.
    sampling : float or None
        Sampling override; ``None`` uses each record's own.

    Returns
    -------
    dict
        Stacked ``points`` / ``quaternions`` / ``entities``, per-record
        ``pixel_sizes``, and merged ``vertex_properties``.
    """
    from .records import VertexPropertyContainer

    points_out, quats_out, entities_out, pixel_sizes = [], [], [], []
    for i, rec in enumerate(records):
        rec_sampling = sampling if sampling is not None else rec.sampling
        pixel_sizes.append(float(np.mean(rec_sampling)))

        pts = np.divide(rec.vertices, rec_sampling)
        points_out.append(pts)
        quats_out.append(_ensure_quaternions(rec))
        entities_out.append(np.full(pts.shape[0], fill_value=i))

    return {
        "points": np.concatenate(points_out) if points_out else np.empty((0, 3)),
        "quaternions": (np.concatenate(quats_out) if quats_out else np.empty((0, 4))),
        "entities": (
            np.concatenate(entities_out) if entities_out else np.empty((0,), dtype=int)
        ),
        "pixel_sizes": pixel_sizes,
        "vertex_properties": VertexPropertyContainer.merge(
            [r.vertex_properties for r in records if r.vertex_properties is not None]
        ),
    }


def _ensure_quaternions(rec):
    """Return ``rec.quaternions``, synthesizing from normals when absent.

    Parameters
    ----------
    rec : GeometryData
        Source record.

    Returns
    -------
    np.ndarray
        Quaternion array, scalar-first.
    """
    from ..utils import normals_to_rot, NORMAL_REFERENCE

    if rec.quaternions is not None:
        return rec.quaternions
    normals = rec.normals
    if normals is None:
        normals = np.full_like(rec.vertices, fill_value=NORMAL_REFERENCE)
    return normals_to_rot(normals, scalar_first=True)


def _write_orientations(
    points,
    quaternions,
    entities,
    path,
    file_format,
    *,
    vertex_properties=None,
    **kwargs,
):
    """Convert oriented points to ZYZ Eulers and write via ``tme.Orientations``.

    Parameters
    ----------
    points : np.ndarray
        Point coordinates.
    quaternions : np.ndarray
        Scalar-first quaternions.
    entities : np.ndarray
        Per-point integer label written to the ``details`` column.
    path : str
        Output path.
    file_format : str
        ``"star"`` or ``"tsv"``.
    vertex_properties : VertexPropertyContainer, optional
        Per-point properties to attach as ``Orientations.metadata``
        (pytme >= 0.3.4). Silently dropped on older pytme.
    **kwargs
        Forwarded to ``Orientations.to_file``.
    """
    from tme import Orientations
    from ..utils import quat_to_euler

    # scipy.spatial.transform.Rotation threading breaks pipelines
    rotations = quat_to_euler(quaternions, degrees=True, inv_quat=True)

    metadata = {}
    if vertex_properties is not None:
        metadata = {
            name: vertex_properties.get_property(name)
            for name in vertex_properties.properties
        }
        metadata["_rlnClassNumber"] = entities

    common = {"translations": points, "rotations": rotations}
    try:
        orientations = Orientations(**common, metadata=metadata)
    except TypeError:
        orientations = Orientations(
            **common, scores=np.zeros(rotations.shape[0]), details=entities
        )
    orientations.to_file(path, file_format=file_format, **kwargs)


def write_topology_file(file_path: str, data: Dict, tsi_format: bool = False) -> None:
    """
    Write a topology file [1]_.

    Parameters
    ----------
    file_path : str
        The path to the output file.
    data : dict
        Topology file data as per :py:meth:`read_topology_file`.
    tsi_format : bool, optional
        Whether to use the '.q' or '.tsi' file, defaults to '.q'.

    References
    ----------
    .. [1] https://github.com/weria-pezeshkian/FreeDTS/wiki/Manual-for-version-1
    """
    vertex_string = f"{data['vertices'].shape[0]}\n"
    if tsi_format:
        vertex_string = f"vertex {vertex_string}"

    stop = data["vertices"].shape[1] - 1
    if tsi_format:
        stop = data["vertices"].shape[1]
    for i in range(data["vertices"].shape[0]):
        vertex_string += f"{int(data['vertices'][i, 0])}  "
        vertex_string += "  ".join([f"{x:<.10f}" for x in data["vertices"][i, 1:stop]])

        if not tsi_format:
            vertex_string += f"  {int(data['vertices'][i, stop])}"
        vertex_string += "\n"

    stop = data["faces"].shape[1] - 1
    face_string = f"{data['faces'].shape[0]}\n"
    if tsi_format:
        face_string = f"triangle {face_string}"
        stop = data["faces"].shape[1]
    for i in range(data["faces"].shape[0]):
        face = [f"{int(x):d}" for x in data["faces"][i, :stop]]
        face[1] += " "
        face.append("")
        face_string += "  ".join(face) + "\n"

    inclusion_string = ""
    inclusions = data.get("inclusions", None)
    if tsi_format and inclusions is not None:
        inclusion_string = f"inclusion {inclusions.shape[0]}\n"
        for i in range(data["inclusions"].shape[0]):
            ret = inclusions[i]
            ret[0] = int(ret[0])
            ret[1] = int(ret[1])
            ret[2] = int(ret[2])
            inclusion_string += f"{'   '.join([f'{x}' for x in ret])}   \n"

    box_string = f"{'   '.join([f'{x:<.10f}' for x in data['box']])}   \n"
    if tsi_format:
        box_string = f"version 1.1\nbox   {box_string}"

    with open(file_path, mode="w", encoding="utf-8") as ofile:
        ofile.write(box_string)
        ofile.write(vertex_string)
        ofile.write(face_string)
        ofile.write(inclusion_string)


def write_star(records, path, sampling, shape=None, relion_5_format=False, **_):
    """Write records to a STAR file.

    Parameters
    ----------
    records : list of GeometryData
        Records to write.
    path : str
        Output path.
    sampling : float, optional
        Sampling override, None defaults to value associated with each record.
    shape : tuple of int, optional
        Tomogram shape; required when ``relion_5_format`` is True.
    relion_5_format : bool, optional
        Write origin-centered RELION-5 coordinates.
    """
    if relion_5_format and shape is None:
        raise ValueError("relion_5_format requires shape to be set.")

    prepared = _prepare_oriented_points(records, 1 if relion_5_format else sampling)
    points = prepared["points"]

    orientation_kwargs = {}
    if relion_5_format:
        shape_arr = np.asarray(shape)
        points = points - np.multiply(np.divide(shape_arr, 2).astype(int), sampling)
        orientation_kwargs["version"] = "# version 50001"

        n = points.shape[0]
        vp = prepared["vertex_properties"]
        vp.set_property("_rlnTomoSizeX", np.full(n, int(shape_arr[0])))
        vp.set_property("_rlnTomoSizeY", np.full(n, int(shape_arr[1])))
        vp.set_property("_rlnTomoSizeZ", np.full(n, int(shape_arr[2])))

    _write_orientations(
        points,
        prepared["quaternions"],
        prepared["entities"],
        path,
        file_format="star",
        vertex_properties=prepared["vertex_properties"],
        **orientation_kwargs,
    )

    if not relion_5_format:
        write_star_header(path, sampling)


def write_tsv(records, path, sampling, **_):
    """Write records to a tab-separated orientation file.

    Parameters
    ----------
    records : list of GeometryData
        Records to write.
    path : str
        Output path.
    sampling : float, optional
        Sampling override, None defaults to value associated with each record.
    """
    prepared = _prepare_oriented_points(records, sampling)
    _write_orientations(
        prepared["points"],
        prepared["quaternions"],
        prepared["entities"],
        path,
        file_format="tsv",
        vertex_properties=prepared["vertex_properties"],
    )


def write_xyz(records, path, sampling, **_):
    """Write records to a plain ``x,y,z`` CSV file.

    Parameters
    ----------
    records : list of GeometryData
        Records to write.
    path : str
        Output path.
    sampling : float, optional
        Sampling override, None defaults to value associated with each record.
    """
    prepared = _prepare_oriented_points(records, sampling)
    np.savetxt(path, prepared["points"], delimiter=",", header="x,y,z", comments="")


def write_ndjson(records, path, sampling, **_):
    """Write records as newline-delimited JSON oriented-point records.

    Parameters
    ----------
    records : list of GeometryData
        Records to write. All records flatten into one stream.
    path : str
        Output path.
    sampling : float, optional
        Sampling override, None defaults to value associated with each record.
    """
    from ..utils import _quat_to_matrix

    lines = []
    for rec in records:
        pts = np.divide(rec.vertices, sampling)
        matrices = _quat_to_matrix(_ensure_quaternions(rec))
        for pt, mat in zip(pts, matrices):
            lines.append(
                json.dumps(
                    {
                        "type": "orientedPoint",
                        "location": {
                            "x": float(pt[0]),
                            "y": float(pt[1]),
                            "z": float(pt[2]),
                        },
                        "xyz_rotation_matrix": mat.tolist(),
                    }
                )
            )

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def write_meshes(records, path, **_):
    """Write fitted mesh models to disk, merging records for single-file output.

    Records without a mesh-bearing model are skipped; if none remain,
    ``ValueError`` is raised.

    Parameters
    ----------
    records : list of GeometryData
        Source records.
    path : str
        Output path.
    """
    from ..parametrization import merge

    models = [r.model for r in records if hasattr(r.model, "mesh")]
    if not models:
        raise ValueError("No geometries have a fitted mesh model to export.")

    if len(models) == 1:
        return models[0].to_file(path)
    merge(models).to_file(path)


def write_volume(records, path, *, shape, sampling, **_):
    """Render records into a single labeled volume at the given sampling.

    Each record paints with its 1-based index as the label value; the
    dtype is the smallest integer type that fits, or ``float32``.

    Parameters
    ----------
    records : list of GeometryData
        Source records.
    path : str
        Output path (e.g. ``.mrc``, ``.em``, ``.h5``).
    shape : tuple of int
        Volume dimensions in voxels.
    sampling : float, optional
        Sampling override, None defaults to value associated with each record.
    """
    from ..utils import points_to_volume

    shape = tuple(int(x) for x in shape)

    max_index = len(records) + 1
    if max_index < np.iinfo(np.int8).max:
        dtype = np.int8
    elif max_index < np.iinfo(np.uint16).max:
        dtype = np.uint16
    else:
        dtype = np.float32

    volume = None
    for i, rec in enumerate(records):
        pts = np.divide(rec.vertices, sampling)
        volume = points_to_volume(
            pts,
            sampling_rate=1,
            shape=shape,
            weight=i + 1,
            out=volume,
            out_dtype=dtype,
        )

    from tme import Density

    Density(volume, sampling_rate=sampling, origin=0).to_file(path)


_FORMAT_MAPPING = {
    write_star: ("star",),
    write_tsv: ("tsv",),
    write_xyz: ("xyz",),
    write_ndjson: ("ndjson",),
    write_meshes: ("obj", "stl", "ply", "tsi", "q"),
    write_volume: ("mrc", "em", "h5"),
}


def resolve_writer(file_format: str):
    """Return the writer registered for *file_format*.

    Raises
    ------
    ValueError
        If no writer is registered for *file_format*.
    """
    for writer, formats in _FORMAT_MAPPING.items():
        if file_format in formats:
            return writer

    supported = ", ".join(f"'{x}'" for fmts in _FORMAT_MAPPING.values() for x in fmts)
    raise ValueError(f"Unsupported format '{file_format}', supported are {supported}.")


def write_geometries(
    geometries,
    file_path,
    *,
    format: str = "star",
    shape=None,
    sampling: float = None,
    relion_5_format: bool = False,
) -> None:
    """Export geometries to file.

    Parameters
    ----------
    geometries : list of Geometry
        Geometries to export.
    file_path : str or list of str
        Single string merges all geometries into one file; a list writes
        one file per geometry and must match ``geometries`` in length.
    format : str
        ``star``, ``tsv``, ``xyz``, ``ndjson`` (points);
        ``obj``, ``stl``, ``ply``, ``tsi``, ``q`` (meshes);
        ``mrc``, ``em``, ``h5`` (volumes).
    shape : tuple of (int, int, int), optional
        Volume grid for volume formats; origin for RELION-5 centering.
    sampling : float, optional
        Sampling override.
    relion_5_format : bool, optional
        Origin-centered RELION-5 STAR output.
    """
    if not len(geometries):
        return None

    records = _coerce_records(geometries)
    if sampling is None:
        # Mirror geometry.py:565: take the max sampling across records
        sampling = float(np.max([r.sampling for r in records]))

    if shape is None:
        bounds = np.max(
            [np.divide(r.vertices.max(axis=0), sampling) for r in records],
            axis=0,
        )
        shape = tuple(int(x + 1) for x in bounds.astype(int))
    else:
        shape = tuple(int(x) for x in shape)

    kwargs = dict(sampling=sampling, shape=shape, relion_5_format=relion_5_format)

    writer = resolve_writer(format)
    if isinstance(file_path, str):
        return writer(records, file_path, **kwargs)

    if len(file_path) != len(records):
        raise ValueError(
            f"file_path list length ({len(file_path)}) must match "
            f"geometries length ({len(records)})"
        )
    for record, path in zip(records, file_path):
        writer([record], path, **kwargs)
