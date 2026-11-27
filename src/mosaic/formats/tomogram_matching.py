"""
Match session names to tomogram files in a folder.

Auto mode scores the leading name tokens (split on ``_ - . space /``, digit
tokens as integers) a tomogram shares with a session. A numeric mismatch at the
first differing token disqualifies it. The score must exceed the leading run
common to all tomograms, cut before its first numeric token (at least 1 for a
single tomogram). A unique best score matches, a tie is ambiguous.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..pipeline._utils import natural_sort_key
from .reader import is_volume_file

__all__ = ["Match", "scan_tomograms", "match_tomograms"]


@dataclass(frozen=True)
class Match:
    """Result of matching one session to the available tomograms."""

    session: str
    tomogram: Optional[str]
    candidates: Tuple[str, ...]
    status: str


def scan_tomograms(folder: str, recursive: bool = False) -> List[str]:
    """
    List volume files and ``.zarr`` directories in a folder.

    Parameters
    ----------
    folder : str
        Folder to scan.
    recursive : bool, optional
        Descend into subfolders. Defaults to False.

    Returns
    -------
    list of str
        Absolute paths in natural sort order.
    """
    found = []
    for root, dirs, files in os.walk(os.path.abspath(folder)):
        dirs.sort()
        zarr = [d for d in dirs if d.endswith(".zarr")]
        found.extend(os.path.join(root, d) for d in zarr)
        found.extend(
            os.path.join(root, f) for f in files if is_volume_file(os.path.join(root, f))
        )
        dirs[:] = [] if not recursive else [d for d in dirs if d not in zarr]

    return sorted(found, key=natural_sort_key)


def _strip_extension(name: str) -> str:
    if name.endswith(".zarr"):
        return name[: -len(".zarr")]

    stem, ext = os.path.splitext(name)
    if ext.lower() == ".gz":
        stem = os.path.splitext(stem)[0]
    return stem


def _tomogram_name(path: str, root: Optional[str]) -> str:
    rel = os.path.relpath(path, root) if root else os.path.basename(path)
    return _strip_extension(rel)


def _tokens(name: str) -> List[str]:
    tokens = re.split(r"[_\-.\s/\\]+", name.lower())
    return [str(int(t)) if t.isdigit() else t for t in tokens if t]


def _shared_run(a: List[str], b: List[str]) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _numeric_conflict(a: List[str], b: List[str]) -> bool:
    n = _shared_run(a, b)
    return n < min(len(a), len(b)) and a[n].isdigit() and b[n].isdigit()


def _auto_match(session: str, names: List[str], tomograms: List[str]) -> Match:
    session_tokens = _tokens(os.path.splitext(os.path.basename(session))[0])
    tomo_tokens = [_tokens(n) for n in names]

    baseline = 0
    if len(tomo_tokens) > 1:
        common = min(_shared_run(tomo_tokens[0], t) for t in tomo_tokens[1:])
        baseline = next(
            (i for i, t in enumerate(tomo_tokens[0][:common]) if t.isdigit()), common
        )

    scores = [
        (
            -1
            if _numeric_conflict(session_tokens, t)
            else _shared_run(session_tokens, t)
        )
        for t in tomo_tokens
    ]
    best = max(scores, default=0)
    if best < 1 or (len(tomo_tokens) > 1 and best <= baseline):
        return Match(session, None, (), "missing")

    tied = tuple(p for p, s in zip(tomograms, scores) if s == best)
    if len(tied) == 1:
        return Match(session, tied[0], tied, "matched")
    return Match(session, None, tied, "ambiguous")


def _compile(template: str) -> re.Pattern:
    if "{key}" not in template:
        raise ValueError(f"Pattern '{template}' has no {{key}}")

    parts = re.split(r"(\{key\}|\*)", template)
    regex = "".join(
        {"{key}": "(?P<key>.+?)", "*": ".*"}.get(p, re.escape(p)) for p in parts
    )
    return re.compile(regex, re.IGNORECASE)


def _pattern_key(regex: re.Pattern, name: str) -> Optional[str]:
    m = regex.fullmatch(name)
    return m.group("key").lower() if m else None


def match_tomograms(
    session_paths: List[str],
    tomogram_paths: List[str],
    root: Optional[str] = None,
    pattern: Optional[Tuple[str, str]] = None,
) -> List[Match]:
    """
    Match each session to a tomogram.

    Parameters
    ----------
    session_paths : list of str
        Session file paths. The file stem is the session name.
    tomogram_paths : list of str
        Tomogram paths, for example from :py:func:`scan_tomograms`.
    root : str, optional
        Folder the tomogram names are taken relative to. Defaults to the
        file name only.
    pattern : tuple of str, optional
        Session and tomogram templates using ``{key}`` and ``*``.

    Returns
    -------
    list of Match
        One entry per session, in session order.

    Raises
    ------
    ValueError
        If a template has no ``{key}``.
    """
    names = [_tomogram_name(p, root) for p in tomogram_paths]
    if pattern is None:
        return [_auto_match(s, names, tomogram_paths) for s in session_paths]

    session_re, tomo_re = (_compile(t) for t in pattern)
    tomo_keys = [_pattern_key(tomo_re, n) for n in names]

    matches = []
    for session in session_paths:
        stem = os.path.splitext(os.path.basename(session))[0]
        key = _pattern_key(session_re, stem)
        found = tuple(
            p for p, k in zip(tomogram_paths, tomo_keys) if key is not None and k == key
        )
        if not found:
            matches.append(Match(session, None, (), "missing"))
        elif len(found) == 1:
            matches.append(Match(session, found[0], found, "matched"))
        else:
            matches.append(Match(session, None, found, "ambiguous"))

    return matches
