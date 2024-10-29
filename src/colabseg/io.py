import warnings
from typing import List
from os.path import basename, splitext

import numpy as np
import open3d as o3d
from numpy.typing import NDArray
from scipy.spatial.transform import Rotation

from tme import Density, Orientations
from tme.matching_utils import rotation_aligning_vectors


class DataIO:
    def __init__(self):
        self._formats = {"txt": _load_txt}
        for ext in ["stl", "obj"]:
            self._formats[ext] = _load_mesh
        for ext in ["mrc", "em", "h5"]:
            self._formats[ext] = _load_volume

    @property
    def supported_formats(self):
        return list(self._formats.keys())

    def open_file(self, filename: str, *args, **kwargs):
        extension = splitext(basename(filename))[1][1:]

        func = self._formats.get(extension, _load_volume)
        return func(filename, *args, **kwargs)


def load_density(filename: str):
    volume = Density.from_file(filename)
    volume.data = np.swapaxes(volume.data, 0, 2)
    volume.sampling_rate = volume.sampling_rate[::-1]
    return volume


def _load_volume(filename: str):
    volume = load_density(filename)

    points = np.where(volume.data > 0)
    points_cluster = volume.data[points]

    points = np.multiply(np.array(points).T, volume.sampling_rate)
    unique_clusters = np.unique(points_cluster)
    if unique_clusters.size > 10000:
        warnings.warn(
            "Found more than 10k cluster. Make sure you are loading a segmentation."
        )

    ret = []
    for cluster in unique_clusters:
        indices = np.where(points_cluster == cluster)
        ret.append(points[indices])

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
        _supported_formats = {"txt": self._to_txt, "star": self._to_star}

        func = _supported_formats.get(file_format, None)
        if func is None:
            raise ValueError(f"Supported formats are {_supported_formats.keys()}")

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
