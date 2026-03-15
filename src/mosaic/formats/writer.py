import re
from typing import Dict
from os.path import splitext

import numpy as np

from ._utils import get_extension


def _sanitize_filename(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", "_", name).strip(". ")
    return name or "unnamed"


def _get_output_path(file_path, index, file_format, file_names=None):
    if file_names is not None and index < len(file_names):
        return f"{file_path}{_sanitize_filename(file_names[index])}.{file_format}"
    return f"{file_path}_{index}.{file_format}"


class OrientationsWriter:
    def __init__(
        self, points: np.ndarray, quaternions: np.ndarray, entities: np.ndarray
    ):
        """
        Initialize writer with point coordinates, quaternions, and entity labels.

        Parameters
        ----------
        points : np.ndarray
            Array of 3D point coordinates.
        quaternions : np.ndarray
            Array of quaternion rotations.
        entities : np.ndarray
            Array of entity labels for each point.
        """
        from ..utils import quat_to_euler

        self.entities = entities
        self.points = points

        # Until we find a better solution for the pipeline module, avoid
        # scipy.spatial.transform.Rotation due to threading complications
        self.rotations = quat_to_euler(quaternions, degrees=True, inv_quat=True)

    def to_file(self, file_path, file_format: str = None, **kwargs):
        """
        Write orientations data to file in specified format.

        Parameters
        ----------
        file_path : str
            Output file path.
        file_format : str, optional
            Output format, inferred from extension if None.
        **kwargs
            Additional keyword arguments passed to writer.

        Raises
        ------
        ValueError
            If the file format is not supported.
        """
        _supported_formats = ("tsv", "star")

        if file_format is None:
            file_format = get_extension(file_path)[1:]

        if file_format not in _supported_formats:
            formats = ", ".join([str(x) for x in _supported_formats])
            raise ValueError(f"Supported formats are {formats}.")
        return self._write_orientations(file_path, **kwargs)

    def _write_orientations(self, file_path, **kwargs):
        """
        Backend function for writing orientations to file.

        Parameters
        ----------
        file_path : str
            Output file path.
        **kwargs
            Additional keyword arguments passed to orientations writer.
        """
        from tme import Orientations

        orientations = Orientations(
            translations=self.points,
            rotations=self.rotations,
            scores=np.zeros(self.rotations.shape[0]),
            details=self.entities,
        )
        return orientations.to_file(file_path, **kwargs)


def write_density(
    data: np.ndarray, filename: str, sampling_rate: float = 1, origin: float = 0
) -> None:
    """
    Write 3D density data to file (typically in CCP4/MRC format).

    Parameters
    ----------
    data : np.ndarray
        3D density array.
    filename : str
        Output file path.
    sampling_rate : float, optional
        Sampling rate per voxel, by default 1 Angstrom / Voxel.
    origin : float, optional
        Origin offset for the density data in Angstrom, by default 0.
    """
    from tme import Density

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


def write_geometries(
    geometries,
    file_path: str,
    *,
    format: str = "star",
    single_file: bool = None,
    file_names=None,
    shape_x: int = None,
    shape_y: int = None,
    shape_z: int = None,
    sampling: float = None,
    relion_5_format: bool = False,
    **kwargs,
) -> None:
    """Export geometries to file.

    Parameters
    ----------
    geometries : list of Geometry
        Geometries to export.
    file_path : str
        Output file path (extension may be appended based on format).
    format : str
        Output format: star, tsv, xyz (point clouds),
        obj, stl, ply (meshes), mrc, em, h5 (volumes).
    single_file : bool, optional
        Merge all geometries into one file. Default is True for
        point/volume formats, False for meshes.
    file_names : list of str, optional
        Custom per-geometry file names (when not single_file).
    shape_x : int, optional
        Volume X dimension (inferred from data if not set).
    shape_y : int, optional
        Volume Y dimension.
    shape_z : int, optional
        Volume Z dimension.
    sampling : float, optional
        Override sampling rate for coordinate scaling.
    relion_5_format : bool, optional
        Apply RELION 5 coordinate transform.
    """
    from ..utils import points_to_volume, normals_to_rot, NORMAL_REFERENCE

    if not len(geometries):
        return None

    mesh_formats = ("obj", "stl", "ply")
    volume_formats = ("mrc", "em", "h5")
    point_formats = ("tsv", "star", "xyz")

    file_format = format
    file_path, _ = splitext(file_path)

    if shape_x is not None and shape_y is not None and shape_z is not None:
        shape = (shape_x, shape_y, shape_z)
    else:
        shape = np.max(
            [np.divide(x.points.max(axis=0), x.sampling_rate) for x in geometries],
            axis=0,
        )
        shape = tuple(int(x + 1) for x in shape.astype(int))

    meshes = []
    center, orientation_kwargs = 0, {}
    data = {"points": [], "quaternions": []}
    for index, geometry in enumerate(geometries):
        if file_format in mesh_formats:
            if not hasattr(geometry.model, "mesh"):
                continue
            meshes.append(geometry.model)
            continue

        points, normals, quaternions = (
            geometry.points,
            geometry.normals,
            geometry.quaternions,
        )
        if file_format in point_formats and quaternions is None:
            # At this point make up the normals
            if normals is None:
                normals = np.full_like(points, fill_value=NORMAL_REFERENCE)
            quaternions = normals_to_rot(normals, scalar_first=True)

        geom_sampling = sampling if sampling is not None else geometry.sampling_rate
        if relion_5_format:
            center = np.divide(shape, 2).astype(int) if shape is not None else 0
            center = np.multiply(center, geom_sampling)
            orientation_kwargs["version"] = "# version 50001"
            geom_sampling = 1

        points = np.subtract(np.divide(points, geom_sampling), center)
        data["points"].append(points)
        data["quaternions"].append(quaternions)

    if file_format in mesh_formats:
        is_single = single_file if single_file is not None else False
        if is_single:
            from ..parametrization import merge

            mesh = merge(meshes)
            mesh.to_file(f"{file_path}.{file_format}")
            meshes.clear()

        for index, mesh in enumerate(meshes):
            mesh.to_file(_get_output_path(file_path, index, file_format, file_names))

        return None

    if file_format in volume_formats:
        is_single = single_file if single_file is not None else True

        # Try saving some memory on write. uint8 would be padded to 16 hence int8
        dtype = np.float32
        max_index = len(data["points"]) + 1
        if max_index < np.iinfo(np.int8).max:
            dtype = np.int8
        elif max_index < np.iinfo(np.uint16).max:
            dtype = np.uint16

        volume, index = None, 0
        for file_index, points in enumerate(data["points"]):
            index += 1
            volume = points_to_volume(
                points,
                sampling_rate=1,
                shape=shape,
                weight=index,
                out=volume,
                out_dtype=dtype,
            )
            if not is_single:
                fname = _get_output_path(file_path, file_index, file_format, file_names)
                write_density(volume, filename=fname, sampling_rate=geom_sampling)
                volume, index = None, 0

        if is_single:
            fname = f"{file_path}.{file_format}"
            write_density(volume, filename=fname, sampling_rate=geom_sampling)

        return None

    if file_format not in point_formats:
        return None

    data["entities"] = [
        np.full(x.shape[0], fill_value=i) for i, x in enumerate(data["points"])
    ]
    is_single = single_file if single_file is not None else True
    if is_single:
        data = {k: [np.concatenate(v)] for k, v in data.items()}

    if file_format == "xyz":
        for index, points in enumerate(data["points"]):
            fname = _get_output_path(file_path, index, file_format, file_names)
            if is_single:
                fname = f"{file_path}.{file_format}"

            csv_header = ",".join(["x", "y", "z"])

            np.savetxt(fname, points, delimiter=",", header=csv_header, comments="")
        return 1

    for index in range(len(data["points"])):
        orientations = OrientationsWriter(**{k: v[index] for k, v in data.items()})
        fname = _get_output_path(file_path, index, file_format, file_names)
        if is_single:
            fname = f"{file_path}.{file_format}"
        orientations.to_file(fname, file_format=file_format, **orientation_kwargs)
