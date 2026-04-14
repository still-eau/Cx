"""Optimizer pass manager — orchestrates AST-level optimisation passes.

Passes are applied in the order they are registered.  Each pass receives
the full Program AST (annotated by the type-checker) and may mutate it
in-place.
"""

from __future__ import annotations

import time
from enum  import Enum, auto
from typing import Callable, List, Optional

from ...frontend.ast import Program
from ...utils.logger import CompileLogger


# ---------------------------------------------------------------------------
# Pass protocol
# ---------------------------------------------------------------------------

PassFn = Callable[[Program], int]   # returns number of changes made


class PassInfo:
    __slots__ = ("name", "fn")

    def __init__(self, name: str, fn: PassFn) -> None:
        self.name = name
        self.fn   = fn


# ---------------------------------------------------------------------------
# Pass manager
# ---------------------------------------------------------------------------

class PassManager:
    """Runs registered optimisation passes until saturation or max-iter."""

    def __init__(
        self,
        logger:   Optional[CompileLogger] = None,
        max_iter: int                     = 8,
    ) -> None:
        self._passes:   List[PassInfo]         = []
        self._logger    = logger or CompileLogger()
        self._max_iter  = max_iter

    def add(self, name: str, fn: PassFn) -> "PassManager":
        self._passes.append(PassInfo(name, fn))
        return self

    def run(self, program: Program) -> int:
        """Run all passes until no changes or max_iter reached.
        Returns total change count."""
        total = 0
        for iteration in range(self._max_iter):
            changed = 0
            for p in self._passes:
                n = p.fn(program)
                if n:
                    self._logger.info(f"  {p.name}: {n} change(s)")
                    changed += n
            total += changed
            if changed == 0:
                break
        self._logger.phase("opt", f"{total} total change(s)")
        return total


# ---------------------------------------------------------------------------
# Convenience: build a default pass pipeline for a given opt level
# ---------------------------------------------------------------------------

def build_pipeline(opt_level: int, logger: Optional[CompileLogger] = None) -> PassManager:
    """Return a pass manager configured for the given LLVM opt level (0-3)."""
    from .constant_fold import fold_constants
    from .dce           import eliminate_dead_code
    from .inline        import inline_functions

    pm = PassManager(logger=logger)

    if opt_level == 0:
        return pm   # O0: no AST passes

    pm.add("constant-fold",  fold_constants)
    pm.add("dce",            eliminate_dead_code)

    if opt_level >= 2:
        pm.add("inline",     inline_functions)

    return pm
