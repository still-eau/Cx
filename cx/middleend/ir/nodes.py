"""IR node definitions — High-level Intermediate Representation (HIR).

The HIR is a simple 3-address SSA form produced from the type-annotated AST.
It is platform-independent and sits between the AST and the LLVM backend.

Design goals
------------
- Each instruction has explicit operand names (strings, "" = unnamed)
- Type information from the type-checker is carried on each value
- Control-flow is explicit (basic blocks + terminators)
- Allows clean passes: constant folding, DCE, inlining
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing      import Dict, List, Optional, Any


# ---------------------------------------------------------------------------
# Values (SSA names)
# ---------------------------------------------------------------------------

@dataclass(eq=True)
class IRValue:
    name: str        # SSA register name: "t0", "t1", …
    type: Any        # CxType

    def __repr__(self) -> str:
        return f"%{self.name}"


UNDEF = IRValue("undef", None)


# ---------------------------------------------------------------------------
# Instructions (non-terminator)
# ---------------------------------------------------------------------------

@dataclass
class IRInstr:
    """Base for all non-terminator HIR instructions."""
    dest: Optional[str] = None    # SSA register written to (None = no output)


@dataclass
class IRAlloca(IRInstr):
    """dest = alloca type (stack allocation)."""
    cx_type: Any = None
    name: Optional[str] = None
    dest: str

    def __repr__(self) -> str:
        return f"{self.dest} = alloca {self.cx_type}"


@dataclass
class IRLoad(IRInstr):
    """dest = load ptr."""
    ptr: IRValue = field(default_factory=lambda: UNDEF)


@dataclass
class IRStore(IRInstr):
    """store value → ptr."""
    value: IRValue = field(default_factory=lambda: UNDEF)
    ptr:   IRValue = field(default_factory=lambda: UNDEF)


@dataclass
class IRBinOp(IRInstr):
    """dest = op left, right."""
    op:    str    = ""
    left:  IRValue = field(default_factory=lambda: UNDEF)
    right: IRValue = field(default_factory=lambda: UNDEF)
    type:  Any     = None


@dataclass
class IRUnOp(IRInstr):
    """dest = op operand."""
    op:      str    = ""
    operand: IRValue = field(default_factory=lambda: UNDEF)
    type:    Any     = None


@dataclass
class IRCall(IRInstr):
    """dest = call callee(args…)."""
    callee: str        = ""
    args:   List[IRValue] = field(default_factory=list)
    ret_ty: Any           = None


@dataclass
class IRGEP(IRInstr):
    """dest = getelementptr ptr, indices…  (field/index access)."""
    ptr:     IRValue    = field(default_factory=lambda: UNDEF)
    indices: List[Any]  = field(default_factory=list)  # List[int | IRValue]
    elem_ty: Any        = None


@dataclass
class IRCast(IRInstr):
    """dest = (cast_kind) value to type."""
    kind:    str    = "bitcast"    # "trunc" | "zext" | "sext" | "fptoui" | etc.
    value:   IRValue = field(default_factory=lambda: UNDEF)
    to_type: Any     = None


@dataclass
class IRConst(IRInstr):
    """dest = constant value (folded)."""
    value: Any = None
    type:  Any = None

@dataclass
class IRBinary(IRInstr):
    op: str = ""
    left: IRValue = field(default_factory=lambda: UNDEF)
    right: IRValue = field(default_factory=lambda: UNDEF)
    type: Any = None

    def __repr__(self) -> str:
        return f"{self.dest} = {self.op} {self.left}, {self.right}"


@dataclass
class IRPhi(IRInstr):
    """dest = phi [val, block] …     (SSA join)."""
    edges: List[tuple] = field(default_factory=list)   # [(IRValue, str), …]
    type:  Any         = None

@dataclass 
class IRIntLit(IRInstr):
    value: int = 0
    type: Any = None
    name: Optional[str] = None

    def __repr__(self) -> str:
        return f"{self.value}"

# ---------------------------------------------------------------------------
# Terminators (exactly one per basic block)
# ---------------------------------------------------------------------------

@dataclass
class IRTerminator:
    pass


@dataclass
class IRRet(IRTerminator):
    value: Optional[IRValue] = None


@dataclass
class IRBr(IRTerminator):
    """Unconditional branch."""
    target: str = ""


@dataclass
class IRCondBr(IRTerminator):
    cond:       IRValue = field(default_factory=lambda: UNDEF)
    true_label:  str    = ""
    false_label: str    = ""


@dataclass
class IRSwitch(IRTerminator):
    """switch val, default, [(const, label), …]"""
    value:   IRValue       = field(default_factory=lambda: UNDEF)
    default: str           = ""
    cases:   List[tuple]   = field(default_factory=list)   # [(int, label)]


@dataclass
class IRUnreachable(IRTerminator):
    pass


# ---------------------------------------------------------------------------
# Basic block
# ---------------------------------------------------------------------------

@dataclass
class IRBlock:
    label:      str
    instrs:     List[IRInstr]      = field(default_factory=list)
    terminator: Optional[IRTerminator] = None

    def emit(self, instr: IRInstr) -> None:
        self.instrs.append(instr)

    def terminate(self, term: IRTerminator) -> None:
        self.terminator = term


# ---------------------------------------------------------------------------
# Function
# ---------------------------------------------------------------------------

@dataclass
class IRFunction:
    name:       str
    params:     List[tuple]         # [(name, CxType), …]
    ret_type:   Any                 # CxType
    blocks:     List[IRBlock]       = field(default_factory=list)
    is_extern:  bool                = False
    extern_sym: Optional[str]       = None
    attrs:      List[str]           = field(default_factory=list)

    def add_block(self, label: str) -> IRBlock:
        b = IRBlock(label)
        self.blocks.append(b)
        return b

    @property
    def entry(self) -> Optional[IRBlock]:
        return self.blocks[0] if self.blocks else None


# ---------------------------------------------------------------------------
# Module
# ---------------------------------------------------------------------------

@dataclass
class IRModule:
    name:      str
    functions: List[IRFunction]   = field(default_factory=list)
    globals:   List[tuple]        = field(default_factory=list)  # (name, CxType, value)
    externs:   List[IRFunction]   = field(default_factory=list)

    def add_function(self, fn: IRFunction) -> None:
        self.functions.append(fn)

    def add_extern(self, fn: IRFunction) -> None:
        self.externs.append(fn)