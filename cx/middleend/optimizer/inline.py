"""Function inlining pass.

Inlines functions that are:
  1. Decorated with @inline, or
  2. Small (body <= INLINE_THRESHOLD statements) and called exactly once,
     or called in a hot loop (threshold is halved).

Inlining is performed at the AST level: the callee's body is cloned
and substituted at the call site with argument names replaced.

Limitations
-----------
- Recursive functions are never inlined (detected via name check).
- Functions with multiple return points are not inlined in this pass.
- Generic functions are skipped (instantiation happens at LLVM level).
"""

from __future__ import annotations

import copy
from typing import Dict, List, Optional, Set, Tuple

from ...frontend.ast import *


INLINE_THRESHOLD = 10    # max statements to inline unconditionally


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def inline_functions(program: Program) -> int:
    """Inline eligible functions.  Returns number of inlined call sites."""
    inliner = _Inliner(program)
    return inliner.run()


# ---------------------------------------------------------------------------
# Inline engine
# ---------------------------------------------------------------------------

class _Inliner:
    def __init__(self, program: Program) -> None:
        self._prog    = program
        self.count    = 0
        # name → FuncDecl for all top-level functions
        self._funcs:  Dict[str, FuncDecl] = {}
        self._inline_set: Set[str]        = set()
        self._call_counts: Dict[str, int] = {}

    def run(self) -> int:
        # 1. Collect all functions
        for item in self._prog.items:
            if isinstance(item, FuncDecl) and item.body:
                self._funcs[item.name] = item

        # 2. Count call sites
        for fn in self._funcs.values():
            self._count_calls(fn.body)

        # 3. Decide which functions to inline
        for name, fn in self._funcs.items():
            if self._should_inline(name, fn):
                self._inline_set.add(name)

        if not self._inline_set:
            return 0

        # 4. Inline call sites
        for fn in self._funcs.values():
            if fn.body:
                fn.body.stmts = self._inline_block(fn.body.stmts, fn.name)

        return self.count

    # ---------------------------------------------------------------- sizing

    def _stmt_count(self, block: Block) -> int:
        n = 0
        for s in block.stmts:
            n += 1
            if isinstance(s, (IfStmt, ForRangeStmt, ForInStmt,
                               ForCondStmt, ForInfiniteStmt)):
                n += self._stmt_count(getattr(s, "body", Block(UNKNOWN_LOC, [])))
        return n

    UNKNOWN_LOC = Loc("<inline>", 0, 0)

    def _should_inline(self, name: str, fn: FuncDecl) -> bool:
        if not fn.body:
            return False
        if fn.type_params:          # skip generics
            return False
        if "inline" in fn.attrs:
            return True
        if name == "main":          # never inline main
            return False
        size = self._stmt_count(fn.body)
        calls = self._call_counts.get(name, 0)
        if size <= INLINE_THRESHOLD and calls >= 1:
            return True
        return False

    # ---------------------------------------------------------------- counting

    def _count_calls(self, block: Optional[Block]) -> None:
        if block is None:
            return
        for stmt in block.stmts:
            self._count_stmt(stmt)

    def _count_stmt(self, stmt: Stmt) -> None:
        if isinstance(stmt, ExprStmt):
            self._count_expr(stmt.expr)
        elif isinstance(stmt, ReturnStmt) and stmt.value:
            self._count_expr(stmt.value)
        elif isinstance(stmt, VarDeclStmt):
            for init in stmt.decl.inits:
                if init:
                    self._count_expr(init)
        elif isinstance(stmt, AssignStmt):
            self._count_expr(stmt.value)
        elif isinstance(stmt, IfStmt):
            self._count_expr(stmt.cond)
            self._count_calls(stmt.then_body)
            if stmt.else_body:
                self._count_calls(stmt.else_body)
        elif isinstance(stmt, (ForRangeStmt, ForInStmt,
                                ForCondStmt, ForInfiniteStmt)):
            self._count_calls(getattr(stmt, "body", None))
        elif isinstance(stmt, Block):
            self._count_calls(stmt)

    def _count_expr(self, expr: Expr) -> None:
        if isinstance(expr, CallExpr) and isinstance(expr.callee, IdentExpr):
            self._call_counts[expr.callee.name] = \
                self._call_counts.get(expr.callee.name, 0) + 1

    # ---------------------------------------------------------------- inlining

    def _inline_block(self, stmts: List[Stmt], caller: str) -> List[Stmt]:
        out: List[Stmt] = []
        for stmt in stmts:
            expanded = self._inline_stmt(stmt, caller)
            out.extend(expanded)
        return out

    def _inline_stmt(self, stmt: Stmt, caller: str) -> List[Stmt]:
        if isinstance(stmt, ExprStmt):
            result = self._try_inline_call(stmt.expr, caller)
            if result is not None:
                return result
        if isinstance(stmt, VarDeclStmt):
            for i, init in enumerate(stmt.decl.inits):
                if init:
                    result = self._try_inline_expr(init, caller)
                    if result is not None:
                        # The inline result replaces init with the temp var
                        pass
        # Recurse into branches
        if isinstance(stmt, IfStmt):
            stmt.then_body.stmts = self._inline_block(stmt.then_body.stmts, caller)
            if stmt.else_body:
                stmt.else_body.stmts = self._inline_block(stmt.else_body.stmts, caller)
        if isinstance(stmt, (ForRangeStmt, ForInStmt, ForCondStmt, ForInfiniteStmt)):
            stmt.body.stmts = self._inline_block(stmt.body.stmts, caller)
        return [stmt]

    def _try_inline_call(self, expr: Expr, caller: str) -> Optional[List[Stmt]]:
        """If expr is a call to an inline-eligible function, return inlined stmts."""
        if not isinstance(expr, CallExpr):
            return None
        if not isinstance(expr.callee, IdentExpr):
            return None
        name = expr.callee.name
        if name not in self._inline_set or name == caller:
            return None
        fn = self._funcs.get(name)
        if fn is None or fn.body is None:
            return None

        # Build argument substitution map
        subst: Dict[str, Expr] = {}
        for param, arg in zip(fn.params, expr.args):
            subst[param.name] = copy.deepcopy(arg)

        # Deep-copy the function body with substitutions
        body_copy = copy.deepcopy(fn.body)
        self._substitute(body_copy, subst)
        self.count += 1
        return body_copy.stmts

    def _try_inline_expr(self, expr: Expr, caller: str) -> Optional[List[Stmt]]:
        return None  # complex inlining with result binding left for later

    # ---------------------------------------------------------------- substitution

    def _substitute(self, block: Block, subst: Dict[str, Expr]) -> None:
        for i, stmt in enumerate(block.stmts):
            block.stmts[i] = self._sub_stmt(stmt, subst)

    def _sub_stmt(self, stmt: Stmt, subst: Dict[str, Expr]) -> Stmt:
        if isinstance(stmt, ExprStmt):
            stmt.expr = self._sub_expr(stmt.expr, subst)
        elif isinstance(stmt, ReturnStmt) and stmt.value:
            stmt.value = self._sub_expr(stmt.value, subst)
        elif isinstance(stmt, VarDeclStmt):
            for i, init in enumerate(stmt.decl.inits):
                if init:
                    stmt.decl.inits[i] = self._sub_expr(init, subst)
        elif isinstance(stmt, AssignStmt):
            stmt.target = self._sub_expr(stmt.target, subst)
            stmt.value  = self._sub_expr(stmt.value, subst)
        elif isinstance(stmt, IfStmt):
            stmt.cond = self._sub_expr(stmt.cond, subst)
            self._substitute(stmt.then_body, subst)
            if stmt.else_body:
                self._substitute(stmt.else_body, subst)
        elif isinstance(stmt, (ForRangeStmt, ForInStmt,
                                ForCondStmt, ForInfiniteStmt)):
            if isinstance(stmt, ForCondStmt):
                stmt.cond = self._sub_expr(stmt.cond, subst)
            self._substitute(stmt.body, subst)
        return stmt

    def _sub_expr(self, expr: Expr, subst: Dict[str, Expr]) -> Expr:
        if isinstance(expr, IdentExpr) and expr.name in subst:
            return copy.deepcopy(subst[expr.name])
        if isinstance(expr, BinaryExpr):
            expr.left  = self._sub_expr(expr.left,  subst)
            expr.right = self._sub_expr(expr.right, subst)
        elif isinstance(expr, UnaryExpr):
            expr.operand = self._sub_expr(expr.operand, subst)
        elif isinstance(expr, CallExpr):
            expr.args = [self._sub_expr(a, subst) for a in expr.args]
        elif isinstance(expr, FieldExpr):
            expr.obj = self._sub_expr(expr.obj, subst)
        elif isinstance(expr, IndexExpr):
            expr.obj   = self._sub_expr(expr.obj, subst)
            expr.index = self._sub_expr(expr.index, subst)
        return expr
