"""
Match session names to tomogram files in a folder.

A key regular expression is searched in both names and equal keys are paired.
Detection proposes the key that pairs the most sessions.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import itertools
import os
import re
from dataclasses import dataclass

from ..pipeline._utils import natural_sort_key, strip_extension
from .reader import is_volume_file
from .session import (
    convert_legacy_session,
    read_session_index,
    update_session_meta,
)

__all__ = [
    "NO_TOMOGRAM",
    "LinkRow",
    "LinkWriteResult",
    "Match",
    "build_rows",
    "detect_key",
    "entries",
    "initial_folder",
    "is_warning",
    "link_summary",
    "match_tomograms",
    "outcome",
    "pending_changes",
    "resolve_note",
    "scan_tomograms",
    "status_text",
    "write_tomogram_links",
]

NO_TOMOGRAM = ""

_SEPARATORS = r"_\-.\s/\\"
_MAX_CANDIDATES = 50


@dataclass(frozen=True)
class Match:
    """Result of matching one session to the available tomograms."""

    session: str
    tomogram: str | None
    candidates: tuple[str, ...]
    status: str


def scan_tomograms(folder: str, recursive: bool = False) -> list[str]:
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
            os.path.join(root, f)
            for f in files
            if is_volume_file(os.path.join(root, f))
        )
        dirs[:] = [] if not recursive else [d for d in dirs if d not in zarr]

    return sorted(found, key=natural_sort_key)


def _tomogram_name(path: str, root: str | None) -> str:
    rel = os.path.relpath(path, root) if root else os.path.basename(path)
    return strip_extension(rel)


def _key(regex: re.Pattern, name: str, case_sensitive: bool) -> tuple | None:
    m = regex.search(name)
    if m is None:
        return None

    key = []
    for part in [g or "" for g in m.groups()] or [m.group(0)]:
        runs = re.split(r"(\d+)", part if case_sensitive else part.lower())
        key.append(tuple(int(r) if i % 2 else r for i, r in enumerate(runs)))
    return tuple(key)


def match_tomograms(
    session_paths: list[str],
    tomogram_paths: list[str],
    root: str | None = None,
    key: str | None = None,
    case_sensitive: bool = False,
) -> list[Match]:
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
    key : str, optional
        Regular expression for the key. Its groups form the key if it has
        any, digit runs compare as numbers. Without a key nothing matches.
    case_sensitive : bool, optional
        Compare keys case sensitively. Defaults to False.

    Returns
    -------
    list of Match
        One entry per session, in session order.

    Raises
    ------
    re.error
        If ``key`` is not a valid regular expression.
    """
    if not key:
        return [Match(s, None, (), "missing") for s in session_paths]

    stems = [_stem(s) for s in session_paths]
    names = [_tomogram_name(p, root) for p in tomogram_paths]
    return _pair(session_paths, stems, tomogram_paths, names, key, case_sensitive)


def _stem(path: str) -> str:
    return strip_extension(os.path.basename(path))


def _pair(
    session_paths: list[str],
    stems: list[str],
    tomogram_paths: list[str],
    names: list[str],
    key: str,
    case_sensitive: bool,
) -> list[Match]:
    regex = re.compile(key, 0 if case_sensitive else re.IGNORECASE)
    by_key = {}
    for path, name in zip(tomogram_paths, names):
        by_key.setdefault(_key(regex, name, case_sensitive), []).append(path)
    by_key.pop(None, None)

    matches = []
    for session, stem in zip(session_paths, stems):
        candidates = tuple(by_key.get(_key(regex, stem, case_sensitive), ()))
        if not candidates:
            matches.append(Match(session, None, (), "missing"))
        elif len(candidates) == 1:
            matches.append(Match(session, candidates[0], candidates, "matched"))
        else:
            matches.append(Match(session, None, candidates, "ambiguous"))
    return matches


def detect_key(
    session_paths: list[str],
    tomogram_paths: list[str],
    root: str | None = None,
    case_sensitive: bool = False,
) -> str | None:
    r"""
    Suggest the key that pairs the most sessions with a tomogram.

    Candidates are the runs of name parts found in the most session names,
    with digit runs as ``\d+``. Keys rank by sessions with exactly one
    tomogram, then sessions with any, then fewer candidates, then fewer
    ``\d+`` and longer keys.

    Parameters
    ----------
    session_paths : list of str
        Session file paths.
    tomogram_paths : list of str
        Tomogram paths.
    root : str, optional
        Folder the tomogram names are taken relative to.
    case_sensitive : bool, optional
        Compare keys case sensitively. Defaults to False.

    Returns
    -------
    str or None
        Key regex, or None if no candidate pairs any session.
    """
    stems = [_stem(s) for s in session_paths]
    sources = {}
    for session, stem in zip(session_paths, stems):
        parts = list(re.finditer(f"[^{_SEPARATORS}]+", stem))
        for i, j in itertools.combinations(range(len(parts) + 1), 2):
            text = stem[parts[i].start() : parts[j - 1].end()]
            if re.search(r"\d", text):
                runs = re.split(r"(\d+)", text)
                key = "".join(
                    r"\d+" if k % 2 else re.escape(r) for k, r in enumerate(runs)
                )
                sources.setdefault(key, set()).add(session)

    minimum = 2 if len(session_paths) > 1 else 1
    common = sorted(
        (k for k, found_in in sources.items() if len(found_in) >= minimum),
        key=lambda k: (-len(sources[k]), k),
    )[:_MAX_CANDIDATES]

    names = [_tomogram_name(p, root) for p in tomogram_paths]
    best, best_score = None, None
    for key in common:
        matches = _pair(
            session_paths, stems, tomogram_paths, names, key, case_sensitive
        )
        paired = [len(m.candidates) for m in matches if m.candidates]
        if not paired:
            continue
        score = (
            paired.count(1),
            len(paired),
            -sum(paired),
            -key.count(r"\d+"),
            len(key),
            key,
        )
        if best_score is None or score > best_score:
            best, best_score = key, score
    return best


@dataclass
class LinkRow:
    """Link state of one session in the link dialog."""

    session: str
    current: str | None
    candidates: tuple[str, ...]
    selection: str | None = None


def outcome(row: LinkRow) -> str:
    """
    Classify what applying a row would do.

    Parameters
    ----------
    row : LinkRow
        Row to classify.

    Returns
    -------
    str
        One of ``ambiguous``, ``missing``, ``removed``, ``skipped``,
        ``linked``, ``new`` and ``replaced``.
    """
    if row.selection is None:
        return "ambiguous" if len(row.candidates) > 1 else "missing"
    if row.selection == NO_TOMOGRAM:
        return "removed" if row.current else "skipped"
    if row.selection == row.current:
        return "linked"
    if row.current is None:
        return "new"
    return "replaced"


def status_text(row: LinkRow) -> str:
    """Return the status shown for a row."""
    if outcome(row) == "ambiguous":
        return f"{len(row.candidates)} candidates"

    return {
        "missing": "No match",
        "removed": "Removed",
        "skipped": "Skipped",
        "linked": "Linked",
        "new": "New",
        "replaced": "Replaced",
    }[outcome(row)]


def is_warning(row: LinkRow) -> bool:
    """Return True if the row still needs a choice."""
    return outcome(row) in ("ambiguous", "missing")


def entries(row: LinkRow) -> list[str]:
    """
    List the tomogram paths offered for a row.

    Parameters
    ----------
    row : LinkRow
        Row to list paths for.

    Returns
    -------
    list of str
        Candidates, then the current link and a chosen file if not listed.
    """
    paths = list(row.candidates)
    for path in (row.current, row.selection):
        if path and path not in paths:
            paths.append(path)
    return paths


def build_rows(
    matches: list[Match], current_links: dict[str, str | None]
) -> list[LinkRow]:
    """
    Create dialog rows, with rows needing attention first.

    Parameters
    ----------
    matches : list of Match
        Output of :py:func:`match_tomograms`.
    current_links : dict
        Existing tomogram link per session path, or None.

    Returns
    -------
    list of LinkRow
        Ambiguous, missing and replaced rows first, each group in natural
        session order.
    """
    rows = []
    for m in matches:
        current = current_links.get(m.session)
        selection = m.tomogram if m.status == "matched" else current
        rows.append(LinkRow(m.session, current, m.candidates, selection))

    attention = ("ambiguous", "missing", "replaced")
    return sorted(
        rows,
        key=lambda r: (outcome(r) not in attention, natural_sort_key(r.session)),
    )


def pending_changes(rows: list[LinkRow]) -> dict[str, str | None]:
    """
    Collect the links to write.

    Parameters
    ----------
    rows : list of LinkRow
        Dialog rows.

    Returns
    -------
    dict
        New link per session path, None to remove the link.
    """
    changes = {}
    for row in rows:
        if outcome(row) in ("new", "replaced"):
            changes[row.session] = row.selection
        elif outcome(row) == "removed":
            changes[row.session] = None
    return changes


def resolve_note(rows: list[LinkRow]) -> str | None:
    """Return the count of rows needing a choice as text, or None if 0."""
    n = sum(is_warning(r) for r in rows)
    return f"{n} to resolve" if n else None


def initial_folder(
    current_links: dict[str, str | None], last: str | None
) -> str | None:
    """
    Pick the folder the dialog opens with.

    Parameters
    ----------
    current_links : dict
        Existing tomogram link per session path, or None.
    last : str or None
        Last folder used in the dialog.

    Returns
    -------
    str or None
        Common folder of the existing links, otherwise ``last``.
    """
    parents = [os.path.dirname(p) for p in current_links.values() if p]
    try:
        common = os.path.commonpath(parents)
    except ValueError:
        common = None

    if common and os.path.dirname(common) != common:
        return common
    return last or None


@dataclass(frozen=True)
class LinkWriteResult:
    """Outcome of :py:func:`write_tomogram_links`."""

    paths: dict[str, str]
    errors: dict[str, str]


def write_tomogram_links(changes: dict[str, str | None]) -> LinkWriteResult:
    """
    Write tomogram links into session files.

    Parameters
    ----------
    changes : dict
        Tomogram path per session path, None to remove the link. Legacy
        plain pickles are converted to ``.mosaic`` first.

    Returns
    -------
    LinkWriteResult
        Session paths that changed by conversion and errors per session.
    """
    from ..parallel import report_progress

    paths, errors = {}, {}
    for i, (path, tomogram) in enumerate(changes.items()):
        report_progress(current=i, total=len(changes))
        try:
            target = path
            if read_session_index(path)["format_version"] == 0:
                target = convert_legacy_session(path)
                paths[path] = target
            update_session_meta(target, {"tomogram": tomogram})
        except Exception as e:
            errors[path] = str(e)

    report_progress(current=len(changes), total=len(changes))
    return LinkWriteResult(paths, errors)


def link_summary(result: LinkWriteResult, n_changes: int) -> tuple[str, bool]:
    """
    Describe a link write for the status bar.

    Parameters
    ----------
    result : LinkWriteResult
        Output of :py:func:`write_tomogram_links`.
    n_changes : int
        Number of sessions passed to the write.

    Returns
    -------
    tuple
        Message and whether it is a warning.
    """
    ok = n_changes - len(result.errors)
    message = f"Updated {ok} session{'' if ok == 1 else 's'}"
    if result.paths:
        message += f", {len(result.paths)} converted to .mosaic"
    if result.errors:
        message += f", {len(result.errors)} failed"
    return message, bool(result.errors)
