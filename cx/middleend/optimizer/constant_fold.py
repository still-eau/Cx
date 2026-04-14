"""Constant folding and constant propagation pass.

Walks the AST and replaces every expression that can be evaluated
at compile time with the corresponding literal node.

Examples
--------
  2 + 3          →  IntLit(5)
  true && false  →  BoolLit(False)
  !false         →  BoolLit(True)
  "a" + ...      →  (string concat is NOT folded — left for the runtime)
"""

from __future__ import annotations

import operator
from typing import Any, Callable, Dict, List, Optional, Tuple

from ...frontend.ast import *
from ...utils.source_loc import UNKNOWN_LOC


# ---------------------------------------------------------------------------
# Arithmetic operators on Python values
# ---------------------------------------------------------------------------

_INT_OPS: Dict[str, Callable[[Any, Any], Any]] = {
    "+":   operator.add,
    "-":   operator.sub,
    "*":   operator.mul,
    "/":   operator.floordiv,
    "%":   operator.mod,
    "**":  operator.pow,
    "&":   operator.and_,
    "|":   operator.or_,
    "^":   operator.xor,
    "<<":  operator.lshift,
    ">>":  operator.rshift,
    ">>>": lambda a, b: (a % (1 << 64)) >> b,
}

_CMP_OPS: Dict[str, Callable[[Any, Any], bool]] = {
    "==": operator.eq,
    "!=": operator.ne,
    "<":  operator.lt,
    ">":  operator.gt,
    "<=": operator.le,
    ">=": operator.ge,
}

_LOG_OPS: Dict[str, Callable[[Any, Any], bool]] = {
    "&&": lambda a, b: a and b,
    "||": lambda a, b: a or b,
}


# ---------------------------------------------------------------------------
# Constant value extraction
# ---------------------------------------------------------------------------

def _const_value(expr: Expr) -> Tuple[bool, Any]:
    """Return (is_const, python_value) for the expression."""
    if isinstance(expr, IntLit):
        return True, expr.value
    if isinstance(expr, FloatLit):
        return True, expr.value
    if isinstance(expr, BoolLit):
        return True, expr.value
    if isinstance(expr, CharLit):
        return True, ord(expr.value) if expr.value else 0
    if isinstance(expr, NullLit):
        return True, None
    return False, None


def _make_lit(loc: Loc, val: Any, orig: Expr) -> Optional[Expr]:
    """Wrap a Python value back into an AST literal."""
    if isinstance(val, bool):
        return BoolLit(loc, val)
    if isinstance(orig, (IntLit, CharLit)) and isinstance(val, int):
        return IntLit(loc, str(val), val)
    if isinstance(orig, FloatLit) and isinstance(val, float):
        return FloatLit(loc, str(val), val)
    return None


# ---------------------------------------------------------------------------
# Pass entry point
# ---------------------------------------------------------------------------

def fold_constants(program: Program) -> int:
    """Fold constant expressions in-place.  Returns the number of folds."""
    folder = _ConstFolder()
    for item in program.items:
        folder.visit_item(item)
    return folder.count


# ---------------------------------------------------------------------------
# Visitor
# ---------------------------------------------------------------------------

class _ConstFolder:
    def __init__(self) -> None:
        self.count = 0

    # -- items ---------------------------------------------------------------

    def visit_item(self, item: Item) -> None:
        if isinstance(item, FuncDecl) and item.body:
            self.visit_block(item.body)
        elif isinstance(item, ObjDecl):
            for m in item.methods:
                if m.body:
                    self.visit_block(m.body)
        elif isinstance(item, VarDecl):
            for i, init in enumerate(item.inits):
                if init is not None:
                    item.inits[i] = self.fold(init)

    # -- statements ----------------------------------------------------------

    def visit_block(self, block: Block) -> None:
        for i, stmt in enumerate(block.stmts):
            block.stmts[i] = self.visit_stmt(stmt)

    def visit_stmt(self, stmt: Stmt) -> Stmt:
        if isinstance(stmt, ExprStmt):
            stmt.expr = self.fold(stmt.expr)
        elif isinstance(stmt, VarDeclStmt):
            for i, init in enumerate(stmt.decl.inits):
                if init is not None:
                    stmt.decl.inits[i] = self.fold(init)
        elif isinstance(stmt, AssignStmt):
            stmt.value = self.fold(stmt.value)
        elif isinstance(stmt, ReturnStmt) and stmt.value:
            stmt.value = self.fold(stmt.value)
        elif isinstance(stmt, IfStmt):
            stmt.cond = self.fold(stmt.cond)
            self.visit_block(stmt.then_body)
            for j, (c, b) in enumerate(stmt.elif_branches):
                stmt.elif_branches[j] = (self.fold(c), b)
                self.visit_block(b)
            if stmt.else_body:
                self.visit_block(stmt.else_body)
        elif isinstance(stmt, ForCondStmt):
            stmt.cond = self.fold(stmt.cond)
            self.visit_block(stmt.body)
        elif isinstance(stmt, (ForRangeStmt, ForInStmt, ForInfiniteStmt)):
            self.visit_block(stmt.body)
        elif isinstance(stmt, MatchStmt):
            stmt.subject = self.fold(stmt.subject)
            for arm in stmt.arms:
                self.visit_block(arm.body)
        elif isinstance(stmt, Block):
            self.visit_block(stmt)
        elif isinstance(stmt, UnsafeBlock):
            self.visit_block(stmt.body)
        elif isinstance(stmt, FailStmt) and stmt.value:
            stmt.value = self.fold(stmt.value)
        return stmt

    # -- expressions ---------------------------------------------------------

    def fold(self, expr: Expr) -> Expr:
        """Attempt constant folding; return the (potentially new) expression."""
        if isinstance(expr, BinaryExpr):
            return self._fold_binary(expr)
        if isinstance(expr, UnaryExpr):
            return self._fold_unary(expr)
        if isinstance(expr, IfExpr):
            return self._fold_if_expr(expr)
        # Recurse into sub-expressions even if we can't fold the outer
        if isinstance(expr, CallExpr):
            expr.args = [self.fold(a) for a in expr.args]
        if isinstance(expr, MethodCallExpr):
            expr.receiver = self.fold(expr.receiver)
            expr.args     = [self.fold(a) for a in expr.args]
        if isinstance(expr, CastExpr):
            expr.value = self.fold(expr.value)
        return expr

    def _fold_binary(self, expr: BinaryExpr) -> Expr:
        expr.left  = self.fold(expr.left)
        expr.right = self.fold(expr.right)
        lc, lv = _const_value(expr.left)
        rc, rv = _const_value(expr.right)
        if not (lc and rc):
            return expr

        loc = expr.loc
        op  = expr.op

        # Integer / float arithmetic
        if op in _INT_OPS:
            try:
                result = _INT_OPS[op](lv, rv)
                lit    = _make_lit(loc, result, expr.left)
                if lit:
                    lit.resolved_type = expr.resolved_type
                    self.count += 1
                    return lit
            except (ZeroDivisionError, OverflowError, TypeError):
                pass

        # Comparison
        if op in _CMP_OPS:
            try:
                result = _CMP_OPS[op](lv, rv)
                self.count += 1
                return BoolLit(loc, bool(result))
            except TypeError:
                pass

        # Logical (short-circuit already determined at compile time)
        if op in _LOG_OPS:
            result = _LOG_OPS[op](lv, rv)
            self.count += 1
            return BoolLit(loc, bool(result))

        return expr

    def _fold_unary(self, expr: UnaryExpr) -> Expr:
        expr.operand = self.fold(expr.operand)
        ok, val = _const_value(expr.operand)
        if not ok:
            return expr
        loc = expr.loc
        try:
            if expr.op == "-":
                lit = _make_lit(loc, -val, expr.operand)
                if lit:
                    self.count += 1
                    return lit
            elif expr.op == "!" and isinstance(val, bool):
                self.count += 1
                return BoolLit(loc, not val)
            elif expr.op == "~" and isinstance(val, int):
                lit = _make_lit(loc, ~val, expr.operand)
                if lit:
                    self.count += 1
                    return lit
        except TypeError:
            pass
        return expr

    def _fold_if_expr(self, expr: IfExpr) -> Expr:
        expr.cond = self.fold(expr.cond)
        ok, val   = _const_value(expr.cond)
        if ok and isinstance(val, bool):
            self.count += 1
            return expr.then_expr if val else expr.else_expr
        return expr
