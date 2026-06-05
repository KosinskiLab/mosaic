import numpy as np

from ._utils import get_extension
from .parser import GeometryDataContainer, read_volume, resolve_parser


def is_volume_file(filepath: str) -> bool:
    """Return True if *filepath* has a volume format extension."""
    try:
        return resolve_parser(get_extension(filepath)[1:]) is read_volume
    except ValueError:
        return False


def is_likely_density_map(filepath: str, max_cluster: int = 10000) -> bool:
    """Return True if *filepath* looks like a density map rather than a label map.

    Uses a two-tier heuristic:
    1. If the MRC header dtype is floating-point, return True immediately.
    2. For integer dtypes (or non-MRC volumes), sample ~125k voxels and check
       whether the unique-value count exceeds *max_cluster*.

    Returns False for non-volume file extensions.
    """
    if not is_volume_file(filepath):
        return False

    from .parser import read_mrc_dtype, read_mrc_flat, load_density

    dtype = read_mrc_dtype(filepath)
    if dtype is not None and not np.issubdtype(dtype, np.integer):
        return True

    data, *_ = read_mrc_flat(filepath)
    if data is None:
        volume = load_density(filepath, use_memmap=False)
        data = volume.data.ravel()

    rng = np.random.default_rng()
    sample = data[rng.integers(0, data.size, size=min(125_000, data.size))]
    return len(np.unique(sample)) > max_cluster


def open_file(filename: str, *args, **kwargs) -> GeometryDataContainer:
    """
    Open and parse a file based on its extension.

    Parameters
    ----------
    filename : str
        Path to the file to be opened.
    *args
        Additional positional arguments passed to the parser function.
    **kwargs
        Additional keyword arguments passed to the parser function.

    Returns
    -------
    GeometryDataContainer
        Parsed geometry data container.

    Raises
    ------
    ValueError
        If the file extension is not supported.
    """
    extension = get_extension(filename)[1:]
    return resolve_parser(extension)(filename, *args, **kwargs)
