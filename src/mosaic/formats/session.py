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
import struct
import pickle
from typing import Dict, Optional

from ._utils import CompatibilityUnpickler

_INDEX_STRUCT = struct.Struct(">I")
_FORMAT_VERSION = 1
_SESSION_EXTENSIONS = (".pickle",)


def is_session_file(filepath: str) -> bool:
    """Return ``True`` if *filepath* has a recognised session extension."""
    return filepath.lower().endswith(_SESSION_EXTENSIONS)


def _read_index(filepath: str) -> Optional[Dict]:
    """Read the file index, returning ``None`` for legacy pickle files."""
    with open(filepath, "rb") as fh:
        first_four = fh.read(4)
        if len(first_four) < 4 or first_four[0] == 0x80:
            return None

        index_len = _INDEX_STRUCT.unpack(first_four)[0]
        return json.loads(fh.read(index_len).decode("utf-8"))


def read_session_index(filepath: str) -> Dict:
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


def read_session_section(filepath: str, section: str) -> Optional[bytes]:
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


def read_session_meta(filepath: str) -> Dict:
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


def open_session(filepath: str) -> Dict:
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


def write_session(
    filepath: str,
    state: dict,
    sections: dict = None,
) -> None:
    """Write a session file in the indexed format.

    Parameters
    ----------
    filepath : str
        Destination file path.
    state : dict
        Session state dictionary to pickle.
    sections : dict, optional
        Extra sections mapping names to ``(encoding, data)`` tuples.
        The ``"state"`` section is always written from *state*.
    """
    from ..__version__ import __version__

    sections_data = {}

    state_bytes = pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL)
    sections_data["state"] = ("pickle", state_bytes)

    if sections:
        sections_data.update(sections)

    index = {
        "format_version": _FORMAT_VERSION,
        "version": __version__,
        "sections": {},
    }

    placeholder_index = json.dumps(index, separators=(",", ":")).encode("utf-8")
    data_start = 4 + len(placeholder_index)

    # Estimate index size with section entries to compute correct offsets.
    # Each section entry adds to the index, shifting offsets.  We iterate
    # once to measure, then build the final index.
    offset = data_start
    for name, (encoding, blob) in sections_data.items():
        # Rough estimate — will be recalculated
        offset += len(blob)

    # Build real index
    offset = 0  # relative to data_start; adjusted below
    section_order = list(sections_data.keys())
    section_blobs = []

    for name in section_order:
        encoding, blob = sections_data[name]
        section_blobs.append(blob)
        index["sections"][name] = {
            "offset": 0,  # placeholder
            "size": len(blob),
            "encoding": encoding,
        }

    # Compute final index size to get real offsets
    trial_index = json.dumps(index, separators=(",", ":")).encode("utf-8")
    data_start = 4 + len(trial_index)

    cursor = data_start
    for name in section_order:
        index["sections"][name]["offset"] = cursor
        cursor += index["sections"][name]["size"]

    # Re-encode — offsets may have changed the index length
    final_index = json.dumps(index, separators=(",", ":")).encode("utf-8")
    if len(final_index) != len(trial_index):
        # Length changed, recompute offsets
        data_start = 4 + len(final_index)
        cursor = data_start
        for name in section_order:
            index["sections"][name]["offset"] = cursor
            cursor += index["sections"][name]["size"]
        final_index = json.dumps(index, separators=(",", ":")).encode("utf-8")

    with open(filepath, "wb") as fh:
        fh.write(_INDEX_STRUCT.pack(len(final_index)))
        fh.write(final_index)
        for blob in section_blobs:
            fh.write(blob)
