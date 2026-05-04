"""
DTS parameter screening and analysis utilities.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import importlib

_module_map = {
    ".screening": [
        "generate_screen",
        "extend_screen",
        "get_screen_status",
    ],
    "._utils": [
        "parse_time_series",
        "parse_run_time_series",
        "load_screen_results",
    ],
    ".analysis": [
        "compute",
    ],
    ".dialog": ["DTSScreeningDialog"],
    ".equilibration_dialog": ["MeshEquilibrationDialog"],
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
