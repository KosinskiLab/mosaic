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
