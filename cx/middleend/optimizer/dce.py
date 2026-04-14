"""Dead-Code Elimination pass.

Removes statements that can never be reached after a terminator
(return / break / continue / fail) inside the same block.

Also prunes:
  - if-branches whose condition is a compile-time boolean constant
  - for-loops with a constant false condition
"""

from __future__ import annotations

from typing import List, Set

from ...frontend.ast import *


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def eliminate_dead_code(program: Program) -> int:
    """Remove unreachable statements in-place.  Returns total removal count."""
    dce = _DCE()
    for item in program.items:
        dce.visit_item(item)
    return dce.count


# ---------------------------------------------------------------------------
# Visitor
# ---------------------------------------------------------------------------

class _DCE:
    def __init__(self) -> None:
        self.count = 0

    # -- items ---------------------------------------------------------------

    def visit_item(self, item: Item) -> None:
        if isinstance(item, FuncDecl) and item.body:
            item.body.stmts = self._prune_block(item.body.stmts)
        elif isinstance(item, ObjDecl):
            for m in item.methods:
                if m.body:
                    m.body.stmts = self._prune_block(m.body.stmts)

    # -- block pruning -------------------------------------------------------

    def _prune_block(self, stmts: List[Stmt]) -> List[Stmt]:
        out: List[Stmt] = []
        for stmt in stmts:
            pruned = self._prune_stmt(stmt)
            if pruned is not None:
                out.append(pruned)
            # Terminator → everything after is dead
            if self._is_terminator(stmt):
                dead = len(stmts) - len(out)
                if dead > 0:
                    self.count += dead
                break
        return out

    def _prune_stmt(self, stmt: Stmt) -> Optional[Stmt]:
        """Return the (potentially modified) statement, or None to drop it."""

        # Constant-true if: keep then-branch, drop else
        if isinstance(stmt, IfStmt):
            return self._prune_if(stmt)

        # Blocks
        if isinstance(stmt, Block):
            stmt.stmts = self._prune_block(stmt.stmts)
            return stmt if stmt.stmts else None

        if isinstance(stmt, UnsafeBlock):
            stmt.body.stmts = self._prune_block(stmt.body.stmts)
            return stmt

        if isinstance(stmt, ForCondStmt):
            # for false { … }  → remove entirely
            if isinstance(stmt.cond, BoolLit) and not stmt.cond.value:
                self.count += 1
                return None
            stmt.body.stmts = self._prune_block(stmt.body.stmts)
            return stmt

        if isinstance(stmt, (ForRangeStmt, ForInStmt, ForInfiniteStmt)):
            stmt.body.stmts = self._prune_block(stmt.body.stmts)
            return stmt

        if isinstance(stmt, MatchStmt):
            for arm in stmt.arms:
                arm.body.stmts = self._prune_block(arm.body.stmts)
            return stmt

        return stmt

    def _prune_if(self, stmt: IfStmt) -> Optional[Stmt]:
        """Evaluate constant conditions and collapse if/else branches."""
        if isinstance(stmt.cond, BoolLit):
            if stmt.cond.value:
                # always true: keep then-branch
                stmt.then_body.stmts = self._prune_block(stmt.then_body.stmts)
                self.count += 1
                return stmt.then_body
            else:
                # always false: keep else-branch (or drop if none)
                self.count += 1
                if stmt.else_body:
                    stmt.else_body.stmts = self._prune_block(stmt.else_body.stmts)
                    return stmt.else_body
                return None

        stmt.then_body.stmts = self._prune_block(stmt.then_body.stmts)
        if stmt.else_body:
            stmt.else_body.stmts = self._prune_block(stmt.else_body.stmts)
        return stmt

    @staticmethod
    def _is_terminator(stmt: Stmt) -> bool:
        return isinstance(stmt, (ReturnStmt, BreakStmt, ContinueStmt, FailStmt))
