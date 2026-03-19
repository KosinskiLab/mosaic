from functools import partial

import numpy as np
from qtpy.QtWidgets import QWidget, QVBoxLayout

from .. import meshing
from .. import operations as _operations  # noqa: F401  # registers geometry operations
from ..registry import MethodRegistry
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
        smoothness=0,
        curvature_weight=0,
        pressure=0,
        flip_normals=False,
        fair_all=False,
        boundary_ring=0,
        **kwargs,
    ):
        import igl
        from ..parametrization import TriangularMesh

        fair_mesh = not (smoothness == 0 and curvature_weight == 0 and pressure == 0)

        for geometry in self._get_selected_meshes():
            model = geometry.model
            model.mesh.remove_non_manifold_edges()
            model.mesh.remove_degenerate_triangles()
            model.mesh.remove_duplicated_triangles()
            model.mesh.remove_unreferenced_vertices()
            model.mesh.remove_duplicated_vertices()

            vs = model.vertices
            fs = model.triangles

            out_fs = meshing.close_holes(vs, fs, max_hole_size)
            if fair_mesh:
                hole_fids = np.arange(len(fs), len(out_fs))

                try:
                    mesh = meshing.remesh(meshing.to_open3d(vs, out_fs))
                    new_vs = np.asarray(mesh.vertices, dtype=np.float64)
                    fs = np.asarray(mesh.triangles)
                except (ValueError, RuntimeError):
                    new_vs, fs = vs, out_fs

                if fair_all:
                    vids = np.arange(len(new_vs))
                else:
                    _, face_ids, _ = igl.point_mesh_squared_distance(
                        new_vs, vs, out_fs.astype(np.int64)
                    )
                    vids = np.where(np.isin(face_ids, hole_fids))[0]

                vs = new_vs
                if len(vids) > 0:
                    vs = meshing.fair_mesh(
                        vs,
                        fs,
                        vids,
                        smoothness=smoothness,
                        curvature_weight=curvature_weight,
                        pressure=pressure,
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

        for geometry in self.cdata.data.get_selected_geometries():
            submit_task(
                "Parametrization",
                GeometryOperations.fit,
                self._default_callback,
                geometry,
                method,
                **kwargs,
            )

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

    def _fill_parallel(self, **kwargs):
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

    def _project_parallel(
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
