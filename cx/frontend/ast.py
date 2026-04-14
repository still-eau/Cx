"""Cx Abstract Syntax Tree — all node types.

Every node carries a ``loc: Loc`` field for precise error messages.
Expressions additionally carry a ``resolved_type`` field (filled by the
type-checker) so that the backend never has to re-infer types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing      import Any, List, Optional, Tuple

from ..utils.source_loc import Loc, UNKNOWN_LOC


# ============================================================================
# Base
# ============================================================================

def _loc() -> Loc:
    return UNKNOWN_LOC


@dataclass
class Node:
    loc: Loc = field(default_factory=_loc, compare=False, repr=False)


# ============================================================================
# ── Types ──────────────────────────────────────────────────────────────────
# ============================================================================

@dataclass
class TypeNode(Node):
    """Base for all type-expression nodes."""


@dataclass
class InferType(TypeNode):
    """'_' — the compiler infers the concrete type."""


@dataclass
class PrimType(TypeNode):
    """int | uint | flt | dbl | char | str | bool | void"""
    name: str


@dataclass
class NamedType(TypeNode):
    """An unqualified user-defined type: Player, Header …"""
    name: str


@dataclass
class GenericType(TypeNode):
    """Node<T>, Pair<A, B>, Option<int> …"""
    name: str
    args: List[TypeNode]


@dataclass
class ModifiedType(TypeNode):
    """base[long], base[ptr], base[ptr][opt] …"""
    base:      TypeNode
    modifiers: List[str]   # ordered list: "long" | "short" | "ptr" | "opt"


@dataclass
class FuncType(TypeNode):
    """func(T1, T2) -> R"""
    params:  List[TypeNode]
    ret:     TypeNode


@dataclass
class TupleType(TypeNode):
    """(T1, T2, …)  — used for multi-return"""
    elems: List[TypeNode]


# ============================================================================
# ── Module-level items ──────────────────────────────────────────────────────
# ============================================================================

@dataclass
class ModuleDecl(Node):
    name: str


@dataclass
class ImportDirective(Node):
    """@import:path  or  @import:path as alias  or  @import:path/{a(), B}"""
    path:      str                       # "std/io"
    alias:     Optional[str] = None      # as io
    selective: List[str]     = field(default_factory=list)   # ["print()", "File"]


# ============================================================================
# ── Declarations (top-level items) ──────────────────────────────────────────
# ============================================================================

@dataclass
class Item(Node):
    is_pub: bool = False


@dataclass
class ParamDecl(Node):
    qualifier: str              # "set" | "const"
    type_node: TypeNode
    name:      str
    default:   Optional[Expr] = None


@dataclass
class WhereClause(Node):
    type_param: str
    constraint: str             # "Numeric" | "Eq" | "Ord"


@dataclass
class FieldDecl(Node):
    qualifier: str              # "set" | "const"
    type_node: TypeNode
    name:      str
    default:   Optional[Expr] = None
    is_pub:    bool            = False


@dataclass
class EnumVariant(Node):
    name:   str
    fields: List[FieldDecl]     # empty → unit variant


@dataclass
class FuncDecl(Item):
    name:          str
    type_params:   List[str]               # <T, U>
    params:        List[ParamDecl]
    ret_type:      Optional[TypeNode]      # None → void
    fail_type:     Optional[TypeNode]      # | fail T
    body:          Optional[Block]         # None for @extern stubs
    attrs:         List[str]  = field(default_factory=list)
    extern_sym:    Optional[str] = None
    where_clauses: List[WhereClause] = field(default_factory=list)


@dataclass
class ObjDecl(Item):
    name:        str
    type_params: List[str]
    fields:      List[FieldDecl]
    methods:     List[FuncDecl]


@dataclass
class EnumDecl(Item):
    name:        str
    type_params: List[str]
    variants:    List[EnumVariant]


@dataclass
class AliasDecl(Item):
    name:      str
    type_node: TypeNode


@dataclass
class VarDecl(Item):
    """set::T name = expr;  or  const::T name = expr;"""
    qualifier: str            # "set" | "const"
    type_node: TypeNode
    names:     List[str]
    inits:     List[Optional[Expr]]


@dataclass
class ArrDecl(Item):
    """arr::T|N| name = (v1, v2, …);"""
    elem_type: TypeNode
    capacity:  int
    name:      str
    elements:  List[Expr]


# ============================================================================
# ── Patterns (for match) ────────────────────────────────────────────────────
# ============================================================================

@dataclass
class Pattern(Node):
    pass


@dataclass
class WildcardPattern(Pattern):
    """_"""


@dataclass
class LiteralPattern(Pattern):
    value: Expr


@dataclass
class IdentPattern(Pattern):
    """Bare name binding (n in  n if n >= 100)."""
    name: str


@dataclass
class EnumPattern(Pattern):
    """Result::Ok { value }  or  Direction::North"""
    enum_name:    str
    variant_name: str
    fields:       List[str]    # field names to bind (empty for unit variants)


@dataclass
class OrPattern(Pattern):
    """1 | 2"""
    alternatives: List[Pattern]


# ============================================================================
# ── Statements ──────────────────────────────────────────────────────────────
# ============================================================================

@dataclass
class Stmt(Node):
    pass


@dataclass
class Block(Stmt):
    stmts: List[Stmt]


@dataclass
class ExprStmt(Stmt):
    expr: Expr


@dataclass
class VarDeclStmt(Stmt):
    decl: VarDecl


@dataclass
class ArrDeclStmt(Stmt):
    decl: ArrDecl


@dataclass
class AssignStmt(Stmt):
    target: Expr
    op:     str    # "=" | "+=" | "-=" | "*=" | "/=" | "%=" | "**=" | "&=" | "|=" | "^=" | "<<=" | ">>="
    value:  Expr


@dataclass
class IncrDecrStmt(Stmt):
    target: Expr
    op:     str    # "++" | "--"


@dataclass
class ReturnStmt(Stmt):
    value: Optional[Expr] = None


@dataclass
class BreakStmt(Stmt):
    label: Optional[str] = None


@dataclass
class ContinueStmt(Stmt):
    label: Optional[str] = None


@dataclass
class FailStmt(Stmt):
    value: Optional[Expr] = None


@dataclass
class IfStmt(Stmt):
    cond:          Expr
    then_body:     Block
    elif_branches: List[Tuple[Expr, Block]] = field(default_factory=list)
    else_body:     Optional[Block]          = None


@dataclass
class MatchArm(Node):
    pattern: Pattern
    guard:   Optional[Expr]
    body:    Block


@dataclass
class MatchStmt(Stmt):
    subject: Expr
    arms:    List[MatchArm]


@dataclass
class ForRangeStmt(Stmt):
    """for i in 0..9  or  for i in 0..<10"""
    var:        str
    range_expr: RangeExpr
    body:       Block
    label:      Optional[str] = None


@dataclass
class ForInStmt(Stmt):
    """for item in col  or  for i, item in col"""
    idx_var:  Optional[str]
    item_var: str
    iterable: Expr
    body:     Block
    label:    Optional[str] = None


@dataclass
class ForCondStmt(Stmt):
    """for cond { body }"""
    cond:  Expr
    body:  Block
    label: Optional[str] = None


@dataclass
class ForInfiniteStmt(Stmt):
    """for { body }"""
    body:  Block
    label: Optional[str] = None


@dataclass
class UnsafeBlock(Stmt):
    body: Block


@dataclass
class WhenBlock(Stmt):
    """@when(cond) { … }"""
    condition: Expr
    body:      Block


# ============================================================================
# ── Expressions ─────────────────────────────────────────────────────────────
# ============================================================================

@dataclass
class Expr(Node):
    # Filled by the type-checker; ignored by the parser.
    resolved_type: Any = field(default=None, compare=False, repr=False)


# -- Literals ----------------------------------------------------------------

@dataclass
class IntLit(Expr):
    raw:   str    # original source text (e.g. "0xFF_AB")
    value: int


@dataclass
class FloatLit(Expr):
    raw:   str
    value: float


@dataclass
class StringLit(Expr):
    value: str


@dataclass
class CharLit(Expr):
    value: str


@dataclass
class BoolLit(Expr):
    value: bool


@dataclass
class NullLit(Expr):
    pass


# -- Identifiers and paths ---------------------------------------------------

@dataclass
class IdentExpr(Expr):
    name: str


@dataclass
class PathExpr(Expr):
    """Module::symbol or Enum::Variant — a sequence of at least two names."""
    parts: List[str]


# -- Operations --------------------------------------------------------------

@dataclass
class BinaryExpr(Expr):
    op:    str
    left:  Expr
    right: Expr


@dataclass
class UnaryExpr(Expr):
    op:      str    # "-" | "!" | "~" | "*" (deref) | "&" (addr-of)
    operand: Expr


@dataclass
class CallExpr(Expr):
    callee:    Expr
    type_args: List[TypeNode]
    args:      List[Expr]


@dataclass
class MethodCallExpr(Expr):
    receiver:  Expr
    method:    str
    type_args: List[TypeNode]
    args:      List[Expr]


@dataclass
class IndexExpr(Expr):
    obj:   Expr
    index: Expr


@dataclass
class FieldExpr(Expr):
    obj:   Expr
    field: str


@dataclass
class OptChainExpr(Expr):
    """expr?.field — short-circuits to null if expr is null."""
    obj:   Expr
    field: str


@dataclass
class NullCoalesceExpr(Expr):
    """left ?? right"""
    left:  Expr
    right: Expr


# -- Memory / intrinsics -----------------------------------------------------

@dataclass
class CastExpr(Expr):
    type_node: TypeNode
    value:     Expr


@dataclass
class TransmuteExpr(Expr):
    type_node: TypeNode
    value:     Expr


@dataclass
class SizeofExpr(Expr):
    type_node: TypeNode


@dataclass
class AlignofExpr(Expr):
    type_node: TypeNode


@dataclass
class AllocExpr(Expr):
    type_node: TypeNode
    count:     Expr


@dataclass
class FreeExpr(Expr):
    ptr: Expr


@dataclass
class MemcpyExpr(Expr):
    dst:   Expr
    src:   Expr
    count: Expr


@dataclass
class MemsetExpr(Expr):
    dst:   Expr
    val:   Expr
    count: Expr


# -- Composites --------------------------------------------------------------

@dataclass
class StructLiteral(Expr):
    """TypeName { field = value, … }"""
    type_name: str                       # "Player", "Node<int>", …
    fields:    List[Tuple[str, Expr]]


@dataclass
class EnumVariantExpr(Expr):
    """Enum::Variant  or  Enum::Variant { field = value, … }"""
    enum_name:    str
    variant_name: str
    fields:       List[Tuple[str, Expr]]


@dataclass
class RangeExpr(Expr):
    start:     Expr
    end:       Expr
    inclusive: bool    # True → '..'  False → '..<'


@dataclass
class TupleExpr(Expr):
    elems: List[Expr]


# -- Control-flow expressions ------------------------------------------------

@dataclass
class IfExpr(Expr):
    """if cond { then } else { else }  used as an expression."""
    cond:      Expr
    then_expr: Expr
    else_expr: Expr


@dataclass
class MatchExpr(Expr):
    """match subject { arm, arm, … }  — expression form yields a value."""
    subject: Expr
    arms:    List[MatchArm]


@dataclass
class LambdaExpr(Expr):
    """|x, y| body_expr"""
    params: List[str]
    body:   Expr


# -- Error handling ----------------------------------------------------------

@dataclass
class TryExpr(Expr):
    """try expr — propagates failure to the caller."""
    inner: Expr


@dataclass
class CatchExpr(Expr):
    """expr catch err { handler }  or  expr catch { handler }"""
    inner:    Expr
    err_name: Optional[str]
    handler:  Block


# ============================================================================
# ── Top-level Program ───────────────────────────────────────────────────────
# ============================================================================

@dataclass
class Program(Node):
    source_file:  str
    module_decl:  Optional[ModuleDecl]
    imports:      List[ImportDirective]
    items:        List[Item]
