""" IO methods to parse a variety of file formats.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import warnings
from string import ascii_lowercase

from typing import List, Dict
from dataclasses import dataclass
import xml.etree.ElementTree as ET

import numpy as np
import open3d as o3d
from scipy.spatial.transform import Rotation
from tme import Density, Structure, Orientations

from ..meshing.utils import to_open3d
from ..utils import volume_to_points, compute_bounding_box, NORMAL_REFERENCE


def _drop_prefix(iterable, target_length: int):
    if len(iterable) == target_length:
        iterable.pop(0)
    return iterable


def _parse_data_array(data_array: ET.Element, dtype: type = float) -> np.ndarray:
    """Parse a DataArray element into a numpy array."""
    rows = [row.strip() for row in data_array.text.strip().split("\n") if row.strip()]
    parsed_rows = [[dtype(x) for x in row.split()] for row in rows]
    data = np.array(parsed_rows)
    return np.squeeze(data)


def _parse_dtype(xml_element) -> object:
    data_type = float if xml_element.get("type", "").startswith("Float") else int
    return data_type


@dataclass
class GeometryData:
    vertices: np.ndarray = None
    normals: np.ndarray = None
    faces: np.ndarray = None
    quaternions: np.ndarray = None
    shape: List[int] = None
    sampling: List[float] = (1, 1, 1)


@dataclass
class GeometryDataContainer:
    vertices: List[np.ndarray] = None
    normals: List[np.ndarray] = None
    faces: List[np.ndarray] = None
    quaternions: List[np.ndarray] = None
    shape: List[int] = None
    sampling: List[float] = (1, 1, 1)

    def __post_init__(self):
        dtype_map = {
            "vertices": np.float32,
            "normals": np.float32,
            "faces": int,
            "quaternions": np.float32,
        }
        for attr_name, dtype in dtype_map.items():
            attr = getattr(self, attr_name)
            setattr(self, attr_name, self._to_dtype(attr, dtype))

        if self.normals is None:
            self.normals = [
                np.full_like(x, fill_value=NORMAL_REFERENCE) for x in self.vertices
            ]

        for i in range(len(self.normals)):
            norm = np.linalg.norm(self.normals[i], axis=1)
            mask = norm < 1e-12
            norm[mask] = 1
            self.normals[i][mask] = NORMAL_REFERENCE
            self.normals[i] = self.normals[i] / norm[:, None]

        if self.shape is None:
            self.shape, _ = compute_bounding_box(self.vertices)

        if len(self.vertices) != len(self.normals):
            raise ValueError("Normals need to be specified for each vertex set.")

        if self.faces is not None:
            if len(self.vertices) != len(self.faces):
                raise ValueError("Faces need to be specified for each vertex set.")

        if self.quaternions is None:
            self.quaternions = [None for x in self.vertices]

    def __len__(self):
        return len(self.vertices)

    def __iter__(self):
        yield from [self[i] for i in range(len(self))]

    def __getitem__(self, index: int) -> GeometryData:
        return GeometryData(
            vertices=self.vertices[index],
            normals=self.normals[index],
            shape=self.shape,
            sampling=self.sampling,
            faces=self.faces[index] if self.faces is not None else None,
            quaternions=self.quaternions[index],
        )

    @staticmethod
    def _to_dtype(data: List[np.ndarray], dtype=np.float32):
        if data is not None:
            return [x.astype(dtype) for x in data]
        return data


def _read_orientations(filename):
    data = Orientations.from_file(filename)
    angles = Rotation.from_euler("zyz", data.rotations, degrees=True)
    normals = angles.apply(NORMAL_REFERENCE)
    return {
        "vertices": [data.translations],
        "normals": [normals],
        "quaternions": [angles.as_quat(scalar_first=True)],
    }


def read_star(filename):
    return GeometryDataContainer(**_read_orientations(filename))


def read_txt(filename: str):
    ret = []

    delimiter = None
    if filename.endswith(("xyz", "csv")):
        delimiter = ","
    elif filename.endswith("txt"):
        delimiter = "\t"

    with open(filename, mode="r") as ifile:
        data = ifile.read().split()
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
    with open(filename, mode="r") as infile:
        header = infile.readline()
    if "euler" not in header:
        return read_txt(filename)
    return GeometryDataContainer(**_read_orientations(filename))


def read_tsi(filename: str) -> GeometryDataContainer:
    data = _read_tsi_file(filename)
    return _return_mesh(to_open3d(data["vertices"][:, 1:4], data["faces"][:, 1:4]))


def read_vtu(filename: str) -> GeometryDataContainer:
    data = _read_vtu_file(filename)
    return _return_mesh(to_open3d(data["points"], data["connectivity"]))


def read_mesh(filename: str) -> GeometryDataContainer:
    return _return_mesh(o3d.io.read_triangle_mesh(filename))


def _return_mesh(mesh: o3d.geometry.TriangleMesh) -> GeometryDataContainer:
    mesh.compute_vertex_normals()
    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.triangles)
    normals = np.asarray(mesh.vertex_normals)
    return GeometryDataContainer(vertices=[vertices], faces=[faces], normals=[normals])


def read_structure(filename: str) -> GeometryDataContainer:
    data = Structure.from_file(filename)
    return GeometryDataContainer(vertices=[data.atom_coordinate])


def read_volume(filename: str):
    volume = load_density(filename)

    ret = volume_to_points(volume.data, volume.sampling_rate, reverse_order=True)
    shape = np.multiply(volume.shape, volume.sampling_rate)
    return GeometryDataContainer(
        vertices=ret, shape=shape, sampling=volume.sampling_rate
    )


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
    Parse a VTK XML file into a dictionary of numpy arrays.

    Parameters
    ----------
    file_path : str
        The path to the topology file to be parsed.

    Returns
    -------
    Dict
        Topology file content.
    """
    with open(file_path, mode="r") as ifile:
        data = ifile.read()

    root = ET.fromstring(data)
    piece = root.find(".//Piece")

    result = {
        "num_points": int(piece.get("NumberOfPoints")),
        "num_cells": int(piece.get("NumberOfCells")),
        "point_data": {},
        "points": None,
        "connectivity": None,
        "offsets": None,
        "types": None,
    }

    # Parse point data arrays
    if (point_data := piece.find("PointData")) is not None:
        for array in point_data.findall("DataArray"):
            data_type = _parse_dtype(array)
            result["point_data"][array.get("Name")] = _parse_data_array(
                array, data_type
            )

    if (points_array := piece.find(".//Points/DataArray")) is not None:
        data_type = _parse_dtype(array)
        result["points"] = _parse_data_array(points_array, data_type)

    if (cells := piece.find("Cells")) is not None:
        for array in cells.findall("DataArray"):
            data_type = _parse_dtype(array)
            result[array.get("Name")] = _parse_data_array(array, float)

    return result


def load_density(filename: str, **kwargs) -> Density:
    volume = Density.from_file(filename, **kwargs)

    if np.allclose(volume.sampling_rate, 0):
        warnings.warn(
            "All sampling rates are 0 - Setting them to 1 for now. Some functions might"
            "not behave properly. Make sure to define sampling rates if you forgot."
        )
        volume.sampling_rate = 1

    return volume
