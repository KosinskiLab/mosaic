import importlib

_module_map = {
    ".reader": [
        "open_file",
        "open_session",
        "read_session_header",
    ],
    ".writer": [
        "OrientationsWriter",
        "write_density",
        "write_session",
    ],
    ".parser": [
        "GeometryDataContainer",
        "VertexPropertyContainer",
        "read_ndjson",
        "read_volume",
        "load_density",
    ],
    ".stream": [
        "ZarrImageSource",
        "open_omezarr",
    ],
}

_lazy_imports = {}
for _module_path, _names in _module_map.items():
    for _name in _names:
        _lazy_imports[_name] = (_module_path, _name)


def __getattr__(name):
    module_path, attr_name = _lazy_imports.get(name, ("", ""))

    if not module_path:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    mod = importlib.import_module(module_path, __name__)
    if attr_name:
        mod = getattr(mod, attr_name)

    globals()[name] = mod
    return mod
