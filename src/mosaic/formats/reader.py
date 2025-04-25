from typing import Dict

from ._utils import get_extension, CompatibilityUnpickler
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
    read_mesh: ["obj", "ply", "stl", "off", "gltf", "glb," "fbx"],
    read_volume: ["mrc", "em", "map", "h5", "mrc.gz", "em.gz", "map.gz"],
    read_tsi: ["q", "tsi"],
    read_vtu: ["vtu"],
    read_structure: ["pdb", "cif", "gro"],
}


def open_file(filename: str, *args, **kwargs) -> GeometryDataContainer:
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


def open_session(filename: str, *args, **kwargs) -> Dict:
    with open(filename, "rb") as ifile:
        unpickler = CompatibilityUnpickler(ifile)
        data = unpickler.load()
    return data
