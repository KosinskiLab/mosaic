"""
Headless session manager for the Mosaic scripting interface.

:class:`Session` is the headless equivalent of :class:`~mosaic.data.MosaicData`,
managing two :class:`~mosaic.container.DataContainer` instances (point clouds
and fitted models) without Qt or VTK rendering dependencies.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import os
import pickle
import warnings
from uuid import uuid4
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Optional

import numpy as np

from ..container import DataContainer
from ..parallel import _init_worker, _wrap_task
from ..widgets.container_list import TreeStateData, TreeState

__all__ = ["Session"]


class Session:
    """Headless workspace that holds geometry data and dispatches operations.

    Attributes
    ----------
    data : DataContainer
        Container for point cloud geometries.
    models : DataContainer
        Container for fitted mesh/model geometries.
    """

    def __init__(self, quiet: bool = False):
        self._data = DataContainer()
        self._models = DataContainer(highlight_color=(0.2, 0.4, 0.8))
        self._data_tree = TreeStateData()
        self._models_tree = TreeStateData()
        self._order: list = []
        self._last_results: list = []
        self._log: List[str] = []
        self._counter: int = 0
        self.quiet: bool = quiet

    def _all_geometries(self) -> list:
        """Return all geometries in insertion order."""
        # Sync any geometries added directly to containers (e.g. tests)
        ordered = set(id(g) for g in self._order)
        for g in list(self._data.data) + list(self._models.data):
            if id(g) not in ordered:
                self._order.append(g)
                ordered.add(id(g))
        return list(self._order)

    def _owner(self, geometry):
        """Return which container owns *geometry*."""
        for container in (self._data, self._models):
            if geometry in container.data:
                return container
        return None

    def _tree_for(self, container) -> TreeStateData:
        """Return the tree state associated with *container*."""
        if container is self._models:
            return self._models_tree
        return self._data_tree

    @staticmethod
    def _flatten(items: list) -> list:
        """Flatten one level of nesting in *items*."""
        flat = []
        for item in items:
            if isinstance(item, list):
                flat.extend(item)
            else:
                flat.append(item)
        return flat

    def resolve(self, spec: str) -> list:
        """Resolve a target specifier to a list of Geometry objects.

        Parameters
        ----------
        spec : str
            ``"#N"`` for a single geometry, ``"#N-M"`` for a range,
            ``"*"`` for every geometry, or ``"@last"`` for the results
            of the most recent ``open()`` or ``apply()`` call.

        Returns
        -------
        list of Geometry
        """
        if spec == "@last":
            return list(self._last_results)

        all_geoms = self._all_geometries()

        if spec == "*":
            return list(all_geoms)

        if spec.startswith("#"):
            body = spec[1:]
            if "-" in body:
                lo, hi = body.split("-", 1)
                lo, hi = int(lo), int(hi)
                if lo > hi:
                    lo, hi = hi, lo
                return [all_geoms[i] for i in range(lo, hi + 1) if i < len(all_geoms)]
            idx = int(body)
            if idx < len(all_geoms):
                return [all_geoms[idx]]
            raise IndexError(f"Geometry {spec} does not exist (have {len(all_geoms)})")

        raise ValueError(f"Invalid target specifier: {spec!r}")

    def resolve_many(self, specs: List[str]) -> list:
        """Resolve multiple specifiers, preserving order and deduplicating."""
        seen, result = set(), []
        for spec in specs:
            for geom in self.resolve(spec):
                if id(geom) not in seen:
                    seen.add(id(geom))
                    result.append(geom)
        return result

    def open(
        self,
        filepath: str,
        offset=0,
        scale=None,
        sampling_rate=None,
        persist=True,
        **kwargs,
    ) -> List[int]:
        """Load geometries from a file.

        Parameters
        ----------
        filepath : str
            Path to the input file.
        offset : float or array-like, optional
            Coordinate offset to subtract from vertices (default 0).
        scale : float or array-like, optional
            Scale factor applied after offset. Defaults to the file's
            native sampling rate (matching GUI behavior).
        sampling_rate : float, optional
            Override the file's native sampling rate.
        persist : bool, optional
            When ``True`` (default), add geometries to session containers.
            When ``False``, geometries are only available via ``@last``.
        **kwargs
            Additional arguments passed to ``open_file()``.

        Returns
        -------
        list of int
            Global indices of the newly added geometries.
        """
        from ..formats import open_file
        from ..geometry import Geometry
        from ..parametrization import TriangularMesh

        container = open_file(filepath, **kwargs)
        base = os.path.basename(filepath).split(".", 1)[0]
        use_index = len(container) > 1

        shape = None
        indices = []
        opened_geoms = []
        effective_sampling = 1
        for index, data in enumerate(container):
            effective_scale = scale if scale is not None else data.sampling
            effective_sampling = (
                sampling_rate if sampling_rate is not None else data.sampling
            )

            # Apply coordinate transforms
            scale_new = np.divide(effective_scale, data.sampling)
            data.vertices = np.subtract(data.vertices, offset, out=data.vertices)
            data.vertices = np.multiply(data.vertices, scale_new, out=data.vertices)

            # Track shape metadata
            data_shape = np.divide(data.shape, data.sampling)
            if shape is None:
                shape = data_shape
            shape = np.maximum(shape, data_shape)

            is_mesh = data.faces is not None
            mesh_model = None
            if is_mesh:
                from ..meshing import to_open3d

                mesh_model = TriangularMesh(to_open3d(data.vertices, data.faces))

            if persist:
                if is_mesh:
                    idx = self._models.add(
                        model=mesh_model,
                        sampling_rate=effective_sampling,
                    )
                    geom = list(self._models.data)[idx]
                else:
                    idx = self._data.add(
                        points=data.vertices,
                        normals=data.normals,
                        quaternions=data.quaternions,
                        sampling_rate=effective_sampling,
                        vertex_properties=data.vertex_properties,
                    )
                    geom = list(self._data.data)[idx]

                self._order.append(geom)
                indices.append(len(self._order) - 1)
            else:
                geom = Geometry(
                    points=data.vertices,
                    normals=data.normals,
                    quaternions=data.quaternions,
                    sampling_rate=effective_sampling,
                    vertex_properties=data.vertex_properties,
                    model=mesh_model,
                )

            if is_mesh:
                geom.change_representation("surface")

            geom._meta["name"] = f"{index}_{base}" if use_index else base
            opened_geoms.append(geom)
            self._counter += 1

        if persist and shape is not None:
            self._data.metadata["shape"] = shape

        self._last_results = opened_geoms
        return indices

    def save(self, geometries: list, filepath: str, **kwargs) -> None:
        """Export geometries to a file.

        Parameters
        ----------
        geometries : list of Geometry
            Geometries to export.
        filepath : str
            Output file path.
        **kwargs
            Additional export parameters (``format``, ``sampling``, etc.).
        """
        from ..formats.writer import write_geometries

        export_parameters = kwargs.copy()
        if export_parameters.get("format") is None:
            suffix = filepath.rsplit(".", 1)[-1].lower()
            export_parameters["format"] = suffix

        if export_parameters.get("shape") is None:
            export_parameters["shape"] = self._data.metadata.get("shape")

        write_geometries(geometries, filepath, **export_parameters)

    def save_session(self, filepath: str) -> None:
        """Pickle the session state to *filepath*."""
        state = {
            "shape": self._data.metadata.get("shape"),
            "_data": self._data,
            "_models": self._models,
            "_data_tree": self._data_tree,
            "_models_tree": self._models_tree,
        }
        with open(filepath, "wb") as fh:
            pickle.dump(state, fh, protocol=pickle.HIGHEST_PROTOCOL)

    def load_session(self, filepath: str, persist: bool = True) -> None:
        """Restore session state from a pickle file.

        Parameters
        ----------
        filepath : str
            Path to the pickle file.
        persist : bool, optional
            When ``True`` (default), replace the current session state.
            When ``False``, geometries are only available via ``@last``.
        """
        with open(filepath, "rb") as fh:
            state = pickle.load(fh)

        loaded_data = state.get("_data", state.get("data", DataContainer()))
        loaded_models = state.get(
            "_models",
            state.get("models", DataContainer(highlight_color=(0.2, 0.4, 0.8))),
        )

        if not persist:
            self._last_results = list(loaded_data.data) + list(loaded_models.data)
            return

        self._data = loaded_data
        self._models = loaded_models

        for attr in ("_data_tree", "_models_tree"):
            tree = state.get(attr)
            if tree is None:
                setattr(self, attr, TreeStateData())
            elif isinstance(tree, TreeState):
                setattr(self, attr, tree.to_tree_state_data())
            else:
                setattr(self, attr, tree)

        shape = state.get("shape")
        if shape is not None:
            self._data.metadata["shape"] = shape

        self._order = list(self._data.data) + list(self._models.data)
        self._last_results = self._all_geometries()

    def _run_parallel(self, func, geometries, operation_name, **kwargs):
        """Execute *func* on each geometry using a process pool.

        Parameters
        ----------
        func : callable
            Function to apply to each geometry.
        geometries : list of Geometry
            Target geometries.
        operation_name : str
            Label for the progress bar.
        **kwargs
            Passed to *func*. ``workers`` is consumed to set pool size.

        Returns
        -------
        results : list
            Per-geometry results (``None`` for failures).
        errors : list of (int, Exception)
            Index and exception for each failed geometry.
        """
        workers = int(kwargs.pop("workers", 1))
        pool = ProcessPoolExecutor(max_workers=workers, initializer=_init_worker)
        futures = {
            pool.submit(_wrap_task, func, None, g, **kwargs): i
            for i, g in enumerate(geometries)
        }

        results = [None] * len(geometries)
        errors = []

        from rich.progress import (
            Progress,
            SpinnerColumn,
            BarColumn,
            TextColumn,
            TimeRemainingColumn,
            MofNCompleteColumn,
        )
        from .theme import get_console

        console = get_console()
        if self.quiet:
            from io import StringIO
            from rich.console import Console
            from .theme import MOSAIC_THEME

            console = Console(file=StringIO(), theme=MOSAIC_THEME)

        progress = Progress(
            SpinnerColumn("dots"),
            TextColumn("[mosaic.accent]{task.description}"),
            BarColumn(
                style="mosaic.bar.remaining",
                complete_style="mosaic.bar.complete",
                finished_style="mosaic.bar.finished",
            ),
            MofNCompleteColumn(),
            TimeRemainingColumn(),
            console=console,
            transient=True,
        )

        with progress:
            task = progress.add_task(operation_name, total=len(futures))
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    ret = future.result()
                    results[idx] = ret["result"]
                    if ret["warnings"]:
                        warnings.warn(f"#{idx}: {ret['warnings']}")
                except Exception as exc:
                    errors.append((idx, exc))
                progress.advance(task)

        pool.shutdown(wait=False)
        return results, errors

    def apply(self, operation_name: str, geometries: List, **kwargs) -> List:
        """Apply a :class:`~mosaic.operations.GeometryOperations` function.

        Parameters
        ----------
        operation_name : str
            Registered operation name (e.g. ``"cluster"``).
        geometries : list of Geometry
            Target geometries.
        **kwargs
            Operation-specific parameters.  Use ``workers=N`` to control
            the number of parallel worker processes.

            Special flags (consumed before dispatching):

            - **persist** (*bool*, default ``True``): when ``False``, results
              are stored in ``_last_results`` but NOT added to session
              containers (transient, only available via ``@last``).

        Returns
        -------
        list of Geometry
            Newly created geometries.
        """
        from ..geometry import Geometry, GeometryData
        from ..operations import GeometryOperations

        persist = kwargs.pop("persist", True)

        func = getattr(GeometryOperations, operation_name, None)
        if func is None:
            raise ValueError(f"Unknown operation: {operation_name}")

        results, errors = self._run_parallel(func, geometries, operation_name, **kwargs)

        created = []
        for i, result in enumerate(results):
            if result is None:
                continue

            if isinstance(result, (Geometry, GeometryData)):
                result = (result,)
            elif isinstance(result, list):
                result = self._flatten(result)

            for new_geom in result:
                if isinstance(new_geom, GeometryData):
                    new_geom = Geometry(**new_geom.to_dict())
                if new_geom.model is not None:
                    new_geom.change_representation("surface")
                if persist:
                    container = self._data if new_geom.model is None else self._models

                    container.add(new_geom)
                    self._order.append(new_geom)
                created.append(new_geom)

        if errors:
            msgs = [f"#{i}: {e}" for i, e in errors]
            warnings.warn(
                f"{len(errors)}/{len(geometries)} failed:\n  " + "\n  ".join(msgs)
            )

        self._last_results = created
        return created

    def measure(self, property_name: str, geometries: List, **kwargs) -> List:
        """Compute a property via :class:`~mosaic.properties.GeometryProperties`.

        Parameters
        ----------
        property_name : str
            Property name (e.g. ``"mesh_area"``).
        geometries : list of Geometry
            Target geometries.
        **kwargs
            Property-specific parameters.

            - **output** (*str*, optional): export results to a CSV file.
            - **store** (*bool*, default ``False``): store per-vertex array
              results as vertex properties on each geometry.

        Returns
        -------
        list
            One result per input geometry.
        """
        from ..properties import GeometryProperties

        output = kwargs.pop("output", None)
        store = kwargs.pop("store", False)

        results = [
            GeometryProperties.compute(property_name, geom, **kwargs)
            for geom in geometries
        ]

        if store:
            for geom, val in zip(geometries, results):
                if val is None or not isinstance(val, np.ndarray):
                    continue
                if val.ndim == 0:
                    continue
                if len(val) != geom.get_number_of_points():
                    continue
                geom.vertex_properties.set_property(property_name, val)

        if output is not None:
            from ..properties import export_property_csv

            paired = [(g, v) for g, v in zip(geometries, results) if v is not None]
            if paired:
                geoms, values = zip(*paired)
                export_property_csv(output, property_name, geoms, values)

        return results

    def filter(
        self, geometries: List, prop_name: str, lower=None, upper=None, **kwargs
    ) -> tuple:
        """Filter geometries by property value range.

        Automatically detects whether the property yields per-vertex arrays
        (point-level filtering) or scalars (population-level filtering).

        Parameters
        ----------
        geometries : list of Geometry
            Target geometries.
        prop_name : str
            Vertex property name or measure name.
        lower : float, optional
            Lower bound (inclusive).
        upper : float, optional
            Upper bound (inclusive).
        **kwargs
            Additional parameters passed to property computation.

        Returns
        -------
        tuple of (int, int, str)
            ``(kept, removed, level)`` where *level* is ``"point"`` or
            ``"population"``.
        """
        from ..properties import GeometryProperties

        kept_geoms = []
        kept, removed = 0, 0
        level = None

        for geom in list(geometries):
            # Check stored vertex properties first
            val = geom.vertex_properties.get_property(prop_name)

            # Fall back to computing the property
            if val is None:
                val = GeometryProperties.compute(prop_name, geom, **kwargs)

            if val is None:
                kept_geoms.append(geom)
                kept += 1
                continue

            is_array = (
                isinstance(val, np.ndarray)
                and val.ndim >= 1
                and len(val) == geom.get_number_of_points()
            )

            if is_array:
                level = "point"
                mask = np.ones(len(val), dtype=bool)
                if lower is not None:
                    mask &= val >= lower
                if upper is not None:
                    mask &= val <= upper

                if not mask.any():
                    self.remove([geom])
                    removed += 1
                else:
                    n_before = geom.get_number_of_points()
                    geom.subset(np.where(mask)[0], copy=False)
                    n_after = geom.get_number_of_points()
                    removed += n_before - n_after
                    kept += n_after
                    kept_geoms.append(geom)
            else:
                level = "population"
                scalar = float(val) if not isinstance(val, (int, float)) else val
                in_range = True
                if lower is not None and scalar < lower:
                    in_range = False
                if upper is not None and scalar > upper:
                    in_range = False

                if in_range:
                    kept_geoms.append(geom)
                    kept += 1
                else:
                    self.remove([geom])
                    removed += 1

        self._last_results = kept_geoms
        return (kept, removed, level or "population")

    def _geometry_name(self, geometry, index: int) -> str:
        """Return the display name, falling back to GUI-style defaults."""
        name = geometry._meta.get("name")
        if name:
            return name
        if geometry in self._models.data:
            return f"Fit {index}"
        return f"Cluster {index}"

    def _geometry_group(self, geometry) -> str:
        """Return the group name a geometry belongs to, or empty string."""
        uuid = geometry.uuid
        for tree in (self._data_tree, self._models_tree):
            for group_id, members in tree.groups.items():
                if uuid in members:
                    return tree.group_names.get(group_id, "")
        return ""

    @staticmethod
    def _match_filter(value: str, pattern: str) -> bool:
        """Check if *value* matches *pattern* (case-insensitive).

        When *pattern* contains glob characters (``*``, ``?``, ``[``),
        :func:`fnmatch.fnmatch` is used.  Otherwise a substring match
        is performed.
        """
        from fnmatch import fnmatch

        value_lower = value.lower()
        pattern_lower = pattern.lower()
        if any(c in pattern for c in ("*", "?", "[")):
            return fnmatch(value_lower, pattern_lower)
        return pattern_lower in value_lower

    def list_filtered(
        self,
        type: Optional[str] = None,
        name: Optional[str] = None,
        group: Optional[str] = None,
        visible: Optional[bool] = None,
    ) -> list:
        """Return matching geometries as ``(index, geometry)`` pairs.

        Parameters
        ----------
        type : str, optional
            Filter by geometry type (``cluster``, ``mesh``, ``parametric``).
        name : str, optional
            Filter by geometry name. Supports glob patterns (e.g. ``0*``)
            and case-insensitive substring matching.
        group : str, optional
            Filter by group name. Supports glob patterns and substring matching.
        visible : bool, optional
            Filter by visibility state. When ``True``, only visible
            geometries are returned; when ``False``, only hidden ones.

        Returns
        -------
        list of (int, Geometry)
            Matching ``(global_index, geometry)`` pairs.
        """
        all_geoms = self._all_geometries()
        entries = []
        for i, g in enumerate(all_geoms):
            if type is not None and g.geometry_type != type:
                continue
            if name is not None and not self._match_filter(
                self._geometry_name(g, i), name
            ):
                continue
            if group is not None and not self._match_filter(
                self._geometry_group(g), group
            ):
                continue
            if visible is not None and g.visible != visible:
                continue
            entries.append((i, g))

        return entries

    def remove(self, geometries: List) -> int:
        """Remove geometries from the session.

        Parameters
        ----------
        geometries : list of Geometry
            Geometries to remove.

        Returns
        -------
        int
            Number of geometries removed.
        """
        count = 0
        removed_ids = set()
        for geom in geometries:
            container = self._owner(geom)
            if container is not None:
                container.remove(geom)
                self._tree_for(container).remove_uuid(geom.uuid)
            if geom in self._order:
                self._order.remove(geom)
            removed_ids.add(id(geom))
            count += 1
        if removed_ids:
            self._last_results = [
                g for g in self._last_results if id(g) not in removed_ids
            ]
        return count

    def merge(self, geometries: List, name: Optional[str] = None) -> "Geometry":
        """Merge multiple geometries into one.

        Parameters
        ----------
        geometries : list of Geometry
            Geometries to merge. All must belong to the same container
            (data or models).
        name : str, optional
            Name for the merged geometry. Defaults to the name of the
            first input geometry.

        Returns
        -------
        Geometry
            The newly created merged geometry.
        """
        from ..geometry import Geometry

        owners = {id(c) for g in geometries if (c := self._owner(g)) is not None}
        if len(owners) > 1:
            raise ValueError(
                "Cannot merge geometries across data and model containers."
            )

        container = self._owner(geometries[0]) or self._data

        if name is None:
            idx = self._all_geometries().index(geometries[0])
            name = self._geometry_name(geometries[0], idx)

        merged = Geometry.merge(geometries)
        merged._meta["name"] = name

        self.remove(geometries)
        container.add(merged)
        self._order.append(merged)
        self._last_results = [merged]
        return merged

    def group(self, geometries: List, name: str) -> str:
        """Assign geometries to a named group.

        Parameters
        ----------
        geometries : list of Geometry
            Geometries to group.
        name : str
            Display name for the group.

        Returns
        -------
        str
            UUID of the created or updated group.
        """
        if not geometries:
            raise ValueError("No geometries to group.")

        owners = [self._owner(g) for g in geometries]
        if any(c is None for c in owners):
            raise ValueError("Cannot group non-persisted geometries.")
        if len({id(c) for c in owners}) > 1:
            raise ValueError(
                "Cannot group geometries across data and model containers."
            )

        container = owners[0]

        tree = self._tree_for(container)

        # Check if a group with this name already exists
        existing_id = None
        for gid, gname in tree.group_names.items():
            if gname == name:
                existing_id = gid
                break

        if existing_id is not None:
            group_id = existing_id
        else:
            group_id = str(uuid4())
            tree.root_items.append(group_id)
            tree.group_names[group_id] = name
            tree.groups[group_id] = []

        for geom in geometries:
            uuid = geom.uuid
            # Remove from any existing group
            for gid in tree.groups:
                tree.groups[gid] = [u for u in tree.groups[gid] if u != uuid]
            tree.groups[group_id].append(uuid)

        # Clean up any groups that became empty during reassignment
        for gid in list(tree.groups):
            if gid != group_id and not tree.groups[gid]:
                del tree.groups[gid]
                tree.group_names.pop(gid, None)
                tree.root_items = [x for x in tree.root_items if x != gid]

        return group_id

    def ungroup(self, geometries: List) -> int:
        """Remove geometries from their groups.

        Parameters
        ----------
        geometries : list of Geometry
            Geometries to ungroup.

        Returns
        -------
        int
            Number of geometries ungrouped.
        """
        count = 0
        for geom in geometries:
            container = self._owner(geom)
            if container is None:
                continue
            tree = self._tree_for(container)
            uuid = geom.uuid
            for gid in list(tree.groups):
                members = tree.groups[gid]
                if uuid in members:
                    tree.groups[gid] = [u for u in members if u != uuid]
                    count += 1
                    # Clean up empty groups
                    if not tree.groups[gid]:
                        del tree.groups[gid]
                        tree.group_names.pop(gid, None)
                        tree.root_items = [x for x in tree.root_items if x != gid]
        return count

    def log_command(self, cmd_str: str) -> None:
        """Append a command string to the session log."""
        self._log.append(cmd_str)
