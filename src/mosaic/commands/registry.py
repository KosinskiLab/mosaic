"""
Command registry and built-in commands for the Mosaic scripting interface.

Commands are auto-registered from :class:`mosaic.operations.GeometryOperations`
and :class:`mosaic.properties.GeometryProperties`.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from .parser import ParsedCommand
from .theme import BOX_PANEL, BOX_TABLE, get_console
from ..registry import _UNSET

__all__ = ["Command", "CommandRegistry"]


@dataclass
class Command:
    """Descriptor for a single registered command.

    Attributes
    ----------
    name : str
        Primary command name.
    handler : callable
        ``fn(session, parsed_command) -> str``.
    description : str
        One-line description.
    usage : str
        Usage synopsis.
    """

    name: str
    handler: Callable
    description: str
    usage: str
    group: str = ""


class CommandRegistry:
    """Global registry mapping verb strings to :class:`Command` handlers."""

    _commands: Dict[str, Command] = {}

    @classmethod
    def register(
        cls,
        name: str,
        handler: Callable,
        description: str,
        usage: str,
        group: str = "",
    ):
        """Register a new command.

        Parameters
        ----------
        name : str
            Primary command name.
        handler : callable
            Function ``(session, parsed_command) -> str``.
        description : str
            Short description shown in help.
        usage : str
            Usage string.
        group : str, optional
            Group label for organized help display.
        """
        cls._commands[name] = Command(
            name=name,
            handler=handler,
            description=description,
            usage=usage,
            group=group,
        )

    @classmethod
    def dispatch(cls, session, parsed: ParsedCommand):
        """Look up and execute a command.

        Parameters
        ----------
        session : Session
            Active scripting session.
        parsed : ParsedCommand
            Parsed command to execute.

        Returns
        -------
        str or rich renderable
            Command output.
        """
        from ..registry import MethodRegistry

        cmd = cls.get(parsed.verb)
        if cmd is None:
            return _error_panel(
                f"Unknown command: {parsed.verb!r}. Type 'help' to list commands."
            )

        op = MethodRegistry.get(parsed.verb)
        if op is not None and parsed.args:
            if op.methods:
                first, parsed.args = parsed.args[0], parsed.args[1:]
                method = op.get_method(first)
                # Method-specific params first so positional args bind to them
                # before the common params (store, output, etc.)
                params = list(method.params) if method is not None else []
                params += list(op.common_params)
                parsed.resolve_positional(params)
                parsed.args.insert(0, first)
            else:
                parsed.resolve_positional(op.common_params)

        # Inject registry defaults for parameters not provided by the user
        if op is not None:
            all_params = list(op.common_params)
            if op.methods and parsed.args:
                method = op.get_method(parsed.args[0])
                if method is not None:
                    all_params += list(method.params)
            for p in all_params:
                if p.name not in parsed.kwargs and p.default is not _UNSET:
                    parsed.kwargs[p.name] = p.default

        return cmd.handler(session, parsed)

    @classmethod
    def get(cls, name: str) -> Optional[Command]:
        """Retrieve a command by name."""
        return cls._commands.get(name)

    @classmethod
    def list_commands(cls) -> List[Command]:
        """Return all registered commands sorted by name."""
        return sorted(cls._commands.values(), key=lambda c: c.name)


def _error_panel(message: str) -> Panel:
    """Wrap an error message in a styled Panel."""
    return Panel(
        Text(message),
        border_style="mosaic.error",
        title="[mosaic.error]Error",
        title_align="left",
        padding=(0, 1),
    )


def _success_text(prefix: str, detail: str) -> Text:
    """Build a success message with styled prefix."""
    t = Text()
    t.append(prefix, style="mosaic.success")
    t.append(detail, style="mosaic.muted")
    return t


def _resolve_targets(session, parsed: ParsedCommand):
    """Resolve targets from a parsed command."""
    if parsed.targets:
        return session.resolve_many(parsed.targets)
    return []


def _is_target_ref(value: str) -> bool:
    """Check if *value* looks like a geometry reference (``#0``, ``@last``, etc.)."""
    from .parser import _TARGET_RE, _SPECIAL_TARGETS

    parts = [v.strip() for v in value.split(",")]
    return all(_TARGET_RE.match(v) or v in _SPECIAL_TARGETS for v in parts)


def _resolve_kwargs(session, kwargs: Dict[str, object]) -> Dict[str, object]:
    """Replace geometry references in kwarg values with resolved Geometry objects.

    Recognises ``#N``, ``#N-M``, ``@last``, ``*``, and comma-separated
    combinations (e.g. ``"#0,#2"``).
    """
    resolved = {}
    for key, value in kwargs.items():
        if isinstance(value, str) and _is_target_ref(value):
            parts = [v.strip() for v in value.split(",")]
            geoms = session.resolve_many(parts)
            if not geoms:
                raise IndexError(
                    f"No geometries matching {value!r} for parameter '{key}'"
                )
            resolved[key] = geoms if len(parts) > 1 else geoms[0]
        else:
            resolved[key] = value
    return resolved


def _usage_for(name: str) -> str:
    """Return the registered usage string for *name*."""
    cmd = CommandRegistry.get(name)
    return cmd.usage if cmd is not None else name


def _build_param_table(params) -> Table:
    """Build a parameters table from a list of Param objects."""
    table = Table(
        box=BOX_TABLE,
        show_header=True,
        show_edge=False,
        pad_edge=True,
        padding=(0, 1),
    )
    table.add_column("Parameter", style="mosaic.param", no_wrap=True)
    table.add_column("Type", style="mosaic.muted")
    table.add_column("Default", style="mosaic.data")
    table.add_column("Description", style="mosaic.muted")

    for p in params:
        default_str = ""
        if p.default is not _UNSET:
            default_str = repr(p.default)

        desc_parts = []
        if p.options:
            desc_parts.append(", ".join(repr(o) for o in p.options))
        if p.description:
            desc_parts.append(p.description)
        if p.notes:
            desc_parts.append(p.notes)

        table.add_row(p.name, p.type, default_str, " — ".join(desc_parts))

    return table


def _usage_line(usage_str: str) -> Text:
    """Build a styled ``Usage: ...`` line."""
    t = Text()
    t.append("Usage: ", style="mosaic.muted")
    t.append(usage_str, style="bold")
    return t


def _help_panel(title: str, *parts) -> Panel:
    """Wrap content parts in a consistently styled help Panel."""
    return Panel(
        Group(*parts),
        title=f"[mosaic.heading]{title}",
        title_align="left",
        border_style="mosaic.border",
        box=BOX_PANEL,
        padding=(0, 1),
    )


def _applied_text(op_name: str, created: list, session) -> Text:
    """Build a styled "Applied ... → N new geometry(s): #0, #1" message."""
    if not created:
        return _success_text(f"Applied {op_name}", " (no new geometries created).")
    all_geoms = session._all_geometries()
    indices = [all_geoms.index(g) for g in created if g in all_geoms]
    t = Text()
    t.append(f"Applied {op_name}", style="mosaic.success")
    t.append(f" → {len(created)} new geometry(s): ", style="mosaic.muted")
    if indices:
        t.append(", ".join(f"#{i}" for i in indices), style="mosaic.index")
    else:
        t.append("@last", style="mosaic.index")
    return t


def _cmd_open(session, parsed: ParsedCommand):
    import glob as _glob

    filepath = parsed.kwargs.pop("filepath", None)
    if filepath is None:
        return _usage_line(_usage_for("open"))

    persist = parsed.kwargs.get("persist", True)

    if any(c in filepath for c in ("*", "?", "[")):
        paths = sorted(_glob.glob(filepath, recursive="**" in filepath))
        if not paths:
            return _error_panel(f"No files matching: {filepath}")
        all_indices = []
        all_geoms = []
        for path in paths:
            all_indices.extend(session.open(path, **parsed.kwargs))
            all_geoms.extend(session._last_results)
        session._last_results = all_geoms
        if persist:
            return _success_text(
                f"Loaded {len(all_indices)} geometry(s) from {len(paths)} file(s)  ",
                ", ".join(f"#{i}" for i in all_indices),
            )
        return _success_text(
            f"Loaded {len(all_geoms)} geometry(s) from {len(paths)} file(s)  ",
            "(available via @last)",
        )

    indices = session.open(filepath, **parsed.kwargs)
    if persist:
        return _success_text(
            f"Loaded {len(indices)} geometry(s)  ",
            ", ".join(f"#{i}" for i in indices),
        )
    n = len(session._last_results)
    return _success_text(f"Loaded {n} geometry(s)  ", "(available via @last)")


def _cmd_save(session, parsed: ParsedCommand):
    filepath = parsed.kwargs.pop("filepath", None)
    if filepath is None:
        return _usage_line(_usage_for("save"))
    geometries = _resolve_targets(session, parsed)
    session.save(geometries, filepath, **parsed.kwargs)
    return _success_text(f"Saved {len(geometries)} geometry(s)  ", filepath)


def _cmd_save_session(session, parsed: ParsedCommand):
    if not parsed.args:
        return _usage_line("save_session <filepath>")
    session.save_session(parsed.args[0])
    return _success_text("Session saved  ", parsed.args[0])


def _cmd_load_session(session, parsed: ParsedCommand):
    if not parsed.args:
        return _usage_line("load_session <filepath>")
    session.load_session(parsed.args[0])
    n = len(session._all_geometries())
    return _success_text(f"Session loaded ({n} geometries)  ", parsed.args[0])


def _build_geometry_table(session, entries) -> Table:
    """Build a geometry listing table from ``(index, geometry)`` pairs."""
    table = Table(
        box=BOX_TABLE,
        show_header=True,
        show_edge=False,
        pad_edge=True,
        padding=(0, 1),
        caption=f"[mosaic.muted]{len(entries)} geometries",
        caption_style="",
    )
    table.add_column("#", justify="right", style="mosaic.index", no_wrap=True)
    table.add_column("Points", justify="right", style="mosaic.data")
    table.add_column("Type", justify="center", style="mosaic.type")
    table.add_column("Group", style="mosaic.group")
    table.add_column("Name", style="bold")

    for i, geom in entries:
        n_pts = geom.get_number_of_points()
        gtype = geom.geometry_type
        ggroup = session._geometry_group(geom)
        name = session._geometry_name(geom, i)
        table.add_row(str(i), f"{n_pts:,}", gtype, ggroup, name)

    return table


def _cmd_list(session, parsed: ParsedCommand):
    all_geoms = session._all_geometries()
    if not all_geoms:
        return Text("No geometries loaded.", style="mosaic.muted")

    # Normalize kwargs to lowercase so Name=, Type=, Group= all work
    kwargs = {k.lower(): v for k, v in parsed.kwargs.items()}
    output_fmt = kwargs.pop("format", "table")

    # Handle visible: default to True (hide invisible), "all" disables filter
    vis = kwargs.pop("visible", True)
    if isinstance(vis, str) and vis.lower() == "all":
        vis = None
    kwargs["visible"] = vis

    entries = session.list_filtered(**kwargs)

    if not entries:
        filter_parts = {
            k: v for k, v in kwargs.items() if v is not None and k != "visible"
        }
        if filter_parts:
            parts = [f"{k}='{v}'" for k, v in filter_parts.items()]
            return Text(
                f"No geometries matching {', '.join(parts)}.", style="mosaic.muted"
            )
        return Text("No geometries loaded.", style="mosaic.muted")

    if output_fmt == "ids":
        return " ".join(f"#{i}" for i, _ in entries)

    return _build_geometry_table(session, entries)


def _cmd_info(session, parsed: ParsedCommand):
    geometries = _resolve_targets(session, parsed)
    if not geometries:
        return Text("No geometries to inspect.", style="mosaic.muted")

    all_geoms = session._all_geometries()
    panels = []

    for geom in geometries:
        idx = all_geoms.index(geom) if geom in all_geoms else "?"
        name = session._geometry_name(geom, idx)

        table = Table(box=None, show_header=False, pad_edge=False, padding=(0, 1))
        table.add_column("Key", style="mosaic.param", justify="right", no_wrap=True)
        table.add_column("Value", style="mosaic.data")

        rows = [
            ("Index", f"#{idx}"),
            ("UUID", str(geom.uuid)),
            ("Type", geom.geometry_type),
            ("Points", f"{geom.get_number_of_points():,}"),
            ("Normals", "yes" if geom.normals is not None else "no"),
            ("Model", "yes" if geom._model is not None else "no"),
            ("Visible", "yes" if geom.visible else "no"),
            ("Sampling", str(geom.sampling_rate)),
        ]
        for k, v in geom._meta.items():
            rows.append((k, str(v)))

        for k, v in rows:
            table.add_row(k, v)

        panels.append(
            Panel(
                table,
                title=f"[mosaic.heading]#{idx} {name}",
                title_align="left",
                border_style="mosaic.border",
                box=BOX_PANEL,
                padding=(0, 1),
                width=min(60, get_console().width),
            )
        )

    if len(panels) == 1:
        return panels[0]
    return Columns(panels, equal=True, expand=True)


def _cmd_remove(session, parsed: ParsedCommand):
    if not parsed.targets:
        return _usage_line("remove [targets]")
    geometries = session.resolve_many(parsed.targets)
    count = session.remove(geometries)
    return _success_text(f"Removed {count} geometry(s).", "")


def _cmd_visibility(session, parsed: ParsedCommand):
    geometries = _resolve_targets(session, parsed)
    if not geometries:
        return Text("No target geometries.", style="mosaic.muted")
    visible = parsed.kwargs.pop("visible", True)
    for geom in geometries:
        geom.set_visibility(visible)
    state = "visible" if visible else "hidden"
    return _success_text(f"Set {len(geometries)} geometry(s) to {state}.", "")


def _cmd_group(session, parsed: ParsedCommand):
    geometries = _resolve_targets(session, parsed)
    if not geometries:
        return _usage_line("group [targets] <name>")
    if not parsed.args:
        return _error_panel("Missing group name. Usage: group [targets] <name>")
    name = " ".join(parsed.args)
    session.group(geometries, name)
    return _success_text(f"Grouped {len(geometries)} geometry(s)  ", f"→ {name}")


def _cmd_ungroup(session, parsed: ParsedCommand):
    geometries = _resolve_targets(session, parsed)
    if not geometries:
        return _usage_line("ungroup [targets]")
    count = session.ungroup(geometries)
    return _success_text(f"Ungrouped {count} geometry(s).", "")


def _cmd_rename(session, parsed: ParsedCommand):
    import re as _re

    if not parsed.args:
        return _usage_line(_usage_for("rename"))

    geometries = _resolve_targets(session, parsed)
    if not geometries:
        return Text("No target geometries.", style="mosaic.muted")

    expr = parsed.args[0]
    match = _re.fullmatch(r"s/(.+?)/(.*?)/(.*)", expr)

    # Simple direct rename: rename #0 new name
    if match is None:
        new_name = " ".join(parsed.args)
        for geom in geometries:
            geom._meta["name"] = new_name
        return _success_text(f"Renamed {len(geometries)} geometry(s).", "")

    # Substitution: rename #0 s/old/new/g
    pattern, replacement, flags_str = match.groups()
    re_flags = 0
    if "i" in flags_str:
        re_flags |= _re.IGNORECASE
    use_global = "g" in flags_str

    try:
        compiled = _re.compile(pattern, re_flags)
    except _re.error as exc:
        return _error_panel(f"Invalid regex: {exc}")

    all_geoms = session._all_geometries()
    count = 0
    for geom in geometries:
        idx = all_geoms.index(geom) if geom in all_geoms else "?"
        old_name = session._geometry_name(geom, idx)
        new_name = compiled.sub(replacement, old_name, count=0 if use_global else 1)
        if new_name != old_name:
            geom._meta["name"] = new_name
            count += 1

    return _success_text(f"Renamed {count} geometry(s).", "")


_GROUP_ORDER = ["I/O", "Session", "Operations", "Analysis", "Shell"]


def _registry_method_listing(op_name: str):
    """Build a method listing table for a registered operation."""
    from ..registry import MethodRegistry

    op = MethodRegistry.get(op_name)
    if op is None:
        return ""

    table = Table(
        box=BOX_TABLE,
        show_header=True,
        show_edge=False,
        pad_edge=True,
        padding=(0, 1),
    )
    table.add_column("Method", style="mosaic.command", no_wrap=True)
    table.add_column("Description", style="mosaic.muted")

    for m in op.methods:
        table.add_row(m.internal_name, m.description or "")

    return _help_panel(
        op_name,
        _usage_line(op.build_usage()),
        Text(),
        table,
        Text(),
        Text(f"Type 'help {op_name} <method>' for parameters.", style="mosaic.muted"),
    )


def _registry_operation_help(op_name: str):
    """Build help panel for a registered operation without sub-methods."""
    from ..registry import MethodRegistry

    op = MethodRegistry.get(op_name)
    if op is None:
        return _error_panel(f"Unknown operation: {op_name!r}")

    parts = []
    if op.description:
        parts += [Text(op.description), Text()]
    parts.append(_usage_line(op.build_usage()))

    if op.common_params:
        parts += [Text(), _build_param_table(op.common_params)]

    return _help_panel(op_name, *parts)


def _registry_method_help(op_name: str, method_name: str):
    """Build help panel for a specific method of a registered operation."""
    from ..registry import MethodRegistry

    op = MethodRegistry.get(op_name)
    if op is None:
        return _error_panel(f"Unknown operation: {op_name!r}")
    method = op.get_method(method_name)
    if method is None:
        available = ", ".join(m.internal_name for m in op.methods)
        return _error_panel(
            f"Unknown {op_name} method: {method_name!r}. Available: {available}"
        )

    title = f"{op_name} {method.internal_name}"
    desc = method.description or f"Apply {op_name} with method {method.internal_name}"
    parts = [
        Text(desc),
        Text(),
        _usage_line(op.build_usage(method_name=method.internal_name)),
    ]

    all_params = list(method.params) + list(op.common_params)
    if all_params:
        parts += [Text(), _build_param_table(all_params)]

    return _help_panel(title, *parts)


def _cmd_help(session, parsed: ParsedCommand):
    from ..registry import MethodRegistry

    if parsed.args:
        cmd = CommandRegistry.get(parsed.args[0])
        if cmd is None:
            return _error_panel(f"Unknown command: {parsed.args[0]!r}")

        op_name = parsed.args[0]
        reg_op = MethodRegistry.get(op_name)

        if reg_op is not None:
            if reg_op.methods:
                if len(parsed.args) > 1:
                    return _registry_method_help(op_name, parsed.args[1])
                return _registry_method_listing(op_name)
            return _registry_operation_help(op_name)

        return _help_panel(
            cmd.name, Text(cmd.description), Text(), _usage_line(cmd.usage)
        )

    groups: Dict[str, List[Command]] = {}
    for cmd in CommandRegistry.list_commands():
        groups.setdefault(cmd.group or "Other", []).append(cmd)

    parts = []
    ordered = [(g, groups.pop(g, [])) for g in _GROUP_ORDER]
    ordered += sorted(groups.items())

    for group_name, cmds in ordered:
        if not cmds:
            continue
        table = Table(
            box=None,
            show_header=False,
            show_edge=False,
            pad_edge=True,
            padding=(0, 1),
        )
        table.add_column("Command", style="mosaic.command", no_wrap=True, min_width=20)
        table.add_column("Description", style="mosaic.muted")
        for cmd in cmds:
            table.add_row(cmd.name, cmd.description)
        parts.append(Rule(group_name, style="mosaic.rule", align="left"))
        parts.append(table)

    parts += [Text(), Text("Type 'help <command>' for details.", style="mosaic.muted")]

    return _help_panel("Mosaic Commands", *parts)


def _cmd_history(session, parsed: ParsedCommand):
    if not session._log:
        return Text("No commands in history.", style="mosaic.muted")

    table = Table(
        box=None,
        show_header=False,
        show_edge=False,
        pad_edge=True,
        padding=(0, 1),
    )
    table.add_column("#", style="mosaic.muted", justify="right", no_wrap=True)
    table.add_column("Command", style="mosaic.command")

    for i, line in enumerate(session._log):
        table.add_row(str(i), line)

    return table


def _make_operation_handler(op_name: str, has_methods: bool = False):
    """Create a handler that dispatches to Session.apply.

    Parameters
    ----------
    op_name : str
        Name of the operation in :class:`GeometryOperations`.
    has_methods : bool, optional
        If True, the first positional arg is treated as a method name
        and validated against :class:`MethodRegistry`.
    """

    def handler(session, parsed: ParsedCommand):
        method_name = None
        if has_methods:
            if not parsed.args:
                return _registry_method_listing(op_name)

            from ..registry import MethodRegistry

            method_name = parsed.args[0]
            op = MethodRegistry.get(op_name)
            if op is not None and op.get_method(method_name) is None:
                if "method" not in parsed.kwargs:
                    available = ", ".join(m.internal_name for m in op.methods)
                    return _error_panel(
                        f"Unknown {op_name} method: {method_name!r}. "
                        f"Available: {available}"
                    )
                method_name = None

        geometries = _resolve_targets(session, parsed)
        if not geometries:
            return Text("No target geometries.", style="mosaic.muted")

        kwargs = _resolve_kwargs(session, parsed.kwargs)
        if method_name is not None:
            kwargs["method"] = method_name
        created = session.apply(op_name, geometries, **kwargs)
        return _applied_text(op_name, created, session)

    return handler


def _cmd_measure(session, parsed: ParsedCommand):
    import numpy as np

    if not parsed.args:
        return _registry_method_listing("measure")

    property_name = parsed.args[0]
    geometries = _resolve_targets(session, parsed)
    if not geometries:
        return Text("No target geometries.", style="mosaic.muted")

    kwargs = _resolve_kwargs(session, parsed.kwargs)
    store = kwargs.get("store", False)
    results = session.measure(property_name, geometries, **kwargs)

    all_geoms = session._all_geometries()

    # Classify results into scalars vs per-vertex arrays
    has_array = any(
        isinstance(v, np.ndarray) and v.ndim >= 1 for v in results if v is not None
    )

    if has_array:
        table = Table(
            box=BOX_TABLE,
            show_header=True,
            show_edge=False,
            pad_edge=True,
            padding=(0, 1),
        )
        table.add_column("#", justify="right", style="mosaic.index", no_wrap=True)
        table.add_column("Points", justify="right", style="mosaic.data")
        table.add_column("Min", justify="right", style="mosaic.data")
        table.add_column("Max", justify="right", style="mosaic.data")
        table.add_column("Mean", justify="right", style="mosaic.data")
        table.add_column("Std", justify="right", style="mosaic.data")
        table.add_column("Median", justify="right", style="mosaic.data")
    else:
        table = Table(
            box=BOX_TABLE,
            show_header=True,
            show_edge=False,
            pad_edge=True,
            padding=(0, 1),
        )
        table.add_column("#", justify="right", style="mosaic.index", no_wrap=True)
        table.add_column("Value", justify="right", style="mosaic.data")

    skipped = []
    for i, (geom, val) in enumerate(zip(geometries, results)):
        if geom in all_geoms:
            label = str(all_geoms.index(geom))
        else:
            label = f"@{i}"
        if val is None:
            skipped.append(label)
            continue

        if has_array and isinstance(val, np.ndarray) and val.ndim >= 1:
            table.add_row(
                label,
                f"{len(val):,}",
                f"{val.min():.4g}",
                f"{val.max():.4g}",
                f"{val.mean():.4g}",
                f"{val.std():.4g}",
                f"{np.median(val):.4g}",
            )
        elif has_array:
            sv = str(val)
            table.add_row(label, "", sv, sv, sv, "0", sv)
        else:
            table.add_row(label, str(val))

    if skipped and not table.rows:
        return _error_panel(
            f"{property_name} returned no results. "
            f"Check that the target geometries support this property."
        )

    parts = [table]

    if skipped:
        parts.append(
            Text(
                f"  Skipped #{', #'.join(skipped)} (property not available)",
                style="mosaic.warning",
            )
        )

    if store:
        parts.append(
            _success_text(
                f"Stored '{property_name}' ",
                "as vertex property on matching geometries.",
            )
        )

    if len(parts) == 1:
        return parts[0]
    return Group(*parts)


def _cmd_filter(session, parsed: ParsedCommand):
    geometries = _resolve_targets(session, parsed)
    if not geometries:
        return Text("No target geometries.", style="mosaic.muted")

    kwargs = _resolve_kwargs(session, parsed.kwargs)
    prop = kwargs.pop("property", None)
    if prop is None:
        return _error_panel("Missing required parameter: property=<name>")

    kept, removed, level = session.filter(geometries, prop_name=prop, **kwargs)

    if level == "point":
        return _success_text(
            f"Point filter '{prop}': ",
            f"kept {kept:,} points, removed {removed:,} points.",
        )
    return _success_text(
        f"Population filter '{prop}': ",
        f"kept {kept}, removed {removed} geometry(s).",
    )


def _cmd_merge(session, parsed: ParsedCommand):
    geometries = _resolve_targets(session, parsed)
    if len(geometries) < 2:
        return _error_panel("Need at least two geometries to merge.")
    kwargs = _resolve_kwargs(session, parsed.kwargs)
    merged = session.merge(geometries, **kwargs)
    all_geoms = session._all_geometries()
    idx = all_geoms.index(merged) if merged in all_geoms else "?"
    return _success_text(f"Merged {len(geometries)} geometries  ", f"→ #{idx}")


def _register_builtins():
    """Register all built-in and auto-discovered commands."""
    from ..operations import GeometryOperations
    from ..registry import MethodRegistry

    for name, handler, desc, group in [
        ("open", _cmd_open, "Load geometries from file", "I/O"),
        ("save", _cmd_save, "Export geometries to file", "I/O"),
        ("list", _cmd_list, "List all loaded geometries", "Session"),
        ("measure", _cmd_measure, "Compute a geometry property", "Analysis"),
        ("merge", _cmd_merge, "Merge geometries into one", "Session"),
        (
            "filter",
            _cmd_filter,
            "Filter geometries by property value range",
            "Analysis",
        ),
    ]:
        op = MethodRegistry.get(name)
        usage = op.build_usage() if op is not None else name
        CommandRegistry.register(name, handler, desc, usage, group=group)

    for name, handler, desc, usage, group in [
        (
            "save_session",
            _cmd_save_session,
            "Save session state",
            "save_session <filepath>",
            "I/O",
        ),
        (
            "load_session",
            _cmd_load_session,
            "Load session state",
            "load_session <filepath>",
            "I/O",
        ),
        ("info", _cmd_info, "Show geometry details", "info [targets]", "Session"),
        ("remove", _cmd_remove, "Remove geometries", "remove [targets]", "Session"),
        (
            "group",
            _cmd_group,
            "Assign geometries to a group",
            "group [targets] <name>",
            "Session",
        ),
        (
            "ungroup",
            _cmd_ungroup,
            "Remove geometries from groups",
            "ungroup [targets]",
            "Session",
        ),
        (
            "rename",
            _cmd_rename,
            "Rename geometries",
            "rename [targets] <new name> or s/pattern/replacement/[flags]",
            "Session",
        ),
        ("help", _cmd_help, "Show help", "help [command]", "Shell"),
        ("history", _cmd_history, "Show command history", "history", "Shell"),
    ]:
        CommandRegistry.register(name, handler, desc, usage, group=group)

    for attr_name in dir(GeometryOperations):

        func = getattr(GeometryOperations, attr_name)
        if attr_name.startswith("_") or attr_name == "register" or not callable(func):
            continue

        if (reg_op := MethodRegistry.get(attr_name)) is None:
            continue

        handler = _make_operation_handler(attr_name, has_methods=bool(reg_op.methods))
        usage = reg_op.build_usage() if reg_op is not None else f"{attr_name} [targets]"
        CommandRegistry.register(
            attr_name,
            handler,
            reg_op.description or f"Apply {attr_name} operation",
            usage,
            group="Operations",
        )

    # Override auto-generated handlers for in-place operations
    CommandRegistry.register(
        "visibility",
        _cmd_visibility,
        "Change geometry visibility",
        "visibility [targets] visible=true|false",
        group="Session",
    )


_register_builtins()
