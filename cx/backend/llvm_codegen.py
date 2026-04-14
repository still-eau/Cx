"""LLVM Code Generation using llvmlite.

Lowers the High-level IR (HIR) down to LLVM IR, applies LLVM optimization
passes, and yields object files or bitcode.
"""

from __future__ import annotations

import llvmlite.ir as ll
import llvmlite.binding as llvm

from typing import Dict, List, Optional, Any

from ..config import CompileOptions, OptLevel, EmitKind
from ..middleend.ir.nodes import (
    IRModule, IRFunction, IRBlock,
    IRAlloca, IRLoad, IRStore, IRBinOp, IRUnOp, IRCall,
    IRGEP, IRCast, IRConst, IRBr, IRCondBr, IRRet, IRUnreachable
)
from ..middleend.semantic.type_system import (
    CxType, PrimCxType, PtrCxType, OptCxType, ObjCxType, EnumCxType,
    ArrCxType, FuncCxType, TupleCxType,
)


class LLVMCodegen:
    def __init__(self, opts: CompileOptions, module_name: str = "cx_main"):
        self.opts = opts
        self._init_llvm()
        
        self.module = ll.Module(name=module_name)
        self.module.triple = llvm.get_default_triple()
        self.module.data_layout = self.target_machine.target_data
        
        # State
        self._funcs: Dict[str, ll.Function] = {}
        self._vals: Dict[str, ll.Value] = {}
        self._blocks: Dict[str, ll.Block] = {}
        self._builder: Optional[ll.IRBuilder] = None

    def _init_llvm(self) -> None:
        llvm.initialize_native_target()
        llvm.initialize_native_asmprinter()
        
        # Create target machine
        target = llvm.Target.from_default_triple()
        
        # Map our opt_level to LLVM opt
        opt_map = {
            OptLevel.O0: 0,
            OptLevel.O1: 1,
            OptLevel.O2: 2,
            OptLevel.O3: 3,
            OptLevel.Os: 2,
        }
        
        self.target_machine = target.create_target_machine(
            opt=opt_map[self.opts.opt_level],
            reloc='pic',
            codemodel='default'
        )

    # ---------------------------------------------------------------- type lowering

    def _lower_type(self, ty: CxType) -> ll.Type:
        if isinstance(ty, PrimCxType):
            if ty.name == "void": return ll.VoidType()
            if ty.name == "bool": return ll.IntType(1)
            if ty.is_integer():   return ll.IntType(ty.bits)
            if ty.name == "flt":  return ll.FloatType()
            if ty.name == "dbl":  return ll.DoubleType()
        elif isinstance(ty, PtrCxType):
            return self._lower_type(ty.pointee).as_pointer()
        elif isinstance(ty, FuncCxType):
            ret = self._lower_type(ty.ret)
            args = [self._lower_type(p) for p in ty.params]
            return ll.FunctionType(ret, args)
            
        return ll.IntType(32)  # Fallback

    # ---------------------------------------------------------------- lowering module

    def lower(self, hir_mod: IRModule) -> str:
        """Lowers the entire HIR module to LLVM IR and returns the IR text."""
        
        # 1. Declare all functions
        for fn in hir_mod.externs + hir_mod.functions:
            ret_ll = self._lower_type(fn.ret_type)
            args_ll = [self._lower_type(ty) for _, ty in fn.params]
            fn_ty = ll.FunctionType(ret_ll, args_ll)
            ll_fn = ll.Function(self.module, fn_ty, name=fn.name)
            self._funcs[fn.name] = ll_fn

        # 2. Define implementations
        for fn in hir_mod.functions:
            self._lower_function(fn)
            
        # 3. Verify module
        mod_ir = str(self.module)
        llvm.parse_assembly(mod_ir) # verify and format
        
        # 4. Optimize
        return self._optimize()

    def _lower_function(self, fn: IRFunction) -> None:
        ll_fn = self._funcs[fn.name]
        self._vals.clear()
        self._blocks.clear()
        
        # Map arguments
        for i, (p_name, _) in enumerate(fn.params):
            ll_fn.args[i].name = p_name
            self._vals[p_name] = ll_fn.args[i]
            
        # Create all blocks
        for b in fn.blocks:
            self._blocks[b.label] = ll_fn.append_basic_block(name=b.label)
            
        # Emit instructions
        self._builder = ll.IRBuilder()
        for b in fn.blocks:
            self._builder.position_at_end(self._blocks[b.label])
            for instr in b.instrs:
                self._lower_instr(instr)
            self._lower_terminator(b.terminator)

    def _lower_instr(self, instr: Any) -> None:
        assert self._builder is not None
        
        if isinstance(instr, IRAlloca):
            ll_ty = self._lower_type(instr.cx_type)
            ptr = self._builder.alloca(ll_ty, name=instr.dest)
            self._vals[instr.dest] = ptr
            
        elif isinstance(instr, IRStore):
            val = self._vals[instr.value.name]
            ptr = self._vals[instr.ptr.name]
            self._builder.store(val, ptr)
            
        elif isinstance(instr, IRLoad):
            ptr = self._vals[instr.ptr.name]
            # LLVMLite needs the pointee type for load, we usually get it from the IRType
            # Here we hack it via load's pointer
            val = self._builder.load(ptr, name=instr.dest)
            self._vals[instr.dest] = val
            
        elif isinstance(instr, IRBinOp):
            lv = self._vals[instr.left.name]
            rv = self._vals[instr.right.name]
            
            is_fp = False
            is_signed = True
            if isinstance(instr.type, PrimCxType):
                is_fp = instr.type.is_fp
                is_signed = instr.type.signed
                
            op = instr.op
            res = None
            if op == "+":
                res = self._builder.fadd(lv, rv) if is_fp else self._builder.add(lv, rv)
            elif op == "-":
                res = self._builder.fsub(lv, rv) if is_fp else self._builder.sub(lv, rv)
            elif op == "*":
                res = self._builder.fmul(lv, rv) if is_fp else self._builder.mul(lv, rv)
            elif op == "/":
                if is_fp: res = self._builder.fdiv(lv, rv)
                else: res = self._builder.sdiv(lv, rv) if is_signed else self._builder.udiv(lv, rv)
            elif op == "==":
                if is_fp: res = self._builder.fcmp_ordered("==", lv, rv)
                else: res = self._builder.icmp_signed("==", lv, rv)
            elif op == "!=":
                if is_fp: res = self._builder.fcmp_unordered("!=", lv, rv)
                else: res = self._builder.icmp_signed("!=", lv, rv)
            elif op == "<":
                if is_fp: res = self._builder.fcmp_ordered("<", lv, rv)
                else: res = self._builder.icmp_signed("<", lv, rv)
            elif op == ">":
                if is_fp: res = self._builder.fcmp_ordered(">", lv, rv)
                else: res = self._builder.icmp_signed(">", lv, rv)
                
            if res:
                self._vals[instr.dest] = res
                res.name = instr.dest
                
        elif isinstance(instr, IRConst):
            ll_ty = self._lower_type(instr.type)
            const = ll.Constant(ll_ty, instr.value)
            self._vals[instr.dest] = const
            
        elif isinstance(instr, IRCall):
            callee = self._funcs[instr.callee]
            args = [self._vals[a.name] for a in instr.args]
            res = self._builder.call(callee, args, name=instr.dest if instr.dest else "")
            if instr.dest:
                self._vals[instr.dest] = res

    def _lower_terminator(self, term: Any) -> None:
        assert self._builder is not None
        
        if isinstance(term, IRRet):
            if term.value:
                self._builder.ret(self._vals[term.value.name])
            else:
                self._builder.ret_void()
                
        elif isinstance(term, IRBr):
            self._builder.branch(self._blocks[term.target])
            
        elif isinstance(term, IRCondBr):
            cond = self._vals[term.cond.name]
            tb = self._blocks[term.true_label]
            fb = self._blocks[term.false_label]
            self._builder.cbranch(cond, tb, fb)
            
        elif isinstance(term, IRUnreachable):
            self._builder.unreachable()

    # ---------------------------------------------------------------- optimization

    def _optimize(self) -> str:
        mod = llvm.parse_assembly(str(self.module))
        
        try:
            # Modern LLVM NewPassManager (llvmlite >= 0.40)
            pto = llvm.create_pipeline_tuning_options()
            if self.opts.llvm_opt > 0:
                pto.loop_unrolling = True
                pto.loop_vectorization = True
                pto.slp_vectorization = True
                
            pb = llvm.create_pass_builder(self.target_machine, pto)
            pm = llvm.create_new_module_pass_manager()
            
            # Add passes based on optimization level
            if self.opts.llvm_opt > 0:
                pm.add_sroa_pass()
                pm.add_instruction_combine_pass()
                pm.add_simplify_cfg_pass()
                pm.add_reassociate_pass()
            if self.opts.llvm_opt > 1:
                pm.add_global_opt_pass()
                pm.add_loop_rotate_pass()
                pm.add_loop_unroll_pass()
            if self.opts.llvm_opt > 2:
                pm.add_dead_arg_elimination_pass()
                
            pm.run(mod, pb)
        except Exception:
            pass # degrade gracefully and just return the unoptimized module
            
        return str(mod)

    # ---------------------------------------------------------------- object generation

    def emit_object(self, ir_str: str, outfile: str) -> None:
        mod = llvm.parse_assembly(ir_str)
        obj_bin = self.target_machine.emit_object(mod)
        with open(outfile, "wb") as f:
            f.write(obj_bin)
            
    def emit_asm(self, ir_str: str, outfile: str) -> None:
        mod = llvm.parse_assembly(ir_str)
        asm = self.target_machine.emit_assembly(mod)
        with open(outfile, "w", encoding='utf8') as f:
            f.write(asm)
