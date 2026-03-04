from functools import partial

import numpy as np
from qtpy.QtWidgets import QWidget, QVBoxLayout

from .. import meshing
from ..widgets.ribbon import create_button
from ..parallel import submit_task, submit_task_batch


def _fill_mesh(mesh_geometry):
    from ..geometry import Geometry

    model = mesh_geometry.model
    voxel_size = max(mesh_geometry.sampling_rate)
    points = meshing.fill_mesh(model.vertices, model.triangles, voxel_size=voxel_size)
    return Geometry(points=points, sampling_rate=mesh_geometry.sampling_rate)


def _project(
    mesh_geometries,
    geometries,
    use_normals: bool = False,
    invert_normals: bool = False,
    update_normals: bool = False,
    partition: bool = False,
):
    from ..geometry import Geometry

    meshes = [mg.model for mg in mesh_geometries]
    n_meshes = len(meshes)

    data_out, meshes_out = [], []
    mesh_subsets = [[] for _ in range(n_meshes)]
    mesh_proj = [[] for _ in range(n_meshes)]
    mesh_tri = [[] for _ in range(n_meshes)]

    for geometry in geometries:
        normals = geometry.normals if use_normals else None
        if normals is not None:
            normals = normals * (-1 if invert_normals else 1)

        all_dist, all_proj, all_tri = [], [], []
        for mesh in meshes:
            dist, proj, tri = mesh.compute_distance(
                points=geometry.points,
                normals=normals,
                return_projection=True,
                return_indices=False,
                return_triangles=True,
            )
            all_dist.append(dist)
            all_proj.append(proj)
            all_tri.append(tri)

        best = np.argmin(np.stack(all_dist), axis=0)
        proj_sel = np.empty_like(all_proj[0])

        for m in range(n_meshes):
            mask = best == m
            if not mask.any():
                continue
            if partition:
                mesh_subsets[m].append(geometry[mask])
            else:
                proj_m = all_proj[m][mask]
                proj_sel[mask] = proj_m
                mesh_proj[m].append(proj_m)
                mesh_tri[m].append(all_tri[m][mask])

        if not partition:
            geo_normals = geometry.normals
            if update_normals:
                geo_normals = np.empty((len(geometry.points), 3))
                for m in range(n_meshes):
                    mask = best == m
                    if mask.any():
                        geo_normals[mask] = meshes[m].compute_normal(proj_sel[mask])
            data_out.append(
                Geometry(
                    points=proj_sel,
                    normals=geo_normals,
                    sampling_rate=geometry.sampling_rate,
                )
            )

    if partition:
        for m, subsets in enumerate(mesh_subsets):
            if subsets:
                geom = subsets[0] if len(subsets) == 1 else Geometry.merge(subsets)
                name = mesh_geometries[m]._meta.get("name", f"Mesh {m}")
                geom._meta["name"] = f"{name}_partition"
                data_out.append(geom)
    else:
        for m in range(n_meshes):
            if not mesh_proj[m]:
                continue
            new_model = meshes[m].add_projections(
                np.concatenate(mesh_proj[m]),
                np.concatenate(mesh_tri[m]),
                return_indices=False,
            )
            meshes_out.append(
                Geometry(
                    model=new_model,
                    sampling_rate=mesh_geometries[m].sampling_rate,
                )
            )

    return data_out, meshes_out


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
            create_button(
                "Sphere",
                "ph.circle",
                self,
                partial(func, "sphere"),
                "Fit to selected clusters",
            ),
            create_button(
                "Ellipse",
                "ph.link-simple-horizontal-break",
                self,
                partial(func, "ellipsoid"),
                "Fit to selected clusters",
            ),
            create_button(
                "Cylinder",
                "ph.hexagon",
                self,
                partial(func, "cylinder"),
                "Fit to selected clusters",
            ),
            create_button(
                "RBF",
                "ph.dots-nine",
                self,
                partial(func, "rbf"),
                "Fit to selected clusters",
                RBF_SETTINGS,
            ),
            create_button(
                "Mesh",
                "ph.triangle",
                self,
                func,
                "Fit to selected clusters",
                MESH_SETTINGS,
            ),
            create_button(
                "Curve",
                "ph.line-segments",
                self,
                partial(func, "spline"),
                "Fit to selected clusters",
                SPLINE_SETTINGS,
            ),
        ]
        self.ribbon.add_section("Parametrization", fitting_actions)

        mesh_actions = [
            create_button(
                "Sample",
                "ph.broadcast",
                self,
                self._sample_parallel,
                "Generate points from fitted model",
                SAMPLE_SETTINGS,
            ),
        ]
        self.ribbon.add_section("Sampling", mesh_actions)

        mesh_actions = [
            create_button(
                "Repair",
                "ph.wrench",
                self,
                self._repair_mesh,
                "Fix holes and topology issues",
                REPAIR_SETTINGS,
            ),
            create_button(
                "Remesh",
                "ph.arrows-clockwise",
                self,
                self._remesh_parallel,
                "Adjust resolution and quality",
                REMESH_SETTINGS,
            ),
            create_button(
                "Smooth",
                "ph.drop",
                self,
                self._smooth_parallel,
                "Reduce surface noise",
                SMOOTH_SETTINGS,
            ),
            create_button(
                "Project",
                "ph.arrow-line-down",
                self,
                self._project_on_mesh,
                "Project points onto mesh",
                PROJECTION_SETTINGS,
            ),
            create_button(
                "Fill",
                "ph.cube",
                self,
                self._fill_volumetric,
                "Fill the interior of a closed mesh with points",
            ),
        ]
        self.ribbon.add_section("Mesh Operations", mesh_actions)

    def _default_callback(self, geom):
        from ..parametrization import TriangularMesh

        if isinstance(geom.model, TriangularMesh):
            geom.change_representation("surface")

        if geom.model is None:
            self.cdata.data.add(geom)
            return self.cdata.data.render()

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
        flip_normals=False,
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
            if flip_normals:
                fs = fs[:, ::-1]
            geom = geometry[...]
            geom._model = TriangularMesh(meshing.to_open3d(vs, fs))
            geom.change_representation("surface")
            self.cdata.models.add(geom)
        return self.cdata.models.render()

    def _fit_parallel(self, method: str, *args, **kwargs):
        from ..operations import GeometryOperations

        # These methods are parallelize and would mess with the worker pool
        tasks, max_concurrent = [], None
        if method in ("Poisson",):
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

    def _fill_volumetric(self, **kwargs):
        tasks = []
        for geometry in self._get_selected_meshes():
            tasks.append(
                {
                    "name": "Fill Mesh",
                    "func": _fill_mesh,
                    "callback": self._default_callback,
                    "kwargs": {"mesh_geometry": geometry},
                }
            )
        submit_task_batch(tasks)

    def _project_on_mesh(
        self,
        use_normals: bool = False,
        invert_normals: bool = False,
        update_normals: bool = False,
        partition: bool = False,
        **kwargs,
    ):
        selected_meshes = self._get_selected_meshes()
        if not selected_meshes:
            raise ValueError("Please select at least one mesh for projection.")

        def _callback(ret):
            data_geoms, mesh_geoms = ret
            for geom in data_geoms:
                self.cdata.data.add(geom)
            for geom in mesh_geoms:
                geom.change_representation("surface")
                self.cdata.models.add(geom)
            if data_geoms:
                self.cdata.data.render()
            if mesh_geoms:
                self.cdata.models.render()

        submit_task(
            "Project",
            _project,
            _callback,
            selected_meshes,
            self.cdata.data.get_selected_geometries(),
            use_normals,
            invert_normals,
            update_normals,
            partition,
        )


SAMPLE_SETTINGS = {
    "title": "Settings",
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
    "title": "Settings",
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
    "title": "Settings",
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
    "title": "Settings",
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
        {
            "label": "Flip Normals",
            "parameter": "flip_normals",
            "type": "boolean",
            "default": False,
            "description": "Reverse normal direction of the mesh.",
        },
    ],
}


REMESH_SETTINGS = {
    "title": "Settings",
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
    "title": "Settings",
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
    "title": "Settings",
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
            ],
            "default": "Alpha Shape",
        },
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
            *REPAIR_SETTINGS["settings"][:5],
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
            REPAIR_SETTINGS["settings"][5],  # Hole Size
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
            *REPAIR_SETTINGS["settings"][:5],
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
            {
                "label": "Smoothing Iterations",
                "parameter": "smoothing_iterations",
                "type": "number",
                "default": 15,
                "min": 0,
                "description": "Number of windowed sinc smoothing iterations.",
            },
            {
                "label": "Smoothing Strength",
                "parameter": "smoothing_strength",
                "type": "float",
                "default": 80.0,
                "min": 0.0,
                "max": 100.0,
                "description": "Smoothing intensity (0 = none, 100 = maximum).",
            },
            {
                "label": "Feature Angle",
                "parameter": "feature_angle",
                "type": "float",
                "default": 120.0,
                "min": 0.0,
                "max": 180.0,
                "description": "Edges sharper than this angle are preserved during "
                "smoothing.",
                "notes": "Angle between adjacent triangle normals. 180 smooths "
                "everything, lower values protect more edges.",
            },
        ],
    },
}


PROJECTION_SETTINGS = {
    "title": "Settings",
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
        {
            "label": "Partition",
            "parameter": "partition",
            "type": "boolean",
            "default": False,
            "description": "Assign points to nearest mesh instead of projecting.",
        },
    ],
}
