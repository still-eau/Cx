"""Source location tracking — attached to every AST node and diagnostic."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Loc:
    """Immutable source position (file, 1-based line, 1-based column)."""

    file: str
    line: int
    col:  int

    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.col}"

    def __repr__(self) -> str:
        return f"Loc({self.file!r}, {self.line}, {self.col})"


# Sentinel used when a location is not available (e.g. built-in types).
UNKNOWN_LOC: Loc = Loc("<builtin>", 0, 0)
