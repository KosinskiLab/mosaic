import importlib

_module_map = {
    ".utils": [
        "to_open3d",
        "compute_edge_lengths",
        "scale",
        "remesh",
        "merge_meshes",
        "equilibrate_edges",
        "compute_scale_factor",
        "compute_scale_factor_lower",
        "center_mesh",
        "to_tsi",
        "fill_mesh",
    ],
    ".repair": [
        "fair_mesh",
        "get_ring_vertices",
        "close_holes",
        "bridge_boundaries",
        "triangulation_refine_leipa",
    ],
    ".volume": [
        "mesh_volume",
        "simplify_mesh",
        "MeshCreator",
        "MeshMerger",
        "MeshSimplifier",
    ],
    ".hmff": ["equilibrate_fit"],
    ".coarse_graining": ["mesh_to_cg"],
    ".texture": ["TextureSampler"],
}

_lazy_imports = {}
for module_path, functions in _module_map.items():
    _lazy_imports[module_path.lstrip(".")] = (module_path, "")
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
