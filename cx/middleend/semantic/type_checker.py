"""Type-checker and semantic analyser for the Cx language.

Performs a two-pass walk over the AST:
  Pass 1 — collect all top-level declarations into the symbol table
            (so forward references inside the same module work).
  Pass 2 — visit every node, resolve names, infer and verify types,
            and annotate every Expr.resolved_type.

Errors are reported via ErrorReporter (non-fatal where possible).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing      import List, Optional, Dict, Any, Iterator
import os

from ...frontend.ast import *
from ...utils.source_loc import Loc
from ...utils.errors     import ErrorReporter
from .symbol_table       import SymbolTable, Symbol, SymKind
from .type_system        import (
    CxType, PrimCxType, PtrCxType, OptCxType, ObjCxType, EnumCxType,
    ArrCxType, FuncCxType, TupleCxType, AliasCxType, GenericCxType,
    VOID, BOOL, CHAR, I32, I64, U32, U64, FLT, DBL, STR, NULL,
    prim_from_name, apply_modifiers, types_equal, is_nullable,
)


class TypeChecker:
    """Semantic analysis visitor."""

    def __init__(self, reporter: ErrorReporter) -> None:
        self._rep   = reporter
        self._tbl   = SymbolTable()
        # stack of current function's return/fail types
        self._ret_stack:  List[Optional[CxType]] = []
        self._fail_stack: List[Optional[CxType]] = []
        # currently resolved obj/enum types by name
        self._types: Dict[str, CxType] = {}

    # ================================================================
    # Public entry point
    # ================================================================

    def check(self, program: Program) -> None:
        self._collect_top_level(program)
        for item in program.items:
            self._check_item(item)

    # ================================================================
    # Pass 1: collect declarations
    # ================================================================

    def _collect_top_level(self, program: Program) -> None:
        for item in program.items:
            self._declare_item(item)

    def _declare_item(self, item: Item) -> None:
        if isinstance(item, FuncDecl):
            sym = Symbol(item.name, SymKind.FUNC, item.loc,
                         ast_node=item, is_pub=item.is_pub)
            self._tbl.define(sym)
        elif isinstance(item, ObjDecl):
            cy = ObjCxType(item.name, [], {}, item.type_params)
            self._types[item.name] = cy
            sym = Symbol(item.name, SymKind.TYPE, item.loc,
                         cx_type=cy, ast_node=item, is_pub=item.is_pub)
            self._tbl.define(sym)
        elif isinstance(item, EnumDecl):
            cy = EnumCxType(item.name, [], item.type_params)
            self._types[item.name] = cy
            sym = Symbol(item.name, SymKind.TYPE, item.loc,
                         cx_type=cy, ast_node=item, is_pub=item.is_pub)
            self._tbl.define(sym)
            # Declare variants
            for v in item.variants:
                self._tbl.define(Symbol(
                    f"{item.name}::{v.name}", SymKind.ENUM_VAR, v.loc,
                    cx_type=cy, ast_node=v, is_pub=item.is_pub,
                ))
        elif isinstance(item, AliasDecl):
            cy = AliasCxType(item.name, VOID)   # filled in pass 2
            sym = Symbol(item.name, SymKind.TYPE, item.loc,
                         cx_type=cy, ast_node=item, is_pub=item.is_pub)
            self._tbl.define(sym)
        elif isinstance(item, VarDecl):
            for name in item.names:
                kind = SymKind.CONST if item.qualifier == "const" else SymKind.VAR
                sym  = Symbol(name, kind, item.loc, is_pub=item.is_pub,
                              is_mut=(item.qualifier == "set"))
                self._tbl.define(sym)
        elif isinstance(item, ImportDirective):
            # Verify if module exists physically (simple heuristics for now)
            # Remove any trailing "()" from selective imports or paths
            clean_path = item.full_path.split('{')[0].strip('/').replace('()', '')
            
            # Paths to check (relative current dir, or as .cx file)
            path_file = f"{clean_path}.cx"
            path_dir = clean_path
            
            if not os.path.exists(path_file) and not os.path.exists(path_dir):
                self._rep.error(
                    f"module '{item.full_path}' not found",
                    item.loc,
                    hint=f"Checked '{path_file}' and '{path_dir}'. Stdlibs might not be implemented yet."
                )

    # ================================================================
    # Pass 2: item checking
    # ================================================================

    def _check_item(self, item: Item) -> None:
        if isinstance(item, FuncDecl):
            self._check_func(item)
        elif isinstance(item, ObjDecl):
            self._check_obj(item)
        elif isinstance(item, EnumDecl):
            self._check_enum(item)
        elif isinstance(item, AliasDecl):
            self._check_alias(item)
        elif isinstance(item, VarDecl):
            self._check_var_decl(item, top_level=True)
        elif isinstance(item, ArrDecl):
            self._check_arr_decl(item)

    # ---------------------------------------------------------------- func

    def _check_func(self, fn: FuncDecl) -> None:
        with self._scope(fn.name):
            # register generic type params
            for tp in fn.type_params:
                self._tbl.define(Symbol(tp, SymKind.TYPE, fn.loc,
                                        cx_type=GenericCxType(tp)))
            # params
            for p in fn.params:
                ptype = self._resolve_type_node(p.type_node)
                sym   = Symbol(p.name, SymKind.PARAM, p.loc,
                               cx_type=ptype, is_mut=(p.qualifier == "set"))
                self._tbl.define(sym)

            ret_type  = self._resolve_type_node(fn.ret_type)  if fn.ret_type  else VOID
            fail_type = self._resolve_type_node(fn.fail_type) if fn.fail_type else None

            self._ret_stack.append(ret_type)
            self._fail_stack.append(fail_type)
            if fn.body is not None:
                self._check_block(fn.body)
            self._ret_stack.pop()
            self._fail_stack.pop()

    # ---------------------------------------------------------------- obj

    def _check_obj(self, obj: ObjDecl) -> None:
        cy = self._types.get(obj.name)
        assert isinstance(cy, ObjCxType)
        fields: List[tuple] = []
        with self._scope(obj.name):
            for tp in obj.type_params:
                self._tbl.define(Symbol(tp, SymKind.TYPE, obj.loc,
                                        cx_type=GenericCxType(tp)))
            for fd in obj.fields:
                ftype = self._resolve_type_node(fd.type_node)
                fields.append((fd.name, ftype))
                self._tbl.define(Symbol(fd.name, SymKind.VAR, fd.loc,
                                        cx_type=ftype))
            for method in obj.methods:
                self._check_func(method)
        cy.fields = fields

    # ---------------------------------------------------------------- enum

    def _check_enum(self, en: EnumDecl) -> None:
        cy = self._types.get(en.name)
        assert isinstance(cy, EnumCxType)
        variants = []
        for v in en.variants:
            vfields = []
            for fd in v.fields:
                ftype = self._resolve_type_node(fd.type_node)
                vfields.append((fd.name, ftype))
            variants.append((v.name, vfields))
        cy.variants = variants

    # ---------------------------------------------------------------- alias

    def _check_alias(self, al: AliasDecl) -> None:
        cy = self._types.get(al.name)
        assert isinstance(cy, AliasCxType)
        cy.aliased = self._resolve_type_node(al.type_node)
        sym = self._tbl.resolve(al.name)
        if sym:
            sym.cx_type = cy

    # ---------------------------------------------------------------- var / arr

    def _check_var_decl(self, decl: VarDecl, top_level: bool = False) -> None:
        ty = self._resolve_type_node(decl.type_node)
        for name, init in zip(decl.names, decl.inits):
            sym = self._tbl.resolve_local(name)
            if sym is None:
                kind = SymKind.CONST if decl.qualifier == "const" else SymKind.VAR
                sym  = Symbol(name, kind, decl.loc, cx_type=ty,
                              is_mut=(decl.qualifier == "set"))
                self._tbl.define(sym)
            sym.cx_type = ty
            if init is not None:
                ity = self._check_expr(init)
                if not self._assignable(ty, ity):
                    self._rep.error(
                        f"cannot assign {ity!r} to {ty!r}",
                        decl.loc,
                        hint=f"expected '{ty!r}', got '{ity!r}'",
                    )

    def _check_arr_decl(self, decl: ArrDecl) -> None:
        ety = self._resolve_type_node(decl.elem_type)
        for elem in decl.elements:
            self._check_expr(elem)
        arr_ty = ArrCxType(ety, decl.capacity)
        sym    = Symbol(decl.name, SymKind.VAR, decl.loc, cx_type=arr_ty)
        self._tbl.define(sym)

    # ================================================================
    # Statement checking
    # ================================================================

    def _check_block(self, block: Block) -> None:
        with self._scope():
            for stmt in block.stmts:
                self._check_stmt(stmt)

    def _check_stmt(self, stmt: Stmt) -> None:
        if isinstance(stmt, VarDeclStmt):
            self._check_var_decl(stmt.decl)
        elif isinstance(stmt, ArrDeclStmt):
            self._check_arr_decl(stmt.decl)
        elif isinstance(stmt, ExprStmt):
            self._check_expr(stmt.expr)
        elif isinstance(stmt, AssignStmt):
            self._check_assign(stmt)
        elif isinstance(stmt, IncrDecrStmt):
            self._check_expr(stmt.target)
        elif isinstance(stmt, ReturnStmt):
            self._check_return(stmt)
        elif isinstance(stmt, FailStmt):
            self._check_fail(stmt)
        elif isinstance(stmt, IfStmt):
            self._check_if(stmt)
        elif isinstance(stmt, (ForRangeStmt, ForInStmt, ForCondStmt, ForInfiniteStmt)):
            self._check_for(stmt)
        elif isinstance(stmt, MatchStmt):
            self._check_match_stmt(stmt)
        elif isinstance(stmt, Block):
            self._check_block(stmt)
        elif isinstance(stmt, UnsafeBlock):
            self._check_block(stmt.body)
        elif isinstance(stmt, WhenBlock):
            self._check_expr(stmt.condition)
            self._check_block(stmt.body)
        elif isinstance(stmt, (BreakStmt, ContinueStmt)):
            pass

    def _check_assign(self, stmt: AssignStmt) -> None:
        lty = self._check_expr(stmt.target)
        rty = self._check_expr(stmt.value)
        if not self._assignable(lty, rty):
            self._rep.error(
                f"type mismatch in assignment: {lty!r} vs {rty!r}",
                stmt.loc,
            )

    def _check_return(self, stmt: ReturnStmt) -> None:
        expected = self._ret_stack[-1] if self._ret_stack else VOID
        if stmt.value is None:
            if expected is not VOID:
                self._rep.error("missing return value", stmt.loc)
        else:
            got = self._check_expr(stmt.value)
            if not self._assignable(expected, got):
                self._rep.error(
                    f"return type mismatch: expected {expected!r}, got {got!r}",
                    stmt.loc,
                )

    def _check_fail(self, stmt: FailStmt) -> None:
        fail_expected = self._fail_stack[-1] if self._fail_stack else None
        if fail_expected is None:
            self._rep.error(
                "'fail' used in a function not declared with '| fail T'",
                stmt.loc,
                hint="add '| fail T' to the function return type",
            )
        if stmt.value is not None:
            got = self._check_expr(stmt.value)
            if fail_expected and not self._assignable(fail_expected, got):
                self._rep.error(
                    f"fail type mismatch: expected {fail_expected!r}, got {got!r}",
                    stmt.loc,
                )

    def _check_if(self, stmt: IfStmt) -> None:
        ct = self._check_expr(stmt.cond)
        if not types_equal(ct, BOOL):
            self._rep.error(f"condition must be bool, got {ct!r}", stmt.loc)
        self._check_block(stmt.then_body)
        for cond, body in stmt.elif_branches:
            self._check_expr(cond)
            self._check_block(body)
        if stmt.else_body:
            self._check_block(stmt.else_body)

    def _check_for(self, stmt: Stmt) -> None:
        if isinstance(stmt, ForRangeStmt):
            self._check_expr(stmt.range_expr)
            with self._scope():
                self._tbl.define(Symbol(stmt.var, SymKind.VAR, stmt.loc, cx_type=I32))
                self._check_block(stmt.body)
        elif isinstance(stmt, ForInStmt):
            ity = self._check_expr(stmt.iterable)
            with self._scope():
                self._tbl.define(Symbol(stmt.item_var, SymKind.VAR, stmt.loc, cx_type=VOID))
                if stmt.idx_var:
                    self._tbl.define(Symbol(stmt.idx_var, SymKind.VAR, stmt.loc, cx_type=I32))
                self._check_block(stmt.body)
        elif isinstance(stmt, ForCondStmt):
            self._check_expr(stmt.cond)
            self._check_block(stmt.body)
        elif isinstance(stmt, ForInfiniteStmt):
            self._check_block(stmt.body)

    def _bind_pattern(self, pat: Pattern, subject_type: CxType) -> None:
        if isinstance(pat, IdentPattern):
            self._tbl.define(Symbol(pat.name, SymKind.VAR, pat.loc, cx_type=subject_type))
        elif isinstance(pat, EnumPattern):
            if isinstance(subject_type, EnumCxType):
                variant_fields = {}
                for v_name, v_fields in subject_type.variants:
                    if v_name == pat.variant_name:
                        variant_fields = {name: ty for name, ty in v_fields}
                        break
                for field_name in pat.fields:
                    fy = variant_fields.get(field_name, VOID)
                    self._tbl.define(Symbol(field_name, SymKind.VAR, pat.loc, cx_type=fy))
            else:
                for field_name in pat.fields:
                    self._tbl.define(Symbol(field_name, SymKind.VAR, pat.loc, cx_type=VOID))
        elif isinstance(pat, OrPattern):
            if pat.alternatives:
                self._bind_pattern(pat.alternatives[0], subject_type)

    def _check_match_stmt(self, stmt: MatchStmt) -> None:
        subj_ty = self._check_expr(stmt.subject)
        for arm in stmt.arms:
            with self._scope():
                self._bind_pattern(arm.pattern, subj_ty)
                if arm.guard:
                    self._check_expr(arm.guard)
                self._check_block(arm.body)

    # ================================================================
    # Expression type inference
    # ================================================================

    def _check_expr(self, expr: Expr) -> CxType:
        ty = self._infer_expr(expr)
        expr.resolved_type = ty
        return ty

    def _infer_expr(self, expr: Expr) -> CxType:  # noqa: C901
        if isinstance(expr, IntLit):
            return I32
        if isinstance(expr, FloatLit):
            return FLT
        if isinstance(expr, StringLit):
            return STR
        if isinstance(expr, CharLit):
            return CHAR
        if isinstance(expr, BoolLit):
            return BOOL
        if isinstance(expr, NullLit):
            return NULL

        if isinstance(expr, IdentExpr):
            sym = self._tbl.resolve(expr.name)
            if sym is None:
                self._rep.error(f"undefined name '{expr.name}'", expr.loc)
                return VOID
            return sym.cx_type or VOID

        if isinstance(expr, PathExpr):
            # Module::name or Enum::variant
            full = "::".join(expr.parts)
            sym  = self._tbl.resolve(full)
            if sym is None and len(expr.parts) == 2:
                sym = self._tbl.resolve(expr.parts[-1])
            if sym is None:
                self._rep.error(f"undefined path '{full}'", expr.loc)
                return VOID
            return sym.cx_type or VOID

        if isinstance(expr, BinaryExpr):
            return self._infer_binary(expr)

        if isinstance(expr, UnaryExpr):
            return self._infer_unary(expr)

        if isinstance(expr, CallExpr):
            return self._infer_call(expr)

        if isinstance(expr, MethodCallExpr):
            return self._infer_method_call(expr)

        if isinstance(expr, FieldExpr):
            return self._infer_field(expr)

        if isinstance(expr, IndexExpr):
            obj_ty = self._check_expr(expr.obj)
            self._check_expr(expr.index)
            if isinstance(obj_ty, ArrCxType):
                return obj_ty.elem
            if isinstance(obj_ty, PtrCxType):
                return obj_ty.pointee
            return VOID

        if isinstance(expr, CastExpr):
            self._check_expr(expr.value)
            return self._resolve_type_node(expr.type_node)

        if isinstance(expr, TransmuteExpr):
            self._check_expr(expr.value)
            return self._resolve_type_node(expr.type_node)

        if isinstance(expr, SizeofExpr):
            return U64

        if isinstance(expr, AlignofExpr):
            return U64

        if isinstance(expr, AllocExpr):
            elem_ty = self._resolve_type_node(expr.type_node)
            self._check_expr(expr.count)
            return PtrCxType(elem_ty)

        if isinstance(expr, FreeExpr):
            self._check_expr(expr.ptr)
            return VOID

        if isinstance(expr, MemcpyExpr):
            self._check_expr(expr.dst)
            self._check_expr(expr.src)
            self._check_expr(expr.count)
            return VOID

        if isinstance(expr, MemsetExpr):
            self._check_expr(expr.dst)
            self._check_expr(expr.val)
            self._check_expr(expr.count)
            return VOID

        if isinstance(expr, StructLiteral):
            sym = self._tbl.resolve(expr.type_name)
            for _, v in expr.fields:
                self._check_expr(v)
            if sym and isinstance(sym.cx_type, ObjCxType):
                return sym.cx_type
            return VOID

        if isinstance(expr, EnumVariantExpr):
            sym = self._tbl.resolve(expr.enum_name)
            for _, v in expr.fields:
                self._check_expr(v)
            if sym and isinstance(sym.cx_type, EnumCxType):
                return sym.cx_type
            return VOID

        if isinstance(expr, RangeExpr):
            self._check_expr(expr.start)
            self._check_expr(expr.end)
            return VOID   # range is iterable but has no single type yet

        if isinstance(expr, TupleExpr):
            etypes = [self._check_expr(e) for e in expr.elems]
            return TupleCxType(etypes)

        if isinstance(expr, IfExpr):
            self._check_expr(expr.cond)
            t1 = self._check_expr(expr.then_expr)
            t2 = self._check_expr(expr.else_expr)
            if not types_equal(t1, t2):
                self._rep.error(
                    f"if-expression branches have different types: {t1!r} vs {t2!r}",
                    expr.loc,
                )
            return t1

        if isinstance(expr, MatchExpr):
            subj_ty = self._check_expr(expr.subject)
            arm_types = []
            for a in expr.arms:
                with self._scope():
                    self._bind_pattern(a.pattern, subj_ty)
                    if a.guard:
                        self._check_expr(a.guard)
                    self._check_block(a.body)
                    if a.body.stmts and isinstance(a.body.stmts[-1], ExprStmt):
                        t = a.body.stmts[-1].expr.resolved_type or VOID
                    else:
                        t = VOID
                    arm_types.append(t)
            return arm_types[0] if arm_types else VOID

        if isinstance(expr, LambdaExpr):
            with self._scope():
                for p in expr.params:
                    self._tbl.define(Symbol(p, SymKind.PARAM, expr.loc, cx_type=VOID))
                ret = self._check_expr(expr.body)
            return FuncCxType([VOID] * len(expr.params), ret)

        if isinstance(expr, TryExpr):
            inner_ty = self._check_expr(expr.inner)
            return inner_ty

        if isinstance(expr, CatchExpr):
            inner_ty = self._check_expr(expr.inner)
            if expr.err_name:
                with self._scope():
                    self._tbl.define(Symbol(expr.err_name, SymKind.VAR,
                                            expr.loc, cx_type=VOID))
                    self._check_block(expr.handler)
            else:
                self._check_block(expr.handler)
            return inner_ty

        if isinstance(expr, NullCoalesceExpr):
            lt = self._check_expr(expr.left)
            self._check_expr(expr.right)
            return lt

        if isinstance(expr, OptChainExpr):
            ot = self._check_expr(expr.obj)
            return OptCxType(VOID)

        # Bare block (used in some contexts)
        if isinstance(expr, Block):
            self._check_block(expr)
            if expr.stmts and isinstance(expr.stmts[-1], ExprStmt):
                return expr.stmts[-1].expr.resolved_type or VOID
            return VOID

        return VOID

    # ---------------------------------------------------------------- binary

    def _infer_binary(self, expr: BinaryExpr) -> CxType:
        lt = self._check_expr(expr.left)
        rt = self._check_expr(expr.right)

        cmp_ops = {"==", "!=", "<", ">", "<=", ">="}
        log_ops = {"&&", "||"}
        bit_ops = {"&", "|", "^", "<<", ">>", ">>>"}

        if expr.op in cmp_ops or expr.op in log_ops:
            return BOOL
        if expr.op in bit_ops:
            return lt if isinstance(lt, PrimCxType) else I32
        # arithmetic: widen
        if isinstance(lt, PrimCxType) and isinstance(rt, PrimCxType):
            if lt.bits >= rt.bits:
                return lt
            return rt
        return lt

    # ---------------------------------------------------------------- unary

    def _infer_unary(self, expr: UnaryExpr) -> CxType:
        inner = self._check_expr(expr.operand)
        if expr.op == "!":
            return BOOL
        if expr.op == "~":
            return inner
        if expr.op == "&":
            return PtrCxType(inner)
        if expr.op == "*":
            if isinstance(inner, PtrCxType):
                return inner.pointee
            self._rep.error("cannot dereference non-pointer", expr.loc)
            return VOID
        return inner

    # ---------------------------------------------------------------- call

    def _infer_call(self, expr: CallExpr) -> CxType:
        for a in expr.args:
            self._check_expr(a)
        callee_ty = self._check_expr(expr.callee)
        if isinstance(callee_ty, FuncCxType):
            return callee_ty.ret
        # look up function name directly
        if isinstance(expr.callee, IdentExpr):
            sym = self._tbl.resolve(expr.callee.name)
            if sym and sym.ast_node and isinstance(sym.ast_node, FuncDecl):
                fn = sym.ast_node
                ret = self._resolve_type_node(fn.ret_type) if fn.ret_type else VOID
                return ret
        return VOID

    # ---------------------------------------------------------------- method call

    def _infer_method_call(self, expr: MethodCallExpr) -> CxType:
        recv_ty = self._check_expr(expr.receiver)
        for a in expr.args:
            self._check_expr(a)
        if isinstance(recv_ty, ObjCxType):
            method = recv_ty.methods.get(expr.method)
            if method:
                return method.ret
        return VOID

    # ---------------------------------------------------------------- field

    def _infer_field(self, expr: FieldExpr) -> CxType:
        obj_ty = self._check_expr(expr.obj)
        if isinstance(obj_ty, ObjCxType):
            for fname, ftype in obj_ty.fields:
                if fname == expr.field:
                    return ftype
        if isinstance(obj_ty, ArrCxType) and expr.field == "len":
            return U64
        return VOID

    # ================================================================
    # Type resolution (TypeNode → CxType)
    # ================================================================

    def _resolve_type_node(self, node: Optional[TypeNode]) -> CxType:
        if node is None:
            return VOID
        if isinstance(node, InferType):
            return VOID   # will be inferred later
        if isinstance(node, PrimType):
            ty = prim_from_name(node.name)
            return ty if ty is not None else VOID
        if isinstance(node, NamedType):
            sym = self._tbl.resolve(node.name)
            if sym and sym.cx_type:
                return sym.cx_type
            ty = prim_from_name(node.name)
            if ty:
                return ty
            self._rep.error(f"unknown type '{node.name}'", node.loc)
            return VOID
        if isinstance(node, GenericType):
            sym = self._tbl.resolve(node.name)
            if sym and isinstance(sym.cx_type, (ObjCxType, EnumCxType)):
                return sym.cx_type   # simplified: ignore type args for now
            return VOID
        if isinstance(node, ModifiedType):
            base = self._resolve_type_node(node.base)
            return apply_modifiers(base, node.modifiers)
        if isinstance(node, FuncType):
            params = [self._resolve_type_node(p) for p in node.params]
            ret    = self._resolve_type_node(node.ret)
            return FuncCxType(params, ret)
        if isinstance(node, TupleType):
            elems = [self._resolve_type_node(e) for e in node.elems]
            return TupleCxType(elems)
        return VOID

    # ================================================================
    # Compatibility helpers
    # ================================================================

    def _assignable(self, target: CxType, source: CxType) -> bool:
        if types_equal(target, source):
            return True
        if source is NULL and is_nullable(target):
            return True
        if isinstance(target, PrimCxType) and isinstance(source, PrimCxType):
            if target.is_numeric() and source.is_numeric():
                return True   # allow numeric conversions
        if isinstance(target, OptCxType):
            return self._assignable(target.inner, source) or source is NULL
        return False

    # ================================================================
    # Context manager for scope
    # ================================================================

    @contextmanager
    def _scope(self, label: str = "") -> Iterator[None]:
        self._tbl.push(label)
        try:
            yield
        finally:
            self._tbl.pop()
