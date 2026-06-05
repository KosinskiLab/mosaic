"""
IO methods to parse a variety of file formats.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import struct
import warnings
from io import BytesIO
from string import ascii_lowercase
from typing import Dict

import numpy as np
from gzip import open as gzip_open

from .records import (
    GeometryData,
    GeometryDataContainer,
    NotASegmentationError,
    VertexPropertyContainer,
)

__all__ = [
    "GeometryData",
    "GeometryDataContainer",
    "NotASegmentationError",
    "VertexPropertyContainer",
    "is_gzipped",
    "load_density",
    "points_from_flat_array",
    "read_mesh",
    "read_mrc_dtype",
    "read_mrc_flat",
    "read_ndjson",
    "read_star",
    "read_structure",
    "read_tsi",
    "read_tsv",
    "read_txt",
    "read_volume",
    "read_vtu",
    "resolve_parser",
]


def is_gzipped(filename: str) -> bool:
    """Check if a file is a gzip file by reading its magic number."""
    with open(filename, "rb") as f:
        return f.read(2) == b"\x1f\x8b"


def _read_orientations(filename: str):
    """
    Read orientation data from file and convert to geometry format.

    Parameters
    ----------
    filename : str
        Path to orientation file.

    Returns
    -------
    dict
        Dictionary containing vertices, normals, and quaternions.
    """
    from tme import Orientations
    from scipy.spatial.transform import Rotation
    from ..utils import NORMAL_REFERENCE

    data = Orientations.from_file(filename)

    # Remap as active (push) rotation
    angles = Rotation.from_euler(seq="ZYZ", angles=data.rotations, degrees=True).inv()

    normals = angles.apply(NORMAL_REFERENCE)
    quaternions = angles.as_quat(scalar_first=True)
    indices = [np.where(data.details == x) for x in np.unique(data.details)]

    # Collect extra per-particle metadata when available (pytme >= 0.3.4).
    extra_metadata = getattr(data, "metadata", None) or {}
    extra_metadata = {
        k: v
        for k, v in extra_metadata.items()
        if isinstance(v, np.ndarray) and v.shape[0] == data.translations.shape[0]
    }

    try:
        vertex_properties = []
        for x in indices:
            props = {
                "pytme_score": data.scores[x],
                "entity": data.details[x],
            }
            for key, val in extra_metadata.items():
                props[key] = val[x]
            vertex_properties.append(VertexPropertyContainer(props))
    except Exception:
        vertex_properties = None

    return {
        "vertices": [data.translations[x] for x in indices],
        "normals": [normals[x] for x in indices],
        "quaternions": [quaternions[x] for x in indices],
        "vertex_properties": vertex_properties,
    }


def read_star(filename: str):
    """
    Read RELION star file format.

    Parameters
    ----------
    filename : str
        Path to star file.

    Returns
    -------
    GeometryDataContainer
        Parsed geometry data container.
    """
    from ._utils import read_star_header

    kwargs = _read_orientations(filename)
    pixel_size = read_star_header(filename).get("pixel_size")
    if pixel_size:
        kwargs["sampling"] = (pixel_size, pixel_size, pixel_size)
    return GeometryDataContainer(**kwargs)


def read_txt(filename: str):
    """
    Read text-based point cloud files.

    Parameters
    ----------
    filename : str
        Path to text file (txt, csv, xyz).

    Returns
    -------
    GeometryDataContainer
        Parsed geometry data container.
    """
    ret = []

    delimiter = None
    if filename.endswith(("csv", "xyz")):
        delimiter = ","
    elif filename.endswith(("txt", "tsv")):
        delimiter = "\t"

    with open(filename, mode="r") as ifile:
        data = ifile.read().split("\n")
        data = [x.strip().split(delimiter) for x in data if x.strip()]

    header = ("x", "y", "z", *ascii_lowercase)[: len(data[0])]
    if "x" in data[0]:
        header = data.pop(0)

    required_columns = ("x", "y", "z")
    for rc in required_columns:
        if rc in header:
            continue
        raise ValueError(f"Colums {required_columns} are required.")

    data = {c: np.asarray(d) for c, d in zip(header, zip(*data))}

    if "id" in data:
        ret = []
        for cluster in np.unique(data["id"]):
            ret.append({c: d[data["id"] == cluster] for c, d in data.items()})
        data = ret
    else:
        data = [data]

    vertices, normals, quaternions = [], [], []
    for cluster in data:
        cols = ("x", "y", "z")
        vertices.append((np.hstack([cluster[k][:, None] for k in cols])))
        try:
            cols = ("nx", "ny", "nz")
            normals.append((np.hstack([cluster[k][:, None] for k in cols])))
        except Exception as e:
            continue

    if len(normals) == 0:
        normals = None

    return GeometryDataContainer(vertices=vertices, normals=normals)


def read_tsv(filename: str) -> GeometryDataContainer:
    """
    Read tab-separated values file with orientation data.

    Parameters
    ----------
    filename : str
        Path to tsv file.

    Returns
    -------
    GeometryDataContainer
        Parsed geometry data container.
    """
    with open(filename, mode="r") as infile:
        header = infile.readline()
    if "euler" not in header:
        return read_txt(filename)
    return GeometryDataContainer(**_read_orientations(filename))


def read_tsi(filename: str) -> GeometryDataContainer:
    """
    Read topology surface information file format.

    Parameters
    ----------
    filename : str
        Path to tsi file.

    Returns
    -------
    GeometryDataContainer
        Parsed geometry data container.
    """
    from .. import meshing

    data = _read_tsi_file(filename)
    mesh = meshing.utils.to_open3d(data["vertices"][:, 1:4], data["faces"][:, 1:4])
    vertex_properties = {}

    try:
        if "inclusions" in data:
            inclusions = np.zeros((len(data["vertices"])))
            inclusion_type = data["inclusions"][:, 1]
            inclusion_vert = data["inclusions"][:, 2].astype(int)
            inclusions[inclusion_vert] = inclusion_type
            vertex_properties = {"inclusion": inclusions}
    except Exception:
        pass
    return _return_mesh(mesh, vertex_properties=vertex_properties)


def read_vtu(filename: str) -> GeometryDataContainer:
    """
    Read VTK unstructured grid XML file format.

    Parameters
    ----------
    filename : str
        Path to vtu file.

    Returns
    -------
    GeometryDataContainer
        Parsed geometry data container.
    """
    from .. import meshing

    data = _read_vtu_file(filename)
    mesh = meshing.utils.to_open3d(data["points"], data["connectivity"])
    return _return_mesh(mesh, vertex_properties=data.get("point_data", {}))


def read_mesh(filename: str) -> GeometryDataContainer:
    """
    Read 3D mesh files using Open3D.

    Parameters
    ----------
    filename : str
        Path to mesh file.

    Returns
    -------
    GeometryDataContainer
        Parsed geometry data container.
    """
    import open3d as o3d

    return _return_mesh(o3d.io.read_triangle_mesh(filename))


def _return_mesh(mesh, vertex_properties: dict = None) -> GeometryDataContainer:
    """
    Convert Open3D mesh to GeometryDataContainer.

    Parameters
    ----------
    mesh : o3d.geometry.TriangleMesh
        Open3D triangle mesh object.
    vertex_properties : dict, optional
        Vertex property data.

    Returns
    -------
    GeometryDataContainer
        Converted geometry data container.
    """
    return GeometryDataContainer(
        vertices=[np.asarray(mesh.vertices)],
        faces=[np.asarray(mesh.triangles)],
        normals=[
            np.asarray(mesh.vertex_normals) if mesh.has_vertex_normals() else None
        ],
        vertex_properties=[VertexPropertyContainer(vertex_properties)],
    )


def read_structure(filename: str) -> GeometryDataContainer:
    """
    Read molecular structure files.

    Parameters
    ----------
    filename : str
        Path to structure file (pdb, cif, gro).

    Returns
    -------
    GeometryDataContainer
        Parsed geometry data container.
    """
    from tme import Structure

    data = Structure.from_file(filename)
    return GeometryDataContainer(vertices=[data.atom_coordinate])


def read_volume(filename: str):
    """
    Read 3D volume data and convert to point clouds.

    Parameters
    ----------
    filename : str
        Path to volume file.

    Returns
    -------
    GeometryDataContainer
        Parsed geometry data container.
    """
    data, dims, spacing, axis_order = read_mrc_flat(filename)
    if data is not None:
        ret = points_from_flat_array(data, dims)

        if axis_order != (0, 1, 2):
            perm = np.argsort(axis_order)
            ret = [pts[:, perm] for pts in ret]
            dims = tuple(dims[i] for i in perm)

        shape = np.asarray(dims, dtype=np.float32)
    else:
        volume = load_density(filename, use_memmap=False)
        spacing = np.asarray(volume.sampling_rate, dtype=np.float32)
        ret = points_from_flat_array(volume.data.ravel(), volume.shape)
        shape = np.asarray(volume.shape, dtype=np.float32)
    return GeometryDataContainer(vertices=ret, shape=shape, sampling=spacing)


def read_mrc_dtype(filepath):
    """Return the NumPy dtype of an MRC file from its header, or None.

    Only reads the first 1024 bytes. Returns None for non-MRC files or
    unrecognised mode values.
    """
    _MRC_DTYPES = {
        0: np.int8,
        1: np.int16,
        2: np.float32,
        4: np.complex64,
        6: np.uint16,
        12: np.float16,
    }

    opener = gzip_open if is_gzipped(filepath) else open
    with opener(filepath, "rb") as fh:
        header = fh.read(1024)

    if len(header) < 1024 or header[208:212] != b"MAP ":
        return None

    nc_le = struct.unpack_from("<i", header, 0)[0]
    endian = "<" if 0 < nc_le < 65536 else ">"
    mode = struct.unpack_from(f"{endian}i", header, 12)[0]
    return _MRC_DTYPES.get(mode)


def read_mrc_flat(filepath):
    """Read an MRC file into a flat buffer.

    Returns
    -------
    tuple
        ``(array, dims, spacing, axis_order)`` or
        ``(None, None, None, None)``.
    """
    _MRC_DTYPES = {
        0: np.int8,
        1: np.int16,
        2: np.float32,
        4: np.complex64,
        6: np.uint16,
        12: np.float16,
    }

    opener = gzip_open if is_gzipped(filepath) else open
    with opener(filepath, "rb") as fh:
        if is_gzipped(filepath):
            fh = BytesIO(fh.read())

        header = fh.read(1024)
        if len(header) < 1024 or header[208:212] != b"MAP ":
            return (None, None, None, None)

        nc_le = struct.unpack_from("<i", header, 0)[0]
        endian = "<" if 0 < nc_le < 65536 else ">"

        grid = struct.unpack_from(f"{endian}3i", header, 0)
        mode = struct.unpack_from(f"{endian}i", header, 12)[0]
        cell = struct.unpack_from(f"{endian}3f", header, 40)
        mapc, mapr, maps = struct.unpack_from(f"{endian}3i", header, 64)
        nsymbt = struct.unpack_from(f"{endian}i", header, 92)[0]

        if (dtype := _MRC_DTYPES.get(mode)) is None:
            return (None, None, None, None)

        if not (1 <= mapc <= 3 and 1 <= mapr <= 3 and 1 <= maps <= 3):
            mapc, mapr, maps = 1, 2, 3

        axis_order = (mapc - 1, mapr - 1, maps - 1)
        spacing = np.array(
            [cell[a] / max(grid[i], 1) for i, a in enumerate(axis_order)],
            dtype=np.float32,
        )

        fh.seek(1024 + nsymbt)
        data = np.frombuffer(fh.read(), dtype=dtype)
        if endian == ">":
            data = data.byteswap().newbyteorder("=")

        return data, grid, spacing, axis_order


def points_from_flat_array(arr, dims, max_cluster=10000):
    """Extract per-label point clouds from a flat voxel array.

    Parameters
    ----------
    arr : ndarray
        Flat 1D array of voxel labels.
    dims : tuple
        Volume dimensions ``(nx, ny, nz)``.
    max_cluster : int
        Reject if more unique sampled values than this.

    Returns
    -------
    list of ndarray
        One ``(N, 3)`` float32 point array of voxel indices per label.

    Raises
    ------
    NotASegmentationError
        If the sampled unique-value count exceeds ``max_cluster``.
    """
    rng = np.random.default_rng()
    sample = arr[rng.integers(0, arr.size, size=min(125_000, arr.size))]
    unique_count = len(np.unique(sample))
    if unique_count > max_cluster:
        raise NotASegmentationError(
            f"Found {unique_count} unique values (limit: {max_cluster}). "
            f"This looks like a density map, not a segmentation."
        )

    flat = np.where(arr != 0)[0]
    if flat.size == 0:
        return []

    labels = arr[flat]
    order = labels.argsort(kind="stable")
    sorted_labels = labels[order]

    coords = np.array(
        np.unravel_index(flat[order], dims, order="F"),
        dtype=np.float32,
    ).T

    splits = np.flatnonzero(np.diff(sorted_labels)) + 1
    bounds = np.concatenate([[0], splits, [len(order)]])

    return [coords[bounds[i] : bounds[i + 1]] for i in range(len(bounds) - 1)]


def _read_tsi_file(file_path: str) -> Dict:
    """
    Reads a topology file [1]_.

    Parameters
    ----------
    file_path : str
        The path to the topology file to be parsed.

    Returns
    -------
    Dict
        Topology file content.

    References
    ----------
    .. [1] https://github.com/weria-pezeshkian/FreeDTS/wiki/Manual-for-version-1
    """
    from ._utils import _drop_prefix

    _keys = ("version", "box", "n_vertices", "vertices", "n_faces", "faces")
    ret = {k: None for k in _keys}

    with open(file_path, mode="r", encoding="utf-8") as infile:
        data = [x.strip() for x in infile.read().split("\n") if len(x.strip())]

    # Version prefix
    if "version" in data[0]:
        ret["version"] = data.pop(0).split()[1]

    # Box prefix
    box = _drop_prefix(data.pop(0).split(), 4)
    ret["box"] = tuple(float(x) for x in box)

    # Vertex prefix
    n_vertices = _drop_prefix(data.pop(0).split(), 2)
    n_vertices = int(n_vertices[0])
    vertices, data = data[:n_vertices], data[n_vertices:]
    ret["n_vertices"] = n_vertices
    ret["vertices"] = np.array([x.split() for x in vertices], dtype=np.float64)

    # Face prefix
    n_faces = _drop_prefix(data.pop(0).split(), 2)
    n_faces = int(n_faces[0])
    faces, data = data[:n_faces], data[n_faces:]
    ret["n_faces"] = n_faces
    ret["faces"] = np.array([x.split() for x in faces], dtype=np.float64)

    while len(data):
        if not data[0].startswith("inclusion"):
            data.pop(0)
        break

    if len(data) == 0:
        return ret

    n_inclusions = _drop_prefix(data.pop(0).split(), 2)
    n_inclusions = int(n_inclusions[0])
    incl, data = data[:n_inclusions], data[n_inclusions:]
    ret["n_inclusions"] = n_inclusions
    ret["inclusions"] = np.array([x.split() for x in incl], dtype=np.float64)

    return ret


def _read_vtu_file(file_path: str) -> Dict:
    """
    Parse a VTK XML UnstructuredGrid file into a dictionary of numpy arrays.

    Parameters
    ----------
    file_path : str
        The path to the topology file to be parsed.

    Returns
    -------
    Dict
        Topology file content.
    """
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy

    reader = vtk.vtkXMLUnstructuredGridReader()
    reader.SetFileName(file_path)
    reader.Update()
    grid = reader.GetOutput()

    points = vtk_to_numpy(grid.GetPoints().GetData())
    cells = grid.GetCells()
    connectivity = vtk_to_numpy(cells.GetConnectivityArray())

    # vtkCellArray offsets are length num_cells+1 with a leading 0. The legacy
    # XML representation stores only the trailing offsets.
    offsets = vtk_to_numpy(cells.GetOffsetsArray())[1:]
    types = vtk_to_numpy(grid.GetCellTypes())

    if offsets.size:
        starts = np.concatenate(([0], offsets[:-1]))
        strides = offsets - starts
        if np.all(strides == strides[0]):
            connectivity = connectivity.reshape(-1, int(strides[0]))

    pd = grid.GetPointData()
    point_data: Dict[str, np.ndarray] = {}
    for i in range(pd.GetNumberOfArrays()):
        arr = vtk_to_numpy(pd.GetArray(i))
        if arr.ndim == 2 and arr.shape[1] == 1:
            arr = arr.reshape(-1)
        point_data[pd.GetArrayName(i)] = arr

    return {
        "num_points": grid.GetNumberOfPoints(),
        "num_cells": grid.GetNumberOfCells(),
        "point_data": point_data,
        "points": points,
        "connectivity": connectivity,
        "offsets": offsets,
        "types": types,
    }


def load_density(filename: str, **kwargs):
    """
    Load 3D density data from file.

    Parameters
    ----------
    filename : str
        Path to density file.
    **kwargs
        Additional keyword arguments passed to Density.from_file.

    Returns
    -------
    Density
        Loaded density object.
    """
    from tme import Density

    volume = Density.from_file(filename, **kwargs)

    if np.allclose(volume.sampling_rate, 0):
        warnings.warn(
            "All sampling rates are 0 - Setting them to 1 for now. Some functions might"
            "not behave properly. Make sure to define sampling rates if you forgot."
        )
        volume.sampling_rate = 1

    return volume


def read_ndjson(filename: str) -> GeometryDataContainer:
    """Read a newline-delimited JSON annotation file.

    Supports OrientedPoint (with rotation matrices), Point, and
    InstanceSegmentation records.  The shape type is inferred from
    the first record.

    Parameters
    ----------
    filename : str
        Path to the ndjson file.

    Returns
    -------
    GeometryDataContainer
        Parsed geometry data container.
    """
    import json
    from scipy.spatial.transform import Rotation
    from ..utils import NORMAL_REFERENCE

    records = []
    with open(filename, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if not records:
        return GeometryDataContainer(vertices=[np.empty((0, 3), dtype=np.float32)])

    first = records[0]

    if "xyz_rotation_matrix" in first:
        points = np.array(
            [
                [r["location"]["x"], r["location"]["y"], r["location"]["z"]]
                for r in records
            ],
            dtype=np.float32,
        )
        rotations = Rotation.from_matrix(
            np.array([r["xyz_rotation_matrix"] for r in records], dtype=np.float64)
        )
        return GeometryDataContainer(
            vertices=[points],
            normals=[rotations.apply(NORMAL_REFERENCE).astype(np.float32)],
            quaternions=[rotations.as_quat(scalar_first=True).astype(np.float32)],
        )

    if "instance_id" in first:
        instances = {}
        for r in records:
            iid = r.get("instance_id", 0)
            loc = r["location"]
            instances.setdefault(iid, []).append([loc["x"], loc["y"], loc["z"]])
        vertices, properties = [], []
        for iid in sorted(instances):
            pts = np.array(instances[iid], dtype=np.float32)
            vertices.append(pts)
            properties.append(
                VertexPropertyContainer(
                    {"instance_id": np.full(len(pts), iid, dtype=np.int32)}
                )
            )
        return GeometryDataContainer(
            vertices=vertices,
            vertex_properties=properties,
        )

    points = np.array(
        [[r["location"]["x"], r["location"]["y"], r["location"]["z"]] for r in records],
        dtype=np.float32,
    )
    return GeometryDataContainer(vertices=[points])


_FORMAT_MAPPING = {
    read_star: ("star",),
    read_tsv: ("tsv",),
    read_txt: ("txt", "xyz", "csv"),
    read_mesh: ("obj", "ply", "stl", "off", "gltf", "glb", "fbx"),
    read_volume: ("mrc", "em", "map", "h5", "nrrd", "nii"),
    read_tsi: ("q", "tsi"),
    read_vtu: ("vtu",),
    read_structure: ("pdb", "cif", "gro"),
    read_ndjson: ("ndjson",),
}


def resolve_parser(extension: str):
    """Return the parser registered for *extension*.

    Raises
    ------
    ValueError
        If no parser is registered for *extension*.
    """
    for parser, formats in _FORMAT_MAPPING.items():
        if extension in formats:
            return parser

    supported = ", ".join(f"'{x}'" for fmts in _FORMAT_MAPPING.values() for x in fmts)
    raise ValueError(f"Unknown extension '{extension}', supported are {supported}.")
