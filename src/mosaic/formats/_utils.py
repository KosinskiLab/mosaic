import pickle

from typing import Any
from os.path import splitext, basename


__all__ = [
    "CompatibilityUnpickler",
    "get_extension",
    "read_density_header",
    "read_star_header",
    "write_star_header",
]


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


def read_density_header(filename: str):
    """Return ``(shape, sampling_rate)`` for a volume file without loading data."""
    import numpy as np

    try:
        import mrcfile

        with mrcfile.open(filename, header_only=True, permissive=True) as mrc:
            data_shape = mrc.header.nz, mrc.header.ny, mrc.header.nx
            sampling_rate = mrc.voxel_size.astype(
                [("x", "<f4"), ("y", "<f4"), ("z", "<f4")]
            ).view(("<f4", 3))
            sampling_rate = np.array(sampling_rate)[::1]
        return data_shape[::1], sampling_rate[::1]

    # Fallback for cases supported by Density.from_file and not mrcfile
    except Exception as exc:
        import warnings

        warnings.warn(f"mrcfile header read failed for {filename}: {exc}")
        from .parser import load_density

        density = load_density(filename)
        return density.data.shape, density.sampling_rate


def read_star_header(filename: str) -> dict:
    """Extract Relion optics metadata from a STAR file.

    Returns
    -------
    dict
        Keys ``pixel_size`` (float or None) and ``centered`` (bool).
        Empty on parse failure.
    """
    try:
        from tme.parser import StarParser

        parser = StarParser(filename)
        optics = parser.get("data_optics") or {}
        particles = parser.get("data_particles") or parser.get("data") or {}

        pixel_size = None
        px = optics.get("_rlnImagePixelSize")
        if px:
            pixel_size = float(px[0])

        centered = "_rlnCenteredCoordinateXAngst" in particles
        return {"pixel_size": pixel_size, "centered": centered}
    except Exception:
        return {}


def write_star_header(filename: str, pixel_size: float) -> None:
    """Prepend a Relion ``data_optics`` block recording the pixel size.

    Parameters
    ----------
    filename : str
        Path to an existing STAR file written by
        :py:meth:`tme.Orientations._to_star`.
    pixel_size : float
        Sampling rate in Angstrom per voxel of the source tomogram. Written
        as ``_rlnImagePixelSize``. No-op if non-positive or None.
    """
    if pixel_size is None or pixel_size <= 0:
        return None

    optics_block = (
        "data_optics\n"
        "\n"
        "loop_\n"
        "_rlnOpticsGroup\n"
        "_rlnOpticsGroupName\n"
        "_rlnImagePixelSize\n"
        f"1 opticsGroup1 {float(pixel_size)}\n"
        "\n"
    )

    with open(filename, mode="r", encoding="utf-8") as ifile:
        existing = ifile.read()

    with open(filename, mode="w", encoding="utf-8") as ofile:
        ofile.write(optics_block)
        ofile.write(existing)
    return None


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
