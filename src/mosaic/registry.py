"""
Unified method and parameter registry for Mosaic operations.

Defines parameters once; derives GUI settings dicts, REPL help,
and display-name resolution from a single source of truth.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Dict, Optional, Tuple

__all__ = [
    "Param",
    "Method",
    "Operation",
    "MethodRegistry",
    "operation",
    "_DECORATED_OPERATIONS",
]


# Maps Python type names to GUI widget types used by create_setting_widget.
_WIDGET_TYPE = {
    "float": "float",
    "int": "number",
    "str": "text",
    "bool": "boolean",
    "path": "PathSelector",
}

_UNSET = object()


@dataclass(frozen=True, slots=True)
class Param:
    """A single parameter accepted by an operation method.

    Parameters
    ----------
    name : str
        Keyword argument name (e.g. ``"depth"``).
    type : str
        Python type: ``"float"``, ``"int"``, ``"str"``, ``"bool"``,
        ``"path"``.  ``options`` turns a ``str`` into a select widget.
        ``"float_list"`` is also accepted for semicolon-separated floats.
    label : str
        GUI label. Defaults to ``name.replace("_", " ").title()``.
    default : Any
        Default value.  Use :data:`_UNSET` (the default) to mark a
        parameter as required.
    description : str
        Short description for tooltip body.
    notes : str
        Additional tooltip notes.
    min : float or str or None
        Minimum value.
    max : float or str or None
        Maximum value.
    step : float or None
        Step size for spinboxes.
    decimals : int or None
        Decimal precision for float spinboxes.
    options : list or None
        Options for select widgets.
    file_mode : bool or None
        For path type: True for files, False for directories.
    placeholder : str or None
        Placeholder text for path / text inputs.
    """

    name: str
    type: str
    label: str = ""
    default: Any = _UNSET
    description: str = ""
    notes: str = ""
    min: Any = None
    max: Any = None
    step: float = None
    decimals: int = None
    options: tuple = None
    file_mode: bool = None
    placeholder: str = None

    @property
    def widget_type(self) -> str:
        """Return the GUI widget type string for :func:`create_setting_widget`."""
        if self.options is not None:
            return "select"
        return _WIDGET_TYPE.get(self.type, self.type)

    def to_setting_dict(self) -> dict:
        """Produce the dict that :func:`create_setting_widget` consumes."""
        wtype = self.widget_type
        d = {
            "label": self.label or self.name.replace("_", " ").title(),
            "parameter": self.name,
            "type": wtype,
        }
        if self.default is not _UNSET:
            d["default"] = self.default
        if self.description:
            d["description"] = self.description
        if self.notes:
            d["notes"] = self.notes
        if self.min is not None:
            d["min"] = self.min
        if self.max is not None:
            d["max"] = self.max
        if self.step is not None:
            d["step"] = self.step
        if self.decimals is not None:
            d["decimals"] = self.decimals
        if self.options is not None:
            d["options"] = list(self.options)
        if self.file_mode is not None:
            d["file_mode"] = self.file_mode
        if self.placeholder is not None:
            d["placeholder"] = self.placeholder
        return d


@dataclass(frozen=True)
class Method:
    """A sub-method within an operation.

    Parameters
    ----------
    display_name : str
        GUI label (e.g. ``"Alpha Shape"``).
    internal_name : str
        Value used in code / REPL (e.g. ``"alpha_shape"``).
    params : tuple of Param
        Method-specific parameters.
    description : str
        One-line description for REPL help.
    """

    display_name: str
    internal_name: str
    params: Tuple[Param, ...] = ()
    description: str = ""
    gui: bool = True


@dataclass(frozen=True)
class Operation:
    """An operation that dispatches to one of several methods.

    Parameters
    ----------
    name : str
        Matches :class:`GeometryOperations` attribute name.
    common_params : tuple of Param
        Parameters shared across all methods.
    methods : tuple of Method
        Available sub-methods.
    method_param_name : str
        Keyword argument name for the method selector (default ``"method"``).
    description : str
        One-line description for REPL help.
    """

    name: str
    common_params: Tuple[Param, ...] = ()
    methods: Tuple[Method, ...] = ()
    method_param_name: str = "method"
    description: str = ""
    title: str = "Settings"
    targets: bool = True

    def build_usage(self, method_name: str = None) -> str:
        """Derive the canonical usage synopsis from parameter metadata.

        Parameters
        ----------
        method_name : str, optional
            Sub-method name to include after the operation name.
            When given, method-specific parameters are included.
        """
        parts = [self.name]
        method = None
        if method_name is not None:
            parts.append(method_name)
            method = self.get_method(method_name)
        elif self.methods:
            parts.append("<method>")
        if self.targets:
            parts.append("[targets]")
        has_params = self.common_params or (method is not None and method.params)
        if has_params:
            parts.append("[parameter=value ...]")
        return " ".join(parts)

    def get_method(self, name: str) -> Optional[Method]:
        """Look up by *display_name* or *internal_name* (case-insensitive)."""
        low = name.lower()
        for m in self.methods:
            if m.display_name.lower() == low or m.internal_name.lower() == low:
                return m
        return None

    def display_to_internal(self, display_name: str) -> str:
        """Map a display name to its internal name.

        Returns *display_name* unchanged if no match is found.
        """
        m = self.get_method(display_name)
        return m.internal_name if m is not None else display_name

    def to_settings_dict(self) -> dict:
        """Generate settings dict for GUI / pipeline (``create_setting_widget`` format).

        Only methods with ``gui=True`` are included.
        """
        gui_methods = [m for m in self.methods if m.gui]
        method_options = [m.display_name for m in gui_methods]
        settings = [
            {
                "label": "Method",
                "parameter": self.method_param_name,
                "type": "select",
                "options": method_options,
                "default": method_options[0] if method_options else None,
            }
        ]
        for p in self.common_params:
            settings.append(p.to_setting_dict())

        result = {"title": self.title, "settings": settings}

        if gui_methods:
            method_settings = {}
            for m in gui_methods:
                method_settings[m.display_name] = [
                    p.to_setting_dict() for p in m.params
                ]
            result["method_settings"] = method_settings

        return result


class MethodRegistry:
    """Global registry of operations with method sub-dispatch."""

    _operations: Dict[str, Operation] = {}

    @classmethod
    def register(cls, op: Operation):
        """Register an operation."""
        cls._operations[op.name] = op

    @classmethod
    def get(cls, name: str) -> Optional[Operation]:
        """Return the :class:`Operation` registered under *name*."""
        return cls._operations.get(name)

    @classmethod
    def settings_dict(cls, name: str) -> dict:
        """Return the GUI/pipeline settings dict for operation *name*."""
        op = cls._operations.get(name)
        if op is None:
            raise KeyError(f"No operation registered as {name!r}")
        return op.to_settings_dict()

    @classmethod
    def resolve_method(cls, op_name: str, display_name: str) -> str:
        """Resolve a display or internal name to the canonical internal name.

        Falls back to *display_name* unchanged if no match is found.
        """
        op = cls._operations.get(op_name)
        if op is None:
            return display_name
        return op.display_to_internal(display_name)

    @classmethod
    def all_operations(cls) -> Dict[str, Operation]:
        """Return all registered operations."""
        return dict(cls._operations)


_DECORATED_OPERATIONS = []


def operation(
    methods=(),
    common_params=(),
    method_param_name="method",
    title="Settings",
    targets=True,
    decorator=None,
):
    """Register an :class:`Operation` from a decorated function.

    The function's ``__name__`` becomes the operation name and the first
    non-empty docstring line becomes the description.  An optional
    *decorator* (e.g. ``use_point_data``) wraps the function after
    registration.
    """

    def wrapper(func):
        desc = ""
        method_descs = {}
        if func.__doc__:
            for line in func.__doc__.strip().splitlines():
                stripped = line.strip()
                if not desc:
                    if stripped:
                        desc = stripped.rstrip(".")
                    continue
                m = re.match(r"^-\s*'([^']+)'\s*:\s*(.+)$", stripped)
                if m:
                    method_descs[m.group(1).lower()] = m.group(2).strip()

        final_methods = methods
        if method_descs and methods:
            updated = []
            for meth in methods:
                if not meth.description:
                    key = meth.display_name.lower()
                    d = method_descs.get(key) or method_descs.get(
                        meth.internal_name.lower()
                    )
                    if d:
                        meth = replace(meth, description=d)
                updated.append(meth)
            final_methods = tuple(updated)

        op = Operation(
            name=func.__name__,
            description=desc,
            methods=final_methods,
            common_params=common_params,
            method_param_name=method_param_name,
            title=title,
            targets=targets,
        )
        MethodRegistry.register(op)
        if decorator is not None:
            func = decorator(func)
        _DECORATED_OPERATIONS.append((func.__name__, func))
        return func

    return wrapper


_K_NEIGHBORS = Param(
    "k_neighbors",
    "int",
    label="Neighbors",
    default=15,
    min=1,
    description="Number of neighbors for normal estimations.",
    notes="Consider decreasing this value for small point clouds.",
)


_CURVATURE_WEIGHT = Param(
    "curvature_weight",
    "float",
    default=0.0,
    min=-(2**28),
    label="Curvature Weight",
    description="Controls propagation of mesh curvature.",
)


_BOUNDARY_RING = Param(
    "boundary_ring",
    "int",
    default=0,
    label="Boundary Ring",
    description="Also optimize n-ring vertices for ill-defined boundaries.",
)

_SMOOTHNESS = Param(
    "smoothness",
    "float",
    default=0.0,
    min=0.0,
    max=1.0,
    label="Smoothness",
    description=(
        "Balance between position anchoring and curvature minimization. "
        "0 = vertices stay in place, 1 = full smoothing."
    ),
)

_PRESSURE = Param(
    "pressure",
    "float",
    default=0.0,
    label="Pressure",
    description="Internal mesh pressure along vertex normals.",
)

_REPAIR_PARAMS = (
    _SMOOTHNESS,
    _CURVATURE_WEIGHT,
    _PRESSURE,
    _BOUNDARY_RING,
)

_HOLE_SIZE = Param(
    "max_hole_size",
    "float",
    default=-1.0,
    min=-1.0,
    label="Hole Size",
    description="Maximum surface area of holes considered for triangulation.",
)

_SMOOTH_ITER = Param(
    "smooth_iter",
    "int",
    default=1,
    min=1,
    label="Smooth Iter",
    description="Number of smoothing iterations for normal estimation.",
)

_NORMAL_OFFSET = Param(
    "normal_offset",
    "float",
    default=0,
    min=-1e32,
    label="Offset",
    description="Points are shifted by n times normal vector for particle picking.",
)

_BIDIRECTIONAL = Param(
    "bidirectional",
    "bool",
    default=False,
    label="Bidirectional",
    description="Draw inward and outward facing points at the same time.",
    notes="This doubles the total number of points compared to running "
    "sample without this option set.",
)


_MESH_CURVATURE = Method(
    "Curvature",
    "mesh_curvature",
    description="Compute mesh curvature values per vertex.",
    params=(
        Param(
            "curvature",
            "str",
            options=("Mean", "Gaussian"),
            default="Mean",
            label="Type",
        ),
        Param(
            "radius",
            "int",
            default=5,
            min=1,
            max=20,
            label="Radius",
            description="Neighborhood radius for curvature estimation.",
        ),
    ),
)

_MESH_AREA = Method(
    "Area",
    "mesh_area",
    description="Compute mesh area.",
    params=(
        Param(
            "area_type",
            "str",
            options=("Total", "Per-Triangle"),
            default="Total",
            label="Type",
        ),
    ),
)

_MESH_VOLUME = Method(
    "Volume",
    "mesh_volume",
    description="Compute mesh volume.",
    params=(
        Param(
            "volume_type",
            "str",
            options=("Total", "Per-Triangle"),
            default="Total",
            label="Type",
        ),
    ),
)

_MESH_STATISTICS = Method(
    "Mesh Statistics",
    "mesh_statistics",
    description="Compute mesh statistics.",
    params=(
        Param(
            "stat_type",
            "str",
            options=("Vertex Count", "Triangle Count", "Edge Length"),
            default="Vertex Count",
            label="Type",
        ),
    ),
)

_DISTANCE = Method(
    "Distance",
    "distance",
    description="Compute nearest-neighbor distances.",
    params=(
        Param("queries", "str", description="Reference geometries (e.g. #0,#1)."),
        Param(
            "k",
            "int",
            default=1,
            min=1,
            label="K",
            description="Number of nearest neighbors.",
        ),
        Param(
            "k_start",
            "int",
            default=1,
            min=1,
            label="K Start",
            description="Starting neighbor index.",
        ),
        Param(
            "aggregation",
            "str",
            options=("mean", "min", "max", "median", "std"),
            default="mean",
            description="How to aggregate multi-neighbor distances.",
        ),
        Param(
            "include_self",
            "bool",
            default=False,
            description="Include self-distances.",
        ),
        Param(
            "only_self",
            "bool",
            default=False,
            description="Measure distances only to self.",
        ),
    ),
)

_THICKNESS = Method(
    "Thickness",
    "thickness",
    description="Estimate point cloud thickness along mesh normals.",
    params=(
        Param(
            "queries",
            "str",
            description="Cluster geometry to measure thickness from (e.g. #0).",
        ),
        Param(
            "smoothing_radius",
            "float",
            default=0.0,
            min=0.0,
            max=1000.0,
            decimals=1,
            label="Smoothing Radius",
            description="Radius for spatial smoothing (0 = none).",
        ),
    ),
)

_PROJECTED_CURVATURE = Method(
    "Projected Curvature",
    "projected_curvature",
    description="Project mesh curvature onto a point cloud.",
    params=(
        Param(
            "queries",
            "str",
            description="Reference mesh geometries (e.g. #0).",
        ),
        Param(
            "curvature",
            "str",
            options=("Mean", "Gaussian"),
            default="Mean",
            label="Type",
        ),
        Param("radius", "int", default=5, min=1, max=20, label="Radius"),
    ),
)

_GEODESIC_DISTANCE = Method(
    "Geodesic Distance",
    "geodesic_distance",
    description="Compute geodesic distances along mesh surface.",
    params=(
        Param(
            "queries",
            "str",
            description="Reference mesh geometries (e.g. #0).",
        ),
        Param("k", "int", default=1, min=1, label="K"),
        Param("k_start", "int", default=1, min=1, label="K Start"),
        Param(
            "aggregation",
            "str",
            options=("mean", "min", "max", "median", "std"),
            default="mean",
            label="Aggregation",
        ),
    ),
)

_PROJECTED_ANGLE = Method(
    "Projected Angle",
    "projected_angle",
    description="Angle between point normals and nearest mesh surface normal.",
    params=(
        Param(
            "queries",
            "str",
            description="Reference mesh geometries (e.g. #0).",
        ),
    ),
)

_VERTEX_PROPERTY = Method(
    "Vertex Property",
    "vertex_property",
    description="Retrieve a named vertex property.",
    params=(Param("name", "str", description="Property name to retrieve."),),
)

_BOX_SIZE = Method(
    "Box Size",
    "box_size",
    description="Compute bounding box dimensions.",
    params=(
        Param(
            "axis",
            "int",
            min=0,
            max=2,
            description="Single axis (0=x, 1=y, 2=z).",
        ),
    ),
)

_WIDTH = Method("Width", "width", description="Return X coordinates.")
_DEPTH = Method("Depth", "depth", description="Return Y coordinates.")
_HEIGHT = Method("Height", "height", description="Return Z coordinates.")
_N_POINTS = Method("Number of Points", "n_points", description="Return point count.")

_OUTPUT_DIR = Param(
    "output_dir",
    "path",
    label="Output Directory",
    file_mode=False,
    default="",
    placeholder="Optional: export results to directory",
    description="If set, write per-geometry CSV files with the computed values.",
)


MethodRegistry.register(
    Operation(
        name="measure",
        description="Compute a geometry property.",
        common_params=(
            Param(
                "store",
                "bool",
                default=False,
                description="Store results as vertex properties.",
            ),
            Param(
                "output",
                "path",
                default=None,
                description="Export results to a CSV file.",
            ),
        ),
        methods=(
            _MESH_CURVATURE,
            _MESH_AREA,
            _MESH_VOLUME,
            _MESH_STATISTICS,
            _DISTANCE,
            _THICKNESS,
            _PROJECTED_CURVATURE,
            _GEODESIC_DISTANCE,
            _PROJECTED_ANGLE,
            _VERTEX_PROPERTY,
            _BOX_SIZE,
            _WIDTH,
            _DEPTH,
            _HEIGHT,
            _N_POINTS,
        ),
    )
)

MethodRegistry.register(
    Operation(
        name="mesh_analysis",
        title="Mesh Analysis",
        common_params=(_OUTPUT_DIR,),
        methods=(_MESH_CURVATURE, _MESH_AREA, _MESH_VOLUME),
    )
)

MethodRegistry.register(
    Operation(
        name="open",
        description="Load geometries from file.",
        targets=False,
        common_params=(
            Param("filepath", "path", description="Path to the input file."),
            Param(
                "offset",
                "float",
                default=0,
                description="Coordinate offset to subtract from vertices.",
            ),
            Param(
                "scale",
                "float",
                default=None,
                description="Scale factor applied after offset. Defaults to the file's native sampling rate.",
            ),
            Param(
                "sampling_rate",
                "float",
                default=None,
                description="Override the file's native sampling rate.",
            ),
        ),
    )
)

MethodRegistry.register(
    Operation(
        name="save",
        description="Export geometries to file.",
        common_params=(
            Param("filepath", "path", description="Path to the output file."),
            Param(
                "format",
                "str",
                default="star",
                options=("star", "tsv", "xyz", "obj", "stl", "ply", "mrc", "em", "h5"),
                description="Output file format.",
            ),
            Param(
                "shape",
                "str",
                default=None,
                description="Tomogram dimensions as x,y,z. Used as output grid for "
                "volumes and coordinate origin for RELION 5. Inferred when omitted.",
            ),
            Param(
                "sampling",
                "float",
                default=None,
                description="Override sampling rate for coordinate scaling.",
            ),
            Param(
                "relion_5_format",
                "bool",
                default=False,
                description="Write origin-centered RELION 5 coordinates.",
            ),
        ),
    )
)

MethodRegistry.register(
    Operation(
        name="filter",
        description="Filter geometries by property value range.",
        common_params=(
            Param(
                "property",
                "str",
                description="Vertex property name or measure name.",
            ),
            Param(
                "lower",
                "float",
                default=None,
                description="Lower bound (inclusive).",
            ),
            Param(
                "upper",
                "float",
                default=None,
                description="Upper bound (inclusive).",
            ),
        ),
    )
)

MethodRegistry.register(
    Operation(
        name="merge",
        description="Merge geometries into one.",
        common_params=(
            Param(
                "name",
                "str",
                default=None,
                description="Name for the output geometry.",
            ),
        ),
    )
)

MethodRegistry.register(
    Operation(
        name="list",
        description="List loaded geometries. Filters support glob patterns (e.g. 0*, *TS21*) and substring matching.",
        targets=False,
        common_params=(
            Param("name", "str", default=None, description="Filter by geometry name."),
            Param(
                "type",
                "str",
                default=None,
                options=("cluster", "mesh", "parametric"),
                description="Filter by geometry type.",
            ),
            Param("group", "str", default=None, description="Filter by group name."),
            Param(
                "format",
                "str",
                default="table",
                options=("table", "ids"),
                description="Output format. Use format=ids for $(list ...) substitution.",
            ),
        ),
    )
)
