"""
Interactive REPL for the Mosaic scripting interface.

Copyright (c) 2026 European Molecular Biology Laboratory

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
    """Tab-completion for command names and target references."""

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

        return []


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

            try:
                output = self.execute(line)
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

        Raises
        ------
        ValueError
            If the command text has a syntax error.
        Exception
            If the command handler raises.
        """
        line = _SUBST_RE.sub(self._subst_inner, line)

        parsed = parse_command(line)
        if parsed is None:
            return ""

        self.session.log_command(line)
        self._append_log(line)

        result = CommandRegistry.dispatch(self.session, parsed)
        return result or ""

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

            try:
                output = self.execute(line)
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
        t.append(f"  v{version}", style="mosaic.banner.version")
        self._console.print(t)
        self._console.print(
            "Type 'help' for commands, 'exit' to quit.",
            style="mosaic.muted",
        )
        self._console.print()

        self._console.print(
            "This is an experimental Mosaic feature and might have rough edges.\n",
            style="mosaic.warning",
        )

    @staticmethod
    def _build_prompt() -> str:
        """Build a readline-safe ANSI-colored prompt string.

        Wraps escape sequences in ``\\x01``/``\\x02`` so readline
        correctly computes the visible prompt width.
        """
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
