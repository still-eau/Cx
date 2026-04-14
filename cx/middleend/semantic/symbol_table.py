"""Symbol table with lexical scoping.

Each ``Scope`` is a dict of name→Symbol plus a reference to its parent.
``SymbolTable`` provides push/pop and a single look-up that walks the chain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum        import Enum, auto
from typing      import Dict, List, Optional, Any

from ...utils.source_loc import Loc


# ---------------------------------------------------------------------------
# Symbol kinds
# ---------------------------------------------------------------------------

class SymKind(Enum):
    VAR      = auto()   # set variable
    CONST    = auto()   # const
    FUNC     = auto()   # function / method
    PARAM    = auto()   # function parameter
    TYPE     = auto()   # obj / enum / alias / primitive
    MODULE   = auto()   # module name
    ENUM_VAR = auto()   # enum variant


@dataclass
class Symbol:
    name:     str
    kind:     SymKind
    loc:      Loc
    # Resolved Cx type (set by type-checker, initially None)
    cx_type:  Any        = field(default=None, repr=False)
    # For SymKind.FUNC: the FuncDecl AST node
    # For SymKind.TYPE: the ObjDecl / EnumDecl / AliasDecl node
    ast_node: Any        = field(default=None, repr=False)
    is_pub:   bool       = False
    is_mut:   bool       = True    # False for const / param

    def __repr__(self) -> str:
        return f"Symbol({self.kind.name}, {self.name!r})"


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------

class Scope:
    """A single lexical scope frame."""

    __slots__ = ("_syms", "parent", "label")

    def __init__(
        self,
        parent: Optional["Scope"] = None,
        label:  str               = "",
    ) -> None:
        self._syms: Dict[str, Symbol] = {}
        self.parent = parent
        self.label  = label

    def define(self, sym: Symbol) -> Optional[Symbol]:
        """Define *sym* in this scope.  Returns the old symbol if it shadowed one."""
        old = self._syms.get(sym.name)
        self._syms[sym.name] = sym
        return old

    def resolve_local(self, name: str) -> Optional[Symbol]:
        return self._syms.get(name)

    def resolve(self, name: str) -> Optional[Symbol]:
        """Walk up the scope chain."""
        scope: Optional[Scope] = self
        while scope is not None:
            sym = scope._syms.get(name)
            if sym is not None:
                return sym
            scope = scope.parent
        return None

    def symbols(self) -> List[Symbol]:
        return list(self._syms.values())


# ---------------------------------------------------------------------------
# SymbolTable
# ---------------------------------------------------------------------------

class SymbolTable:
    """Manages the scope stack for the current compilation unit."""

    __slots__ = ("_root", "_current")

    def __init__(self) -> None:
        # The global / module scope
        self._root    = Scope(label="<global>")
        self._current = self._root
        self._populate_builtins()

    # ------------------------------------------------------------------ scope

    def push(self, label: str = "") -> Scope:
        """Open a new child scope and return it."""
        child         = Scope(parent=self._current, label=label)
        self._current = child
        return child

    def pop(self) -> Scope:
        """Close the current scope and return it."""
        old           = self._current
        if self._current.parent is not None:
            self._current = self._current.parent
        return old

    @property
    def current(self) -> Scope:
        return self._current

    # ------------------------------------------------------------------ define / resolve

    def define(self, sym: Symbol) -> Optional[Symbol]:
        return self._current.define(sym)

    def resolve(self, name: str) -> Optional[Symbol]:
        return self._current.resolve(name)

    def resolve_local(self, name: str) -> Optional[Symbol]:
        return self._current.resolve_local(name)

    # ------------------------------------------------------------------ builtins

    _BUILTIN_LOC = Loc("<builtin>", 0, 0)

    def _builtin(self, name: str, kind: SymKind = SymKind.TYPE) -> Symbol:
        return Symbol(name, kind, self._BUILTIN_LOC)

    def _populate_builtins(self) -> None:
        primitives = [
            "int", "uint", "flt", "dbl", "char", "str", "bool", "void", "null",
        ]
        for prim in primitives:
            self._root.define(self._builtin(prim, SymKind.TYPE))

        # Built-in functions
        builtins_funcs = [
            "alloc", "free", "sizeof", "alignof", "memcpy", "memset",
            "cast", "transmute", "print",
        ]
        for fn in builtins_funcs:
            self._root.define(self._builtin(fn, SymKind.FUNC))
