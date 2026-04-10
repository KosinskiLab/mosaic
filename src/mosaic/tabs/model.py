from functools import partial

import warnings
import numpy as np
from qtpy.QtWidgets import QWidget, QVBoxLayout

from .. import meshing
from .. import operations as _operations  # noqa: F401  # registers geometry operations
from ..registry import MethodRegistry
from ..widgets.ribbon import create_button
from ..parallel import submit_task, submit_task_batch


def _repair_mesh(
    geometry,
    max_hole_size=-1,
    smoothness=0,
    curvature_weight=0,
    pressure=0,
    flip_normals=False,
    fair_all=False,
    boundary_ring=0,
):
    import igl
    from .. import meshing
    from ..geometry import GeometryData
    from ..parametrization import TriangularMesh

    model = geometry.model
    model.mesh.remove_non_manifold_edges()
    model.mesh.remove_degenerate_triangles()
    model.mesh.remove_duplicated_triangles()
    model.mesh.remove_unreferenced_vertices()
    model.mesh.remove_duplicated_vertices()

    vs = np.asarray(model.mesh.vertices, dtype=np.float64).copy()
    fs = np.asarray(model.mesh.triangles).copy()

    new_fs = meshing.close_holes(vs, fs, max_hole_size)
    hole_fids = np.arange(len(fs), len(new_fs))

    if not (smoothness == 0 and curvature_weight == 0 and pressure == 0):
        try:
            mesh = meshing.remesh(meshing.to_open3d(vs, new_fs))
            new_vs = np.asarray(mesh.vertices, dtype=np.float64)
            new_fs = np.asarray(mesh.triangles)
            _, face_ids, _ = igl.point_mesh_squared_distance(
                new_vs, vs, new_fs.astype(np.int64)
            )
            vids = np.where(np.isin(face_ids, hole_fids))[0]

        except (ValueError, RuntimeError) as e:
            warnings.warn(
                f"Remeshing failed: {e}. Falling back to Liepa triangulation."
            )
            new_vs, new_fs, _ = meshing.repair.triangulation_refine_leipa(
                vs, new_fs, hole_fids, np.sqrt(2)
            )
            vids = np.arange(len(vs), len(new_vs))

        if fair_all:
            vids = np.arange(len(new_vs))

        if len(vids) > 0:
            vs = meshing.fair_mesh(
                new_vs,
                new_fs,
                vids,
                smoothness=smoothness,
                curvature_weight=curvature_weight,
                pressure=pressure,
                n_ring=boundary_ring,
            )
        else:
            vs = new_vs

    if flip_normals:
        new_fs = new_fs[:, ::-1]

    return GeometryData(
        model=TriangularMesh(meshing.to_open3d(vs, new_fs)),
        sampling_rate=geometry.sampling_rate.copy(),
        meta=geometry._meta.copy(),
    )


def _fill_mesh(mesh_geometry):
    from ..geometry import GeometryData

    model = mesh_geometry.model
    voxel_size = max(mesh_geometry.sampling_rate)
    points = meshing.fill_mesh(model.vertices, model.triangles, voxel_size=voxel_size)
    return GeometryData(points=points, sampling_rate=mesh_geometry.sampling_rate.copy())


def _project(
    mesh_geometries,
    geometries,
    use_normals: bool = False,
    invert_normals: bool = False,
    update_normals: bool = False,
    partition: bool = False,
):
    from ..geometry import Geometry, GeometryData

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
                GeometryData(
                    points=proj_sel,
                    normals=geo_normals,
                    sampling_rate=geometry.sampling_rate.copy(),
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
                GeometryData(
                    model=new_model,
                    sampling_rate=mesh_geometries[m].sampling_rate.copy(),
                )
            )

    return data_out + meshes_out


class ModelTab(QWidget):
    def __init__(self, cdata, ribbon, legend, **kwargs):
        super().__init__()
        self.cdata = cdata
        self.ribbon = ribbon
        self.legend = legend

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
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
                MethodRegistry.settings_dict("fit"),
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
                self._repair_mesh_parallel,
                "Fix holes and topology issues",
                REPAIR_SETTINGS,
            ),
            create_button(
                "Remesh",
                "ph.arrows-clockwise",
                self,
                self._remesh_parallel,
                "Adjust resolution and quality",
                MethodRegistry.settings_dict("remesh"),
            ),
            create_button(
                "Smooth",
                "ph.drop",
                self,
                self._smooth_parallel,
                "Reduce surface noise",
                MethodRegistry.settings_dict("smooth"),
            ),
            create_button(
                "Project",
                "ph.arrow-line-down",
                self,
                self._project_parallel,
                "Project points onto mesh",
                PROJECTION_SETTINGS,
            ),
            create_button(
                "Fill",
                "ph.cube",
                self,
                self._fill_parallel,
                "Fill the interior of a closed mesh with points",
            ),
        ]
        self.ribbon.add_section("Mesh Operations", mesh_actions)

    def _default_callback(self, geom):
        from ..geometry import Geometry, GeometryData
        from ..parametrization import TriangularMesh

        if isinstance(geom, (Geometry, GeometryData)):
            geom = (geom,)

        new_model, new_cluster = False, False
        for new_geom in geom:

            if isinstance(new_geom, GeometryData):
                new_geom = new_geom.to_geometry()

            if isinstance(new_geom.model, TriangularMesh):
                new_geom.change_representation("surface")

            if new_geom.model is None:
                new_cluster = True
                self.cdata.data.add(new_geom)
                continue

            new_model = True
            self.cdata.models.add(new_geom)

        if new_model:
            self.cdata.models.render()
        if new_cluster:
            self.cdata.data.render()

    def _get_selected_meshes(self):
        from ..parametrization import TriangularMesh

        ret = []
        for geometry in self.cdata.models.get_selected_geometries():
            fit = geometry.model
            if not isinstance(fit, TriangularMesh):
                continue
            ret.append(geometry)
        return ret

    def _repair_mesh_parallel(self, **kwargs):
        submit_task_batch(
            [
                {
                    "name": "Repair Mesh",
                    "func": _repair_mesh,
                    "callback": self._default_callback,
                    "args": (geometry._geometry_data,),
                    "kwargs": kwargs,
                }
                for geometry in self._get_selected_meshes()
            ]
        )

    def _fit_parallel(self, method: str, *args, **kwargs):
        from ..operations import GeometryOperations

        submit_task_batch(
            [
                {
                    "name": "Parametrization",
                    "func": GeometryOperations.fit,
                    "callback": self._default_callback,
                    "args": (geometry._geometry_data, method),
                    "kwargs": kwargs,
                }
                for geometry in self.cdata.data.get_selected_geometries()
            ]
        )

    def _smooth_parallel(self, method, **kwargs):
        from ..operations import GeometryOperations

        submit_task_batch(
            [
                {
                    "name": "Smooth",
                    "func": GeometryOperations.smooth,
                    "callback": self._default_callback,
                    "args": (geometry._geometry_data, method),
                    "kwargs": kwargs,
                }
                for geometry in self._get_selected_meshes()
            ]
        )

    def _sample_parallel(self, sampling, method, normal_offset=0.0, **kwargs):
        from ..operations import GeometryOperations

        submit_task_batch(
            [
                {
                    "name": "Sample Fit",
                    "func": GeometryOperations.sample,
                    "callback": self._default_callback,
                    "args": (geometry._geometry_data,),
                    "kwargs": {
                        "method": method,
                        "sampling": sampling,
                        "normal_offset": normal_offset,
                        **kwargs,
                    },
                }
                for geometry in self.cdata.models.get_selected_geometries()
            ]
        )

    def _remesh_parallel(self, method, **kwargs):
        from ..operations import GeometryOperations

        submit_task_batch(
            [
                {
                    "name": "Remesh",
                    "func": GeometryOperations.remesh,
                    "callback": self._default_callback,
                    "args": (geometry._geometry_data, method),
                    "kwargs": kwargs,
                }
                for geometry in self._get_selected_meshes()
            ]
        )

    def _fill_parallel(self, **kwargs):
        submit_task_batch(
            [
                {
                    "name": "Fill Mesh",
                    "func": _fill_mesh,
                    "callback": self._default_callback,
                    "args": (geometry._geometry_data,),
                }
                for geometry in self._get_selected_meshes()
            ]
        )

    def _project_parallel(
        self,
        use_normals: bool = False,
        invert_normals: bool = False,
        update_normals: bool = False,
        partition: bool = False,
        **kwargs,
    ):
        submit_task(
            "Project",
            _project,
            self._default_callback,
            self._get_selected_meshes(),
            self.cdata.data.get_selected_geometries(),
            use_normals,
            invert_normals,
            update_normals,
            partition,
        )


SAMPLE_SETTINGS = MethodRegistry.settings_dict("sample")

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
            "label": "Smoothness",
            "parameter": "smoothness",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "max": 1.0,
            "description": "Balance between position anchoring and curvature "
            "minimization. 0 = stay in place, 1 = full smoothing.",
        },
        {
            "label": "Curvature Weight",
            "parameter": "curvature_weight",
            "type": "float",
            "default": 0.0,
            "description": "Higher-order smoothing for curvature continuity.",
        },
        {
            "label": "Pressure",
            "parameter": "pressure",
            "type": "float",
            "default": 0.0,
            "description": "Internal mesh pressure along vertex normals.",
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
        {
            "label": "Fair All Vertices",
            "parameter": "fair_all",
            "type": "boolean",
            "default": False,
            "description": "Apply fairing to all vertices, not just inferred ones.",
        },
        {
            "label": "Boundary Ring",
            "parameter": "boundary_ring",
            "type": "number",
            "default": 0,
            "min": 0,
            "description": "Number of vertex rings around inferred vertices to include in fairing.",
        },
    ],
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
