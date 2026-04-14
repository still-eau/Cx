"""Compilation-phase timing logger with Rich output."""

from __future__ import annotations

import time
from typing import Optional

from rich.console import Console

_console = Console(stderr=True)

_PHASE_COLORS: dict[str, str] = {
    "lex":     "bold blue",
    "parse":   "bold cyan",
    "check":   "bold magenta",
    "opt":     "bold yellow",
    "codegen": "bold green",
    "link":    "bold white",
}


class CompileLogger:
    """Phase-level timing logger.  Activated only in verbose mode."""

    __slots__ = ("_verbose", "_t0")

    def __init__(self, verbose: bool = False) -> None:
        self._verbose = verbose
        self._t0 = time.perf_counter()

    # ------------------------------------------------------------------

    def phase(self, name: str, detail: str = "") -> None:
        if not self._verbose:
            return
        elapsed = (time.perf_counter() - self._t0) * 1_000
        color   = _PHASE_COLORS.get(name, "white")
        suffix  = f"  [dim]{detail}[/dim]" if detail else ""
        _console.print(f"  [{color}]{name:>7}[/{color}]{suffix}  [dim]{elapsed:.1f}ms[/dim]")

    def done(self, output: str) -> None:
        elapsed = (time.perf_counter() - self._t0) * 1_000
        _console.print(
            f"[bold green]  Compiled[/bold green] [white]→[/white] {output}"
            f"  [dim]({elapsed:.0f}ms)[/dim]"
        )

    def info(self, msg: str) -> None:
        if self._verbose:
            _console.print(f"[dim]{msg}[/dim]")

    def warn(self, msg: str) -> None:
        _console.print(f"[bold yellow]warning[/bold yellow]: {msg}")
