import pickle

from typing import Any
from os.path import splitext, basename


class CompatibilityUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str) -> Any:
        if module.startswith("colabseg"):
            module = "mosaic" + module[len("colabseg") :]
        return super().find_class(module, name)


def get_extension(filename: str) -> str:
    base, extension = splitext(basename(filename))
    if extension.lower() == ".gz":
        _, extension = splitext(basename(base))
    return extension.lower()
