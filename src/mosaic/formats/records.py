"""
Shared data records used by readers and writers.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import warnings
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np


class NotASegmentationError(ValueError):
    """Raised when a volume cannot be interpreted as a segmentation.

    The sampled unique-value count exceeded ``max_cluster``, indicating
    the file is most likely a density map rather than a label map. The
    caller should offer to render it as a volume instead.
    """


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
    model : Any, optional
        Fitted model (e.g. a TriangularMesh instance).
    """

    vertices: np.ndarray = None
    normals: np.ndarray = None
    faces: np.ndarray = None
    quaternions: np.ndarray = None
    vertex_properties: "VertexPropertyContainer" = None
    shape: List[int] = None
    sampling: List[float] = (1, 1, 1)
    model: Any = None


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
        from ..utils import compute_bounding_box, NORMAL_REFERENCE

        dtype_map = {
            "vertices": np.float32,
            "normals": np.float32,
            "faces": int,
            "quaternions": np.float32,
        }

        if self.normals is None:
            self.normals = [None for x in self.vertices]

        for i in range(len(self.normals)):
            if self.normals[i] is None:
                continue
            norm = np.linalg.norm(self.normals[i], axis=1)
            mask = norm < 1e-12
            norm[mask] = 1
            self.normals[i][mask] = NORMAL_REFERENCE
            self.normals[i] = self.normals[i] / norm[:, None]

        if self.quaternions is None:
            self.quaternions = [None for x in self.vertices]

        if self.vertex_properties is None:
            self.vertex_properties = [VertexPropertyContainer() for _ in self.vertices]

        for attr_name, dtype in dtype_map.items():
            attr = getattr(self, attr_name)
            setattr(self, attr_name, self._to_dtype(attr, dtype))

        if self.shape is None:
            shape, starts = compute_bounding_box(self.vertices)
            self.shape = np.add(shape, starts)

        if len(self.vertices) != len(self.normals):
            raise ValueError("Normals need to be specified for each vertex set.")

        if self.faces is not None:
            if len(self.vertices) != len(self.faces):
                raise ValueError("Faces need to be specified for each vertex set.")

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
        try:
            n_elements = len(data)
        except Exception:
            n_elements = 0

        for i in range(n_elements):
            try:
                data[i] = data[i].astype(dtype)
            except Exception:
                pass
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

    def set_property(self, name: str, data: np.ndarray) -> None:
        """Insert or replace a vertex property.

        Parameters
        ----------
        name : str
            Property name.
        data : np.ndarray
            Array of per-vertex values.

        Raises
        ------
        ValueError
            If *data* length does not match the existing vertex count.
        """
        data = np.asarray(data)
        if self._properties and len(data) != self._n_vertices:
            raise ValueError(
                f"Property '{name}' has {len(data)} values, "
                f"but expected {self._n_vertices} to match vertex count"
            )
        if not self._properties:
            self._n_vertices = len(data)
        self._properties[name] = data

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
