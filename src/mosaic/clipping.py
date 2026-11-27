"""
One clipping plane that cuts chosen objects open.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np
from scipy.spatial.transform import Rotation
from vtkmodules.vtkCommonDataModel import vtkPlane

__all__ = ["ClipCut", "bounds", "clip_targets", "eligible", "remap"]


def eligible(geometry) -> bool:
    """Return whether a geometry can be clipped.

    Parameters
    ----------
    geometry : Geometry
        Candidate object.

    Returns
    -------
    bool
        True for point clouds, trajectories and mesh models.
    """
    from .parametrization import TriangularMesh

    if geometry._representation in ("volume", "segmentation"):
        return False

    # A shared world-space plane would cut a transformed actor in the wrong place.
    if geometry.actor.GetUserTransform() is not None:
        return False

    model = geometry.model
    return model is None or isinstance(model, TriangularMesh)


def clip_targets(data_pane, models_pane) -> list:
    """Return the geometries a cut applies to.

    Parameters
    ----------
    data_pane : DataContainerInteractor
        Pane of the data container.
    models_pane : DataContainerInteractor
        Pane of the models container.

    Returns
    -------
    list of Geometry
        Eligible selected geometries across both panes, or all visible
        eligible geometries when nothing is selected.
    """
    panes = (data_pane, models_pane)
    selected = [g for pane in panes for g in pane.get_selected_geometries()]
    if selected:
        return [g for g in selected if eligible(g)]
    return [
        g for pane in panes for g in pane.container.data if g.visible and eligible(g)
    ]


def bounds(geometries: list) -> tuple:
    """Return the combined bounds of geometries.

    Parameters
    ----------
    geometries : list of Geometry
        At least one geometry.

    Returns
    -------
    tuple of float
        Bounds (xmin, xmax, ymin, ymax, zmin, zmax) of their actors.
    """
    actor_bounds = np.array([g.actor.GetBounds() for g in geometries])
    lower = actor_bounds[:, 0::2].min(axis=0)
    upper = actor_bounds[:, 1::2].max(axis=0)
    return tuple(np.column_stack([lower, upper]).ravel())


def remap(geometries: list, live: list) -> list:
    """Return ``geometries`` as they are found in ``live``.

    Parameters
    ----------
    geometries : list of Geometry
        Geometries to look up.
    live : list of Geometry
        Geometries in the session.

    Returns
    -------
    list of Geometry
        Each geometry still in ``live``, or the eligible geometry in
        ``live`` with its uuid. Others are dropped.
    """
    alive = set(map(id, live))
    by_uuid = {g.uuid: g for g in live}
    ret = []
    for geometry in geometries:
        if id(geometry) not in alive:
            geometry = by_uuid.get(geometry.uuid)
            if geometry is None or not eligible(geometry):
                continue
        ret.append(geometry)
    return ret


def _mappers(geometry):
    mappers = [geometry.actor.GetMapper()]
    if geometry.lod.actor is not None:
        mappers.append(geometry.lod.actor.GetMapper())
    return mappers


def _has_plane(mapper, plane) -> bool:
    planes = mapper.GetClippingPlanes()
    return planes is not None and bool(planes.IsItemPresent(plane))


def _corners(bounds) -> np.ndarray:
    grid = np.meshgrid(bounds[0:2], bounds[2:4], bounds[4:6], indexing="ij")
    return np.stack(grid, axis=-1).reshape(-1, 3)


class ClipCut:
    """One plane clipping the mappers of chosen geometries.

    The plane is attached only while it has a pose. The kept side is the
    one its normal points to.
    """

    def __init__(self):
        self.plane = vtkPlane()
        self._geometries = []
        self._has_pose = False

    @property
    def geometries(self) -> list:
        """Geometries the cut applies to."""
        return list(self._geometries)

    @property
    def has_pose(self) -> bool:
        """Whether the plane has been placed."""
        return self._has_pose

    def set_objects(self, geometries: list) -> None:
        """Move the cut to other geometries, keeping its pose.

        Parameters
        ----------
        geometries : list of Geometry
            Geometries to clip.
        """
        self._detach()
        self._geometries = list(geometries)
        self._attach()
        return None

    def place_facing(self, view_direction, bounds) -> None:
        """Place the plane facing the viewer in front of ``bounds``.

        Parameters
        ----------
        view_direction : array_like
            Direction from the camera to its focal point (3,).
        bounds : tuple of float
            Bounds (xmin, xmax, ymin, ymax, zmin, zmax) to place the plane
            in front of.
        """
        normal = np.asarray(view_direction, dtype=float)
        normal = normal / np.linalg.norm(normal)
        corners = _corners(bounds)
        center = corners.mean(axis=0)
        depth = (corners @ normal).min()

        self.plane.SetNormal(normal)
        self.plane.SetOrigin(center + normal * (depth - center @ normal))
        self._has_pose = True
        self._attach()
        return None

    def push(self, distance: float) -> None:
        """Move the plane along its normal, clamped to :meth:`extent`.

        Parameters
        ----------
        distance : float
            Signed distance, positive cuts deeper.
        """
        normal = np.array(self.plane.GetNormal())
        origin = np.array(self.plane.GetOrigin())
        depth = origin @ normal
        target = np.clip(depth + distance, *self.extent())
        self.plane.SetOrigin(origin + normal * (target - depth))
        return None

    def tilt(self, axis, degrees: float) -> None:
        """Rotate the normal about ``axis`` through the origin.

        Parameters
        ----------
        axis : array_like
            Rotation axis (3,).
        degrees : float
            Rotation angle in degrees.
        """
        axis = np.asarray(axis, dtype=float)
        rotation = Rotation.from_rotvec(
            np.radians(degrees) * axis / np.linalg.norm(axis)
        )
        self.plane.SetNormal(rotation.apply(self.plane.GetNormal()))
        return None

    def face(self, view_direction) -> None:
        """Turn the normal to ``view_direction``, keeping the origin.

        Parameters
        ----------
        view_direction : array_like
            Direction from the camera to its focal point (3,).
        """
        normal = np.asarray(view_direction, dtype=float)
        self.plane.SetNormal(normal / np.linalg.norm(normal))
        return None

    def extent(self) -> tuple[float, float]:
        """Return the range of the geometries' bounds along the normal.

        Returns
        -------
        tuple of float
            Smallest and largest projection of the combined bounds corners
            on the normal.
        """
        corners = _corners(bounds(self._geometries))
        depths = corners @ np.array(self.plane.GetNormal())
        return float(depths.min()), float(depths.max())

    def sync(self, geometries: list) -> None:
        """Follow removed and replaced geometries and re-add lost planes.

        Parameters
        ----------
        geometries : list of Geometry
            Geometries in the session, matched with :func:`remap`. The cut
            is removed when none of its geometries is left.
        """
        current = self._geometries
        remaining = remap(current, geometries)
        if current and not remaining:
            self.clear()
            return None

        if list(map(id, remaining)) != list(map(id, current)):
            self._detach()
            self._geometries = remaining

        # Rebuilding a geometry in place replaces its mapper.
        self._attach()
        return None

    def clear(self) -> None:
        """Remove the cut from all geometries and forget its pose."""
        self._detach()
        self._geometries = []
        self._has_pose = False
        return None

    def to_state(self, existing_uuids: set[str]) -> dict | None:
        """Return the cut as session metadata.

        Parameters
        ----------
        existing_uuids : set of str
            Uuids of geometries still in the session.

        Returns
        -------
        dict or None
            Plane origin, normal and uuids of existing clipped geometries,
            or None without a cut.
        """
        if not self._has_pose:
            return None
        return {
            "origin": list(self.plane.GetOrigin()),
            "normal": list(self.plane.GetNormal()),
            "uuids": [g.uuid for g in self._geometries if g.uuid in existing_uuids],
        }

    def from_state(self, state: dict | None, geometries_by_uuid: dict) -> None:
        """Restore the cut from session metadata.

        Parameters
        ----------
        state : dict or None
            Output of :meth:`to_state`. None removes the cut.
        geometries_by_uuid : dict
            Geometries in the session by uuid. Unknown uuids are skipped,
            and the cut is removed when none is known.
        """
        self.clear()
        if state is None:
            return None

        uuids = [u for u in state["uuids"] if u in geometries_by_uuid]
        if not uuids:
            return None

        self.plane.SetOrigin(state["origin"])
        self.plane.SetNormal(state["normal"])
        self._has_pose = True
        self.set_objects([geometries_by_uuid[u] for u in uuids])
        return None

    def _attach(self):
        if not self._has_pose:
            return None

        for geometry in self._geometries:
            for mapper in _mappers(geometry):
                if not _has_plane(mapper, self.plane):
                    mapper.AddClippingPlane(self.plane)
        return None

    def _detach(self):
        for geometry in self._geometries:
            for mapper in _mappers(geometry):
                if _has_plane(mapper, self.plane):
                    mapper.RemoveClippingPlane(self.plane)
        return None
