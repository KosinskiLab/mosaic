from functools import partial

import numpy as np
from qtpy.QtCore import QThread, Signal
from qtpy.QtWidgets import QWidget, QVBoxLayout, QFileDialog

from ..utils import cmap_to_vtkctf
from ..formats.parser import load_density
from ..widgets.ribbon import create_button
from ..dialogs import MeshPropertiesDialog
from ..parametrization import TriangularMesh
from ..meshing import (
    to_open3d,
    marching_cubes,
    merge_meshes,
    remesh,
    triangulate_refine_fair,
)


class FitWorker(QThread):
    finished = Signal()

    def __init__(self, cdata, **kwargs):
        super().__init__()
        self.cdata = cdata
        self.kwargs = kwargs

    def run(self):
        self.cdata.add_fit(**self.kwargs)
        self.finished.emit()

    def kill(self, timeout=10000):
        self.quit()
        if not self.wait(timeout):
            self.terminate()
            self.wait()


def get_dense_skeleton(skel, samples_per_edge=10):
    segments = skel.get_segments()
    dense_points = []
    vertices = skel.vertices

    for seg in segments:
        # Get points for this segment
        seg_points = vertices[seg]

        # Calculate total segment length to distribute points evenly
        segment_length = np.sum(
            np.sqrt(np.sum(np.diff(seg_points, axis=0) ** 2, axis=1))
        )

        # Create parameter space based on cumulative distance
        distances = np.cumsum(np.sqrt(np.sum(np.diff(seg_points, axis=0) ** 2, axis=1)))
        distances = np.insert(distances, 0, 0)  # Add starting point

        # Normalize distances to [0,1]
        distances = distances / distances[-1]

        # Create evenly spaced points
        t = np.linspace(0, 1, samples_per_edge)

        # Interpolate each dimension
        x = np.interp(t, distances, seg_points[:, 0])
        y = np.interp(t, distances, seg_points[:, 1])
        z = np.interp(t, distances, seg_points[:, 2])

        dense_points.extend(np.column_stack([x, y, z]))

    return np.array(dense_points)


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

        func = self._fit
        fitting_actions = [
            create_button("Sphere", "mdi.circle", self, partial(func, "sphere")),
            create_button("Ellipse", "mdi.ellipse", self, partial(func, "ellipsoid")),
            create_button("Cylinder", "mdi.hexagon", self, partial(func, "cylinder")),
            create_button(
                "RBF", "mdi.grid", self, partial(func, "rbf"), "Fit RBF", RBF_SETTINGS
            ),
            create_button(
                "Mesh", "mdi.vector-polyline", self, func, "Fit Mesh", MESH_SETTINGS
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
        self.ribbon.add_section("Fitting Operations", fitting_actions)

        mesh_actions = [
            create_button(
                "Sample",
                "mdi.chart-scatter-plot",
                self,
                self.cdata.sample_fit,
                "Sample from Fit",
                SAMPLE_SETTINGS,
            ),
            create_button("To Cluster", "mdi.plus", self, self._to_cluster),
            create_button(
                "Remove", "fa5s.trash", self, self.cdata.models.remove_cluster
            ),
        ]
        self.ribbon.add_section("Sampling Operations", mesh_actions)

        mesh_actions = [
            create_button(
                "Volume",
                "mdi.cube-outline",
                self,
                self._mesh_volume,
                "Mesh Volume",
                MESHVOLUME_SETTINGS,
            ),
            create_button(
                "Curvature",
                "mdi.vector-curve",
                self,
                self._color_curvature,
                "Compute Curvature",
                CURVATURE_SETTINGS,
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
                self._remesh_meshes,
                "Remesh Mesh",
                REMESH_SETTINGS,
            ),
            create_button(
                "Analyze",
                "mdi.poll",
                self,
                self._show_mesh_dialog,
                "Analyze Mesh",
            ),
            create_button("Merge", "mdi.merge", self, self._merge_meshes),
            create_button("Skeleton", "mdi.merge", self, self._sceleton),
        ]
        self.ribbon.add_section("Mesh Operations", mesh_actions)

    def _fit(self, method: str, **kwargs):
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

        self.fit_worker = FitWorker(self.cdata, method=method, **kwargs)
        self.fit_worker.finished.connect(self._on_fit_complete)
        self.fit_worker.start()

    def _on_fit_complete(self):
        self.fit_worker.deleteLater()
        self.fit_worker = None

        self.cdata.data.render()
        self.cdata.models.render()

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

            self.cdata._data.new(points, normals=normals, sampling_rate=sampling)
        self.cdata.data.data_changed.emit()
        self.cdata.data.render()
        return None

    def _get_selected_meshes(self):
        ret = []
        for index in self.cdata.models._get_selected_indices():
            fit = self.cdata._models.data[index]._meta.get("fit", None)
            if not isinstance(fit, TriangularMesh):
                continue
            ret.append(index)
        return ret

    def _repair_mesh(
        self,
        hole_size=-1,
        elastic_weight=0,
        curvature_weight=0,
        volume_weight=0,
        boundary_ring=0,
        **kwargs,
    ):
        for index in self._get_selected_meshes():
            mesh = self.cdata._models.data[index]._meta.get("fit", None).mesh
            vs, fs = triangulate_refine_fair(
                vs=np.asarray(mesh.vertices),
                fs=np.asarray(mesh.triangles),
                alpha=elastic_weight,
                beta=curvature_weight,
                gamma=volume_weight,
                hole_len_thr=hole_size,
                n_ring=boundary_ring,
            )

            fit = TriangularMesh(to_open3d(vs, fs))
            meta = {
                "fit": fit,
                "points": np.asarray(fit.mesh.vertices),
                "faces": np.asarray(fit.mesh.triangles),
                "normals": fit.compute_vertex_normals(),
            }

            self.cdata._models.add(
                points=meta["points"],
                normals=meta["normals"],
                meta=meta,
                sampling_rate=self.cdata._models.data[index].sampling_rate,
            )

        self.cdata.models.data_changed.emit()
        return self.cdata.models.render()

    def _remesh_meshes(self, method, **kwargs):
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
            mesh = self.cdata._models.data[index]._meta.get("fit", None).mesh
            if method == "edge length":
                mesh = remesh(mesh=mesh, **kwargs)
            elif method == "vertex clustering":
                mesh = mesh.simplify_vertex_clustering(**kwargs)
            elif method == "subdivide":
                func = mesh.subdivide_midpoint
                smooth = kwargs.pop("smooth", False)
                if smooth:
                    func = mesh.subdivide_loop
                mesh = func(**kwargs)
            else:
                mesh = mesh.simplify_quadric_decimation(**kwargs)

            fit = TriangularMesh(mesh)
            self.cdata._add_fit(
                fit=fit,
                points=np.asarray(fit.mesh.vertices),
                sampling_rate=self.cdata._models.data[index].sampling_rate,
            )
        self.cdata.models.data_changed.emit()
        return self.cdata.models.render()

    def _merge_meshes(self):
        meshes, selected_meshes = [], self._get_selected_meshes()

        if len(selected_meshes) < 2:
            return None

        for index in selected_meshes:
            meshes.append(self.cdata._models.data[index]._meta.get("fit", None).mesh)

        vertices, faces = merge_meshes(
            vertices=[np.asarray(x.vertices) for x in meshes],
            faces=[np.asarray(x.triangles) for x in meshes],
        )
        fit = TriangularMesh(to_open3d(vertices, faces))
        self.cdata._add_fit(
            fit=fit,
            points=np.asarray(fit.mesh.vertices),
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

            mesh = self.cdata._models.data[index]._meta.get("fit", None).mesh
            mesh = trimesh.Trimesh(mesh.vertices, mesh.triangles)
            mesh = sk.pre.fix_mesh(mesh)
            skel = sk.skeletonize.by_wavefront(mesh, waves=5, step_size=1)
            from ..utils import com_cluster_points

            vertices = com_cluster_points(skel.vertices, 100)
            self.cdata._data.add(vertices)

        self.cdata.data.data_changed.emit()
        return self.cdata.data.render()

    def _mesh_volume(self, **kwargs):
        filename, _ = QFileDialog.getOpenFileName(self, "Select Meshes")
        if not filename:
            return -1

        dens = load_density(filename)
        meshes = marching_cubes(dens.data, dens.sampling_rate, **kwargs)
        for mesh in meshes:
            fit = TriangularMesh(mesh)
            self.cdata._add_fit(
                fit=fit,
                points=np.asarray(fit.mesh.vertices),
                sampling_rate=dens.sampling_rate,
            )

        self.cdata.models.data_changed.emit()
        return self.cdata.models.render()

    def _show_mesh_dialog(self):
        fits = self.cdata.format_datalist("models")
        fits = [(x[0], x[1]._meta.get("fit", None)) for x in fits]
        fits = [(x[0], x[1]) for x in fits if isinstance(x[1], TriangularMesh)]
        dialog = MeshPropertiesDialog(fits=fits, parent=self)
        return dialog.show()

    def _color_curvature(
        self, cmap="viridis", curvature="gaussian", radius: int = 3, **kwargs
    ):
        selected_meshes, curvatures = [], []
        for index in self.cdata.models._get_selected_indices():
            fit = self.cdata._models.data[index]._meta.get("fit")
            if not isinstance(fit, TriangularMesh):
                continue

            selected_meshes.append(index)
            curvatures.append(fit.compute_curvature(curvature=curvature, radius=radius))

        if len(selected_meshes) == 0:
            print("No mesh was selected for curvature computation.")
            return None

        all_curvatures = np.concatenate([c.flatten() for c in curvatures])
        valid_curvatures = all_curvatures[~np.isnan(all_curvatures)]

        n_bins = min(valid_curvatures.size // 10, 100)
        bins = np.percentile(valid_curvatures, np.linspace(0, 100, n_bins + 1))
        curvatures = [np.digitize(curv, bins) - 1 for curv in curvatures]

        self.cdata.models.set_selection([])
        lut, lut_range = cmap_to_vtkctf(cmap=cmap, max_value=n_bins, min_value=0)
        for index, k in zip(selected_meshes, curvatures):
            self.cdata._models.data[index].set_scalars(k, lut, lut_range)

        self.legend.set_lookup_table(lut, f"{curvature.title()} curvature")
        return self.cdata.models.render_vtk()


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
            "description": "Control mesh smoothness and elasticity.",
            "notes": "0 - strong anchoring, 1 - no anchoring, > 1 repulsion.",
        },
        {
            "label": "Curvature Weight",
            "parameter": "curvature_weight",
            "type": "float",
            "default": 0.0,
            "description": "Controls propagation of mesh curvature.",
        },
        {
            "label": "Volume Weight",
            "parameter": "volume_weight",
            "type": "float",
            "default": 0.0,
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
            "label": "Hole Size",
            "parameter": "hole_size",
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
                "label": "Triangles",
                "parameter": "target_number_of_triangles",
                "type": "number",
                "default": 1000,
                "min": 1,
                "description": "Target number of triangles.",
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
        *REPAIR_SETTINGS["settings"][:4],
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
        ],
        "Ball Pivoting": [
            {
                "label": "Radii",
                "parameter": "radii",
                "type": "text",
                "default": "5",
                "description": "Voxel size ball radii used for surface reconstruction.",
                "notes": "Use commas to specify multiple radii, e.g. '5,3.5,1.0'.",
            },
            REPAIR_SETTINGS["settings"][-1],
            {
                "label": "Downsample",
                "parameter": "downsample_input",
                "type": "boolean",
                "default": False,
                "description": "Thin input point cloud to core.",
            },
            {
                "label": "Smoothing Steps",
                "parameter": "smoothing_steps",
                "type": "number",
                "default": 5,
                "description": "Pre-smoothing steps before fairing.",
                "notes": "Improves repair but less impactful for topolgoy than weights.",
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
        ],
    },
}


MESHVOLUME_SETTINGS = {
    "title": "Meshing Settings",
    "settings": [
        {
            "label": "Reduction Factor",
            "parameter": "reduction_factor",
            "type": "number",
            "default": 100,
            "min": 1,
            "description": "Reduce initial mesh by x times the number of triangles.",
        },
        {
            "label": "Simplify",
            "parameter": "simplify",
            "type": "boolean",
            "default": True,
            "description": "Simplify mesh after initial reduction.",
        },
    ],
}


CURVATURE_SETTINGS = {
    "title": "Curvature Settings",
    "settings": [
        {
            "label": "Curvature",
            "parameter": "curvature_type",
            "type": "select",
            "options": ["gaussian", "mean"],
            "default": "gaussian",
            "description": "Curvature type to compute on the mesh.",
        },
        {
            "label": "Radius",
            "parameter": "radius",
            "type": "number",
            "default": 5,
            "min": 1,
            "description": "Number of neighbor vertices considered during computation.",
        },
        {
            "label": "Colormap",
            "parameter": "cmap",
            "type": "select",
            "options": [
                "viridis",
                "plasma",
                "inferno",
                "magma",
                "cividis",
                "RdBu",
                "Spectral",
            ],
            "default": "viridis",
            "description": "Colormap to apply to curvature estimates.",
        },
    ],
}
