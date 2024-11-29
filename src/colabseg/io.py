import warnings
from typing import List, Dict
from os.path import basename, splitext

import numpy as np
import open3d as o3d
from numpy.typing import NDArray
from scipy.spatial.transform import Rotation

from .utils import volume_to_points

from tme import Density, Orientations
from tme.matching_utils import rotation_aligning_vectors


class DataIO:
    def __init__(self):
        self._formats = {"txt": _load_txt, "tsv": _load_txt}
        for ext in ["stl", "obj"]:
            self._formats[ext] = _load_mesh
        for ext in ["mrc", "em", "h5"]:
            self._formats[ext] = _load_volume
        for ext in ["q", "tsi"]:
            self._formats[ext] = _load_topology_file

    @property
    def supported_formats(self):
        return list(self._formats.keys())

    def open_file(self, filename: str, *args, **kwargs):
        extension = splitext(basename(filename))[1][1:]

        func = self._formats.get(extension, _load_volume)
        return func(filename, *args, **kwargs)


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


def _numpy_to_string(arr: NDArray) -> str:
    ret = ""
    stop = arr.shape[1] - 1
    for i in range(arr.shape[0]):
        ret += f"{int(arr[i, 0])}  "
        ret += "  ".join([str(x) for x in arr[i, 1:stop]])
        ret += f"  {int(arr[i, stop])}\n"
    return ret


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

    with open(file_path, mode="w", encoding="utf-8") as ofile:
        ofile.write(f"{'   '.join([f'{x:<.10f}' for x in data['box']])}   \n")
        ofile.write(f"{data['n_vertices']}\n")
        ofile.write(vertex_string)
        ofile.write(f"{data['n_faces']}\n")
        ofile.write(face_string)


def _load_topology_file(filename):
    data = read_topology_file(filename)
    return data["vertices"][:, 1:4]


def load_density(filename: str):
    volume = Density.from_file(filename)
    volume.data = np.swapaxes(volume.data, 0, 2)
    volume.sampling_rate = volume.sampling_rate[::-1]

    if np.allclose(volume.sampling_rate, 0):
        warnings.warn(
            "All sampling rates are 0 - Setting them to 1 for now. Some functions might"
            "not behave properly. Make sure to define sampling rates if you forgot."
        )
        volume.sampling_rate = 1

    return volume


def write_density(data, filename, sampling_rate=1, origin=0):
    dens = Density(data, sampling_rate=sampling_rate, origin=origin)
    dens.data = np.swapaxes(dens.data, 0, 2)
    dens.sampling_rate = dens.sampling_rate[::-1]
    return dens.to_file(filename)


def _load_volume(filename: str):
    volume = load_density(filename)

    ret = volume_to_points(volume.data, volume.sampling_rate)
    shape = np.multiply(volume.shape, volume.sampling_rate)
    return ret, shape, volume.sampling_rate


def _load_txt(filename: str):
    ret = []
    data = np.loadtxt(filename)

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

    shape = _compute_bounding_box(ret)
    return ret, shape, (1, 1, 1)


def _load_mesh(filename: str):
    mesh = o3d.io.read_triangle_mesh(filename)
    ret = [np.asarray(mesh.vertices)]

    shape = _compute_bounding_box(ret)
    return ret, shape, (1, 1, 1)


def _compute_bounding_box(points: List[NDArray]) -> List[float]:
    if len(points) == 0:
        return (0, 0, 0)
    starts = points[0].min(axis=0)
    stops = points[0].max(axis=0)
    for point in points[1:]:
        starts_inner = point.min(axis=0)
        stops_inner = point.max(axis=0)
        starts = np.minimum(starts, starts_inner)
        stops = np.maximum(stops, stops_inner)

    return stops - starts


def import_points(filename, scale=1, offset=1) -> List[NDArray]:
    ret = DataIO().open_file(filename=filename)

    if isinstance(ret, np.ndarray):
        data = [ret]

    if len(ret) == 3:
        data, shape, sampling_rate = ret

    return [np.divide(np.subtract(x, offset), scale) for x in data]


class OrientationsIO:
    def __init__(self, points, normals):
        print(points)
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
            translations=self.points,
            rotations=rotations.as_euler(seq="zyx", degrees=True),
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
