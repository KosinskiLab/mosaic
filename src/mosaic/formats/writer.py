from typing import Dict

import numpy as np
from scipy.spatial.transform import Rotation
from tme import Orientations, Density

from ._utils import get_extension


class OrientationsWriter:
    def __init__(
        self, points: np.ndarray, quaternions: np.ndarray, entities: np.ndarray
    ):
        self.entities = entities
        self.points = points
        self.rotations = Rotation.from_quat(quaternions, scalar_first=True)
        self.rotations = self.rotations.as_euler(seq="zyz", degrees=True)

    def to_file(self, file_path, file_format: str = None, **kwargs):
        _supported_formats = {"tsv": self._to_txt, "star": self._to_star}

        if file_format is None:
            file_format = get_extension(file_path)[1:]
        func = _supported_formats.get(file_format, None)
        if func is None:
            formats = ", ".join([str(x) for x in _supported_formats.keys()])
            raise ValueError(f"Supported formats are {formats}.")

        return func(file_path)

    def _to_txt(self, file_path):
        orientations = Orientations(
            translations=self.points,
            rotations=self.rotations,
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
            "_mosaicGroup",
        ]

        with open(file_path, "w") as f:
            f.write("\n".join(particle_header) + "\n")

            for i in range(self.points.shape[0]):
                x, y, z = self.points[i]
                rot, tilt, psi = self.rotations[i]
                mosaic_group = self.entities[i]

                particle_data = [
                    f"{x:.6f}",
                    f"{y:.6f}",
                    f"{z:.6f}",
                    f"{rot:.6f}",
                    f"{tilt:.6f}",
                    f"{psi:.6f}",
                    f"{mosaic_group}",
                ]
                f.write("\t".join(particle_data) + "\n")

        return None


def write_density(
    data: np.ndarray, filename: str, sampling_rate: float = 1, origin: float = 0
) -> None:
    return Density(data, sampling_rate=sampling_rate, origin=origin).to_file(filename)


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
