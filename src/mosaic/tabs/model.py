from functools import partial

import numpy as np
from qtpy.QtWidgets import QWidget, QVBoxLayout

from .. import meshing
from ..widgets.ribbon import create_button
from ..parallel import submit_task, submit_task_batch


def _project(
    mesh_geometry,
    geometries,
    use_normals: bool = False,
    invert_normals: bool = False,
    update_normals: bool = False,
):
    from ..geometry import Geometry

    mesh = mesh_geometry.model
    new_geometries, projections, triangles = [], [], []
    for geometry in geometries:
        normals = geometry.normals if use_normals else None
        if normals is not None:
            normals = normals * (-1 if invert_normals else 1)

        kwargs = {
            "points": geometry.points,
            "normals": normals,
            "return_projection": True,
            "return_indices": False,
            "return_triangles": True,
        }
        _, projection, triangle = mesh.compute_distance(**kwargs)

        normals = geometry.normals
        if update_normals:
            normals = mesh.compute_normal(projection)

        projections.append(projection)
        triangles.append(triangle)
        new_geometries.append(
            Geometry(
                points=projection, normals=normals, sampling_rate=geometry.sampling_rate
            )
        )

    if not len(projections):
        return None

    projections = np.concatenate(projections)
    triangles = np.concatenate(triangles)
    new_mesh = mesh.add_projections(projections, triangles, return_indices=False)
    new_mesh = Geometry(model=new_mesh, sampling_rate=mesh_geometry.sampling_rate)

    return new_mesh, new_geometries


class ModelTab(QWidget):
    def __init__(self, cdata, ribbon, legend, **kwargs):
        super().__init__()
        self.cdata = cdata
        self.ribbon = ribbon
        self.legend = legend

        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ribbon)

    def show_ribbon(self):
        self.ribbon.clear()

        func = self._fit_parallel
        fitting_actions = [
            create_button("Sphere", "mdi.circle", self, partial(func, "sphere")),
            create_button("Ellipse", "mdi.ellipse", self, partial(func, "ellipsoid")),
            create_button("Cylinder", "mdi.hexagon", self, partial(func, "cylinder")),
            create_button(
                "RBF", "mdi.grid", self, partial(func, "rbf"), "Fit RBF", RBF_SETTINGS
            ),
            create_button(
                "Mesh", "mdi.triangle-outline", self, func, "Fit Mesh", MESH_SETTINGS
            ),
            create_button(
                "Curve",
                "mdi.chart-bell-curve",
                self,
                partial(func, "spline"),
                "Fit Spline",
                SPLINE_SETTINGS,
            ),
        ]
        self.ribbon.add_section("Parametrization", fitting_actions)

        mesh_actions = [
            create_button(
                "Sample",
                "mdi.chart-scatter-plot",
                self,
                self._sample_parallel,
                "Sample from Fit",
                SAMPLE_SETTINGS,
            ),
        ]
        self.ribbon.add_section("Sampling", mesh_actions)

        mesh_actions = [
            create_button(
                "Repair",
                "mdi.auto-fix",
                self,
                self._repair_mesh,
                "Repair Mesh",
                REPAIR_SETTINGS,
            ),
            create_button(
                "Remesh",
                "mdi.repeat",
                self,
                self._remesh_parallel,
                "Remesh Mesh",
                REMESH_SETTINGS,
            ),
            create_button(
                "Smooth",
                "mdi.blur",
                self,
                self._smooth_parallel,
                "Smooth Mesh",
                SMOOTH_SETTINGS,
            ),
            create_button(
                "Project",
                "mdi.vector-curve",
                self,
                self._project_on_mesh,
                "Project on Mesh",
                PROJECTION_SETTINGS,
            ),
        ]
        self.ribbon.add_section("Mesh Operations", mesh_actions)

    def _default_callback(self, geom):
        from ..parametrization import TriangularMesh

        if isinstance(geom.model, TriangularMesh):
            geom.change_representation("surface")
        self.cdata.models.add(geom)
        self.cdata.models.render()

    def _get_selected_meshes(self):
        from ..parametrization import TriangularMesh

        ret = []
        for geometry in self.cdata.models.get_selected_geometries():
            fit = geometry.model
            if not isinstance(fit, TriangularMesh):
                continue
            ret.append(geometry)
        return ret

    def _repair_mesh(
        self,
        max_hole_size=-1,
        elastic_weight=0,
        curvature_weight=0,
        volume_weight=0,
        boundary_ring=0,
        **kwargs,
    ):
        from ..parametrization import TriangularMesh

        for geometry in self._get_selected_meshes():
            fit = geometry.model
            fit.mesh.remove_non_manifold_edges()
            fit.mesh.remove_degenerate_triangles()
            fit.mesh.remove_duplicated_triangles()
            fit.mesh.remove_unreferenced_vertices()
            fit.mesh.remove_duplicated_vertices()
            vs, fs = meshing.triangulate_refine_fair(
                vs=fit.vertices,
                fs=fit.triangles,
                alpha=elastic_weight,
                beta=curvature_weight,
                gamma=volume_weight,
                hole_len_thr=max_hole_size,
                n_ring=boundary_ring,
            )
            geom = geometry[...]
            geom._model = TriangularMesh(meshing.to_open3d(vs, fs))
            geom.change_representation("surface")
            self.cdata.models.add(geom)
        return self.cdata.models.render()

    def _fit_parallel(self, method: str, *args, **kwargs):
        from ..operations import GeometryOperations

        # These methods are parallelize and would mess with the worker pool
        tasks, max_concurrent = [], None
        if method in ("Poisson", "Marching Cubes"):
            max_concurrent = 1

        for geometry in self.cdata.data.get_selected_geometries():
            tasks.append(
                {
                    "name": "Parametrization",
                    "func": GeometryOperations.fit,
                    "callback": self._default_callback,
                    "kwargs": {"geometry": geometry, "method": method} | kwargs,
                }
            )
        submit_task_batch(tasks, max_concurrent=max_concurrent)

    def _smooth_parallel(self, method, **kwargs):
        from ..operations import GeometryOperations

        for geometry in self._get_selected_meshes():
            submit_task(
                "Smooth",
                GeometryOperations.smooth,
                self._default_callback,
                geometry,
                method,
                **kwargs,
            )

    def _sample_parallel(self, sampling, method, normal_offset=0.0, **kwargs):
        from ..operations import GeometryOperations

        def _callback(*args, **kwargs):
            self.cdata.data.add(*args, **kwargs)
            self.cdata.data.render()

        for geometry in self.cdata.models.get_selected_geometries():
            submit_task(
                "Sample Fit",
                GeometryOperations.sample,
                _callback,
                geometry,
                method=method,
                sampling=sampling,
                normal_offset=normal_offset,
                **kwargs,
            )

    def _remesh_parallel(self, method, **kwargs):
        from ..operations import GeometryOperations

        for geometry in self._get_selected_meshes():
            submit_task(
                "Remesh",
                GeometryOperations.remesh,
                self._default_callback,
                geometry,
                method,
                **kwargs,
            )

    def _project_on_mesh(
        self,
        use_normals: bool = False,
        invert_normals: bool = False,
        update_normals: bool = False,
        **kwargs,
    ):
        selected_meshes = self._get_selected_meshes()
        if len(selected_meshes) != 1:
            raise ValueError("Please select one mesh for projection.")

        mesh = selected_meshes[0]
        if mesh.model is None:
            return None

        def _callback(ret):
            new_mesh, new_geometries = ret

            for new_geometry in new_geometries:
                self.cdata.data.add(new_geometry)

            new_mesh.change_representation("surface")
            self.cdata.models.add(new_mesh)
            self.cdata.data.render()
            self.cdata.models.render()

        submit_task(
            "Project",
            _project,
            _callback,
            mesh,
            self.cdata.data.get_selected_geometries(),
            use_normals,
            invert_normals,
            update_normals,
        )


SAMPLE_SETTINGS = {
    "title": "Sample Fit",
    "settings": [
        {
            "label": "Sampling Method",
            "parameter": "method",
            "type": "select",
            "options": ["Points", "Distance"],
            "default": "Distance",
            "notes": "Number of points or average distance between points.",
        },
        {
            "label": "Sampling",
            "parameter": "sampling",
            "type": "float",
            "min": 1,
            "default": 40,
            "notes": "Numerical value for sampling method.",
        },
        {
            "label": "Offset",
            "parameter": "normal_offset",
            "type": "float",
            "default": 0,
            "min": -1e32,
            "notes": "Points are shifted by n times normal vector for particle picking.",
        },
        {
            "label": "Bidirectional",
            "parameter": "bidirectional",
            "type": "boolean",
            "default": False,
            "notes": "Draw inward and outward facing points at the same time. This "
            "doubles the total number of points compared to running sample without "
            "this option set.",
        },
    ],
}

RBF_SETTINGS = {
    "title": "RBF Settings",
    "settings": [
        {
            "label": "Direction",
            "parameter": "direction",
            "type": "select",
            "options": ["xy", "xz", "yz"],
            "default": "xy",
            "description": "Coordinate plane to fit RBF in.",
        },
    ],
}

SPLINE_SETTINGS = {
    "title": "Curve Settings",
    "settings": [
        {
            "label": "Order",
            "parameter": "order",
            "type": "number",
            "default": 3,
            "min": 1,
            "max": 5,
            "description": "Spline order to fit to control points.",
        },
    ],
}

REPAIR_SETTINGS = {
    "title": "Repair Settings",
    "settings": [
        {
            "label": "Elastic Weight",
            "parameter": "elastic_weight",
            "type": "float",
            "default": 0.0,
            "min": -(2**28),
            "description": "Control mesh smoothness and elasticity.",
            "notes": "0 - strong anchoring, 1 - no anchoring, > 1 repulsion.",
        },
        {
            "label": "Curvature Weight",
            "parameter": "curvature_weight",
            "type": "float",
            "default": 0.0,
            "min": -(2**28),
            "description": "Controls propagation of mesh curvature.",
        },
        {
            "label": "Volume Weight",
            "parameter": "volume_weight",
            "type": "float",
            "default": 0.0,
            "min": -(2**28),
            "description": "Controls internal pressure of mesh.",
        },
        {
            "label": "Boundary Ring",
            "parameter": "boundary_ring",
            "type": "number",
            "default": 0,
            "description": "Also optimize n-ring vertices for ill-defined boundaries.",
        },
        {
            "label": "Flexibility",
            "parameter": "anchoring",
            "type": "float_list",
            "default": "1",
            "min": "0",
            "max": "1",
            "description": "Flexibility of inferred vertices. 1 is maximum. Can be "
            "specified for all axes, e.g., 1, or per-axis, e.g., 1;1;0.5.",
        },
        {
            "label": "Hole Size",
            "parameter": "max_hole_size",
            "type": "float",
            "min": -1.0,
            "default": -1.0,
            "description": "Maximum surface area of holes considered for triangulation.",
        },
    ],
}


REMESH_SETTINGS = {
    "title": "Remesh Settings",
    "settings": [
        {
            "label": "Method",
            "parameter": "method",
            "type": "select",
            "options": [
                "Decimation",
                "Edge Length",
                "Subdivide",
                "Vertex Clustering",
            ],
            "default": "Decimation",
        },
    ],
    "method_settings": {
        "Edge Length": [
            {
                "label": "Edge Length",
                "parameter": "target_edge_length",
                "type": "float",
                "default": 40.0,
                "min": 1e-6,
                "description": "Average edge length to remesh to.",
            },
            {
                "label": "Iterations",
                "parameter": "n_iter",
                "type": "number",
                "default": 100,
                "min": 1,
                "description": "Number of remeshing operations to repeat on the mesh.",
            },
            {
                "label": "Mesh Angle",
                "parameter": "featuredeg",
                "type": "float",
                "default": 30.0,
                "min": 0.0,
                "description": "Minimum angle between faces to preserve the edge feature.",
            },
        ],
        "Vertex Clustering": [
            {
                "label": "Radius",
                "parameter": "voxel_size",
                "type": "float",
                "default": 40.0,
                "min": 1e-6,
                "description": "Radius within which vertices are clustered.",
            },
        ],
        "Decimation": [
            {
                "label": "Method",
                "parameter": "decimation_method",
                "type": "select",
                "options": ["Triangle Count", "Reduction Factor"],
                "default": "Reduction Factor",
                "description": "Choose how to specify the decimation target.",
            },
            {
                "label": "Sampling",
                "parameter": "sampling",
                "type": "float",
                "default": 10,
                "min": 0,
                "description": "Numerical value for reduction method.",
            },
            {
                "label": "Smooth",
                "parameter": "smooth",
                "type": "boolean",
                "default": True,
                "description": "Use quadratic decimation instead of pyfqmr.",
            },
        ],
        "Subdivide": [
            {
                "label": "Iterations",
                "parameter": "number_of_iterations",
                "type": "number",
                "default": 1,
                "min": 1,
                "description": "Number of iterations.",
                "notes": "A single iteration splits each triangle into four triangles.",
            },
            {
                "label": "Smooth",
                "parameter": "smooth",
                "type": "boolean",
                "default": True,
                "description": "Perform smooth midpoint division.",
            },
        ],
    },
}


SMOOTH_SETTINGS = {
    "title": "Smooth Settings",
    "settings": [
        {
            "label": "Method",
            "parameter": "method",
            "type": "select",
            "options": [
                "Taubin",
                "Laplacian",
                "Average",
            ],
            "default": "Taubin",
        },
    ],
    "method_settings": {
        "Taubin": [
            {
                "label": "Iterations",
                "parameter": "number_of_iterations",
                "type": "number",
                "default": 10,
                "min": 1,
                "description": "Number of smoothing iterations.",
                "notes": "Taubin filter prevents mesh shrinkage by applying two Laplacian filters with different parameters.",
            },
        ],
        "Laplacian": [
            {
                "label": "Iterations",
                "parameter": "number_of_iterations",
                "type": "number",
                "default": 10,
                "min": 1,
                "description": "Number of smoothing iterations.",
                "notes": "May lead to mesh shrinkage with high iteration counts.",
            },
        ],
        "Average": [
            {
                "label": "Iterations",
                "parameter": "number_of_iterations",
                "type": "number",
                "default": 5,
                "min": 1,
                "description": "Number of smoothing iterations.",
                "notes": "Simplest filter - vertices are replaced by the average of adjacent vertices.",
            },
        ],
    },
}

MESH_SETTINGS = {
    "title": "Mesh Settings",
    "settings": [
        {
            "label": "Method",
            "parameter": "method",
            "type": "select",
            "options": [
                "Alpha Shape",
                "Ball Pivoting",
                "Cluster Ball Pivoting",
                "Poisson",
                "Flying Edges",
                "Marching Cubes",
            ],
            "default": "Alpha Shape",
        },
        *REPAIR_SETTINGS["settings"][:5],
    ],
    "method_settings": {
        "Alpha Shape": [
            {
                "label": "Alpha",
                "parameter": "alpha",
                "type": "float",
                "default": 1.0,
                "description": "Alpha-shape parameter.",
                "notes": "Large values yield coarser features.",
            },
            {
                "label": "Scaling Factor",
                "parameter": "resampling_factor",
                "type": "float",
                "default": 12.0,
                "description": "Resample mesh to scaling factor times sampling rate.",
                "notes": "Decrease for creating smoother pressurized meshes.",
            },
            {
                "label": "Distance",
                "parameter": "distance_cutoff",
                "type": "float",
                "default": 2.0,
                "description": "Vertices further than distance time sampling rate are "
                "labled as inferred for subsequent optimization.",
            },
        ],
        "Ball Pivoting": [
            {
                "label": "Radii",
                "parameter": "radii",
                "type": "text",
                "default": "50",
                "description": "Ball radii used for surface reconstruction.",
                "notes": "Use commas to specify multiple radii, e.g. '50,30.5,10.0'.",
            },
            REPAIR_SETTINGS["settings"][-1],
            {
                "label": "Downsample",
                "parameter": "downsample_input",
                "type": "boolean",
                "default": True,
                "description": "Thin input point cloud to core.",
            },
            {
                "label": "Smoothing Steps",
                "parameter": "n_smoothing",
                "type": "number",
                "default": 5,
                "description": "Pre-smoothing steps before fairing.",
                "notes": "Improves repair but less impactful for topolgoy than weights.",
            },
            {
                "label": "Neighbors",
                "parameter": "k_neighbors",
                "type": "number",
                "min": 1,
                "default": 15,
                "description": "Number of neighbors for normal estimations.",
                "notes": "Consider decreasing this value for small point clouds.",
            },
        ],
        "Cluster Ball Pivoting": [
            {
                "label": "Radius",
                "parameter": "radius",
                "type": "float",
                "default": 0.0,
                "max": 100,
                "min": 0.0,
                "description": "Ball radius compared to point cloud box size.",
                "notes": "Default 0 corresponds to an automatically determined radius.",
            },
            {
                "label": "Mesh Angle",
                "parameter": "creasethr",
                "type": "float",
                "min": 0,
                "default": 90.0,
                "description": "Maximum crease angle before stoping ball pivoting.",
            },
            {
                "label": "Smooth Iter",
                "parameter": "smooth_iter",
                "type": "number",
                "min": 1,
                "default": 1,
                "description": "Number of smoothing iterations for normal estimation.",
            },
            {
                "label": "Distance",
                "parameter": "deldist",
                "type": "float",
                "min": -1.0,
                "default": -1.0,
                "description": "Drop vertices distant from input sample points.",
                "notes": "This is post-normalization by the sampling rate.",
            },
            {
                "label": "Neighbors",
                "parameter": "k_neighbors",
                "type": "number",
                "min": 1,
                "default": 15,
                "description": "Number of neighbors for normal estimations.",
                "notes": "Consider decreasing this value for small point clouds.",
            },
        ],
        "Poisson": [
            {
                "label": "Depth",
                "parameter": "depth",
                "type": "number",
                "min": 1,
                "default": 9,
                "description": "Depth of the Octree for surface reconstruction.",
            },
            {
                "label": "Samples",
                "parameter": "samplespernode",
                "type": "float",
                "min": 0,
                "default": 5.0,
                "description": "Minimum number of points per octree node.",
            },
            {
                "label": "Smooth Iter",
                "parameter": "smooth_iter",
                "type": "number",
                "min": 1,
                "default": 1,
                "description": "Number of smoothing iterations for normal estimation.",
            },
            {
                "label": "Pointweight",
                "parameter": "pointweight",
                "type": "float",
                "min": 0,
                "default": 0.1,
                "description": "Interpolation weight of point samples.",
            },
            {
                "label": "Scale",
                "parameter": "scale",
                "type": "float",
                "min": 0,
                "default": 1.2,
                "description": "Ratio between reconstruction and sample cube.",
            },
            {
                "label": "Distance",
                "parameter": "deldist",
                "type": "float",
                "min": -1.0,
                "default": -1.0,
                "description": "Drop vertices further than distance from input.",
            },
            {
                "label": "Neighbors",
                "parameter": "k_neighbors",
                "type": "number",
                "min": 1,
                "default": 15,
                "description": "Number of neighbors for normal estimations.",
                "notes": "Consider decreasing this value for small point clouds.",
            },
        ],
        "Flying Edges": [
            {
                "label": "Distance",
                "parameter": "distance",
                "type": "float",
                "description": "Distance between points to be considered connected.",
                "default": -1.0,
                "min": -1.0,
                "max": 1e32,
                "notes": "Defaults to the sampling rate of the object.",
            },
        ],
        "Marching Cubes": [
            {
                "label": "Simplifcation Factor",
                "parameter": "simplification_factor",
                "type": "number",
                "default": 100,
                "min": 1,
                "description": "Reduce initial mesh by x times the number of triangles.",
            },
            {
                "label": "Workers",
                "parameter": "num_workers",
                "type": "number",
                "default": 8,
                "min": 1,
                "description": "Number of parallel workers to use.",
            },
            {
                "label": "Close Dataset Edges",
                "parameter": "closed_dataset_edges",
                "type": "boolean",
                "default": True,
                "description": "Close mesh at at dataset edges.",
            },
        ],
    },
}


PROJECTION_SETTINGS = {
    "title": "Projection Settings",
    "settings": [
        {
            "label": "Cast Normals",
            "parameter": "use_normals",
            "type": "boolean",
            "default": True,
            "description": "Include normal vectors in raycasting.",
        },
        {
            "label": "Invert Normals",
            "parameter": "invert_normals",
            "type": "boolean",
            "default": False,
            "description": "Invert direction of normal vectors.",
        },
        {
            "label": "Update Normals",
            "parameter": "update_normals",
            "type": "boolean",
            "default": False,
            "description": "Update normal vectors of projection based on the mesh.",
        },
    ],
}
