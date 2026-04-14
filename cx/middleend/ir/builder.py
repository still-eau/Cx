"""AST to HIR (High-level IR) builder.

Performs a single-pass walk over the fully type-annotated AST and
emits 3-address SSA instructions grouped into basic blocks.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any

from ...frontend.ast import *
from .nodes import (
    IRModule, IRFunction, IRBlock, IRValue, UNDEF,
    IRAlloca, IRLoad, IRStore, IRBinOp, IRUnOp, IRCall,
    IRGEP, IRCast, IRConst, IRBr, IRCondBr, IRRet, IRUnreachable
)
from ..semantic.type_system import (
    CxType, PrimCxType, PtrCxType, OptCxType, ObjCxType, EnumCxType,
    ArrCxType, FuncCxType, TupleCxType, VOID, BOOL, I32, NULL
)


class IRBuilder:
    """Translates a typed AST into a flat HIR module."""

    def __init__(self, name: str) -> None:
        self.module = IRModule(name)
        
        # State during translation
        self._fn: Optional[IRFunction] = None
        self._block: Optional[IRBlock] = None
        
        self._reg_counter = 0
        self._label_counter = 0
        
        # Environment mapping variable names to their memory location (IRValue of ptr type)
        # We always allocate local variables on the stack (alloca) to let
        # LLVM's mem2reg pass construct proper SSA form later.
        self._env: Dict[str, IRValue] = {}
        # Environment stack for variable shadowing in nested scopes
        self._env_stack: List[Dict[str, IRValue]] = []

    # ================================================================
    # Public entry
    # ================================================================

    def build(self, program: Program) -> IRModule:
        for item in program.items:
            self._build_item(item)
        return self.module

    # ================================================================
    # Scopes and Identifiers
    # ================================================================

    def _next_reg(self, ty: Any) -> IRValue:
        name = f"t{self._reg_counter}"
        self._reg_counter += 1
        return IRValue(name, ty)

    def _next_label(self, prefix: str = "L") -> str:
        name = f"{prefix}{self._label_counter}"
        self._label_counter += 1
        return name

    def _push_scope(self) -> None:
        self._env_stack.append(self._env.copy())

    def _pop_scope(self) -> None:
        self._env = self._env_stack.pop()

    def _declare_var(self, name: str, ty: Any) -> IRValue:
        """Allocate space on the stack for a local variable."""
        assert self._block is not None
        ptr_ty = PtrCxType(ty)
        ptr = self._next_reg(ptr_ty)
        self._block.emit(IRAlloca(dest=ptr.name, cx_type=ty))
        self._env[name] = ptr
        return ptr

    def _get_var_ptr(self, name: str) -> IRValue:
        """Get the pointer to a variable's stack slot."""
        if name in self._env:
            return self._env[name]
        return UNDEF  # Global/undefined

    # ================================================================
    # Items
    # ================================================================

    def _build_item(self, item: Item) -> None:
        if isinstance(item, FuncDecl):
            self._build_func(item)
        elif isinstance(item, VarDecl):
            # Globals (simplified, usually need a global init pass)
            pass

    def _build_func(self, fn: FuncDecl) -> None:
        # Skip generic functions (must be instantiated first)
        if fn.type_params:
            return

        name = fn.extern_sym if fn.extern_sym else fn.name
        params = [(p.name, getattr(p.type_node, 'resolved_type', I32)) for p in fn.params]
        ret_type = getattr(fn.ret_type, 'resolved_type', VOID)
        
        ir_fn = IRFunction(
            name=name,
            params=params,
            ret_type=ret_type,
            is_extern=(fn.body is None),
            extern_sym=fn.extern_sym,
            attrs=fn.attrs
        )
        
        if ir_fn.is_extern:
            self.module.add_extern(ir_fn)
            return

        self.module.add_function(ir_fn)
        
        self._fn = ir_fn
        self._reg_counter = 0
        self._label_counter = 0
        self._env.clear()
        self._env_stack.clear()
        
        # Entry block
        entry = self._fn.add_block(self._next_label("entry_"))
        self._block = entry
        
        # Allocate arguments to stack slots
        for p_name, p_ty in params:
            ptr = self._declare_var(p_name, p_ty)
            # Store the argument (which arrives in a register) to the stack stack
            arg_val = IRValue(p_name, p_ty) # arguments share name with AST currently
            self._block.emit(IRStore(value=arg_val, ptr=ptr))
            
        assert fn.body is not None
        self._build_block(fn.body)
        
        # Add implicit return if block wasn't terminated
        if self._block and not isinstance(self._block.terminator, (IRRet, IRBr, IRCondBr)):
            self._block.terminate(IRRet(None))
            
        self._fn = None
        self._block = None

    # ================================================================
    # Statements
    # ================================================================

    def _build_block(self, block: Block) -> None:
        self._push_scope()
        for stmt in block.stmts:
            if self._block and isinstance(self._block.terminator, IRUnreachable):
                break  # Block already terminated
            self._build_stmt(stmt)
        self._pop_scope()

    def _build_stmt(self, stmt: Stmt) -> None:
        assert self._block is not None

        if isinstance(stmt, ExprStmt):
            self._build_expr(stmt.expr)
            
        elif isinstance(stmt, VarDeclStmt):
            ty = stmt.decl.type_node.resolved_type
            for name, init in zip(stmt.decl.names, stmt.decl.inits):
                ptr = self._declare_var(name, ty)
                if init:
                    val = self._build_expr(init)
                    self._block.emit(IRStore(value=val, ptr=ptr))
                    
        elif isinstance(stmt, AssignStmt):
            # Simplified: assign to plain identifiers
            if isinstance(stmt.target, IdentExpr):
                ptr = self._get_var_ptr(stmt.target.name)
                if ptr is not UNDEF:
                    val = self._build_expr(stmt.value)
                    if stmt.op != "=":
                        # +=, -=, etc.
                        old_val = self._next_reg(ptr.type.pointee)
                        self._block.emit(IRLoad(dest=old_val.name, ptr=ptr))
                        binop = stmt.op[:-1] # strip '='
                        new_val = self._next_reg(ptr.type.pointee)
                        self._block.emit(IRBinOp(dest=new_val.name, op=binop, left=old_val, right=val, type=ptr.type.pointee))
                        self._block.emit(IRStore(value=new_val, ptr=ptr))
                    else:
                        self._block.emit(IRStore(value=val, ptr=ptr))
            # TODO: handle assignment to fields (a.b = c) and indices (a[i] = c)
                        
        elif isinstance(stmt, ReturnStmt):
            val = self._build_expr(stmt.value) if stmt.value else None
            self._block.terminate(IRRet(val))
            # Start a new unreachable block for any subsequent code
            self._block = self._fn.add_block(self._next_label("dead_"))
            
        elif isinstance(stmt, IfStmt):
            cond_val = self._build_expr(stmt.cond)
            
            then_lbl = self._next_label("then_")
            else_lbl = self._next_label("else_")
            merge_lbl = self._next_label("endif_")
            
            has_else = (stmt.else_body is not None) or bool(stmt.elif_branches)
            false_lbl = else_lbl if has_else else merge_lbl
            
            self._block.terminate(IRCondBr(cond=cond_val, true_label=then_lbl, false_label=false_lbl))
            
            # Then
            self._block = self._fn.add_block(then_lbl)
            self._build_block(stmt.then_body)
            if isinstance(self._block.terminator, IRUnreachable):
                self._block.terminate(IRBr(merge_lbl))
                
            # TODO: elif branches
                
            # Else
            if stmt.else_body:
                self._block = self._fn.add_block(else_lbl)
                self._build_block(stmt.else_body)
                if isinstance(self._block.terminator, IRUnreachable):
                    self._block.terminate(IRBr(merge_lbl))
                    
            # Merge
            self._block = self._fn.add_block(merge_lbl)

    # ================================================================
    # Expressions
    # ================================================================

    def _build_expr(self, expr: Expr) -> IRValue:
        assert self._block is not None
        
        if isinstance(expr, IntLit):
            res = self._next_reg(expr.resolved_type)
            self._block.emit(IRConst(dest=res.name, value=expr.value, type=expr.resolved_type))
            return res
            
        if isinstance(expr, FloatLit):
            res = self._next_reg(expr.resolved_type)
            self._block.emit(IRConst(dest=res.name, value=expr.value, type=expr.resolved_type))
            return res
            
        if isinstance(expr, BoolLit):
            res = self._next_reg(BOOL)
            self._block.emit(IRConst(dest=res.name, value=1 if expr.value else 0, type=BOOL))
            return res
            
        if isinstance(expr, StringLit):
            # Strings need global linkage, handled differently
            res = self._next_reg(expr.resolved_type)
            self._block.emit(IRConst(dest=res.name, value=expr.value, type=expr.resolved_type))
            return res
            
        if isinstance(expr, IdentExpr):
            ptr = self._get_var_ptr(expr.name)
            if ptr is not UNDEF:
                res = self._next_reg(ptr.type.pointee)
                self._block.emit(IRLoad(dest=res.name, ptr=ptr))
                return res
            # Could be a function name
            return UNDEF
            
        if isinstance(expr, BinaryExpr):
            lv = self._build_expr(expr.left)
            rv = self._build_expr(expr.right)
            res = self._next_reg(expr.resolved_type)
            self._block.emit(IRBinOp(dest=res.name, op=expr.op, left=lv, right=rv, type=expr.resolved_type))
            return res
            
        if isinstance(expr, CallExpr):
            # Direct calls
            if isinstance(expr.callee, IdentExpr):
                args = [self._build_expr(a) for a in expr.args]
                res = self._next_reg(expr.resolved_type)
                self._block.emit(IRCall(dest=res.name if expr.resolved_type != VOID else None, 
                                        callee=expr.callee.name, args=args, ret_ty=expr.resolved_type))
                return res
            
        # Simplified implementations return UNDEF for unhandled nodes
        return UNDEF
