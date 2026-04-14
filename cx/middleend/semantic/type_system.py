"""Cx type representation used by the semantic layer and backend.

CxType is a discriminated hierarchy mirroring the AST TypeNode hierarchy
but fully resolved (no inference markers, all generics instantiated).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing      import Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..semantic.symbol_table import Symbol


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

@dataclass(eq=False)
class CxType:
    """Base class for all resolved Cx types."""

    def is_numeric(self) -> bool:
        return False

    def is_integer(self) -> bool:
        return False

    def is_float(self) -> bool:
        return False

    def is_pointer(self) -> bool:
        return False

    def is_optional(self) -> bool:
        return False

    def is_void(self) -> bool:
        return False

    def is_bool(self) -> bool:
        return False

    def compatible_with(self, other: "CxType") -> bool:
        return self is other or self == other

    def __repr__(self) -> str:
        return self.__class__.__name__


# ---------------------------------------------------------------------------
# Primitive types
# ---------------------------------------------------------------------------

@dataclass(eq=True)
class PrimCxType(CxType):
    name:    str
    bits:    int    # 1, 8, 16, 32, 64
    signed:  bool
    is_fp:   bool   # float / double

    def is_numeric(self) -> bool:
        return True

    def is_integer(self) -> bool:
        return not self.is_fp

    def is_float(self) -> bool:
        return self.is_fp

    def is_bool(self) -> bool:
        return self.name == "bool"

    def is_void(self) -> bool:
        return self.name == "void"

    def compatible_with(self, other: CxType) -> bool:
        if isinstance(other, PrimCxType):
            if self.name == other.name:
                return True
            # allow implicit widening: int → int[long], flt → dbl, etc.
            if self.is_integer() and other.is_integer() and other.bits >= self.bits:
                return True
        return False

    def __repr__(self) -> str:
        return self.name


# -- predefined singletons (module-level constants) --------------------------

VOID  = PrimCxType("void",  0,  False, False)
BOOL  = PrimCxType("bool",  1,  False, False)
CHAR  = PrimCxType("char",  8,  False, False)
I16   = PrimCxType("int",   16, True,  False)     # int[short]
I32   = PrimCxType("int",   32, True,  False)     # int
I64   = PrimCxType("int",   64, True,  False)     # int[long]
U32   = PrimCxType("uint",  32, False, False)
U64   = PrimCxType("uint",  64, False, False)
FLT   = PrimCxType("flt",   32, True,  True)
DBL   = PrimCxType("dbl",   64, True,  True)
STR   = PrimCxType("str",   64, False, False)     # fat-ptr {i8*, i64}
NULL  = PrimCxType("null",  0,  False, False)


def prim_from_name(name: str) -> Optional[PrimCxType]:
    return _PRIMS.get(name)


_PRIMS: Dict[str, PrimCxType] = {
    "void": VOID, "bool": BOOL, "char": CHAR,
    "int":  I32,  "uint": U32,  "flt": FLT,
    "dbl":  DBL,  "str":  STR,  "null": NULL,
}


# ---------------------------------------------------------------------------
# Pointer / optional
# ---------------------------------------------------------------------------

@dataclass(eq=True)
class PtrCxType(CxType):
    pointee: CxType

    def is_pointer(self) -> bool:
        return True

    def __repr__(self) -> str:
        return f"{self.pointee!r}[ptr]"


@dataclass(eq=True)
class OptCxType(CxType):
    inner: CxType

    def is_optional(self) -> bool:
        return True

    def __repr__(self) -> str:
        return f"{self.inner!r}[opt]"


# ---------------------------------------------------------------------------
# Composite types
# ---------------------------------------------------------------------------

@dataclass(eq=False)
class ObjCxType(CxType):
    name:        str
    fields:      List[Tuple[str, CxType]]
    methods:     Dict[str, "FuncCxType"] = field(default_factory=dict)
    type_params: List[str]               = field(default_factory=list)

    def __repr__(self) -> str:
        return self.name


@dataclass(eq=False)
class EnumCxType(CxType):
    name:        str
    variants:    List[Tuple[str, List[Tuple[str, CxType]]]]
    type_params: List[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return self.name


@dataclass(eq=True)
class ArrCxType(CxType):
    elem:     CxType
    capacity: int

    def __repr__(self) -> str:
        return f"arr::{self.elem!r}|{self.capacity}|"


@dataclass(eq=True)
class FuncCxType(CxType):
    params:    List[CxType]
    ret:       CxType
    fail_type: Optional[CxType] = None

    def __repr__(self) -> str:
        params = ", ".join(repr(p) for p in self.params)
        tail   = f" | fail {self.fail_type!r}" if self.fail_type else ""
        return f"func({params}) -> {self.ret!r}{tail}"


@dataclass(eq=True)
class TupleCxType(CxType):
    elems: List[CxType]

    def __repr__(self) -> str:
        return "(" + ", ".join(repr(e) for e in self.elems) + ")"


@dataclass(eq=False)
class AliasCxType(CxType):
    name:    str
    aliased: CxType

    def __repr__(self) -> str:
        return self.name


@dataclass(eq=False)
class GenericCxType(CxType):
    """Uninstantiated generic type (e.g. T in a generic function)."""
    name: str

    def __repr__(self) -> str:
        return f"<{self.name}>"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def apply_modifiers(base: CxType, mods: List[str]) -> CxType:
    """Apply [long], [short], [ptr], [opt] modifiers to a base type."""
    ty = base
    for mod in mods:
        if mod == "ptr":
            ty = PtrCxType(ty)
        elif mod == "opt":
            ty = OptCxType(ty)
        elif mod == "long":
            if isinstance(ty, PrimCxType) and ty.name == "int":
                ty = I64
            elif isinstance(ty, PrimCxType) and ty.name == "uint":
                ty = U64
        elif mod == "short":
            if isinstance(ty, PrimCxType) and ty.name == "int":
                ty = I16
    return ty


def types_equal(a: CxType, b: CxType) -> bool:
    return a == b or (type(a) is type(b) and repr(a) == repr(b))


def is_nullable(t: CxType) -> bool:
    return isinstance(t, OptCxType) or isinstance(t, PtrCxType) or t is NULL
