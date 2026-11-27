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

from ..pipeline._utils import natural_sort_key
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
    "detected_key",
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


def _strip_extension(name: str) -> str:
    if name.endswith(".zarr"):
        return name[: -len(".zarr")]

    stem, ext = os.path.splitext(name)
    if ext.lower() == ".gz":
        stem = os.path.splitext(stem)[0]
    return stem


def _tomogram_name(path: str, root: str | None) -> str:
    rel = os.path.relpath(path, root) if root else os.path.basename(path)
    return _strip_extension(rel)


def _tokens(name: str) -> list[str]:
    tokens = re.split(f"[{_SEPARATORS}]+", name.lower())
    return [str(int(t)) if t.isascii() and t.isdigit() else t for t in tokens if t]


def _shared_run(a: list[str], b: list[str]) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _numeric_conflict(a: list[str], b: list[str]) -> bool:
    n = _shared_run(a, b)
    return n < min(len(a), len(b)) and all(
        t.isascii() and t.isdigit() for t in (a[n], b[n])
    )


def _auto_match(session: str, names: list[str], tomograms: list[str]) -> Match:
    session_tokens = _tokens(os.path.splitext(os.path.basename(session))[0])
    tomo_tokens = [_tokens(n) for n in names]

    baseline = 0
    if len(tomo_tokens) > 1:
        common = min(_shared_run(tomo_tokens[0], t) for t in tomo_tokens[1:])
        baseline = next(
            (
                i
                for i, t in enumerate(tomo_tokens[0][:common])
                if t.isascii() and t.isdigit()
            ),
            common,
        )

    scores = [
        (-1 if _numeric_conflict(session_tokens, t) else _shared_run(session_tokens, t))
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
    if template.count("{key}") != 1:
        raise ValueError(f"Pattern '{template}' needs exactly one {{key}}")

    parts = re.split(r"(\{key\}|\*)", template)
    regex = "".join(
        {"{key}": "(?P<key>.+?)", "*": ".*"}.get(p, re.escape(p)) for p in parts
    )
    return re.compile(regex, re.IGNORECASE)


def _pattern_key(regex: re.Pattern, name: str) -> str | None:
    m = regex.fullmatch(name)
    return m.group("key").lower() if m else None


def match_tomograms(
    session_paths: list[str],
    tomogram_paths: list[str],
    root: str | None = None,
    pattern: tuple[str, str] | None = None,
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


def detected_key(matches: list[Match]) -> tuple[str, str, str] | None:
    """
    Describe the auto-detected key with an example pair.

    Parameters
    ----------
    matches : list of Match
        Output of :py:func:`match_tomograms` in auto mode.

    Returns
    -------
    tuple of str or None
        Key with digits shown as ``#``, the example session stem and the
        example tomogram name, or None if nothing matched.
    """
    matched = sorted(
        (m for m in matches if m.status == "matched"),
        key=lambda m: natural_sort_key(m.session),
    )
    if not matched:
        return None

    example = matched[0]
    stem = os.path.splitext(os.path.basename(example.session))[0]
    session_tokens = _tokens(stem)

    # The scan root is unknown here, so try each trailing run of path parts.
    path = example.tomogram.rstrip("/\\")
    starts = [0] + [m.end() for m in re.finditer(r"[/\\]", path)]
    name, shared = path, -1
    for start in reversed(starts):
        n = _shared_run(session_tokens, _tokens(_strip_extension(path[start:])))
        if n > shared:
            name, shared = path[start:], n

    spans = list(re.finditer(f"[^{_SEPARATORS}]+", stem))
    key = stem[: spans[shared - 1].end()] if shared > 0 else ""
    return re.sub(r"\d", "#", key), stem, name


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

    # A filesystem root is too broad to scan, especially with subfolders.
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
