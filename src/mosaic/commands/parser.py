"""
Text command parser for the Mosaic scripting interface.

Parses ``verb [target...] [positional_args...] [key=value ...]`` into a
structured :class:`ParsedCommand`.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import re
import shlex
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = ["ParsedCommand", "parse_command", "format_value", "format_kwargs"]

_TARGET_RE = re.compile(r"^#\d+(-\d+)?$")
_SPECIAL_TARGETS = {"@last", "*"}


def _coerce_value(value: str) -> Any:
    """Auto-coerce a string value to int, float, bool, array, or leave as str.

    Comma-separated numeric values (e.g. ``"1.0,2.0,3.0"``) are returned as
    a :class:`numpy.ndarray`.  Bracket syntax (``"[1,2,3]"``) is also
    accepted for backwards compatibility.

    Parameters
    ----------
    value : str
        Raw string token from command line.

    Returns
    -------
    int, float, bool, np.ndarray, or str
        Coerced value.
    """
    import numpy as np

    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    # Strip optional brackets for backwards compatibility
    inner = value
    if inner.startswith("[") and inner.endswith("]"):
        inner = inner[1:-1].strip()
    if "," in inner:
        parts = [v.strip() for v in inner.split(",")]
        try:
            return np.array([float(v) for v in parts])
        except ValueError:
            return parts if inner is not value else value
    return value


def format_value(value) -> str:
    """Format a Python value as a REPL-safe token.

    Inverse of :func:`_coerce_value`.  Arrays, lists and tuples become
    comma-separated strings (e.g. ``"1.0,2.0,3.0"``).

    Parameters
    ----------
    value
        Python value to format.

    Returns
    -------
    str
        Formatted string suitable for embedding in a REPL command.
    """
    import numpy as np

    if isinstance(value, np.ndarray):
        return ",".join(str(v) for v in value.ravel())
    if isinstance(value, (list, tuple)):
        return ",".join(str(v) for v in value)
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def format_kwargs(settings: dict) -> str:
    """Format a settings dict as ``key=value`` pairs for a REPL command.

    Parameters
    ----------
    settings : dict
        Key-value pairs to format.

    Returns
    -------
    str
        Space-separated ``key=value`` tokens.  Values containing spaces
        are quoted so that :func:`shlex.split` can reconstruct them.
    """
    parts = []
    for key, value in settings.items():
        if value is None:
            continue
        sv = format_value(value)
        if (
            any(c in sv for c in (" ", '"', "'", "\\"))
            or sv != sv.strip()
            or "\n" in sv
            or "\t" in sv
        ):
            sv = shlex.quote(sv)
        parts.append(f"{key}={sv}")
    return " ".join(parts)


@dataclass
class ParsedCommand:
    """Structured representation of a parsed scripting command.

    Attributes
    ----------
    verb : str
        Command verb (e.g. ``"cluster"``, ``"open"``).
    targets : list of str
        Geometry references starting with ``#`` (e.g. ``["#0", "#1-3"]``).
    args : list of str
        Positional arguments (e.g. file paths, sub-commands).
    kwargs : dict
        Keyword arguments with auto-coerced values.
    """

    verb: str
    targets: List[str] = field(default_factory=list)
    args: List[str] = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)

    def resolve_positional(self, params) -> None:
        """Map remaining positional *args* into *kwargs* by parameter order.

        Parameters already present in *kwargs* are skipped.  Values are
        auto-coerced through :func:`_coerce_value` unless the parameter
        type is ``"path"`` or ``"str"``.

        Parameters
        ----------
        params : list
            Either a list of parameter name strings, or a list of
            :class:`~mosaic.registry.Param` objects (which carry
            ``.name`` and ``.type`` attributes).
        """
        remaining = []
        _STR_TYPES = ("path", "str")
        name_iter = iter(
            p
            for p in params
            if (p.name if hasattr(p, "name") else p) not in self.kwargs
        )
        for arg in self.args:
            param = next(name_iter, None)
            if param is not None:
                name = param.name if hasattr(param, "name") else param
                ptype = getattr(param, "type", None)
                self.kwargs[name] = arg if ptype in _STR_TYPES else _coerce_value(arg)
            else:
                remaining.append(arg)
        self.args = remaining


def parse_command(text: str) -> Optional[ParsedCommand]:
    """Parse a text command into a :class:`ParsedCommand`.

    Parameters
    ----------
    text : str
        Raw command text. Lines starting with ``#`` (not followed by a digit)
        are treated as comments and return ``None``.

    Returns
    -------
    ParsedCommand or None
        Parsed command, or ``None`` for comments and blank lines.
    """
    text = text.strip()
    if not text:
        return None

    # Comment line: starts with # but not #<digit> (geometry ref)
    if text.startswith("#") and not re.match(r"^#\d", text):
        return None

    try:
        tokens = shlex.split(text)
    except ValueError as exc:
        raise ValueError(f"Syntax error: {exc}") from None
    if not tokens:
        return None

    verb = tokens[0].lower()
    targets = []
    args = []
    kwargs = {}

    for token in tokens[1:]:
        if "=" in token and not token.startswith("="):
            key, _, val = token.partition("=")
            kwargs[key] = _coerce_value(val)
        elif _TARGET_RE.match(token) or token in _SPECIAL_TARGETS:
            targets.append(token)
        else:
            args.append(token)

    return ParsedCommand(
        verb=verb,
        targets=targets,
        args=args,
        kwargs=kwargs,
    )
