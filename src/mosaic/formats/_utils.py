import pickle

from typing import Any
from os.path import splitext, basename


class CompatibilityUnpickler(pickle.Unpickler):
    """Custom unpickler for colabseg backwards compatibility."""

    def find_class(self, module: str, name: str) -> Any:
        if module.startswith("colabseg"):
            module = "mosaic" + module[len("colabseg") :]
        return super().find_class(module, name)


def get_extension(filename: str) -> str:
    """
    Extract file extension handling compressed files.

    Parameters
    ----------
    filename : str
        Path to file.

    Returns
    -------
    str
        File extension in lowercase
    """
    base, extension = splitext(basename(filename))
    if extension.lower() == ".gz":
        _, extension = splitext(basename(base))
    return extension.lower()


def _drop_prefix(iterable, target_length: int):
    """
    Remove first element if iterable exceeds target length.

    Parameters
    ----------
    iterable : list
        List to potentially modify.
    target_length : int
        Target length threshold.

    Returns
    -------
    list
        Modified iterable with first element removed if needed.
    """
    if len(iterable) == target_length:
        iterable.pop(0)
    return iterable
