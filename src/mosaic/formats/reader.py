import numpy as np

from ._utils import get_extension
from .parser import (
    read_star,
    read_tsv,
    read_txt,
    read_mesh,
    read_volume,
    read_tsi,
    read_vtu,
    read_structure,
    read_ndjson,
    GeometryDataContainer,
)

FORMAT_MAPPING = {
    read_star: ["star"],
    read_tsv: ["tsv"],
    read_txt: ["txt", "xyz", "csv"],
    read_mesh: ["obj", "ply", "stl", "off", "gltf", "glb", "fbx"],
    read_volume: [
        "mrc",
        "em",
        "map",
        "h5",
        "mrc.gz",
        "em.gz",
        "map.gz",
        "nrrd",
        "nii",
        "nii.gz",
    ],
    read_tsi: ["q", "tsi"],
    read_vtu: ["vtu"],
    read_structure: ["pdb", "cif", "gro"],
    read_ndjson: ["ndjson"],
}


def is_volume_file(filepath: str) -> bool:
    """Return True if *filepath* has a volume format extension."""
    ext = get_extension(filepath)[1:]
    return any(ext in fmts for f, fmts in FORMAT_MAPPING.items() if f is read_volume)


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

    func = None
    for reader_func, reader_formats in FORMAT_MAPPING.items():
        if extension not in reader_formats:
            continue
        func = reader_func

    if func is None:
        supported = ", ".join([f"'{x}'" for t in FORMAT_MAPPING.values() for x in t])
        raise ValueError(f"Unknown extension '{extension}', supported are {supported}.")
    return func(filename, *args, **kwargs)
