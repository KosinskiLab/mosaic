import json
from typing import Dict

from ._utils import get_extension, CompatibilityUnpickler, _HEADER_STRUCT
from .parser import (
    read_star,
    read_tsv,
    read_txt,
    read_mesh,
    read_volume,
    read_tsi,
    read_vtu,
    read_structure,
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


def read_session_header(filepath: str) -> Dict:
    """Read the JSON header without deserialising the pickle payload.

    Returns ``{"version": 0}`` for legacy pure-pickle session files.

    Parameters
    ----------
    filepath : str
        Path to a session file.

    Returns
    -------
    dict
        Parsed header dictionary.
    """
    with open(filepath, "rb") as fh:
        first_four = fh.read(4)
        if len(first_four) < 4:
            return {"version": 0}

        if first_four[0] == 0x80:
            return {"version": 0}

        header_len = _HEADER_STRUCT.unpack(first_four)[0]
        header_bytes = fh.read(header_len)
        return json.loads(header_bytes.decode("utf-8"))


def open_session(filepath: str) -> Dict:
    """Read a session file, handling both legacy and header+pickle formats.

    Legacy pure-pickle files (first byte ``0x80``) are detected
    automatically.

    Parameters
    ----------
    filepath : str
        Path to a session file.

    Returns
    -------
    dict
        Deserialised session state.
    """
    with open(filepath, "rb") as fh:
        first_four = fh.read(4)
        if len(first_four) < 4:
            raise ValueError(f"Session file too short: {filepath}")

        if first_four[0] == 0x80:
            fh.seek(0)
            return CompatibilityUnpickler(fh).load()

        header_len = _HEADER_STRUCT.unpack(first_four)[0]
        fh.seek(4 + header_len)
        return CompatibilityUnpickler(fh).load()
