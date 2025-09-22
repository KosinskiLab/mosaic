"""
IO methods to parse a variety of file formats.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import warnings
from string import ascii_lowercase
from dataclasses import dataclass
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional

import numpy as np
from scipy.spatial.transform import Rotation
from tme import Density, Structure, Orientations

from ._utils import _drop_prefix
from ..meshing.utils import to_open3d
from ..utils import volume_to_points, compute_bounding_box, NORMAL_REFERENCE


def _parse_data_array(data_array: ET.Element, dtype: type = float) -> np.ndarray:
    """
    Parse a DataArray element into a numpy array.

    Parameters
    ----------
    data_array : ET.Element
        XML element containing array data.
    dtype : type, optional
        Data type for parsing, by default float.

    Returns
    -------
    np.ndarray
        Parsed numpy array.
    """
    rows = [row.strip() for row in data_array.text.strip().split("\n") if row.strip()]
    parsed_rows = [[dtype(x) for x in row.split()] for row in rows]
    data = np.array(parsed_rows)
    return np.squeeze(data)


def _parse_dtype(xml_element) -> object:
    """
    Determine data type from XML element type attribute.

    Parameters
    ----------
    xml_element : ET.Element
        XML element to parse type from.

    Returns
    -------
    object
        Data type (float or int).
    """
    return float if xml_element.get("type", "").startswith("Float") else int


@dataclass
class GeometryData:
    """
    Container for single geometry entity data.

    Parameters
    ----------
    vertices : np.ndarray, optional
        3D vertex coordinates.
    normals : np.ndarray, optional
        Normal vectors at each vertex.
    faces : np.ndarray, optional
        Face connectivity indices.
    quaternions : np.ndarray, optional
        Orientation quaternions for each vertex.
    vertex_properties : VertexPropertyContainer, optional
        Additional vertex properties.
    shape : List[int], optional
        Bounding box dimensions.
    sampling : List[float], optional
        Sampling rates along each axis, by default (1, 1, 1).
    """

    vertices: np.ndarray = None
    normals: np.ndarray = None
    faces: np.ndarray = None
    quaternions: np.ndarray = None
    vertex_properties: "VertexPropertyContainer" = None
    shape: List[int] = None
    sampling: List[float] = (1, 1, 1)


@dataclass
class GeometryDataContainer:
    """
    Container for multiple geometry entities with automatic validation.

    Parameters
    ----------
    vertices : List[np.ndarray], optional
        List of vertex arrays for each geometry entity.
    normals : List[np.ndarray], optional
        List of normal arrays for each geometry entity.
    faces : List[np.ndarray], optional
        List of face arrays for each geometry entity.
    quaternions : List[np.ndarray], optional
        List of quaternion arrays for each geometry entity.
    vertex_properties : List[VertexPropertyContainer], optional
        List of vertex property containers for each geometry entity.
    shape : List[int], optional
        Bounding box dimensions.
    sampling : List[float], optional
        Sampling rates along each axis, by default (1, 1, 1).
    """

    vertices: List[np.ndarray] = None
    normals: List[np.ndarray] = None
    faces: List[np.ndarray] = None
    quaternions: List[np.ndarray] = None
    vertex_properties: List["VertexPropertyContainer"] = None
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

        if self.vertex_properties is None:
            self.vertex_properties = [VertexPropertyContainer() for _ in self.vertices]

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
            vertex_properties=self.vertex_properties[index],
        )

    @staticmethod
    def _to_dtype(data: List[np.ndarray], dtype=np.float32):
        if data is not None:
            return [x.astype(dtype) for x in data]
        return data


class VertexPropertyContainer:
    """
    Container for managing custom vertex properties with automatic synchronization.

    Parameters
    ----------
    properties : dict of str -> np.ndarray, optional
        Dictionary mapping property names to vertex data arrays.
    """

    def __init__(self, properties: Optional[Dict[str, np.ndarray]] = None):
        """
        Initialize vertex property container.

        Parameters
        ----------
        properties : dict of str -> np.ndarray, optional
            Dictionary mapping property names to vertex data arrays
        """
        properties = {} if properties is None else properties
        properties = {name: np.asarray(data) for name, data in properties.items()}

        # We use len instead of size for future vector field support
        self._n_vertices = max((*(len(x) for x in properties.values()), 0))
        for name, data in properties.items():
            if len(data) == self._n_vertices:
                continue
            raise ValueError(
                f"Property '{name}' has {len(data)} values, "
                f"but expected {self._n_vertices} to match vertex count"
            )
        self._properties = properties

    def __getitem__(self, idx: str) -> "VertexPropertyContainer":
        """Array-like indexing using int/bool numpy arrays, slices or ellipses."""
        if not self._properties:
            return VertexPropertyContainer()

        if isinstance(idx, (int, np.integer)):
            idx = [idx]
        elif isinstance(idx, slice) or idx is ...:
            idx = np.arange(self._n_vertices)[idx]

        idx = np.asarray(idx)
        if idx.dtype == bool:
            idx = np.where(idx)[0]

        return VertexPropertyContainer(
            {k: v[idx].copy() for k, v in self._properties.items()}
        )

    @property
    def properties(self):
        """List available vertex properties."""
        return list(self._properties.keys())

    def get_property(self, name: str, default: Any = None) -> Optional[np.ndarray]:
        """Get property data by name."""
        return self._properties.get(name, default)

    def remove_property(self, name: str) -> None:
        _ = self._properties.pop(name, None)

    def copy(self) -> "VertexPropertyContainer":
        """Create a deep copy of the container."""
        return self[...]

    @classmethod
    def merge(
        cls, containers: List["VertexPropertyContainer"]
    ) -> "VertexPropertyContainer":
        """
        Merge multiple property containers.

        Parameters
        ----------
        containers : list of VertexPropertyContainer
            Containers to merge

        Returns
        -------
        VertexPropertyContainer
            New container with merged properties
        """
        containers = [c for c in containers if c._properties]
        if not containers:
            return cls()

        all_props = set(containers[0].properties)
        common_props = set(containers[0].properties)
        for container in containers[1:]:
            container_props = set(container.properties)

            common_props &= container_props
            all_props |= container_props

        if not common_props:
            warnings.warn("No common properties found across containers to merge")
            return cls()

        dropped_props = all_props - common_props
        if dropped_props:
            warnings.warn(
                f"Properties {sorted(dropped_props)} were not common across all "
                f"containers and were dropped during merge"
            )

        merged_props = {}
        for prop_name in common_props:
            merged_props[prop_name] = np.concatenate(
                [container.get_property(prop_name) for container in containers], axis=0
            )
        return cls(merged_props)


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
    data = Orientations.from_file(filename)

    # Remap as active (push) rotation
    angles = Rotation.from_euler(seq="ZYZ", angles=data.rotations, degrees=True).inv()

    normals = angles.apply(NORMAL_REFERENCE)
    quaternions = angles.as_quat(scalar_first=True)

    cluster = data.details.astype(int)
    indices = [np.where(cluster == x) for x in np.unique(cluster)]
    return {
        "vertices": [data.translations[x] for x in indices],
        "normals": [normals[x] for x in indices],
        "quaternions": [quaternions[x] for x in indices],
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
    return GeometryDataContainer(**_read_orientations(filename))


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
    if filename.endswith("csv"):
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
    data = _read_tsi_file(filename)
    mesh = to_open3d(data["vertices"][:, 1:4], data["faces"][:, 1:4])
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
    data = _read_vtu_file(filename)
    mesh = to_open3d(data["points"], data["connectivity"])
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
    mesh.compute_vertex_normals()
    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.triangles)
    normals = np.asarray(mesh.vertex_normals)

    return GeometryDataContainer(
        vertices=[vertices],
        faces=[faces],
        normals=[normals],
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
    data = Structure.from_file(filename)
    return GeometryDataContainer(vertices=[data.atom_coordinate])


def read_volume(filename: str):
    """
    Read 3D volume data and convert to point cloud.

    Parameters
    ----------
    filename : str
        Path to volume file.

    Returns
    -------
    GeometryDataContainer
        Parsed geometry data container.
    """
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
    volume = Density.from_file(filename, **kwargs)

    if np.allclose(volume.sampling_rate, 0):
        warnings.warn(
            "All sampling rates are 0 - Setting them to 1 for now. Some functions might"
            "not behave properly. Make sure to define sampling rates if you forgot."
        )
        volume.sampling_rate = 1

    return volume
