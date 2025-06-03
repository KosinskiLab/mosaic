import importlib

# from .__version__ import __version__
from . import dialogs

_module_map = {
    ".animate": ["ExportManager"],
    ".interactor": ["DataContainerInteractor"],
    ".data": ["MosaicData"],
    ".container": ["DataContainer"],
    ".__version__": ["__version__"],
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
