""" IO methods to parse a variety of file formats.

    Copyright (c) 2024 European Molecular Biology Laboratory

    Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import re
import warnings
import xml.etree.ElementTree as ET
from os import listdir
from typing import List, Dict
from os.path import basename, splitext, isdir, join

import numpy as np
import open3d as o3d
from numpy.typing import NDArray
from scipy.spatial.transform import Rotation
from tme import Density, Orientations
from tme.matching_utils import rotation_aligning_vectors

from .utils import volume_to_points, compute_bounding_box


class VertexDataLoader:
    def __init__(self):
        self._formats = {"star": read_star, "tsv": read_tsv}
        for ext in ["txt", "xyz", "csv"]:
            self._formats[ext] = read_txt
        for ext in ["stl", "obj"]:
            self._formats[ext] = read_mesh
        for ext in ["mrc", "em", "map", "h5", "mrc.gz", "em.gz", "map.gz"]:
            self._formats[ext] = read_volume
        for ext in ["q", "tsi"]:
            self._formats[ext] = read_topology_vertices
        for ext in ["vtu"]:
            self._formats[ext] = read_vtu_vertices

    @property
    def supported_formats(self) -> List[str]:
        return list(self._formats.keys())

    def open_file(self, filename: str, *args, **kwargs):
        base, extension = splitext(basename(filename))
        if extension.lower() == ".gz":
            _, extension = splitext(basename(base))

        extension = extension[1:]
        func = self._formats.get(extension, None)
        if func is None:
            raise ValueError(f"Unknown format with extension '{extension}'.")
        return func(filename, *args, **kwargs)


def read_star(filename):
    data = Orientations.from_file(filename)
    ret = [data.translations[:, ::-1]]
    angles = Rotation.from_euler(
        angles=data.rotations[:, ::-1], seq="zyx", degrees=True
    )
    normals = [angles.inv().as_matrix() @ np.array((1, 0, 0))]
    shape = compute_bounding_box(ret)
    return ret, normals, shape, (1, 1, 1)


def read_txt(filename: str):
    ret = []

    delimiter = None
    if filename.endswith("csv"):
        delimiter = ","
    elif filename.endswith("txt"):
        delimiter = "\t"

    data = np.loadtxt(filename, delimiter=delimiter)

    n_cols = data.shape[1]
    if n_cols < 3 or n_cols > 4:
        raise ValueError(
            f"{filename} needs to have 3 coordinate and optionally 1 cluster column."
        )

    if n_cols == 3:
        ret.append(data)
    elif n_cols == 4:
        unique_clusters = np.unique(data[:, 3])
        for cluster in unique_clusters:
            keep = data[:, 3] == cluster
            ret.append(data[keep, :3])

    shape = compute_bounding_box(ret)
    return ret, [np.zeros_like(x) for x in ret], shape, (1, 1, 1)


def read_tsv(filename: str):
    with open(filename, mode="r") as infile:
        header = infile.readline()
    if "euler" not in header:
        return read_txt(filename)

    orientations = Orientations.from_file(filename)
    data = [orientations.translations[:, ::-1]]
    angles = Rotation.from_euler(
        angles=orientations.rotations[:, ::-1], seq="zyx", degrees=True
    )
    normals = [angles.inv().as_matrix() @ np.array((1, 0, 0))]

    shape = compute_bounding_box(data)
    return data, normals, shape, (1, 1, 1)


def read_topology_vertices(filename: str):
    data = read_topology_file(filename)
    ret = [data["vertices"][:, 1:4]]
    shape = compute_bounding_box(ret)
    return ret, [np.zeros_like(x) for x in ret], shape, (1, 1, 1)


def read_vtu_vertices(filename: str):
    data = read_vtu_file(filename)
    ret = [data["points"].astype(np.float32)]
    shape = compute_bounding_box(ret)
    return ret, [np.zeros_like(x) for x in ret], shape, (1, 1, 1)


def read_volume(filename: str):
    volume = load_density(filename)

    ret = volume_to_points(volume.data, volume.sampling_rate)

    # Issue with jrc_macrophage-2/nucleus_seg
    # print(volume.sampling_rate)
    # if volume.sampling_rate[-1] == 64:
    # 64 * 30 instead of 64 * 30  - 53.76 * 25.2 ...
    # offset = np.array([0,0,1920])
    # ret = [x - offset for x in ret]

    shape = np.multiply(volume.shape, volume.sampling_rate)
    return ret, [np.zeros_like(x) for x in ret], shape, volume.sampling_rate


def read_mesh(filename: str):
    from .parametrization import TriangularMesh

    mesh = TriangularMesh(o3d.io.read_triangle_mesh(filename))
    ret = [np.asarray(mesh.mesh.vertices)]

    shape = compute_bounding_box(ret)
    return ret, [mesh.compute_vertex_normals(x) for x in ret], shape, (1, 1, 1)


class OrientationsWriter:
    def __init__(self, points: np.ndarray, normals: np.ndarray):
        self.entities = np.concatenate(
            [np.full(x.shape[0], fill_value=i) for i, x in enumerate(points)]
        )
        self.points, self.normals = np.concatenate(points), np.concatenate(normals)

        self.rotations = np.zeros_like(self.normals)
        for i in range(self.normals.shape[0]):
            self.rotations[i] = rotation_aligning_vectors(
                self.normals[i], target_vector=(1, 0, 0), convention="zyz"
            )

    def to_file(self, file_path, file_format):
        _supported_formats = {"tsv": self._to_txt, "star": self._to_star}

        func = _supported_formats.get(file_format, None)
        if func is None:
            formats = ", ".join([str(x) for x in _supported_formats.keys()])
            raise ValueError(f"Supported formats are {formats}.")

        return func(file_path)

    def _to_txt(self, file_path):
        rotations = Rotation.from_euler(angles=self.rotations, seq="zyz", degrees=True)
        orientations = Orientations(
            translations=self.points[:, ::-1],
            rotations=rotations.as_euler(seq="zyx", degrees=True)[:, ::-1],
            scores=np.zeros(self.rotations.shape[0]),
            details=self.entities,
        )
        return orientations.to_file(file_path, file_format="text")

    def _to_star(self, file_path):
        particle_header = [
            "data_particles",
            "",
            "loop_",
            "_rlnCoordinateX",
            "_rlnCoordinateY",
            "_rlnCoordinateZ",
            "_rlnAngleRot",
            "_rlnAngleTilt",
            "_rlnAnglePsi",
            "_colabsegGroup",
        ]

        with open(file_path, "w") as f:
            f.write("\n".join(particle_header) + "\n")

            for i in range(self.points.shape[0]):
                x, y, z = self.points[i]
                rot, tilt, psi = self.rotations[i]
                colabseg_group = self.entities[i]

                particle_data = [
                    f"{x:.6f}",
                    f"{y:.6f}",
                    f"{z:.6f}",
                    f"{rot:.6f}",
                    f"{tilt:.6f}",
                    f"{psi:.6f}",
                    f"{colabseg_group}",
                ]
                f.write("\t".join(particle_data) + "\n")

        return None


def _drop_prefix(iterable, target_length: int):
    if len(iterable) == target_length:
        iterable.pop(0)
    return iterable


def read_topology_file(file_path: str) -> Dict:
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

    return ret


def _parse_data_array(data_array: ET.Element, dtype: type = float) -> np.ndarray:
    """Parse a DataArray element into a numpy array."""
    rows = [row.strip() for row in data_array.text.strip().split("\n") if row.strip()]
    parsed_rows = [[dtype(x) for x in row.split()] for row in rows]
    data = np.array(parsed_rows)
    return np.squeeze(data)


def _parse_dtype(xml_element) -> object:
    data_type = float if xml_element.get("type", "").startswith("Float") else int
    return data_type


def read_vtu_file(file_path: str) -> Dict:
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


def load_density(filename: str) -> Density:
    volume = Density.from_file(filename)

    fname = filename.lower()
    if fname.endswith((".mrc", ".map", ".rec", "mrc.gz", "map.gz", "rec.gz")):
        volume.data = np.swapaxes(volume.data, 0, 2)
        volume.sampling_rate = volume.sampling_rate[::-1]

    if np.allclose(volume.sampling_rate, 0):
        warnings.warn(
            "All sampling rates are 0 - Setting them to 1 for now. Some functions might"
            "not behave properly. Make sure to define sampling rates if you forgot."
        )
        volume.sampling_rate = 1

    return volume


def write_density(
    data: np.ndarray, filename: str, sampling_rate: float = 1, origin: float = 0
) -> None:
    dens = Density(data, sampling_rate=sampling_rate, origin=origin)
    dens.data = np.swapaxes(dens.data, 0, 2)
    dens.sampling_rate = dens.sampling_rate[::-1]
    return dens.to_file(filename)


def write_topology_file(file_path: str, data: Dict) -> None:
    """
    Write a topology file [1]_.

    Parameters
    ----------
    file_path : str
        The path to the output file.
    data : Dict
        Topology file data as per :py:meth:`read_topology_file`.

    References
    ----------
    .. [1] https://github.com/weria-pezeshkian/FreeDTS/wiki/Manual-for-version-1
    """

    vertex_string = ""
    stop = data["vertices"].shape[1] - 1
    for i in range(data["vertices"].shape[0]):
        vertex_string += f"{int(data['vertices'][i, 0])}  "
        vertex_string += "  ".join([f"{x:<.10f}" for x in data["vertices"][i, 1:stop]])
        vertex_string += f"  {int(data['vertices'][i, stop])}\n"

    face_string = ""
    stop = data["faces"].shape[1] - 1
    for i in range(data["faces"].shape[0]):
        face = [f"{int(x):d}" for x in data["faces"][i]]
        face[1] += " "
        face.append("")
        face_string += "  ".join(face) + "\n"

    inclusion_string = ""
    inclusions = data.get("inclusions", None)
    if inclusions is not None:
        inclusion_string = f"inclusions {inclusions.shape[0]}\n"
        for i in range(data["inclusions"].shape[0]):
            inclusion_string += f"{'   '.join([f'{x}' for x in inclusions[i]])}   \n"

    with open(file_path, mode="w", encoding="utf-8") as ofile:
        ofile.write(f"{'   '.join([f'{x:<.10f}' for x in data['box']])}   \n")
        ofile.write(f"{data['n_vertices']}\n")
        ofile.write(vertex_string)
        ofile.write(f"{data['n_faces']}\n")
        ofile.write(face_string)
        ofile.write(inclusion_string)


def import_points(filename, scale=1, offset=1) -> List[NDArray]:
    ret = VertexDataLoader().open_file(filename=filename)

    if isinstance(ret, np.ndarray):
        data = [ret]

    if len(ret) == 4:
        data, normals, shape, sampling_rate = ret

    return [np.divide(np.subtract(x, offset), scale) for x in data], normals


def import_mesh(file: str) -> o3d.geometry.TriangleMesh:
    if file.endswith((".tsi", ".q")):
        data = read_topology_file(file)
        vertices = data["vertices"][:, 1:4]
        faces = data["faces"][:, 1:4]
    elif file.endswith(".vtu"):
        data = read_vtu_file(file)
        vertices = data["points"].astype(np.float32)
        faces = data["connectivity"].astype(int)
    else:
        data = o3d.io.read_triangle_mesh(file)
        vertices = np.asarray(data.vertices).astype(np.float32)
        faces = np.asarray(data.triangles).astype(int)

    return vertices, faces


def import_mesh_trajectory(path: str) -> List[List[np.ndarray]]:
    files = [path]
    if isdir(path):
        files = [join(path, x) for x in listdir(path)]

    files = [x for x in files if x.endswith(".tsi") or x.endswith(".vtu")]
    files = sorted(files, key=lambda x: int(re.findall(r"\d+", basename(x))[0]))

    ret = []
    for file in files:
        vertices, faces = import_mesh(file)
        ret.append((vertices, faces, file))

    return ret
