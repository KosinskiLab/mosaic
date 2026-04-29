"""
Interactive REPL for the Mosaic scripting interface.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import re
import readline
from pathlib import Path
from typing import Optional

from .parser import parse_command
from .session import Session
from .registry import CommandRegistry, _error_panel
from .theme import get_console, render_to_text

_SUBST_RE = re.compile(r"\$\(([^)]+)\)")

__all__ = ["MosaicREPL"]

_HISTORY_PATH = Path.home() / ".mosaic_history"


class _Completer:
    """Tab-completion for commands, methods, targets, parameters and values."""

    def __init__(self, session: Session):
        self._session = session
        self._matches = []

    def complete(self, text: str, state: int) -> Optional[str]:
        if state == 0:
            self._matches = self._build_matches(text)
        if state < len(self._matches):
            return self._matches[state]
        return None

    def _build_matches(self, text: str) -> list:
        line = readline.get_line_buffer().lstrip()

        if " " not in line:
            names = [c.name for c in CommandRegistry.list_commands()]
            return [n + " " for n in sorted(names) if n.startswith(text)]

        if text.startswith("#"):
            n = len(self._session._all_geometries())
            refs = [f"#{i}" for i in range(n)]
            return [r + " " for r in refs if r.startswith(text)]

        if text.startswith("@"):
            return ["@last "] if "@last".startswith(text) else []

        if "=" in text:
            return self._complete_value(text, line)

        verb = line.split()[0].lower()
        op = self._get_operation(verb)
        if op is None:
            return []

        tokens = line.split()
        has_method = self._has_method_token(tokens, op)

        if op.methods and not has_method:
            candidates = []
            for m in op.methods:
                name = m.internal_name
                if name.startswith(text):
                    candidates.append(name + " ")
            if "help".startswith(text):
                candidates.append("help ")
            return sorted(candidates)

        candidates = self._complete_param_names(text, line, op, tokens)
        if "help".startswith(text):
            candidates.append("help ")
        return candidates

    def _get_operation(self, verb: str):
        """Look up the Operation for a command verb."""
        from ..registry import MethodRegistry

        return MethodRegistry.get(verb)

    def _has_method_token(self, tokens: list, op) -> bool:
        """Check whether any token matches a known method of *op*."""
        for tok in tokens[1:]:
            if "=" in tok:
                continue
            if op.get_method(tok) is not None:
                return True
        return False

    def _active_method(self, tokens: list, op):
        """Return the Method for the first matching token, or None."""
        for tok in tokens[1:]:
            if "=" in tok:
                continue
            m = op.get_method(tok)
            if m is not None:
                return m
        return None

    def _complete_param_names(self, text: str, line: str, op, tokens: list) -> list:
        """Complete parameter names, filtering out those already used."""
        already_used = set()
        for tok in tokens[1:]:
            if "=" in tok:
                key, _, _ = tok.partition("=")
                already_used.add(key)

        params = list(op.common_params)
        method = self._active_method(tokens, op)
        if method is not None:
            params = list(method.params) + params

        candidates = []
        for p in params:
            if p.name in already_used:
                continue
            key = p.name + "="
            if key.startswith(text):
                candidates.append(key)
        return sorted(candidates)

    def _complete_value(self, text: str, line: str) -> list:
        """Complete the value side of a key=value token."""
        key, _, partial = text.partition("=")

        verb = line.split()[0].lower()
        op = self._get_operation(verb)
        if op is None:
            return []

        tokens = line.split()
        param = self._find_param(key, op, tokens)
        if param is None:
            return []

        # Boolean parameters
        if param.type == "bool":
            options = ["true", "false"]
            return [f"{key}={o} " for o in options if o.startswith(partial.lower())]

        # Select / options parameters
        if param.options is not None:
            candidates = []
            for opt in param.options:
                val = str(opt)
                if val.lower().startswith(partial.lower()):
                    suffix = f"{key}={val} "
                    candidates.append(suffix)
            return candidates

        # Format parameter (common enough to special-case)
        if param.name == "format":
            formats = ("star", "tsv", "xyz", "obj", "stl", "ply", "mrc", "em", "h5")
            return [f"{key}={f} " for f in formats if f.startswith(partial.lower())]

        return []

    def _find_param(self, key: str, op, tokens: list):
        """Find the Param matching *key* in the operation + active method."""
        for p in op.common_params:
            if p.name == key:
                return p

        method = self._active_method(tokens, op)
        if method is not None:
            for p in method.params:
                if p.name == key:
                    return p

        return None


class MosaicREPL:
    """Interactive Mosaic scripting shell.

    Parameters
    ----------
    session : Session, optional
        Pre-existing session. A new one is created if not provided.
    log_file : str, optional
        Path for the session command log. When ``None`` (default),
        commands are not logged to disk.
    """

    def __init__(
        self, session: Optional[Session] = None, log_file: Optional[str] = None
    ):
        self.session = session or Session()
        self._log_file = log_file
        self._console = get_console()

    def run(self) -> None:
        """Start the interactive read-eval-print loop."""
        self._setup_readline()
        self._print_banner()

        prompt = self._build_prompt()

        _interrupted = False
        while True:
            try:
                line = input(prompt)
                _interrupted = False
            except EOFError:
                self._console.print()
                break
            except KeyboardInterrupt:
                self._console.print()
                if _interrupted:
                    break
                _interrupted = True
                self._console.print(
                    "[mosaic.warning]Press Ctrl+C again or type 'exit' to quit.[/]"
                )
                continue

            line = line.strip()
            if not line:
                continue

            _interrupted = False
            if line.lower() in ("exit", "quit"):
                break

            for cmd in self._split_commands(line):
                try:
                    output = self.execute(cmd)
                except Exception as exc:
                    output = _error_panel(str(exc))
                if output:
                    from rich.table import Table
                    from rich.columns import Columns

                    if isinstance(output, (Table, Columns)):
                        self._console.print()
                    self._console.print(output)

        self._save_readline_history()

    def execute(self, line: str):
        """Execute a single command line.

        Parameters
        ----------
        line : str
            Raw command text.

        Returns
        -------
        str or rich renderable
            Command output (may be empty).
        """
        line = _SUBST_RE.sub(self._subst_inner, line)

        parsed = parse_command(line)
        if parsed is None:
            return ""

        self.session.log_command(line)
        self._append_log(line)

        result = CommandRegistry.dispatch(self.session, parsed)
        return result or ""

    @staticmethod
    def _split_commands(line: str) -> list:
        """Split a command line on semicolons, respecting quoted strings.

        Parameters
        ----------
        line : str
            Raw input potentially containing semicolons.

        Returns
        -------
        list of str
            Individual command strings.
        """
        commands = []
        current = []
        in_quote = None
        for char in line:
            if char in ('"', "'") and in_quote is None:
                in_quote = char
                current.append(char)
            elif char == in_quote:
                in_quote = None
                current.append(char)
            elif char == ";" and in_quote is None:
                part = "".join(current).strip()
                if part:
                    commands.append(part)
                current = []
            else:
                current.append(char)
        part = "".join(current).strip()
        if part:
            commands.append(part)
        return commands if commands else [line.strip()]

    def _subst_inner(self, match: re.Match) -> str:
        """Handle ``$(...)`` substitution, converting renderables to text."""
        result = self.execute(match.group(1))
        if isinstance(result, str):
            return result
        return render_to_text(result).strip()

    def execute_script(self, filepath: str) -> str:
        """Execute a script file line-by-line.

        Parameters
        ----------
        filepath : str
            Path to the script file.

        Returns
        -------
        str
            Combined output from all commands.
        """
        try:
            text = Path(filepath).read_text()
        except FileNotFoundError:
            return f"Script not found: {filepath}"
        return self.execute_script_text(text)

    def execute_script_text(self, text: str) -> str:
        """Execute script text (multiple lines) through the REPL.

        Parameters
        ----------
        text : str
            Multi-line script text.

        Returns
        -------
        str
            Combined output from all commands.
        """
        outputs = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            for cmd in self._split_commands(line):
                try:
                    output = self.execute(cmd)
                except Exception as exc:
                    output = _error_panel(str(exc))
                if output:
                    if isinstance(output, str):
                        outputs.append(output)
                    else:
                        outputs.append(render_to_text(output))
        return "\n".join(outputs)

    def _print_banner(self) -> None:
        from rich.text import Text

        try:
            from ..__version__ import __version__

            version = __version__
        except Exception:
            version = "dev"

        self._console.print()
        t = Text()
        t.append("Mosaic Shell", style="mosaic.banner.title")
        t.append(f"  v{version}", style="mosaic.muted")
        self._console.print(t)
        self._console.print(
            "Type 'help' for commands, '<command> help' for details, 'exit' to quit.",
            style="mosaic.muted",
        )
        self._console.print()

    @staticmethod
    def _build_prompt() -> str:
        """Build a readline-safe prompt string."""
        from io import StringIO

        from rich.console import Console
        from rich.text import Text
        from .theme import MOSAIC_THEME

        buf = StringIO()
        c = Console(file=buf, theme=MOSAIC_THEME, force_terminal=True, width=999)
        prompt_text = Text()
        prompt_text.append("mosaic", style="mosaic.prompt.name")
        prompt_text.append(">", style="mosaic.prompt.sep")
        prompt_text.append(" ")
        c.print(prompt_text, end="")
        raw = buf.getvalue()

        # Wrap each ANSI escape in \x01...\x02 so readline ignores their width
        parts = re.split(r"(\x1b\[[^m]*m)", raw)
        return "".join(f"\x01{p}\x02" if p.startswith("\x1b[") else p for p in parts)

    def _setup_readline(self) -> None:
        completer = _Completer(self.session)
        readline.set_completer(completer.complete)
        readline.set_completer_delims(" \t\n")

        if "libedit" in (readline.__doc__ or ""):
            readline.parse_and_bind("bind ^I rl_complete")
        else:
            readline.parse_and_bind("tab: complete")

        if _HISTORY_PATH.exists():
            try:
                readline.read_history_file(str(_HISTORY_PATH))
            except Exception:
                pass

    def _save_readline_history(self) -> None:
        try:
            readline.write_history_file(str(_HISTORY_PATH))
        except Exception:
            pass

    def _append_log(self, line: str) -> None:
        if self._log_file is None:
            return
        try:
            with open(self._log_file, "a") as fh:
                fh.write(line + "\n")
        except Exception:
            pass
