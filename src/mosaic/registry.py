"""
Unified method and parameter registry for Mosaic operations.

Defines parameters once; derives GUI settings dicts, REPL help,
and display-name resolution from a single source of truth.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

__all__ = ["Param", "Method", "Operation", "MethodRegistry"]


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
        Value used in code / REPL (e.g. ``"convexhull"``).
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


_K_NEIGHBORS = Param(
    "k_neighbors",
    "int",
    label="Neighbors",
    default=15,
    min=1,
    description="Number of neighbors for normal estimations.",
    notes="Consider decreasing this value for small point clouds.",
)

_ELASTIC_WEIGHT = Param(
    "elastic_weight",
    "float",
    default=0.0,
    min=-(2**28),
    label="Elastic Weight",
    description="Control mesh smoothness and elasticity.",
    notes="0 - strong anchoring, 1 - no anchoring, > 1 repulsion.",
)

_CURVATURE_WEIGHT = Param(
    "curvature_weight",
    "float",
    default=0.0,
    min=-(2**28),
    label="Curvature Weight",
    description="Controls propagation of mesh curvature.",
)

_VOLUME_WEIGHT = Param(
    "volume_weight",
    "float",
    default=0.0,
    min=-(2**28),
    label="Volume Weight",
    description="Controls internal pressure of mesh.",
)

_BOUNDARY_RING = Param(
    "boundary_ring",
    "int",
    default=0,
    label="Boundary Ring",
    description="Also optimize n-ring vertices for ill-defined boundaries.",
)

_ANCHORING = Param(
    "anchoring",
    "float_list",
    default="1",
    min="0",
    max="1",
    label="Flexibility",
    description=(
        "Flexibility of inferred vertices. 1 is maximum. Can be "
        "specified for all axes, e.g., 1, or per-axis, e.g., 1;1;0.5."
    ),
)

_REPAIR_PARAMS = (
    _ELASTIC_WEIGHT,
    _CURVATURE_WEIGHT,
    _VOLUME_WEIGHT,
    _BOUNDARY_RING,
    _ANCHORING,
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


MethodRegistry.register(
    Operation(
        name="fit",
        description="Fit a model to a point cloud",
        methods=(
            Method(
                "Alpha Shape",
                "convexhull",
                description="Alpha-shape based surface reconstruction.",
                params=(
                    Param(
                        "alpha",
                        "float",
                        default=1.0,
                        label="Alpha",
                        description="Alpha-shape parameter.",
                        notes="Large values yield coarser features.",
                    ),
                    Param(
                        "resampling_factor",
                        "float",
                        default=12.0,
                        label="Scaling Factor",
                        description="Resample mesh to factor times sampling rate.",
                        notes="Decrease for creating smoother repaired meshes.",
                    ),
                    Param(
                        "distance_cutoff",
                        "float",
                        default=2.0,
                        label="Distance",
                        description="Vertices further than distance time sampling rate are "
                        "labled as inferred for subsequent optimization.",
                    ),
                    *_REPAIR_PARAMS,
                ),
            ),
            Method(
                "Ball Pivoting",
                "mesh",
                description="Ball pivoting surface reconstruction.",
                params=(
                    Param(
                        "radii",
                        "str",
                        default="50",
                        label="Radii",
                        description="Ball radii used for surface reconstruction.",
                        notes="Use commas to specify multiple radii, e.g. '50,30.5,10.0'.",
                    ),
                    _HOLE_SIZE,
                    Param(
                        "downsample_input",
                        "bool",
                        default=True,
                        label="Downsample",
                        description="Thin input point cloud to core.",
                    ),
                    Param(
                        "n_smoothing",
                        "int",
                        default=5,
                        label="Smoothing Steps",
                        description="Pre-smoothing steps before fairing.",
                        notes="Improves repair but less impactful for topolgoy than weights.",
                    ),
                    _K_NEIGHBORS,
                    *_REPAIR_PARAMS,
                ),
            ),
            Method(
                "Cluster Ball Pivoting",
                "clusterballpivoting",
                description="Cluster-based ball pivoting reconstruction.",
                params=(
                    Param(
                        "radius",
                        "float",
                        default=0.0,
                        min=0.0,
                        max=100,
                        label="Radius",
                        description="Ball radius compared to point cloud box size.",
                        notes="Default 0 corresponds to an automatically determined radius.",
                    ),
                    Param(
                        "creasethr",
                        "float",
                        default=90.0,
                        min=0,
                        label="Mesh Angle",
                        description="Maximum crease angle before stoping ball pivoting.",
                    ),
                    _SMOOTH_ITER,
                    Param(
                        "deldist",
                        "float",
                        default=-1.0,
                        min=-1.0,
                        label="Distance",
                        description="Drop vertices distant from input sample points.",
                        notes="This is post-normalization by the sampling rate.",
                    ),
                    _K_NEIGHBORS,
                ),
            ),
            Method(
                "Poisson",
                "poissonmesh",
                description="Poisson surface reconstruction.",
                params=(
                    Param(
                        "depth",
                        "int",
                        default=9,
                        min=1,
                        label="Depth",
                        description="Depth of the Octree for surface reconstruction.",
                    ),
                    Param(
                        "samplespernode",
                        "float",
                        default=5.0,
                        min=0,
                        label="Samples",
                        description="Minimum number of points per octree node.",
                    ),
                    _SMOOTH_ITER,
                    Param(
                        "pointweight",
                        "float",
                        default=0.1,
                        min=0,
                        label="Pointweight",
                        description="Interpolation weight of point samples.",
                    ),
                    Param(
                        "scale",
                        "float",
                        default=1.2,
                        min=0,
                        label="Scale",
                        description="Ratio between reconstruction and sample cube.",
                    ),
                    Param(
                        "deldist",
                        "float",
                        default=-1.0,
                        min=-1.0,
                        label="Distance",
                        description="Drop vertices further than distance from input.",
                    ),
                    _K_NEIGHBORS,
                ),
            ),
            Method(
                "Flying Edges",
                "flyingedges",
                description="Flying edges isosurface extraction.",
                params=(
                    Param(
                        "distance",
                        "float",
                        default=-1.0,
                        min=-1.0,
                        max=1e32,
                        label="Distance",
                        description="Distance between points to be considered connected.",
                        notes="Defaults to the sampling rate of the object.",
                    ),
                    Param(
                        "smoothing_iterations",
                        "int",
                        default=15,
                        min=0,
                        label="Smoothing Iterations",
                        description="Number of windowed sinc smoothing iterations.",
                    ),
                    Param(
                        "smoothing_strength",
                        "float",
                        default=80.0,
                        min=0.0,
                        max=100.0,
                        label="Smoothing Strength",
                        description="Smoothing intensity (0 = none, 100 = maximum).",
                    ),
                    Param(
                        "feature_angle",
                        "float",
                        default=120.0,
                        min=0.0,
                        max=180.0,
                        label="Feature Angle",
                        description="Edges sharper than this angle are preserved during "
                        "smoothing.",
                        notes="Angle between adjacent triangle normals. 180 smooths "
                        "everything, lower values protect more edges.",
                    ),
                ),
            ),
            Method(
                "Sphere",
                "sphere",
                gui=False,
                description="Fit a sphere using least-squares.",
            ),
            Method(
                "Ellipsoid",
                "ellipsoid",
                gui=False,
                description="Fit an ellipsoid via eigenvalue decomposition.",
            ),
            Method(
                "Cylinder",
                "cylinder",
                gui=False,
                description="Fit a cylinder via PCA and constrained optimization.",
            ),
            Method(
                "RBF",
                "rbf",
                gui=False,
                description="Radial basis function interpolation.",
                params=(
                    Param(
                        "direction",
                        "str",
                        default="xz",
                        label="Direction",
                        options=("xy", "xz", "yz"),
                        description="Plane of the independent axes.",
                        notes="'xz' maps (x,z)->y, 'yz' maps (y,z)->x, "
                        "'xy' maps (x,y)->z.",
                    ),
                    Param(
                        "function",
                        "str",
                        default="linear",
                        label="Function",
                        description="Radial basis function type.",
                        notes="E.g. 'linear', 'thin_plate', 'multiquadric', 'cubic'.",
                    ),
                    Param(
                        "smooth",
                        "int",
                        default=5,
                        label="Smooth",
                        description="Smoothing factor for the RBF interpolator.",
                    ),
                ),
            ),
            Method(
                "Spline",
                "spline",
                gui=False,
                description="Fit a spline curve through control points.",
                params=(
                    Param(
                        "order",
                        "int",
                        default=1,
                        min=1,
                        max=5,
                        label="Order",
                        description="Spline degree. 1 = linear, 3 = cubic.",
                    ),
                ),
            ),
        ),
    )
)

MethodRegistry.register(
    Operation(
        name="cluster",
        description="Cluster points into groups",
        common_params=(
            Param(
                "use_points",
                "bool",
                default=True,
                label="Use Points",
                description="Use spatial coordinates for clustering",
            ),
            Param(
                "use_normals",
                "bool",
                default=False,
                label="Use Normals",
                description="Use normal vectors for clustering",
            ),
            Param(
                "drop_noise",
                "bool",
                default=True,
                label="Drop Noise",
                description="Drop noise cluster if available.",
            ),
        ),
        methods=(
            Method(
                "Connected Components",
                "connected_components",
                description="Connected components by spatial proximity.",
                params=(
                    Param(
                        "distance",
                        "float",
                        default=-1.0,
                        min=-1.0,
                        max=1e32,
                        label="Distance",
                        description="Distance between points to be considered connected.",
                        notes="Defaults to the associated sampling rate of the cluster.",
                    ),
                ),
            ),
            Method(
                "Envelope",
                "envelope",
                description="Envelope-based connected components.",
                params=(
                    Param(
                        "distance",
                        "float",
                        default=-1.0,
                        min=-1.0,
                        max=1e32,
                        label="Distance",
                        description="Distance between points to be considered connected.",
                        notes="Defaults to the associated sampling rate of the cluster.",
                    ),
                ),
            ),
            Method(
                "Leiden",
                "leiden",
                description="Leiden graph-based clustering.",
                params=(
                    Param(
                        "distance",
                        "float",
                        default=-1.0,
                        min=-1.0,
                        max=1e32,
                        label="Distance",
                        description="Distance between points to be considered connected.",
                        notes="Defaults to the associated sampling rate of the cluster.",
                    ),
                    Param(
                        "resolution_parameter",
                        "float",
                        default=-7.3,
                        min=-1e32,
                        max=1e32,
                        decimals=8,
                        label="Resolution (log10)",
                        description="Log10 of resolution parameter for graph clustering.",
                        notes="Smaller values yield larger clusters. Range: -8 to -2 for membranes.",
                    ),
                ),
            ),
            Method(
                "DBSCAN",
                "dbscan",
                description="DBSCAN density-based clustering.",
                params=(
                    Param(
                        "distance",
                        "float",
                        default=100.0,
                        label="Distance",
                        description="Expected distance between neighbors in a cluster.",
                    ),
                    Param(
                        "min_points",
                        "int",
                        default=500,
                        min=1,
                        label="Min Points",
                        description="Minimum cluster size.",
                    ),
                ),
            ),
            Method(
                "K-Means",
                "kmeans",
                description="K-Means partitioning.",
                params=(Param("k", "int", default=2, min=1, label="Clusters"),),
            ),
            Method(
                "Birch",
                "birch",
                description="Birch hierarchical clustering.",
                params=(
                    Param(
                        "n_clusters",
                        "int",
                        default=3,
                        min=1,
                        label="Clusters",
                        description="Number of clusters to form.",
                    ),
                    Param(
                        "threshold",
                        "float",
                        default=50.0,
                        label="Threshold",
                        description="Radius for merging subclusters. Lower values create more clusters.",
                    ),
                    Param(
                        "branching_factor",
                        "int",
                        default=50,
                        min=1,
                        label="Branching Factor",
                        description="Max subclusters per node. Higher values use more memory.",
                    ),
                ),
            ),
        ),
    )
)

MethodRegistry.register(
    Operation(
        name="downsample",
        description="Downsample point cloud",
        methods=(
            Method(
                "Radius",
                "radius",
                description="Uniform voxel grid downsampling.",
                params=(
                    Param(
                        "voxel_size",
                        "float",
                        default=40.0,
                        label="Radius",
                        notes="Points within this radius are merged into one point per "
                        "voxel. Larger values produce coarser results.",
                    ),
                ),
            ),
            Method(
                "Number",
                "number",
                description="Random subsampling to target count.",
                params=(
                    Param(
                        "size",
                        "int",
                        default=1000,
                        min=1,
                        label="Number",
                        notes="Randomly selects this many points from the input.",
                    ),
                ),
            ),
            Method(
                "Center of Mass",
                "center_of_mass",
                description="Replace nearby points by their centroid.",
                params=(
                    Param(
                        "radius",
                        "float",
                        default=40.0,
                        label="Radius",
                        notes="Points within this radius are clustered and replaced by "
                        " their centroid. Larger values produce coarser results.",
                    ),
                ),
            ),
        ),
    )
)

MethodRegistry.register(
    Operation(
        name="skeletonize",
        description="Extract structural skeleton from point cloud",
        methods=(
            Method(
                "core",
                "core",
                description="Extract medial axis/centerline through the middle of structures.",
                params=(
                    Param(
                        "sigma",
                        "float",
                        default=1.0,
                        min=0.1,
                        max=10.0,
                        label="Sigma",
                        description="Gaussian smoothing for Hessian computation.",
                        notes="Higher sigma produces smoother skeletons.",
                    ),
                ),
            ),
            Method(
                "boundary",
                "boundary",
                description="Extract both inner and outer boundaries for hollow structures.",
                params=(
                    Param(
                        "sigma",
                        "float",
                        default=1.0,
                        min=0.1,
                        max=10.0,
                        label="Sigma",
                        description="Gaussian smoothing for Hessian computation.",
                        notes="Higher sigma produces smoother boundaries.",
                    ),
                ),
            ),
            Method(
                "outer",
                "outer",
                description="Extract outer boundary via skeletonization + convex hull.",
                params=(
                    Param(
                        "sigma",
                        "float",
                        default=1.0,
                        min=0.1,
                        max=10.0,
                        label="Sigma",
                        description="Gaussian smoothing for Hessian computation.",
                        notes="Higher sigma produces smoother results before convex hull fitting.",
                    ),
                ),
            ),
            Method(
                "outer_hull",
                "outer_hull",
                description="Fast convex hull approximation (legacy, no skeletonization).",
                params=(
                    Param(
                        "sample_fraction",
                        "float",
                        default=0.5,
                        min=0.1,
                        max=1.0,
                        label="Sample fraction",
                        description="Fraction of points to sample from convex hull.",
                        notes="Controls density of output points on the convex hull surface.",
                    ),
                ),
            ),
        ),
    )
)

MethodRegistry.register(
    Operation(
        name="smooth",
        description="Smooth a triangle mesh",
        methods=(
            Method(
                "Taubin",
                "taubin",
                description="Volume-preserving Taubin smoothing.",
                params=(
                    Param(
                        "number_of_iterations",
                        "int",
                        default=10,
                        min=1,
                        label="Iterations",
                        description="Number of smoothing iterations.",
                        notes="Taubin filter prevents mesh shrinkage by applying two "
                        "Laplacian filters with different parameters.",
                    ),
                ),
            ),
            Method(
                "Laplacian",
                "laplacian",
                description="Laplacian mesh smoothing.",
                params=(
                    Param(
                        "number_of_iterations",
                        "int",
                        default=10,
                        min=1,
                        label="Iterations",
                        description="Number of smoothing iterations.",
                        notes="May lead to mesh shrinkage with high iteration counts.",
                    ),
                ),
            ),
            Method(
                "Average",
                "average",
                description="Simple neighbor averaging.",
                params=(
                    Param(
                        "number_of_iterations",
                        "int",
                        default=5,
                        min=1,
                        label="Iterations",
                        description="Number of smoothing iterations.",
                        notes="Simplest filter - vertices are replaced by the average "
                        "of adjacent vertices.",
                    ),
                ),
            ),
        ),
    )
)

MethodRegistry.register(
    Operation(
        name="remesh",
        description="Remesh a triangle mesh",
        methods=(
            Method(
                "Decimation",
                "decimation",
                description="Reduce triangle count via decimation.",
                params=(
                    Param(
                        "decimation_method",
                        "str",
                        label="Method",
                        options=("Triangle Count", "Reduction Factor"),
                        default="Reduction Factor",
                        description="Choose how to specify the decimation target.",
                    ),
                    Param(
                        "sampling",
                        "float",
                        default=10,
                        min=0,
                        label="Sampling",
                        description="Numerical value for reduction method.",
                    ),
                    Param(
                        "smooth",
                        "bool",
                        default=True,
                        label="Smooth",
                        description="Use quadratic decimation instead of pyfqmr.",
                    ),
                ),
            ),
            Method(
                "Edge Length",
                "edge_length",
                description="Remesh to target edge length.",
                params=(
                    Param(
                        "target_edge_length",
                        "float",
                        default=40.0,
                        min=1e-6,
                        label="Edge Length",
                        description="Average edge length to remesh to.",
                    ),
                    Param(
                        "n_iter",
                        "int",
                        default=100,
                        min=1,
                        label="Iterations",
                        description="Number of remeshing operations to repeat on the mesh.",
                    ),
                    Param(
                        "featuredeg",
                        "float",
                        default=30.0,
                        min=0.0,
                        label="Mesh Angle",
                        description="Minimum angle between faces to preserve the edge feature.",
                    ),
                ),
            ),
            Method(
                "Subdivide",
                "subdivide",
                description="Subdivide mesh triangles.",
                params=(
                    Param(
                        "number_of_iterations",
                        "int",
                        default=1,
                        min=1,
                        label="Iterations",
                        description="Number of iterations.",
                        notes="A single iteration splits each triangle into four triangles.",
                    ),
                    Param(
                        "smooth",
                        "bool",
                        default=True,
                        label="Smooth",
                        description="Perform smooth midpoint division.",
                    ),
                ),
            ),
            Method(
                "Vertex Clustering",
                "vertex_clustering",
                description="Simplify via vertex clustering.",
                params=(
                    Param(
                        "voxel_size",
                        "float",
                        default=40.0,
                        min=1e-6,
                        label="Radius",
                        description="Radius within which vertices are clustered.",
                    ),
                ),
            ),
        ),
    )
)

MethodRegistry.register(
    Operation(
        name="compute_normals",
        description="Compute or flip point normals.",
        methods=(
            Method(
                "Compute",
                "compute",
                description="Calculate new normals from point neighborhoods.",
                params=(
                    Param(
                        "k",
                        "int",
                        default=15,
                        min=3,
                        max=100,
                        label="Neighbors",
                        description="Number of neighboring points to consider for normal estimation",
                    ),
                ),
            ),
            Method(
                "Flip",
                "flip",
                description="Reverse existing normal directions.",
                params=(),
            ),
        ),
    )
)

MethodRegistry.register(
    Operation(
        name="remove_outliers",
        description="Remove statistical outliers from point cloud.",
        common_params=(
            Param(
                "k_neighbors",
                "int",
                default=10,
                min=1,
                label="Neighbors",
                description="k-neigbors for estimating local densities.",
            ),
            Param(
                "thresh",
                "float",
                default=0.02,
                label="Threshold",
                description="Threshold is sdev for statistical, eigenvalue ratio otherwise.",
            ),
        ),
        methods=(
            Method(
                "statistical",
                "statistical",
                description="General statistical outlier removal.",
            ),
            Method(
                "eigenvalue",
                "eigenvalue",
                description="Eigenvalue-based edge noise removal.",
            ),
        ),
    )
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
        methods=(_MESH_CURVATURE, _MESH_AREA, _MESH_VOLUME, _MESH_STATISTICS),
    )
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

MethodRegistry.register(
    Operation(
        name="sample",
        description="Sample points from a fitted model.",
        methods=(
            Method(
                "Distance",
                "Distance",
                description="Sampling rate as average distance between points.",
            ),
            Method(
                "Points",
                "Points",
                description="Sampling rate as number of points.",
            ),
        ),
        common_params=(
            Param(
                "sampling",
                "float",
                default=40,
                min=1,
                label="Sampling",
                description="Numerical value for sampling method.",
            ),
            _NORMAL_OFFSET,
            _BIDIRECTIONAL,
        ),
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
                "single_file",
                "bool",
                default=None,
                description="Write all geometries into a single file.",
            ),
            Param(
                "shape_x", "int", default=None, description="Volume shape along X axis."
            ),
            Param(
                "shape_y", "int", default=None, description="Volume shape along Y axis."
            ),
            Param(
                "shape_z", "int", default=None, description="Volume shape along Z axis."
            ),
            Param(
                "sampling",
                "float",
                default=None,
                description="Voxel sampling rate for volumes.",
            ),
            Param(
                "relion_5_format",
                "bool",
                default=False,
                description="Apply RELION 5 format coordinate transformation.",
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
        name="duplicate",
        description="Duplicate a geometry.",
    )
)

MethodRegistry.register(
    Operation(
        name="visibility",
        description="Change geometry visibility.",
        common_params=(
            Param(
                "visible",
                "bool",
                default=True,
                description="Whether the geometry should be visible.",
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
