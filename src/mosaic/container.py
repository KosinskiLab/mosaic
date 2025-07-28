"""
Implements DataContainer as handler of Geometry object collections.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import List, Tuple, Union

import numpy as np

__all__ = ["DataContainer"]


class DataContainer:
    """
    Container for managing and manipulating point cloud data collections.

    Parameters
    ----------
    base_color : tuple of float, optional
        Default color for points in RGB format in range 0-1.
        Default is (0.7, 0.7, 0.7).
    highlight_color : tuple of float, optional
        Highlight color for points in RGB format in range 0-1.
        Default is (0.8, 0.2, 0.2).
    """

    def __init__(self, base_color=(0.7, 0.7, 0.7), highlight_color=(0.8, 0.2, 0.2)):
        self.data = []
        self.metadata = {}
        self.base_color = base_color
        self.highlight_color = highlight_color

    def __len__(self):
        return len(self.data)

    def get_actors(self):
        """Get VTK actors from all geometries.

        Returns
        -------
        list
            List of VTK actors.
        """
        return [x.actor for x in self.data]

    def add(self, points, color=None, **kwargs):
        """Add a new geometry object to the container.

        Parameters
        ----------
        points : np.ndarray or Geometry
            Points to add to the container.
        color : tuple of float, optional
            RGB color values for the point cloud.

        Returns
        -------
        int
            Index of the new point cloud.
        """
        from .geometry import Geometry

        if color is None:
            color = self.base_color

        if issubclass(type(points), Geometry):
            new_geometry = points
        else:
            new_geometry = Geometry(points, color=color, **kwargs)

        new_geometry.set_appearance(
            base_color=color, highlight_color=self.highlight_color
        )
        self.data.append(new_geometry)
        return len(self.data) - 1

    def remove(self, indices: Union[int, List[int]]):
        """Remove geometries at specified indices.

        Parameters
        ----------
        indices : int or list of int
            Indices of geometries to remove.
        """
        if isinstance(indices, int):
            indices = [indices]

        indices = [x for x in indices if self._index_ok(x)]

        # Reverse order to avoid potential shift issue
        for index in sorted(indices, reverse=True):
            self.data.pop(index)

    def clear(self):
        """Remove all data associated with the container."""
        self.data.clear()
        self.metadata.clear()

    def get(self, index: int):
        """Retrieve the Geometry object at index.

        Parameters
        ----------
        index : int
            Geometry object to retrieve.

        Returns
        -------
        geometry : :py:class:`mosaic.geometry.Geometry`
            Selected geometry or None if index is invalid.
        """

        if self._index_ok(index):
            return self.data[index]
        return None

    def highlight(self, indices: Tuple[int]):
        """Highlight specified geometries.

        Parameters
        ----------
        indices : tuple of int
            Indices of clouds to highlight.
        """
        _highlighted = getattr(self, "_highlighted_indices", set())
        for index, geometry in enumerate(self.data):
            appearance = geometry._appearance
            color = appearance.get("base_color", self.base_color)
            if index in indices:
                color = appearance.get("highlight_color", self.highlight_color)
            elif index not in _highlighted:
                continue

            if not geometry.visible:
                continue

            geometry.set_color(color=color)

        self._highlighted_indices = set(indices)
        return None

    def highlight_points(self, index: int, point_ids: set, color: Tuple[float]):
        """Highlight specific points in a cloud.

        Parameters
        ----------
        index : int
            Index of target cloud.
        point_ids : set
            IDs of points to highlight.
        color : tuple of float
            RGB color for highlighting.
        """
        geometry = self.get(index)
        if geometry is None:
            return None

        if color is None:
            color = geometry._appearance.get("highlight_color", (0.8, 0.2, 0.2))
        geometry.color_points(point_ids, color)

    def update_appearance(self, indices: list, parameters: dict) -> bool:
        from .formats.parser import load_density
        from .geometry import VolumeGeometry

        volume = parameters.get("volume", None)
        volume_path = parameters.get("volume_path", None)
        if volume_path is not None:
            volume = load_density(volume_path)

        if volume is not None:
            sampling = volume.sampling_rate
            volume = volume.data * parameters.get("scale", 1.0)

        full_render = False
        parameters["isovalue_percentile"] = (
            parameters.get("isovalue_percentile", 99) / 100
        )
        for index in indices:
            geometry = self.get(index)
            if geometry is None:
                continue

            if volume is not None:
                if not isinstance(geometry, VolumeGeometry):
                    geometry = geometry[...]
                state = geometry.__getstate__()

                try:
                    data_recent = np.allclose(state["volume"], volume)
                except Exception:
                    data_recent = False

                if not data_recent:
                    state["volume"] = volume
                    state["volume_sampling_rate"] = sampling

                    # New actor so make sure to re-render
                    full_render = True
                    geometry = VolumeGeometry(**state)
                    self.data[index] = geometry

            geometry.set_appearance(**parameters)

        self.highlight(indices)
        return full_render

    def get_cluster_size(self) -> List[int]:
        """Get number of points in each cloud.

        Returns
        -------
        list of int
            Point count for each cloud.
        """
        return [cluster.get_number_of_points() for cluster in self.data]

    def _index_ok(self, index: int) -> bool:
        """Check if index is valid.

        Parameters
        ----------
        index : int
            Index to check.

        Returns
        -------
        bool
            True if index is valid.
        """
        try:
            index = int(index)
        except Exception:
            return False

        if 0 <= index < len(self.data):
            return True
        return False
