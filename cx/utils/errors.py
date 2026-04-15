"""Rustc-style error reporter for the Cx compiler.

Features
--------
- Accumulates diagnostics without aborting immediately
- Prints annotated source snippets with underlines
- Rich colour output (errors=red, warnings=yellow, hints=green)
- abort_if_errors() exits with code 1 after printing a summary
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import List, Optional

from rich.console import Console
from rich.text    import Text

from .source_loc import Loc

_console = Console(stderr=True)

# ---------------------------------------------------------------------------
# Diagnostic dataclass
# ---------------------------------------------------------------------------

@dataclass
class Diagnostic:
    level:   str              # "error" | "warning" | "note" | "hint"
    message: str
    loc:     Optional[Loc] = None
    source_cache: dict[str, str] = field(default_factory=dict)
    hint:    Optional[str] = None
    note:    Optional[str] = None

    # -- rendering -----------------------------------------------------------

    def render(self) -> None:
        _COLORS = {
            "error":   "bold red",
            "warning": "bold yellow",
            "note":    "bold cyan",
            "hint":    "bold green",
        }
        color = _COLORS.get(self.level, "bold white")
        
        # 1. Message
        _console.print(f"[{color}]{self.level}[/{color}]: [bold]{self.message}[/bold]")

        # 2. Source code snippet
        if self.loc and self.loc.file in self.source_cache and self.loc.line > 0:
            source = self.source_cache[self.loc.file]
            lines = source.splitlines()
            lineno = self.loc.line
            if 1 <= lineno <= len(lines):
                raw_line = lines[lineno - 1]
                raw_line = raw_line.replace('\t', '    ') 
                
                col = max(1, self.loc.col)
                length = getattr(self.loc, 'length', 1)
                
                gutter = f"{lineno}"
                padding = max(2, len(gutter))
                
                _console.print(f" {' ' * padding}[dim]╭─[[/dim]{self.loc.file}:{lineno}:{col}[dim]][/dim]")
                _console.print(f" {' ' * padding}[dim]│[/dim]")
                _console.print(f" [bold blue]{gutter:>{padding}}[/bold blue] [dim]│[/dim] {raw_line}")
                
                underline_pad = " " * (col - 1)
                underline_chars = "^" * length
                caption_str = f" {self.message}"
                _console.print(f" {' ' * padding}[dim]│[/dim] {underline_pad}[bold {color}]{underline_chars}{caption_str}[/bold {color}]")
                _console.print(f" {' ' * padding}[dim]╰────[/dim]")
        elif self.loc:
            _console.print(f"  [dim]--> {self.loc.file}:{self.loc.line}:{self.loc.col}[/dim]")

        # 3. Additional info
        if self.note:
            _console.print(f"  [bold cyan]=[/bold cyan] [bold]note[/bold]: {self.note}")
        if self.hint:
            _console.print(f"  [bold green]=[/bold green] [bold]hint[/bold]: {self.hint}")
        _console.print("")


# ---------------------------------------------------------------------------
# ErrorReporter
# ---------------------------------------------------------------------------

class ErrorReporter:
    """Accumulates diagnostics across multiple source files."""

    __slots__ = ("_main_file", "_sources", "_errors", "_warnings")

    def __init__(self, main_file: str, source: Optional[str] = None) -> None:
        self._main_file = main_file
        self._sources: dict[str, str] = {}
        if source:
            self._sources[main_file] = source
        self._errors:   List[Diagnostic] = []
        self._warnings: List[Diagnostic] = []

    def add_source(self, filename: str, content: str) -> None:
        """Register source code for a file to enable snippet rendering."""
        self._sources[filename] = content

    # -- emit -----------------------------------------------------------------

    def error(
        self,
        msg:  str,
        loc:  Optional[Loc] = None,
        hint: Optional[str] = None,
        note: Optional[str] = None,
    ) -> None:
        d = Diagnostic("error", msg, loc, self._sources, hint, note)
        self._errors.append(d)
        d.render()

    def warning(
        self,
        msg:  str,
        loc:  Optional[Loc] = None,
        hint: Optional[str] = None,
    ) -> None:
        d = Diagnostic("warning", msg, loc, self._source, hint)
        self._warnings.append(d)
        d.render()

    def note(self, msg: str, loc: Optional[Loc] = None) -> None:
        Diagnostic("note", msg, loc, self._source).render()

    def hint(self, msg: str) -> None:
        Diagnostic("hint", msg).render()

    # -- queries --------------------------------------------------------------

    @property
    def has_errors(self) -> bool:
        return bool(self._errors)

    @property
    def error_count(self) -> int:
        return len(self._errors)

    @property
    def warning_count(self) -> int:
        return len(self._warnings)

    def abort_if_errors(self) -> None:
        """Print summary and exit(1) if any errors were recorded."""
        if not self._errors:
            return
        n = self.error_count
        w = self.warning_count
        w_part = f", {w} warning(s)" if w else ""
        _console.print(
            f"\n[bold red]aborting: {n} error(s){w_part} in "
            f"[underline]{self._main_file}[/underline][/bold red]"
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Internal compiler errors
# ---------------------------------------------------------------------------

class CxError(Exception):
    """Unrecoverable internal compiler (ICE) or user-facing error."""

    def __init__(self, msg: str, loc: Optional[Loc] = None) -> None:
        super().__init__(msg)
        self.loc = loc
