"""
Implements DataContainer as handler of Geometry object collections.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import List, Tuple, Union, Dict

from .geometry import BASE_COLOR

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

    def __init__(self, base_color=BASE_COLOR, highlight_color=(0.8, 0.2, 0.2)):
        self.data = []
        self.metadata = {}
        self.base_color = base_color
        self.highlight_color = highlight_color

    def __len__(self):
        return len(self.data)

    def get_actors(self, include_lod=False):
        """Get VTK actors from all geometries.

        Parameters
        ----------
        include_lod : bool, optional
            Include interaction-LOD shadow actors. Only the renderer
            should set this to True; index-based lookups rely on the
            default 1:1 correspondence with :pyattr:`data`.

        Returns
        -------
        list
            List of VTK actors.
        """
        if not include_lod:
            return [x.actor for x in self.data]
        actors = []
        for x in self.data:
            actors.append(x.actor)
            lod = getattr(x, "_lod_actor", None)
            if lod is not None:
                actors.append(lod)
        return actors

    def refresh_lod(self, budget=None, force=False):
        """Recompute LOD for all geometries based on aggregate scene budget.

        Distributes the point budget proportionally across geometries
        so that many small geometries that collectively exceed the budget
        still benefit from interaction-LOD.

        Parameters
        ----------
        budget : int, optional
            Total scene point budget.  Reads from application settings
            when *None*.

        Returns
        -------
        bool
            True when LOD actors were created or destroyed (caller
            should sync the renderer).
        """
        from . import lod

        if budget is None:
            budget = lod.get_point_budget()

        budgets = lod.compute_scene_lod(self.data, budget)
        changed = False

        for g in self.data:
            per_geom = budgets.get(g.uuid)
            if per_geom is not None:
                if force or getattr(g, "_lod_indices", None) is None:
                    g.setup_lod(per_geom)
                    changed = True
            elif getattr(g, "_lod_actor", None) is not None:
                g.setup_lod(lod.LOD_DISABLED)
                changed = True

        return changed

    def add(self, points=None, color=None, **kwargs):
        """Add a new geometry object to the container.

        Parameters
        ----------
        points_or_geometry : np.ndarray or Geometry or SegmentationGeometry
            Points to add to the container, or an existing geometry object.
        color : tuple of float, optional
            RGB color values for the point cloud.

        Returns
        -------
        int
            Index of the new point cloud.
        """
        from .geometry import Geometry

        geometry = points
        if not isinstance(geometry, Geometry):
            if color is None:
                color = self.base_color
            geometry = Geometry(points=points, **kwargs)
            geometry.set_appearance(
                base_color=color, highlight_color=self.highlight_color
            )
        else:
            if color is not None:
                geometry.set_appearance(base_color=color)
            geometry._appearance.setdefault("highlight_color", self.highlight_color)

        self.data.append(geometry)
        self.refresh_lod()
        return len(self.data) - 1

    def remove(self, uuids_or_geometries: Union[List[str], List["Geometry"]]):
        """Remove geometries at specified indices or by geometry objects.

        Parameters
        ----------
        uuids_or_geometries : str, list of str, Geometry, or list of Geometry
            UUIDs of geometries to remove or geometry objects to remove.
        """
        indices = [self.uuid_to_index(x) for x in self._to_uuids(uuids_or_geometries)]
        indices = list(set(x for x in indices if self._index_ok(x)))

        # Reverse order to avoid potential shift issue
        for index in sorted(indices, reverse=True):
            self.data.pop(index)

        self.refresh_lod()

    def clear(self):
        """Remove all data associated with the container."""
        self.data.clear()
        self.metadata.clear()

    def uuid_to_index(self, uuid: str) -> int:
        """Convert a uuid to an index in self.data."""
        for index, geometry in enumerate(self.data):
            if geometry.uuid == uuid:
                return index
        return None

    def get(self, index_or_uuid: Union[int, str]):
        """
        Retrieve the Geometry object by index or UUID.

        Parameters
        ----------
        index_or_uuid : int or str
            Geometry index or UUID to retrieve.

        Returns
        -------
        geometry : :py:class:`mosaic.geometry.Geometry`
            Selected geometry or None if not found.
        """
        if isinstance(index_or_uuid, str):
            index_or_uuid = self.uuid_to_index(index_or_uuid)

        if self._index_ok(index_or_uuid):
            return self.data[index_or_uuid]
        return None

    def update(self, uuid_or_geometry, new_geometry) -> bool:
        """
        Update a geometry by UUID or geometry object.

        Parameters
        ----------
        uuid_or_geometry : str or Geometry
            UUID of geometry to update, or the geometry object itself
        new_geometry : Geometry
            New geometry to replace the old one

        Returns
        -------
        bool
            True if update succeeded, False if UUID not found
        """
        uuid = self._to_uuid(uuid_or_geometry)
        if (index := self.uuid_to_index(uuid)) is None:
            return False

        if new_geometry.uuid != uuid:
            new_geometry.uuid = uuid

        self.data[index] = new_geometry
        self.refresh_lod()
        return True

    def highlight_points(self, uuid_or_geometry, point_ids: set, color: Tuple[float]):
        """Highlight specific points in a cloud.

        Parameters
        ----------
        uuid_or_geometry : int or str
            UUID of geometry to update, or the geometry object itself
        point_ids : set
            IDs of points to highlight.
        color : tuple of float
            RGB color for highlighting.
        """
        if (geometry := self.get(self._to_uuid(uuid_or_geometry))) is None:
            return None

        if color is None:
            color = geometry._appearance.get("highlight_color", (0.8, 0.2, 0.2))
        geometry.color_points(point_ids, color)

    def highlight(self, uuids_or_geometries: Union[List[str], List["Geometry"]]):
        """Highlight specified geometries.

        Parameters
        ----------
        uuids_or_geometries : list of str or list of Geometry
            UUIDs or geometry objects to highlight.
        """
        uuids = self._to_uuids(uuids_or_geometries)
        _highlighted = getattr(self, "_highlighted_uuids", set())

        for geometry in self.data:
            appearance = geometry._appearance
            color = appearance.get("base_color", self.base_color)
            if geometry.uuid in uuids:
                color = appearance.get("highlight_color", self.highlight_color)
            elif geometry.uuid not in _highlighted:
                continue

            geometry.set_color(color=color)
        self._highlighted_uuids = set(uuids)

    def update_appearance(
        self, uuids_or_geometries: Union[List[str], List["Geometry"]], parameters: Dict
    ) -> bool:
        """Update appearance parameters for specified geometries.

        Parameters
        ----------
        uuids_or_geometries : list of str or list of Geometry
            UUIDs or geometry objects to update
        parameters : dict
            Appearance parameters to update

        Returns
        -------
        bool
            True if full render required (actor was replaced)
        """
        from .formats.parser import load_density
        from .geometry import VolumeGeometry, SegmentationGeometry

        uuids = self._to_uuids(uuids_or_geometries)
        geometries = [self.get(x) for x in uuids if self.get(x) is not None]

        scale, volume_path = parameters.get("scale", 1.0), parameters.get("volume_path")
        if volume_path is not None:
            rel_geoms = [x for x in geometries if "volume_path" in x._meta]

            paths = set([x._meta.get("volume_path") for x in rel_geoms])
            scales = set([x._meta.get("volume_scale") for x in rel_geoms])

            # We are dealing with a VolumeGeometry for which we might have
            # to update the volume to account for scale changes
            same_volume = len(paths) == 1 and volume_path in paths
            same_scale = len(scales) == 1 and scale in scales
            if same_volume and same_scale:
                volume_path = None

            # We are dealing with a reattach, where a Geometry instance has volume_path
            # in its metadata to be quickly converted into a VolumeGeometry
            same_geom = len([x for x in rel_geoms if isinstance(x, VolumeGeometry)])
            if same_geom != len(rel_geoms) and not parameters.get("reattach_volume"):
                volume_path = None

        volume = None
        if volume_path is not None:
            density = load_density(volume_path)

            sampling = density.sampling_rate
            volume = density.data * scale

        full_render = False
        parameters["isovalue_percentile"] = parameters.get("isovalue_percentile", 99.5)
        for uuid in uuids:
            if (geometry := self.get(uuid)) is None:
                continue

            if isinstance(geometry, SegmentationGeometry):
                geometry.set_appearance(**parameters)
                continue

            if volume is not None:
                if not isinstance(geometry, VolumeGeometry):
                    geometry = geometry[...]
                state = geometry.__getstate__()

                state["volume"] = volume
                state["volume_sampling_rate"] = sampling
                state["meta"]["volume_path"] = volume_path
                state["meta"]["volume_scale"] = scale

                # New actor so make sure to re-render
                full_render = True
                geometry = VolumeGeometry(**state)
                self.update(uuid, geometry)

            geometry.set_appearance(**parameters)

        return full_render

    def _to_uuid(self, uuid_or_geometry: Union[str, "Geometry"]) -> str:
        """Convert UUID or Geometry to UUID.

        Parameters
        ----------
        uuid_or_geometry : str or Geometry
            UUID or geometry object

        Returns
        -------
        str
            UUID string
        """
        # Check if input is a geometry-like object (has uuid attribute)
        if hasattr(uuid_or_geometry, "uuid"):
            uuid_or_geometry = uuid_or_geometry.uuid
        return uuid_or_geometry

    def _to_uuids(
        self, uuids_or_geometries: Union[List[str], List["Geometry"]]
    ) -> List[str]:
        """Convert list of UUIDs or Geometries to UUIDs.

        Parameters
        ----------
        uuids_or_geometries : list of str or list of Geometry
            UUIDs or geometry objects

        Returns
        -------
        list of str
            UUIDs (strings)
        """
        if not isinstance(uuids_or_geometries, (list, tuple)):
            uuids_or_geometries = [uuids_or_geometries]
        return [self._to_uuid(x) for x in uuids_or_geometries]

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
