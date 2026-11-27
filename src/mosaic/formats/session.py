"""
Session file I/O: read, write, and inspect session metadata.

File format (v1)::

    [4 bytes : uint32 big-endian index length N]
    [N bytes : UTF-8 JSON index]
    [section bytes ...]

The index maps section names to ``{"offset": int, "size": int, "encoding": str}``
descriptors.  Readers seek directly to the section they need.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import json
import os
import pickle
import struct

from ._utils import CompatibilityUnpickler

_INDEX_STRUCT = struct.Struct(">I")
_FORMAT_VERSION = 1
_SESSION_EXTENSIONS = (".mosaic", ".pickle")


def is_session_file(filepath: str) -> bool:
    """Return ``True`` if *filepath* has a recognised session extension."""
    return filepath.lower().endswith(_SESSION_EXTENSIONS)


def session_save_path(filepath: str) -> str:
    """Return *filepath* with a trailing ``.pickle`` replaced by ``.mosaic``."""
    if filepath.lower().endswith(".pickle"):
        return filepath[: -len(".pickle")] + ".mosaic"
    return filepath


def _read_index(filepath: str) -> dict | None:
    """Read the file index, returning ``None`` for legacy pickle files."""
    with open(filepath, "rb") as fh:
        first_four = fh.read(4)
        if len(first_four) < 4 or first_four[0] == 0x80:
            return None

        index_len = _INDEX_STRUCT.unpack(first_four)[0]
        return json.loads(fh.read(index_len).decode("utf-8"))


def read_session_index(filepath: str) -> dict:
    """Read the session file index.

    Returns ``{"format_version": 0}`` for legacy pure-pickle files.

    Parameters
    ----------
    filepath : str
        Path to a session file.

    Returns
    -------
    dict
        Parsed index dictionary.
    """
    index = _read_index(filepath)
    return index if index is not None else {"format_version": 0}


def read_session_section(filepath: str, section: str) -> bytes | None:
    """Read raw bytes for a named section without decoding.

    Parameters
    ----------
    filepath : str
        Path to a session file.
    section : str
        Section name (e.g. ``"thumbnail"``, ``"meta"``).

    Returns
    -------
    bytes or None
        Raw section bytes, or ``None`` if the section does not exist.
    """
    index = _read_index(filepath)
    if index is None:
        return None

    info = index.get("sections", {}).get(section)
    if info is None:
        return None

    with open(filepath, "rb") as fh:
        fh.seek(info["offset"])
        return fh.read(info["size"])


def read_session_meta(filepath: str) -> dict:
    """Read session metadata without loading geometry data.

    Parameters
    ----------
    filepath : str
        Path to a session file.

    Returns
    -------
    dict
        Metadata dictionary, or empty dict for legacy files.
    """
    data = read_session_section(filepath, "meta")
    if data is None:
        return {}
    return json.loads(data.decode("utf-8"))


def open_session(filepath: str) -> dict:
    """Read session state, handling both legacy and indexed formats.

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

        index_len = _INDEX_STRUCT.unpack(first_four)[0]
        index = json.loads(fh.read(index_len).decode("utf-8"))

        state_info = index.get("sections", {}).get("state")
        if state_info is None:
            raise ValueError(f"Session file has no 'state' section: {filepath}")

        fh.seek(state_info["offset"])
        return CompatibilityUnpickler(fh).load()


def _write_sections(filepath: str, sections_data: dict) -> None:
    """Write ``{name: (encoding, bytes)}`` as an indexed file, replacing atomically."""
    from ..__version__ import __version__

    index = {
        "format_version": _FORMAT_VERSION,
        "version": __version__,
        "sections": {
            name: {"offset": 0, "size": len(blob), "encoding": encoding}
            for name, (encoding, blob) in sections_data.items()
        },
    }

    # Offsets are digits inside the index, so its length depends on them.
    index_bytes = b""
    while True:
        cursor = 4 + len(index_bytes)
        for info in index["sections"].values():
            info["offset"] = cursor
            cursor += info["size"]

        encoded = json.dumps(index, separators=(",", ":")).encode("utf-8")
        settled = len(encoded) == len(index_bytes)
        index_bytes = encoded
        if settled:
            break

    tmp_path = f"{filepath}.partial"
    try:
        with open(tmp_path, "wb") as fh:
            fh.write(_INDEX_STRUCT.pack(len(index_bytes)))
            fh.write(index_bytes)
            for _, blob in sections_data.values():
                fh.write(blob)

        os.replace(tmp_path, filepath)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    return None


def write_session(
    filepath: str,
    state: dict = None,
    sections: dict = None,
    *,
    state_bytes: bytes = None,
) -> None:
    """Write a session file in the indexed format.

    Parameters
    ----------
    filepath : str
        Destination file path.
    state : dict, optional
        Session state dictionary to pickle.
    sections : dict, optional
        Extra sections mapping names to ``(encoding, data)`` tuples.
        The ``"state"`` section is always written from *state*.
    state_bytes : bytes, optional
        Pickled state written verbatim. Exactly one of *state* and
        *state_bytes* is required.
    """
    if (state is None) == (state_bytes is None):
        raise ValueError("Pass exactly one of state and state_bytes.")

    if state_bytes is None:
        state_bytes = pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL)

    sections_data = {"state": ("pickle", state_bytes)}
    if sections:
        sections_data.update(sections)

    return _write_sections(filepath, sections_data)


def update_session_meta(filepath: str, updates: dict) -> None:
    """Merge *updates* into the ``meta`` section, deleting keys set to ``None``.

    Parameters
    ----------
    filepath : str
        Path to an indexed session file.
    updates : dict
        Metadata keys to set. A ``None`` value removes the key.

    Raises
    ------
    ValueError
        If *filepath* is a legacy plain pickle.
    """
    index = _read_index(filepath)
    if index is None:
        raise ValueError(f"Cannot update metadata of a legacy session: {filepath}")

    sections_data = {}
    with open(filepath, "rb") as fh:
        for name, info in index.get("sections", {}).items():
            fh.seek(info["offset"])
            sections_data[name] = (info["encoding"], fh.read(info["size"]))

    meta = read_session_meta(filepath)
    for key, value in updates.items():
        if value is None:
            meta.pop(key, None)
        else:
            meta[key] = value

    sections_data["meta"] = ("json", json.dumps(meta).encode("utf-8"))
    return _write_sections(filepath, sections_data)


def convert_legacy_session(filepath: str) -> str:
    """Wrap a legacy plain pickle into an indexed ``.mosaic`` file.

    Parameters
    ----------
    filepath : str
        Path to a legacy plain pickle session. It is left in place.

    Returns
    -------
    str
        Path of the new file.

    Raises
    ------
    ValueError
        If *filepath* is not a legacy plain pickle.
    FileExistsError
        If the target path already exists.
    """
    if _read_index(filepath) is not None:
        raise ValueError(f"Not a legacy session: {filepath}")

    target = session_save_path(filepath)
    if os.path.exists(target):
        raise FileExistsError(target)

    with open(filepath, "rb") as fh:
        write_session(target, state_bytes=fh.read())

    return target


def prefer_mosaic_sessions(paths: list[str]) -> list[str]:
    """Drop ``x.pickle`` entries that have an ``x.mosaic`` sibling."""
    present = set(paths)
    keep = []
    for path in paths:
        if path.lower().endswith(".pickle"):
            sibling = session_save_path(path)
            if sibling in present or os.path.exists(sibling):
                continue

        keep.append(path)

    return keep
