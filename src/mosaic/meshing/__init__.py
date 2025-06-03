import importlib

_module_map = {
    ".utils": [
        "to_open3d",
        "compute_edge_lengths",
        "scale",
        "remesh",
        "poisson_mesh",
        "merge_meshes",
        "equilibrate_edges",
        "compute_scale_factor",
        "compute_scale_factor_lower",
        "center_mesh",
        "to_tsi",
        "visualize_ray_casting",
    ],
    ".repair": [
        "triangulate_refine_fair",
        "fair_mesh",
        "get_ring_vertices",
        "close_holes",
        "get_mollified_edge_length",
        "harmonic_deformation",
    ],
    ".volume": [
        "mesh_volume",
        "simplify_mesh",
        "MeshCreator",
        "MeshMerger",
        "MeshSimplifier",
    ],
    ".hmff": ["equilibrate_fit", "setup_hmff"],
    ".coarse_graining": ["mesh_to_cg"],
}

_lazy_imports = {}
for module_path, functions in _module_map.items():
    for func_name in functions:
        _lazy_imports[func_name] = (module_path, func_name)


def __getattr__(name):
    module_path, attr_name = _lazy_imports.get(name, ("", ""))

    if not module_path:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    mod = importlib.import_module(module_path, __name__)
    if attr_name:
        mod = getattr(mod, attr_name)

    globals()[name] = mod
    return mod
