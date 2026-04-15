"""AST to HIR (High-level IR) builder.

Performs a single-pass walk over the fully type-annotated AST and
emits 3-address SSA instructions grouped into basic blocks.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Dict, List, Optional, Any, Iterator

from ...frontend.ast import *
from .nodes import (
    IRModule, IRFunction, IRBlock, IRValue, UNDEF,
    IRAlloca, IRLoad, IRStore, IRBinOp, IRUnOp, IRCall,
    IRGEP, IRCast, IRConst, IRBr, IRCondBr, IRRet, IRUnreachable, IRIntLit, IRBinary
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

    @contextmanager
    def _scope(self) -> Iterator[None]:
        self._push_scope()
        try:
            yield
        finally:
            self._pop_scope()

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
        elif isinstance(item, ObjDecl):
            for method in item.methods:
                self._build_func(method, parent_obj=item)
        elif isinstance(item, VarDecl):
            # Globals (simplified, usually need a global init pass)
            pass

    def _build_func(self, fn: FuncDecl, parent_obj: Optional[ObjDecl] = None) -> None:
        # Skip generic functions (must be instantiated first)
        if fn.type_params:
            return

        name = fn.extern_sym if fn.extern_sym else fn.name
        if parent_obj:
            name = f"{parent_obj.name}_{name}"

        params = [(p.name, getattr(p.type_node, 'resolved_type', I32)) for p in fn.params]
        if parent_obj:
            # Inject 'self' as first parameter with full object type (crucial for GEP)
            f_infos = []
            for fd in parent_obj.fields:
                f_ty = getattr(fd.type_node, 'resolved_type', VOID)
                f_infos.append((fd.name, f_ty))
            
            self_obj_ty = ObjCxType(parent_obj.name, f_infos)
            self_ty = PtrCxType(self_obj_ty)
            params.insert(0, ("self", self_ty))

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
        if self._block and self._block.terminator is None:
            if not self._block.instrs and "dead" in self._block.label:
                self._block.terminate(IRUnreachable())
            elif self._fn.name == "main" and isinstance(self._fn.ret_type, PrimCxType) and self._fn.ret_type.is_integer():
                # main() returns 0 by default
                zero_val = 0
                zero = self._next_reg(self._fn.ret_type)
                self._block.emit(IRConst(dest=zero.name, value=zero_val, type=self._fn.ret_type))
                self._block.terminate(IRRet(zero))
            elif self._fn.ret_type == VOID:
                self._block.terminate(IRRet(None))
            else:
                # Missing return in non-void function
                self._block.terminate(IRUnreachable())
            
        self._fn = None
        self._block = None

    # ================================================================
    # Statements
    # ================================================================

    def _build_block(self, block: Block) -> None:
        self._push_scope()
        for stmt in block.stmts:
            if self._block and self._block.terminator is not None:
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
            ptr = self._get_lvalue_ptr(stmt.target)
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
            
            self._block = self._fn.add_block(then_lbl)
            self._build_block(stmt.then_body)
            if self._block.terminator is None:
                self._block.terminate(IRBr(merge_lbl)) 

            for elif_branch in stmt.elif_branches:
                elif_cond_val = self._build_expr(elif_branch.cond)
                elif_lbl = self._next_label("elif_")
                self._block.terminate(IRCondBr(cond=elif_cond_val, true_label=elif_lbl, false_label=else_lbl))
                self._block = self._fn.add_block(elif_lbl)
                self._build_block(elif_branch.body)
                if self._block.terminator is None:
                    self._block.terminate(IRBr(merge_lbl)) 
                
            # Else
            if stmt.else_body:
                self._block = self._fn.add_block(else_lbl)
                self._build_block(stmt.else_body)
                if isinstance(self._block.terminator, IRUnreachable):
                    self._block.terminate(IRBr(merge_lbl))
                    
            # Merge
            self._block = self._fn.add_block(merge_lbl)

        elif isinstance(stmt, ForCondStmt):
            cond_lbl = self._next_label("for_cond_")
            body_lbl = self._next_label("for_body_")
            end_lbl = self._next_label("for_end_")
            
            self._block.terminate(IRBr(cond_lbl))
            
            # Condition
            self._block = self._fn.add_block(cond_lbl)
            cv = self._build_expr(stmt.cond)
            self._block.terminate(IRCondBr(cond=cv, true_label=body_lbl, false_label=end_lbl))
            
            # Body
            self._block = self._fn.add_block(body_lbl)
            self._build_block(stmt.body)
            if not isinstance(self._block.terminator, (IRRet, IRBr, IRCondBr)):
                self._block.terminate(IRBr(cond_lbl))
                
            # End
            self._block = self._fn.add_block(end_lbl)

        elif isinstance(stmt, ForRangeStmt):
            # for i in start..end
            with self._scope():
                start_v = self._build_expr(stmt.range_expr.start)
                end_v = self._build_expr(stmt.range_expr.end)
                
                # Allocation for loop variable
                i_ptr = self._declare_var(stmt.var, start_v.type)
                self._block.emit(IRStore(value=start_v, ptr=i_ptr))
                
                cond_lbl = self._next_label("range_cond_")
                body_lbl = self._next_label("range_body_")
                end_lbl = self._next_label("range_end_")
                
                self._block.terminate(IRBr(cond_lbl))
                
                # Condition
                self._block = self._fn.add_block(cond_lbl)
                curr_i = self._next_reg(start_v.type)
                self._block.emit(IRLoad(dest=curr_i.name, ptr=i_ptr))
                
                cv = self._next_reg(BOOL)
                op = "<=" if stmt.range_expr.inclusive else "<"
                self._block.emit(IRBinOp(dest=cv.name, op=op, left=curr_i, right=end_v, type=BOOL))
                self._block.terminate(IRCondBr(cond=cv, true_label=body_lbl, false_label=end_lbl))
                
                # Body
                self._block = self._fn.add_block(body_lbl)
                self._build_block(stmt.body)
                
                # Increment
                fresh_i = self._next_reg(start_v.type)
                self._block.emit(IRLoad(dest=fresh_i.name, ptr=i_ptr))
                one = self._next_reg(start_v.type)
                self._block.emit(IRConst(dest=one.name, value=1, type=start_v.type))
                next_i = self._next_reg(start_v.type)
                self._block.emit(IRBinOp(dest=next_i.name, op="+", left=fresh_i, right=one, type=start_v.type))
                self._block.emit(IRStore(value=next_i, ptr=i_ptr))
                
                if not isinstance(self._block.terminator, (IRRet, IRBr, IRCondBr)):
                    self._block.terminate(IRBr(cond_lbl))
                    
                # End
                self._block = self._fn.add_block(end_lbl)

        elif isinstance(stmt, ForInfiniteStmt):
            body_lbl = self._next_label("loop_body_")
            self._block.terminate(IRBr(body_lbl))
            self._block = self._fn.add_block(body_lbl)
            self._build_block(stmt.body)
            if not isinstance(self._block.terminator, (IRRet, IRBr, IRCondBr)):
                self._block.terminate(IRBr(body_lbl))
            # No end label strictly needed unless we have break, but good practice
            self._block = self._fn.add_block(self._next_label("loop_after_"))

        elif isinstance(stmt, MatchStmt):
            subject_v = self._build_expr(stmt.subject)
            subject_ty = stmt.subject.resolved_type
            assert isinstance(subject_ty, EnumCxType)
            
            # 1. Get the tag
            tag_ptr = self._next_reg(PtrCxType(I32))
            self._block.emit(IRGEP(dest=tag_ptr.name, ptr=subject_v, indices=[0, 0]))
            tag_val = self._next_reg(I32)
            self._block.emit(IRLoad(dest=tag_val.name, ptr=tag_ptr))
            
            # Store tag for usage in different blocks (arms) - avoids using a stale register
            tag_alloca = self._declare_var("__match_tag", I32)
            self._block.emit(IRStore(value=tag_val, ptr=tag_alloca))
            
            merge_lbl = self._next_label("match_merge_")
            
            # Map variants to blocks
            variant_map = {name: i for i, (name, _) in enumerate(subject_ty.variants)}
            

            for arm in stmt.arms:
                arm_lbl = self._next_label("arm_")
                next_arm_lbl = self._next_label("next_arm_")
                
                # Check pattern
                if isinstance(arm.pattern, EnumPattern):
                    v_idx = variant_map[arm.pattern.variant_name]
                    is_match = self._next_reg(BOOL)
                    match_tag = self._next_reg(I32)
                    self._block.emit(IRConst(dest=match_tag.name, value=v_idx, type=I32))
                    
                    # Reload tag from memory to ensure correct SSA/visibility across blocks
                    tag_reloaded = self._next_reg(I32)
                    self._block.emit(IRLoad(dest=tag_reloaded.name, ptr=tag_alloca))
                    
                    self._block.emit(IRBinOp(dest=is_match.name, op="==", left=tag_reloaded, right=match_tag, type=BOOL))
                    self._block.terminate(IRCondBr(cond=is_match, true_label=arm_lbl, false_label=next_arm_lbl))
                    
                    # Arm Body
                    self._block = self._fn.add_block(arm_lbl)
                    self._push_scope()
                    
                    # Bindings: unpack fields from the payload
                    if arm.pattern.fields:
                        variant_fields = subject_ty.variants[v_idx][1]
                        payload_ptr = self._next_reg(PtrCxType(I32))
                        self._block.emit(IRGEP(dest=payload_ptr.name, ptr=subject_v, indices=[0, 1]))
                        
                        var_struct_ty = TupleCxType([f_ty for _, f_ty in variant_fields])
                        var_ptr = self._next_reg(PtrCxType(var_struct_ty))
                        self._block.emit(IRCast(dest=var_ptr.name, kind="bitcast", value=payload_ptr, to_type=PtrCxType(var_struct_ty)))
                        
                        field_map = {name: i for i, (name, _) in enumerate(variant_fields)}
                        for binding_name in arm.pattern.fields:
                            idx = field_map[binding_name]
                            f_ty = variant_fields[idx][1]
                            
                            f_ptr = self._next_reg(PtrCxType(f_ty))
                            self._block.emit(IRGEP(dest=f_ptr.name, ptr=var_ptr, indices=[0, idx]))
                            
                            f_val = self._next_reg(f_ty)
                            self._block.emit(IRLoad(dest=f_val.name, ptr=f_ptr))
                            
                            # Declare and store in environment (shadows outer scope)
                            new_ptr = self._declare_var(binding_name, f_ty)
                            self._block.emit(IRStore(value=f_val, ptr=new_ptr))
                    
                    self._build_block(arm.body)
                    self._pop_scope()
                    if not isinstance(self._block.terminator, (IRRet, IRBr, IRCondBr)):
                        self._block.terminate(IRBr(merge_lbl))
                        
                    self._block = self._fn.add_block(next_arm_lbl)
                # ... other patterns ...
            
            self._block.terminate(IRBr(merge_lbl))
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
            if expr.op == "&&":
                # Short-circuiting AND
                res_ptr = self._declare_var(f"and_tmp", BOOL)
                self._block.emit(IRStore(value=IRValue("0", BOOL), ptr=res_ptr)) # Initial false
                
                rhs_lbl = self._next_label("and_rhs_")
                merge_lbl = self._next_label("and_merge_")
                
                lv = self._build_expr(expr.left)
                self._block.terminate(IRCondBr(cond=lv, true_label=rhs_lbl, false_label=merge_lbl))
                
                self._block = self._fn.add_block(rhs_lbl)
                rv = self._build_expr(expr.right)
                self._block.emit(IRStore(value=rv, ptr=res_ptr))
                self._block.terminate(IRBr(merge_lbl))
                
                self._block = self._fn.add_block(merge_lbl)
                res = self._next_reg(BOOL)
                self._block.emit(IRLoad(dest=res.name, ptr=res_ptr))
                return res
                
            if expr.op == "||":
                # Short-circuiting OR
                res_ptr = self._declare_var(f"or_tmp", BOOL)
                self._block.emit(IRStore(value=IRValue("1", BOOL), ptr=res_ptr)) # Initial true
                
                rhs_lbl = self._next_label("or_rhs_")
                merge_lbl = self._next_label("or_merge_")
                
                lv = self._build_expr(expr.left)
                self._block.terminate(IRCondBr(cond=lv, true_label=merge_lbl, false_label=rhs_lbl))
                
                self._block = self._fn.add_block(rhs_lbl)
                rv = self._build_expr(expr.right)
                self._block.emit(IRStore(value=rv, ptr=res_ptr))
                self._block.terminate(IRBr(merge_lbl))
                
                self._block = self._fn.add_block(merge_lbl)
                res = self._next_reg(BOOL)
                self._block.emit(IRLoad(dest=res.name, ptr=res_ptr))
                return res

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
                callee = expr.callee.name
                if callee == "print":
                    # Choose runtime print function based on argument type
                    if args:
                        arg_ty = args[0].type
                        if isinstance(arg_ty, PrimCxType) and arg_ty.name == "str":
                            callee = "__cx_print_str"
                        elif isinstance(arg_ty, PrimCxType) and arg_ty.is_integer():
                            callee = "__cx_print_int"
                        else:
                            callee = "__cx_print_str"
                    else:
                        callee = "__cx_print_str"
                
                self._block.emit(IRCall(dest=res.name if expr.resolved_type != VOID else None, 
                                        callee=callee, args=args, ret_ty=expr.resolved_type))
                return res if expr.resolved_type != VOID else UNDEF
            
            elif isinstance(expr.callee, PathExpr):
                args = [self._build_expr(a) for a in expr.args]
                res = self._next_reg(expr.resolved_type)
                callee = "::".join(expr.callee.parts)
                self._block.emit(IRCall(dest=res.name if expr.resolved_type != VOID else None, 
                                        callee=callee, args=args, ret_ty=expr.resolved_type))
                return res if expr.resolved_type != VOID else UNDEF

        if isinstance(expr, MethodCallExpr):
            receiver = self._build_expr(expr.receiver)
            args = [receiver] + [self._build_expr(a) for a in expr.args]
            
            res = self._next_reg(expr.resolved_type)
            
            # Resolve callee name (manglied Class_Method)
            recv_ty = expr.receiver.resolved_type
            if isinstance(recv_ty, PtrCxType):
                recv_ty = recv_ty.pointee
                
            if isinstance(recv_ty, (ObjCxType, NamedType)):
                callee = f"{recv_ty.name}_{expr.method}"
            else:
                callee = expr.method # Fallback
                
            self._block.emit(IRCall(dest=res.name if expr.resolved_type != VOID else None, 
                                    callee=callee, args=args, ret_ty=expr.resolved_type))
            return res if expr.resolved_type != VOID else UNDEF

        if isinstance(expr, NewExpr):
            return self._build_new_expr(expr)
            
        if isinstance(expr, NullLit):
            res = self._next_reg(NULL)
            self._block.emit(IRConst(dest=res.name, value=None, type=NULL))
            return res

        if isinstance(expr, UnaryExpr):
            # Pointer address-of
            if expr.op == "&" and isinstance(expr.operand, IdentExpr):
                ptr = self._get_var_ptr(expr.operand.name)
                # Ensure the return value has the correct type (PtrCxType)
                if ptr is not UNDEF:
                    return ptr
                    
            # Other unops can be evaluated here...
            inner = self._build_expr(expr.operand)
            res = self._next_reg(expr.resolved_type)
            self._block.emit(IRUnOp(dest=res.name, op=expr.op, operand=inner, type=expr.resolved_type))
            return res

        if isinstance(expr, FieldExpr):
            ptr = self._get_lvalue_ptr(expr)
            res = self._next_reg(expr.resolved_type)
            self._block.emit(IRLoad(dest=res.name, ptr=ptr))
            return res

        if isinstance(expr, IndexExpr):
            ptr = self._get_lvalue_ptr(expr)
            res = self._next_reg(expr.resolved_type)
            self._block.emit(IRLoad(dest=res.name, ptr=ptr))
            return res

        if isinstance(expr, EnumVariantExpr):
            # { i32 tag, payload }
            res_ptr = self._next_reg(PtrCxType(expr.resolved_type))
            self._block.emit(IRAlloca(dest=res_ptr.name, cx_type=expr.resolved_type))
            
            ety = expr.resolved_type
            assert isinstance(ety, EnumCxType)
            v_idx = -1
            for i, (name, _) in enumerate(ety.variants):
                if name == expr.variant_name:
                    v_idx = i
                    break
            
            # 1. Set tag
            tag_ptr = self._next_reg(PtrCxType(I32))
            self._block.emit(IRGEP(dest=tag_ptr.name, ptr=res_ptr, indices=[0, 0]))
            tag_val = self._next_reg(I32)
            self._block.emit(IRConst(dest=tag_val.name, value=v_idx, type=I32))
            self._block.emit(IRStore(value=tag_val, ptr=tag_ptr))
            
            # 2. Pack fields into payload (if any)
            variant_fields = ety.variants[v_idx][1]
            if variant_fields:
                # payload_ptr is a pointer to the [32 x i8] payload
                payload_ptr = self._next_reg(PtrCxType(I32))
                self._block.emit(IRGEP(dest=payload_ptr.name, ptr=res_ptr, indices=[0, 1]))
                
                # Bitcast payload_ptr to a pointer to the specific variant tuple-struct
                var_struct_ty = TupleCxType([f_ty for _, f_ty in variant_fields])
                var_ptr = self._next_reg(PtrCxType(var_struct_ty))
                self._block.emit(IRCast(dest=var_ptr.name, kind="bitcast", value=payload_ptr, to_type=PtrCxType(var_struct_ty)))
                
                field_map = {name: idx for idx, (name, _) in enumerate(variant_fields)}
                for f_name, f_val_expr in expr.fields:
                    idx = field_map[f_name]
                    f_ty = variant_fields[idx][1]
                    f_val = self._build_expr(f_val_expr)
                    
                    f_ptr = self._next_reg(PtrCxType(f_ty))
                    self._block.emit(IRGEP(dest=f_ptr.name, ptr=var_ptr, indices=[0, idx]))
                    self._block.emit(IRStore(value=f_val, ptr=f_ptr))
            
            res = self._next_reg(expr.resolved_type)
            self._block.emit(IRLoad(dest=res.name, ptr=res_ptr))
            return res
        if isinstance(expr, IfExpr):
            # Use a unique name for the result temp to avoid collisions
            res_name = f"if_tmp_{self._reg_counter}"
            cond_val = self._build_expr(expr.cond)
            res_ptr = self._declare_var(res_name, expr.resolved_type)
            
            then_lbl = self._next_label("if_then_")
            else_lbl = self._next_label("if_else_")
            merge_lbl = self._next_label("if_merge_")
            
            self._block.terminate(IRCondBr(cond=cond_val, true_label=then_lbl, false_label=else_lbl))
            
            # Then
            self._block = self._fn.add_block(then_lbl)
            tv = self._build_expr(expr.then_expr)
            self._block.emit(IRStore(value=tv, ptr=res_ptr))
            self._block.terminate(IRBr(merge_lbl))
            
            # Else
            self._block = self._fn.add_block(else_lbl)
            ev = self._build_expr(expr.else_expr)
            self._block.emit(IRStore(value=ev, ptr=res_ptr))
            self._block.terminate(IRBr(merge_lbl))
            
            # Merge
            self._block = self._fn.add_block(merge_lbl)
            res = self._next_reg(expr.resolved_type)
            self._block.emit(IRLoad(dest=res.name, ptr=res_ptr))
            return res

        if isinstance(expr, StructLiteral):
            # 1. Allocate on stack
            ptr = self._next_reg(PtrCxType(expr.resolved_type))
            self._block.emit(IRAlloca(dest=ptr.name, cx_type=expr.resolved_type))
            
            # 2. Initialize fields
            obj_ty = expr.resolved_type
            assert isinstance(obj_ty, ObjCxType)
            
            field_map = {name: i for i, (name, _) in enumerate(obj_ty.fields)}
            for f_name, f_val in expr.fields:
                idx = field_map[f_name]
                f_ptr = self._next_reg(PtrCxType(obj_ty.fields[idx][1]))
                self._block.emit(IRGEP(dest=f_ptr.name, ptr=ptr, indices=[0, idx]))
                v = self._build_expr(f_val)
                self._block.emit(IRStore(value=v, ptr=f_ptr))
            
            # 3. Load and return the struct (by value in IR usually, or just return ptr?)
            # Usually builders return a value. Let's return the loaded struct.
            res = self._next_reg(expr.resolved_type)
            self._block.emit(IRLoad(dest=res.name, ptr=ptr))
            return res

        if isinstance(expr, AllocExpr):
            count = self._build_expr(expr.count)
            res = self._next_reg(expr.resolved_type)
            
            # Calculate total size: count * sizeof(element_type)
            elem_size  = self._sizeof(expr.type_node)
            sz_const   = IRIntLit(name=None, value=elem_size, type=I32)
            total_size = self._next_reg(I32)
            self._block.emit(IRBinary(dest=total_size.name, op="*", left=count, right=sz_const))
            
            # Call native malloc
            self._block.emit(IRCall(dest=res.name, callee="__cx_malloc", args=[total_size], ret_ty=expr.resolved_type))
            return res

        if isinstance(expr, FreeExpr):
            ptr = self._build_expr(expr.ptr)
            self._block.emit(IRCall(dest=None, callee="__cx_free", args=[ptr], ret_ty=VOID))
            return VOID

        return UNDEF

    def _build_new_expr(self, expr: NewExpr) -> IRValue:
        # 1. Allocate memory (always 1 for 'new')
        res = self._next_reg(expr.resolved_type)
        obj_ty = expr.resolved_type.pointee
        
        # Calculate size based on the resolved type
        total_size = self._get_type_size(obj_ty)
        sz_reg = self._next_reg(I32)
        self._block.emit(IRConst(dest=sz_reg.name, value=total_size, type=I32))
        
        # Call malloc
        self._block.emit(IRCall(dest=res.name, callee="__cx_malloc", args=[sz_reg], ret_ty=expr.resolved_type))
        
        # 2. Call 'init' if it exists
        if isinstance(obj_ty, ObjCxType) and "init" in obj_ty.methods:
            callee = f"{obj_ty.name}_init"
            args = [res] + [self._build_expr(a) for a in expr.args]
            self._block.emit(IRCall(dest=None, callee=callee, args=args, ret_ty=VOID))
            
        return res

    def _get_lvalue_ptr(self, expr: Expr) -> IRValue:
        """Factor out getting the pointer to an expression (for assignment/addr-of)."""
        if isinstance(expr, IdentExpr):
            return self._get_var_ptr(expr.name)
            
        if isinstance(expr, FieldExpr):
            obj_ptr = self._get_lvalue_ptr(expr.obj)
            obj_ty = expr.obj.resolved_type
            
            # Handle pointer to struct vs direct struct
            if isinstance(obj_ty, PtrCxType):
                obj_ptr = self._build_expr(expr.obj) # Load the pointer value
                obj_ty = obj_ty.pointee
            
            if isinstance(obj_ty, ObjCxType):
                idx = -1
                for i, (name, _) in enumerate(obj_ty.fields):
                    if name == expr.field:
                        idx = i
                        break
                if idx != -1:
                    res_ty = PtrCxType(obj_ty.fields[idx][1])
                    res = self._next_reg(res_ty)
                    self._block.emit(IRGEP(dest=res.name, ptr=obj_ptr, indices=[0, idx]))
                    return res

        if isinstance(expr, IndexExpr):
            obj_ptr = self._get_lvalue_ptr(expr.obj)
            obj_ty = expr.obj.resolved_type
            
            # Pointers allow indexing (ptr[0])
            if isinstance(obj_ty, PtrCxType):
                obj_ptr = self._build_expr(expr.obj)
                obj_ty = obj_ty.pointee
                
            idx_val = self._build_expr(expr.index)
            res_ty = PtrCxType(expr.resolved_type)
            res = self._next_reg(res_ty)
            # Correct GEP for array indexing
            self._block.emit(IRGEP(dest=res.name, ptr=obj_ptr, indices=[idx_val]))
            return res
                    
        return UNDEF
    def _sizeof(self, ty_node: TypeNode) -> int:
        """Calculate the size of a type in bytes (simplified for common types)."""
        # Ideally we'd resolve the TypeNode to a CxType first.
        # This is a legacy helper; _get_type_size is preferred.
        if isinstance(ty_node, PrimType):
            if ty_node.name in ("int", "uint", "flt"): return 8
            if ty_node.name in ("dbl"):                 return 8
            if ty_node.name in ("char", "bool"):        return 1
            if ty_node.name == "str":                   return 16 # {ptr, len}
            if ty_node.name == "void":                  return 1
            return 8
        if isinstance(ty_node, ModifiedType):
            if "ptr" in ty_node.modifiers:              return 8
        return 8 # Fallback

    def _get_type_size(self, ty: CxType) -> int:
        """Calculates size of a resolved CxType in bytes."""
        if isinstance(ty, PrimCxType):
            if ty.name == "str": return 16
            if ty.bits == 0: return 1 # void
            return (ty.bits + 7) // 8
        if isinstance(ty, PtrCxType):
            return 8
        if isinstance(ty, ObjCxType):
            return sum(self._get_type_size(f_ty) for _, f_ty in ty.fields)
        if isinstance(ty, ArrCxType):
            return ty.capacity * self._get_type_size(ty.elem)
        return 8
