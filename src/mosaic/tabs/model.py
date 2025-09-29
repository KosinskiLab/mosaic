from functools import partial

import numpy as np
from qtpy.QtWidgets import QWidget, QVBoxLayout, QFileDialog

from .. import meshing
from ..parallel import submit_task
from ..widgets.ribbon import create_button


def on_fit_complete(self, *args, **kwargs):
    self.cdata.data.render()
    self.cdata.models.render()


def _fit(method, geometry, **kwargs):
    from ..parametrization import PARAMETRIZATION_TYPE

    fit_object = PARAMETRIZATION_TYPE.get(method)
    if fit_object is None:
        raise ValueError(f"{method} is not supported ({PARAMETRIZATION_TYPE.keys()}).")

    n = geometry.points.shape[0]
    if n < 50 and method not in ["convexhull", "spline"]:
        raise ValueError(f"Insufficient points for fit ({n}<50).")
    return fit_object.fit(geometry.points, **kwargs)


def _remesh(method, geometry, **kwargs):
    from ..parametrization import TriangularMesh

    mesh = geometry._meta.get("fit", None)

    mesh = meshing.to_open3d(mesh.vertices.copy(), mesh.triangles.copy())
    if method == "edge length":
        mesh = meshing.remesh(mesh=mesh, **kwargs)
    elif method == "vertex clustering":
        mesh = mesh.simplify_vertex_clustering(**kwargs)
    elif method == "subdivide":
        func = mesh.subdivide_midpoint
        if kwargs.get("smooth"):
            func = mesh.subdivide_loop
        kwargs = {k: v for k, v in kwargs.items() if k != "smooth"}
        mesh = func(**kwargs)
    else:
        method = kwargs.get("decimation_method", "Triangle Count").lower()
        sampling = kwargs.get("sampling")
        if method == "reduction factor":
            sampling = np.asarray(mesh.triangles).shape[0] // sampling

        mesh = mesh.simplify_quadric_decimation(int(sampling))
    return TriangularMesh(mesh)


def _project(
    mesh,
    geometries,
    use_normals: bool = False,
    invert_normals: bool = False,
    update_normals: bool = False,
):
    from ..geometry import Geometry

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

    return new_mesh, new_geometries


def _run_marching_cubes(filename, **kwargs):
    from ..formats.parser import load_density
    from ..parametrization import TriangularMesh

    mesh_paths = meshing.mesh_volume(filename, **kwargs)
    sampling = load_density(filename, use_memmap=True).sampling_rate

    meshes = [TriangularMesh.from_file(x) for x in mesh_paths]
    return meshes, sampling


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
            create_button("To Cluster", "mdi.plus", self, self._to_cluster),
            create_button("Remove", "fa5s.trash", self, self.cdata.models.remove),
        ]
        self.ribbon.add_section("Sampling", mesh_actions)

        mesh_actions = [
            create_button(
                "Merge", "mdi.merge", self, self._merge_meshes, "Merge Meshes"
            ),
            create_button(
                "Volume",
                "mdi.cube-outline",
                self,
                self._mesh_volume,
                "Mesh Volume",
                MESHVOLUME_SETTINGS,
            ),
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
                "Project",
                "mdi.vector-curve",
                self,
                self._project_on_mesh,
                "Project on Mesh",
                PROJECTION_SETTINGS,
            ),
            # create_button("Skeleton", "mdi.vector-line", self, self._sceleton),
        ]
        self.ribbon.add_section("Mesh Operations", mesh_actions)

    def _to_cluster(self, *args, **kwargs):
        indices = self.cdata.models._get_selected_indices()

        for index in indices:
            if not self.cdata._models._index_ok(index):
                continue

            geometry = self.cdata._models.data[index]

            fit = geometry._meta.get("fit", None)
            normals, sampling = None, geometry._sampling_rate
            if hasattr(fit, "mesh"):
                points = fit.vertices
                normals = fit.compute_vertex_normals()
            else:
                points = geometry.points
                if fit is not None:
                    normals = fit.compute_normal(points)

            normals = fit.compute_normal(points)

            self.cdata.data.add(points, normals=normals, sampling_rate=sampling)
        self.cdata.data.data_changed.emit()
        self.cdata.data.render()
        return None

    def _get_selected_meshes(self):
        from ..parametrization import TriangularMesh

        ret = []
        for index in self.cdata.models._get_selected_indices():
            fit = self.cdata._models.data[index]._meta.get("fit", None)
            if not isinstance(fit, TriangularMesh):
                continue
            ret.append(index)
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

        for index in self._get_selected_meshes():
            fit = self.cdata._models.data[index]._meta.get("fit", None)
            if not hasattr(fit, "vertices"):
                continue

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
            self.cdata._add_fit(
                fit=TriangularMesh(meshing.to_open3d(vs, fs)),
                sampling_rate=self.cdata._models.data[index].sampling_rate,
            )

        return self.cdata.models.render()

    def _merge_meshes(self):
        from ..parametrization import TriangularMesh

        meshes, selected_meshes = [], self._get_selected_meshes()

        if len(selected_meshes) < 2:
            return None

        for index in selected_meshes:
            meshes.append(self.cdata._models.data[index]._meta.get("fit"))

        vertices, faces = meshing.merge_meshes(
            vertices=[x.vertices for x in meshes],
            faces=[x.triangles for x in meshes],
        )
        self.cdata._add_fit(
            fit=TriangularMesh(meshing.to_open3d(vertices, faces)),
            sampling_rate=self.cdata._models.data[index].sampling_rate,
        )
        self.cdata._models.remove(selected_meshes)

        self.cdata.models.data_changed.emit()
        return self.cdata.models.render()

    def _sceleton(self):
        selected_meshes = self._get_selected_meshes()

        if len(selected_meshes) == 0:
            return None

        for index in selected_meshes:
            import trimesh
            import skeletor as sk
            from ..utils import com_cluster_points

            mesh = self.cdata._models.data[index]._meta.get("fit", None)
            mesh = trimesh.Trimesh(mesh.vertices, mesh.triangles)
            mesh = sk.pre.fix_mesh(mesh)
            skel = sk.skeletonize.by_wavefront(mesh, waves=5, step_size=1)

            vertices = com_cluster_points(skel.vertices, 100)
            vertices = skel.vertices
            self.cdata._data.add(vertices)

        self.cdata.data.data_changed.emit()
        return self.cdata.data.render()

    def _fit_parallel(self, method: str, *args, **kwargs):
        _conversion = {
            "Alpha Shape": "convexhull",
            "Ball Pivoting": "mesh",
            "Poisson": "poissonmesh",
            "Cluster Ball Pivoting": "clusterballpivoting",
        }
        method = _conversion.get(method, method)

        if method == "mesh":
            radii = kwargs.get("radii", None)
            try:
                kwargs["radii"] = [float(x) for x in radii.split(",")]
            except Exception as e:
                raise ValueError(f"Incorrect radius specification {radii}.") from e

        for index in self.cdata.data._get_selected_indices():
            if (geometry := self.cdata.data.get_geometry(index)) is None:
                continue

            if geometry.sampling_rate is None:
                geometry.sampling_rate = 10
            kwargs["voxel_size"] = np.max(geometry.sampling_rate)

            def _callback(fit):
                self.cdata._add_fit(fit, sampling_rate=geometry.sampling_rate)
                self.cdata.models.render()

            submit_task(
                "Parametrization",
                _fit,
                _callback,
                method.lower(),
                geometry,
                **kwargs,
            )

    def _sample_parallel(self, sampling, sampling_method, normal_offset=0.0, **kwargs):
        from ..operations import GeometryOperations

        def _callback(*args, **kwargs):
            self.cdata.data.add(*args, **kwargs)
            self.cdata.data.render()

        for index in self.cdata.models._get_selected_indices():
            if (geometry := self.cdata.models.get_geometry(index)) is None:
                continue

            submit_task(
                "Sample Fit",
                GeometryOperations.sample,
                _callback,
                geometry,
                sampling,
                sampling_method,
                normal_offset,
                **kwargs,
            )

    def _remesh_parallel(self, method, **kwargs):
        selected_meshes = self._get_selected_meshes()
        if len(selected_meshes) == 0:
            return None

        method = method.lower()
        supported = (
            "edge length",
            "vertex clustering",
            "quadratic decimation",
            "subdivide",
        )
        if method not in (supported):
            raise ValueError(f"{method} is not supported, chose one of {supported}.")

        for index in selected_meshes:
            if (geometry := self.cdata.models.get_geometry(index)) is None:
                continue

            def _callback(fit):
                self.cdata._add_fit(fit, sampling_rate=geometry.sampling_rate)
                self.cdata.models.render()

            submit_task("Remesh", _remesh, _callback, method, geometry, **kwargs)

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

        geometry = self.cdata.models.get_geometry(selected_meshes[0])
        if (mesh := geometry._meta.get("fit", None)) is None:
            return None

        geometries = []
        for index in self.cdata.data._get_selected_indices():
            if (geometry := self.cdata.data.get_geometry(index)) is None:
                continue
            geometries.append(geometry)

        def _callback(ret):
            new_mesh, new_geometries = ret

            for new_geometry in new_geometries:
                self.cdata.data.add(new_geometry)

            self.cdata._add_fit(new_mesh, sampling_rate=geometry.sampling_rate)
            self.cdata.data.render()
            self.cdata.models.render()

        submit_task(
            "Project",
            _project,
            _callback,
            mesh,
            geometries,
            use_normals,
            invert_normals,
            update_normals,
        )

    def _mesh_volume(self, **kwargs):
        filename, _ = QFileDialog.getOpenFileName(self, "Select Meshes")
        if not filename:
            return -1

        def _callback(ret):
            meshes, sampling = ret
            for mesh in meshes:
                self.cdata._add_fit(
                    fit=mesh,
                    sampling_rate=sampling,
                )
            self.cdata.models.render()

        submit_task(
            "Mesh Volume",
            _run_marching_cubes,
            _callback,
            filename,
        )


SAMPLE_SETTINGS = {
    "title": "Sample Fit",
    "settings": [
        {
            "label": "Sampling Method",
            "parameter": "sampling_method",
            "type": "select",
            "options": ["Points", "Distance"],
            "default": "Points",
            "notes": "Number of points or average distance between points.",
        },
        {
            "label": "Sampling",
            "parameter": "sampling",
            "type": "float",
            "min": 1,
            "default": 1000,
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
            "type": "float",
            "default": 1.0,
            "min": 0.0,
            "max": 1.0,
            "description": "Flexibility of inferred vertices. 1 is maximum.",
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
                "Edge Length",
                "Vertex Clustering",
                "Quadratic Decimation",
                "Subdivide",
            ],
            "default": "Edge Length",
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
        "Quadratic Decimation": [
            {
                "label": "Method",
                "parameter": "decimation_method",
                "type": "select",
                "options": ["Triangle Count", "Reduction Factor"],
                "default": "Triangle Count",
                "description": "Choose how to specify the decimation target.",
            },
            {
                "label": "Sampling",
                "parameter": "sampling",
                "type": "float",
                "default": 1000,
                "min": 0,
                "description": "Numerical value for reduction method.",
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
    },
}


MESHVOLUME_SETTINGS = {
    "title": "Meshing Settings",
    "settings": [
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
