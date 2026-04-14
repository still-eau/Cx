"""Compiler-wide configuration and compile options."""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class OptLevel(Enum):
    O0 = 0   # No optimisation
    O1 = 1   # Basic (mem2reg, instcombine)
    O2 = 2   # Standard  (default)
    O3 = 3   # Aggressive (loop unroll, vectorise, full inline)
    Os = 4   # Optimise for size


class EmitKind(Enum):
    EXE = "exe"   # linked executable  (default)
    OBJ = "obj"   # object file
    ASM = "asm"   # assembly
    IR  = "ir"    # LLVM IR text (.ll)
    BC  = "bc"    # LLVM bitcode (.bc)


def _default_target() -> str:
    m = platform.machine().lower()
    if m in ("amd64", "x86_64"):
        return "x86_64"
    if m in ("arm64", "aarch64"):
        return "aarch64"
    return "x86_64"


@dataclass
class CompileOptions:
    """All user-visible options that drive a single compilation."""

    source_file: str        = ""
    output:      str        = ""          # "" → derived from source_file
    opt_level:   OptLevel   = OptLevel.O2
    emit:        EmitKind   = EmitKind.EXE
    target:      str        = field(default_factory=_default_target)
    verbose:     bool       = False
    debug_info:  bool       = False
    run_after:   bool       = False       # `cx run`

    # @when() defines available at compile time
    defines: dict[str, str] = field(default_factory=lambda: {
        "debug":    "false",
        "optimize": "speed",
        "target":   _default_target(),
        "arch":     _default_target(),
    })

    # ------------------------------------------------------------------ helpers

    @property
    def llvm_opt(self) -> int:
        """LLVM numeric optimisation level (0-3)."""
        mapping = {
            OptLevel.O0: 0,
            OptLevel.O1: 1,
            OptLevel.O2: 2,
            OptLevel.O3: 3,
            OptLevel.Os: 2,  # size uses level-2 + size flag
        }
        return mapping[self.opt_level]

    @property
    def is_size_opt(self) -> bool:
        return self.opt_level is OptLevel.Os

    def derived_output(self, ext: str = "") -> str:
        """Return output path, deriving it from source_file if not set."""
        if self.output:
            return self.output
        base = self.source_file
        for suffix in (".cx",):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        return base + ext

    @classmethod
    def from_opt_string(cls, s: str) -> "OptLevel":
        mapping = {lv.name: lv for lv in OptLevel}
        mapping.update({str(lv.value): lv for lv in OptLevel
                        if isinstance(lv.value, int)})
        return mapping.get(s.upper(), OptLevel.O2)
