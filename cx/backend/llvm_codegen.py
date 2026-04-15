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
    IRModule, IRFunction, IRBlock, IRBinary, IRValue,
    IRAlloca, IRLoad, IRStore, IRBinOp, IRUnOp, IRCall, IRIntLit,
    IRGEP, IRCast, IRConst, IRBr, IRCondBr, IRRet, IRUnreachable
)
from ..middleend.semantic.type_system import (
    CxType, PrimCxType, PtrCxType, OptCxType, ObjCxType, EnumCxType,
    ArrCxType, FuncCxType, TupleCxType, VOID, I32, CHAR,
)

# Convenience type aliases
_i8  = ll.IntType(8)
_i32 = ll.IntType(32)
_i64 = ll.IntType(64)
_i8p = _i8.as_pointer()
_STR_TYPE = ll.LiteralStructType([_i8p, _i64])  # fat pointer { i8*, i64 }


class LLVMCodegen:
    def __init__(self, opts: CompileOptions, module_name: str = "cx_main"):
        self.opts = opts
        self._init_llvm()

        self.module = ll.Module(name=module_name)
        self.module.triple = llvm.get_default_triple()
        self.module.data_layout = self.target_machine.target_data

        # State
        self._funcs: Dict[str, ll.Function] = {}
        self._vals:  Dict[str, ll.Value]    = {}
        self._blocks: Dict[str, ll.Block]   = {}
        self._struct_types: Dict[str, ll.Type] = {}
        self._builder: Optional[ll.IRBuilder] = None

    # ---------------------------------------------------------------- init

    def _init_llvm(self) -> None:
        llvm.initialize_native_target()
        llvm.initialize_native_asmprinter()

        target = llvm.Target.from_default_triple()
        opt_map = {
            OptLevel.O0: 0, OptLevel.O1: 1,
            OptLevel.O2: 2, OptLevel.O3: 3,
            OptLevel.Os: 2,
        }
        self.target_machine = target.create_target_machine(
            opt=opt_map[self.opts.opt_level],
            reloc='pic',
            codemodel='default',
        )

    # ---------------------------------------------------------------- type lowering

    def _lower_type(self, ty: CxType) -> ll.Type:
        if isinstance(ty, PrimCxType):
            name = ty.name
            if name == "void":   return ll.VoidType()
            if name == "bool":   return ll.IntType(1)
            if name == "null":   return _i8p
            if name == "str":    return _STR_TYPE
            if ty.is_integer():  return ll.IntType(ty.bits if ty.bits > 0 else 32)
            if name == "flt":    return ll.FloatType()
            if name == "dbl":    return ll.DoubleType()

        elif isinstance(ty, PtrCxType):
            inner = self._lower_type(ty.pointee)
            # FunctionType cannot be directly pointed at; wrap in a pointer type
            if isinstance(inner, ll.FunctionType):
                return inner.as_pointer()
            return inner.as_pointer()

        elif isinstance(ty, OptCxType):
            # Optional<T> is represented as a nullable pointer to T.
            # If T is already a pointer, we don't need another level of indirection.
            inner_ll = self._lower_type(ty.inner)
            if isinstance(inner_ll, ll.PointerType):
                return inner_ll
            return inner_ll.as_pointer()

        elif isinstance(ty, FuncCxType):
            ret  = self._lower_type(ty.ret)
            args = [self._lower_type(p) for p in ty.params]
            return ll.FunctionType(ret, args)

        elif isinstance(ty, ObjCxType):
            if ty.name in self._struct_types:
                return self._struct_types[ty.name]
            # Create opaque named struct first to handle recursive types
            st = self.module.context.get_identified_type(ty.name)
            self._struct_types[ty.name] = st
            elems = [self._lower_type(ft) for _, ft in ty.fields]
            st.set_body(*elems)
            return st

        elif isinstance(ty, ArrCxType):
            return ll.ArrayType(self._lower_type(ty.elem), ty.capacity)

        elif isinstance(ty, TupleCxType):
            name = f"tuple.{'_'.join(str(i) for i in range(len(ty.elems)))}"
            if name in self._struct_types:
                return self._struct_types[name]
            st = self.module.context.get_identified_type(name)
            self._struct_types[name] = st
            st.set_body(*[self._lower_type(e) for e in ty.elems])
            return st

        elif isinstance(ty, EnumCxType):
            if ty.name in self._struct_types:
                return self._struct_types[ty.name]
            st = self.module.context.get_identified_type(f"enum.{ty.name}")
            self._struct_types[ty.name] = st
            # Enum = { i32 tag, [32 x i8] payload }
            st.set_body(_i32, ll.ArrayType(_i8, 32))
            return st

        return _i32  # Fallback — should not be reached in well-typed IR

    # ---------------------------------------------------------------- module lowering

    def lower(self, hir_mod: IRModule) -> str:
        """Lower the entire HIR module to LLVM IR and return the IR text."""

        # 0. Declare native runtime functions (implemented in cx/backend/runtime.py)
        self._declare_runtime()

        # 1. Forward-declare all functions (externs + implementations)
        import sys
        # sys.stderr.write(f"DEBUG: LLVMCodegen lowering {len(hir_mod.functions)} functions and {len(hir_mod.externs)} externs\n")
        for fn in hir_mod.externs + hir_mod.functions:
            if fn.name in self._funcs:
                continue
            ret_ll  = self._lower_type(fn.ret_type)
            args_ll = [self._lower_type(ty) for _, ty in fn.params]
            fn_ty   = ll.FunctionType(ret_ll, args_ll)
            ll_fn   = ll.Function(self.module, fn_ty, name=fn.name)
            self._funcs[fn.name] = ll_fn
            # sys.stderr.write(f"DEBUG: LLVMCodegen declared '{fn.name}'\n")

        # 2. Emit function bodies
        for fn in hir_mod.functions:
            # sys.stderr.write(f"DEBUG: LLVMCodegen emitting body for '{fn.name}'\n")
            self._lower_function(fn)

        # 3. Verify + stringify
        mod_ir = str(self.module)
        llvm.parse_assembly(mod_ir)  # raises on malformed IR

        # 4. Optimize
        return self._optimize()

    # ---------------------------------------------------------------- function lowering

    def _declare_runtime(self) -> None:
        """Declare compiler-internal runtime functions as externals."""
        _i32 = ll.IntType(32)
        _i64 = ll.IntType(64)
        _ptr = ll.PointerType(ll.IntType(8))
        _str_struct_ty = ll.LiteralStructType([_ptr, _i64])

        # __cx_print_str({char*, i64})
        fn_print_str = ll.Function(self.module, ll.FunctionType(ll.VoidType(), [_str_struct_ty]), name="__cx_print_str")
        self._funcs["__cx_print_str"] = fn_print_str
        
        # __cx_print_int(i32)
        fn_print_int = ll.Function(self.module, ll.FunctionType(ll.VoidType(), [_i32]), name="__cx_print_int")
        self._funcs["__cx_print_int"] = fn_print_int
        
        # __cx_malloc(i64)
        fn_malloc = ll.Function(self.module, ll.FunctionType(_ptr, [_i64]), name="__cx_malloc")
        self._funcs["__cx_malloc"] = fn_malloc
        
        # __cx_free(ptr)
        fn_free = ll.Function(self.module, ll.FunctionType(ll.VoidType(), [_ptr]), name="__cx_free")
        self._funcs["__cx_free"] = fn_free

    def _lower_function(self, fn: IRFunction) -> None:
        ll_fn = self._funcs[fn.name]
        self._vals.clear()
        self._blocks.clear()

        # Bind argument names
        for i, (p_name, p_type) in enumerate(fn.params):
            arg = ll_fn.args[i]
            arg.name = p_name
            arg.hir_type = p_type  # Attach HIR type
            self._vals[p_name] = arg

        # Create all basic blocks up front (needed for forward branches)
        for b in fn.blocks:
            self._blocks[b.label] = ll_fn.append_basic_block(name=b.label)

        # Emit instructions block by block
        self._builder = ll.IRBuilder()
        for b in fn.blocks:
            self._builder.position_at_end(self._blocks[b.label])
            for instr in b.instrs:
                self._lower_instr(instr)
            self._lower_terminator(b.terminator)

    def _resolve_val(self, val: IRValue) -> ll.Value:
        # Resolve the intended LLVM type for this value.
        # Note: If it's UNDEF, val.type might be None/VOID.
        ll_ty = self._lower_type(val.type or VOID)
        
        if val.name == "undef" or val.name == "" or val.name is None:
            if isinstance(ll_ty, ll.VoidType):
                # Return a dummy untyped-like constant. 
                # Instructions using this MUST check for VoidType manually.
                return ll.Constant(_i8, 0)
            return ll.Constant(ll_ty, None) # LLVM 'undef'
        
        # Check integer literals
        if isinstance(val.name, str) and val.name.isdigit():
             return ll.Constant(ll_ty, int(val.name))
             
        if val.name in self._vals:
            return self._vals[val.name]
            
        raise KeyError(f"Value name not found: {val.name!r}")

    def _coerce_arg(self, val: ll.Value, expected: ll.Type) -> ll.Value:
        """Best-effort coercion when an argument type doesn't match exactly."""
        if self._builder is None: return val # Should not happen
        
        actual = val.type
        if actual == expected:
            return val
            
        # If we have a dummy i8 0 from a void/undef return, promote it to a typed undef
        # to avoid invalid bitcasts to structs or non-matching pointers.
        if isinstance(actual, ll.IntType) and actual.width == 8 and isinstance(val, ll.Constant) and str(val).find("i8 0") != -1:
             if not isinstance(expected, ll.VoidType):
                 return ll.Constant(expected, None)
             return val

        # Pointer ↔ pointer: bitcast
        if isinstance(actual, ll.PointerType) and isinstance(expected, ll.PointerType):
            return self._builder.bitcast(val, expected)
        # Integer widening / narrowing
        if isinstance(actual, ll.IntType) and isinstance(expected, ll.IntType):
            if actual.width < expected.width:
                return self._builder.zext(val, expected)
            return self._builder.trunc(val, expected)
        # Pointer → integer (e.g. null → i64)
        if isinstance(actual, ll.PointerType) and isinstance(expected, ll.IntType):
            return self._builder.ptrtoint(val, expected)
        # Integer → pointer
        if isinstance(actual, ll.IntType) and isinstance(expected, ll.PointerType):
            return self._builder.inttoptr(val, expected)
        # Float widening / narrowing
        if isinstance(actual, ll.FloatType) and isinstance(expected, ll.DoubleType):
            return self._builder.fpext(val, expected)
        if isinstance(actual, ll.DoubleType) and isinstance(expected, ll.FloatType):
            return self._builder.fptrunc(val, expected)
        # Generic fallback: bitcast (only valid for same-size types, but better than crashing)
        try:
            return self._builder.bitcast(val, expected)
        except Exception:
            return val  # give up — let LLVM's verifier report the mismatch

    def _str_global(self, value: str):
        """Return (global, char_len) for a string literal, reusing cached globals."""
        key = f"str_{abs(hash(value))}"
        g = self.module.globals.get(key)
        if g is not None:
            # L'array type est [N x i8] ; N inclut le \0, donc char_len = N - 1
            char_len = g.type.pointee.count - 1
            return g, char_len                           # ← était : return g  (BUG 1)
        try:
            raw = value.encode('utf-8').decode('unicode_escape').encode('utf-8') + b'\0'
        except Exception:
            raw = value.encode('utf-8') + b'\0'
        arr_ty = ll.ArrayType(_i8, len(raw))
        g = ll.GlobalVariable(self.module, arr_ty, name=key)
        g.linkage         = 'internal'
        g.global_constant = True
        g.initializer     = ll.Constant(arr_ty, bytearray(raw))
        return g, len(raw) - 1

    # ---------------------------------------------------------------- instruction lowering

    def _lower_instr(self, instr: Any) -> None:  # noqa: C901 (complex but exhaustive)
        assert self._builder is not None
        b = self._builder

        # ---- Memory ----

        if isinstance(instr, IRAlloca):
            ll_ty = self._lower_type(instr.cx_type)
            val = b.alloca(ll_ty, name=instr.dest)
            val.hir_type = PtrCxType(instr.cx_type)
            self._vals[instr.dest] = val

        elif isinstance(instr, IRStore):
            val = self._resolve_val(instr.value)
            ptr = self._resolve_val(instr.ptr)
            
            if isinstance(val.type, ll.VoidType):
                return # Skip storing void
            
            ptr_hir = getattr(ptr, 'hir_type', instr.ptr.type)
            if hasattr(ptr_hir, 'pointee'):
                target_ll_ty = self._lower_type(ptr_hir.pointee)
            else:
                target_ll_ty = ptr.type.pointee if hasattr(ptr.type, 'pointee') else val.type

            val = self._coerce_arg(val, target_ll_ty)

            expected_ptr_ty = target_ll_ty.as_pointer()
            if ptr.type != expected_ptr_ty:
                ptr = b.bitcast(ptr, expected_ptr_ty)

            b.store(val, ptr)

        elif isinstance(instr, IRLoad):
            ptr = self._resolve_val(instr.ptr)
            # When using opaque pointers, load requires the element type
            ptr_hir = getattr(ptr, 'hir_type', instr.ptr.type)
            if hasattr(ptr_hir, 'pointee'):
                etype = self._lower_type(ptr_hir.pointee)
            else:
                etype = ptr.type.pointee if hasattr(ptr.type, 'pointee') else _i8
            
            if not isinstance(ptr.type, ll.PointerType):
                raise TypeError(f"Load from non-pointer: {ptr.type}")

            res = b.load(ptr, name=instr.dest) 
            res.hir_type = ptr_hir.pointee if hasattr(ptr_hir, 'pointee') else VOID
            self._vals[instr.dest] = res

        # ---- Constants ----

        elif isinstance(instr, IRConst):
            val = self._lower_const(instr)
            val.hir_type = instr.type
            self._vals[instr.dest] = val

        # ---- Arithmetic / comparison ----

        elif isinstance(instr, (IRBinOp, IRBinary)):
            val = self._lower_binop(instr)
            val.hir_type = instr.type
            self._vals[instr.dest] = val

        elif isinstance(instr, IRUnOp):
            val = self._lower_unop(instr)
            val.hir_type = instr.type
            self._vals[instr.dest] = val

        # ---- Casts ----

        elif isinstance(instr, IRCast):
            val = self._lower_cast(instr)
            val.hir_type = instr.to_type
            self._vals[instr.dest] = val

        # ---- Pointer arithmetic ----

        elif isinstance(instr, IRGEP):
            ptr = self._resolve_val(instr.ptr)
            
            # Defensive: if we are GEPing a value instead of a pointer, spill it to a temporary
            if not isinstance(ptr.type, ll.PointerType):
                tmp = b.alloca(ptr.type, name=f"spill.{instr.ptr.name}")
                # Use current hir type if possible for the alloca
                tmp.hir_type = PtrCxType(getattr(ptr, 'hir_type', instr.ptr.type))
                b.store(ptr, tmp)
                ptr = tmp

            indices = [
                ll.Constant(_i32, idx) if isinstance(idx, int)
                else self._resolve_val(idx)
                for idx in instr.indices
            ]
            
            # Use HIR as the source of truth for the type being indexed
            ptr_hir = getattr(ptr, 'hir_type', instr.ptr.type)
            
            if hasattr(ptr_hir, 'pointee'):
                etype = self._lower_type(ptr_hir.pointee)
            elif isinstance(ptr_hir, (EnumCxType, ObjCxType)):
                etype = self._lower_type(ptr_hir)
            else:
                etype = ptr.type.pointee if hasattr(ptr.type, 'pointee') else _i8
            
            res = b.gep(ptr, indices, name=instr.dest, source_etype=etype)
            
            # Result of GEP is always a pointer in HIR.
            res_hir_etype = instr.elem_ty
            if res_hir_etype is None and hasattr(ptr_hir, 'pointee'):
                curr = ptr_hir.pointee
                try:
                    it = iter(instr.indices)
                    next(it, None) # Skip first index
                    for idx in it:
                        if isinstance(idx, int):
                            if isinstance(curr, ObjCxType):
                                if 0 <= idx < len(curr.fields):
                                    _, curr = curr.fields[idx]
                            elif isinstance(curr, TupleCxType):
                                if 0 <= idx < len(curr.elems):
                                    curr = curr.elems[idx]
                            elif isinstance(curr, ArrCxType):
                                curr = curr.elem
                            elif isinstance(curr, EnumCxType):
                                if idx == 0: curr = I32
                                else: curr = ArrCxType(CHAR, 32)
                except Exception:
                    pass 
                res_hir_etype = curr

            res.hir_type = PtrCxType(res_hir_etype) if res_hir_etype else PtrCxType(VOID)
            
            # Hard-cast to the expected LLVM type if they mismatch (e.g. GEP returned struct-ptr instead of field-ptr)
            expected_res_ll_ty = self._lower_type(res.hir_type)
            if res.type != expected_res_ll_ty:
                 res = b.bitcast(res, expected_res_ll_ty, name=f"{instr.dest}.cast")
                 res.hir_type = PtrCxType(res_hir_etype)

            self._vals[instr.dest] = res

        # ---- Calls ----

        elif isinstance(instr, IRCall):
            val = self._lower_call(instr)
            if instr.dest is not None:
                if not isinstance(val.type, ll.VoidType):
                    val.hir_type = instr.ret_ty
                    self._vals[instr.dest] = val

    def _lower_const(self, instr: IRConst) -> ll.Value:
        assert self._builder is not None
        b = self._builder

        ty = instr.type
        if isinstance(ty, PrimCxType) and ty.name == "str":
            # Build fat pointer { i8*, i64 }
            g, char_len = self._str_global(instr.value)
            raw_ptr = b.bitcast(g, _i8p)
            length  = ll.Constant(_i64, char_len)
            fat     = b.insert_value(ll.Constant(_STR_TYPE, ll.Undefined), raw_ptr, 0)
            fat     = b.insert_value(fat, length, 1, name=instr.dest)
            return fat

        if instr.value is None or (isinstance(ty, PrimCxType) and ty.name == "null"):
            ll_ty = self._lower_type(ty)
            return ll.Constant(ll_ty, None)

        ll_ty = self._lower_type(ty)
        if isinstance(ll_ty, ll.VoidType):
            return ll.Constant(_i8, 0)

        try:
            return ll.Constant(ll_ty, instr.value)
        except Exception:
            return ll.Constant(ll_ty, 0)

    def _lower_binop(self, instr: IRBinOp) -> ll.Value:
        b  = self._builder

        def _resolve(operand):
            if operand.name is not None:
                return self._vals[operand.name]
            
            v = getattr(operand, 'value', None)
            if v is not None:
                ll_ty = self._lower_type(operand.type) if operand.type else _i64
                if isinstance(ll_ty, ll.VoidType):
                    return ll.Constant(_i8, 0)
                return ll.Constant(ll_ty, int(v))
            
            raise KeyError(f"Operand has no name and no value: {operand!r}")

        lv = _resolve(instr.left)
        rv = _resolve(instr.right)

        is_fp     = False
        is_signed = True
        if isinstance(instr.type, PrimCxType):
            is_fp     = instr.type.is_fp
            is_signed = instr.type.signed

        op = instr.op

        # Arithmetic
        if op == "+":
            val = b.fadd(lv, rv, name=instr.dest) if is_fp else b.add(lv, rv, name=instr.dest)
        elif op == "-":
            val = b.fsub(lv, rv, name=instr.dest) if is_fp else b.sub(lv, rv, name=instr.dest)
        elif op == "*":
            val = b.fmul(lv, rv, name=instr.dest) if is_fp else b.mul(lv, rv, name=instr.dest)
        elif op == "/":
            if is_fp:       val = b.fdiv(lv, rv, name=instr.dest)
            elif is_signed: val = b.sdiv(lv, rv, name=instr.dest)
            else:           val = b.udiv(lv, rv, name=instr.dest)
        elif op == "%":
            if is_fp:       val = b.frem(lv, rv, name=instr.dest)
            elif is_signed: val = b.srem(lv, rv, name=instr.dest)
            else:           val = b.urem(lv, rv, name=instr.dest)

        # Bitwise
        elif op == "&":
            val = b.and_(lv, rv, name=instr.dest)
        elif op == "|":
            val = b.or_(lv, rv, name=instr.dest)
        elif op == "^":
            val = b.xor(lv, rv, name=instr.dest)
        elif op == "<<":
            val = b.shl(lv, rv, name=instr.dest)
        elif op == ">>":
            val = b.ashr(lv, rv, name=instr.dest) if is_signed else b.lshr(lv, rv, name=instr.dest)

        # Comparisons
        elif op == "==":
            val = b.fcmp_ordered("==", lv, rv, name=instr.dest) if is_fp else b.icmp_signed("==", lv, rv, name=instr.dest)
        elif op == "!=":
            val = b.fcmp_unordered("!=", lv, rv, name=instr.dest) if is_fp else b.icmp_signed("!=", lv, rv, name=instr.dest)
        elif op == "<":
            val = b.fcmp_ordered("<", lv, rv, name=instr.dest) if is_fp else b.icmp_signed("<", lv, rv, name=instr.dest)
        elif op == ">":
            val = b.fcmp_ordered(">", lv, rv, name=instr.dest) if is_fp else b.icmp_signed(">", lv, rv, name=instr.dest)
        elif op == "<=":
            val = b.fcmp_ordered("<=", lv, rv, name=instr.dest) if is_fp else b.icmp_signed("<=", lv, rv, name=instr.dest)
        elif op == ">=":
            val = b.fcmp_ordered(">=", lv, rv, name=instr.dest) if is_fp else b.icmp_signed(">=", lv, rv, name=instr.dest)

        else:
            raise NotImplementedError(f"Unsupported binary operator: {op!r}")

        self._vals[instr.dest] = val
        return val

    def _lower_unop(self, instr: IRUnOp) -> ll.Value:
        assert self._builder is not None
        b   = self._builder
        val = self._vals[instr.operand.name]
        op  = instr.op

        is_fp = isinstance(instr.type, PrimCxType) and instr.type.is_fp

        if op == "-":
            return b.fneg(val, name=instr.dest) if is_fp else b.neg(val, name=instr.dest)
        if op in ("!", "not"):
            # Logical NOT: val == 0
            zero = ll.Constant(val.type, 0)
            return b.icmp_signed("==", val, zero, name=instr.dest)
        if op == "~":
            # Bitwise NOT: val XOR -1
            minus_one = ll.Constant(val.type, -1)
            return b.xor(val, minus_one, name=instr.dest)

        raise NotImplementedError(f"Unsupported unary operator: {op!r}")

    def _lower_cast(self, instr: IRCast) -> ll.Value:
        assert self._builder is not None
        b    = self._builder
        val  = self._resolve_val(instr.value)
        dest = self._lower_type(instr.to_type)
        
        # If we are casting an 'undef' that resolve_val couldn't type properly (so it returned i8 0),
        # replace it with a properly typed undef for this cast destination.
        if isinstance(val.type, ll.IntType) and val.type.width == 8 and isinstance(dest, (ll.AggregateType, ll.PointerType)):
            # Check if it was actually a void/undef in HIR
            if instr.value.name in ("undef", "", None):
                return ll.Constant(dest, None)

        op   = instr.kind  # e.g. "trunc", "zext", "sext", "fpext", "fptrunc",
                               #      "fptoui", "fptosi", "uitofp", "sitofp",
                               #      "inttoptr", "ptrtoint", "bitcast"

        cast_fn = {
            "trunc":    b.trunc,
            "zext":     b.zext,
            "sext":     b.sext,
            "fpext":    b.fpext,
            "fptrunc":  b.fptrunc,
            "fptoui":   b.fptoui,
            "fptosi":   b.fptosi,
            "uitofp":   b.uitofp,
            "sitofp":   b.sitofp,
            "inttoptr": b.inttoptr,
            "ptrtoint": b.ptrtoint,
            "bitcast":  b.bitcast,
        }.get(op)

        if cast_fn is None:
            raise NotImplementedError(f"Unsupported cast op: {op!r}")
        return cast_fn(val, dest, name=instr.dest)

    def _lower_call(self, instr: IRCall) -> ll.Value:
        """Lowers a function call, including argument coercion and return value handling."""
        assert self._builder is not None
        b = self._builder

        if instr.callee not in self._funcs:
            # Fallback for undeclared internals or built-ins
            ret_ll  = self._lower_type(instr.ret_ty)
            args_ll = [self._lower_type(a.type) for a in instr.args]
            fn_ty   = ll.FunctionType(ret_ll, args_ll)
            self._funcs[instr.callee] = ll.Function(self.module, fn_ty, name=instr.callee)

        callee = self._funcs[instr.callee]
        param_types = list(callee.function_type.args)

        # Build and coerce arguments
        raw_args = [self._resolve_val(a) for a in instr.args]
        args: List[ll.Value] = []
        for i, (arg, param_ty) in enumerate(zip(raw_args, param_types)):
            args.append(self._coerce_arg(arg, param_ty))
        
        # Append remaining args for variadic functions
        if len(raw_args) > len(param_types):
            args.extend(raw_args[len(param_types):])

        # Execute call
        res = b.call(callee, args, name=instr.dest if instr.dest else "")
        return res

    # ---------------------------------------------------------------- terminator lowering

    def _lower_terminator(self, term: Any) -> None:
        assert self._builder is not None
        b = self._builder

        if isinstance(term, IRRet):
            if term.value is None or isinstance(b.block.parent.function_type.return_type, ll.VoidType):
                b.ret_void()
            else:
                val = self._resolve_val(term.value)
                # Coerce to declared return type if needed
                ret_ty = b.block.parent.function_type.return_type
                b.ret(self._coerce_arg(val, ret_ty))

        elif isinstance(term, IRBr):
            b.branch(self._blocks[term.target])

        elif isinstance(term, IRCondBr):
            cond = self._resolve_val(term.cond)
            # Ensure condition is i1
            if cond.type != ll.IntType(1):
                cond = b.trunc(cond, ll.IntType(1))
            b.cbranch(cond, self._blocks[term.true_label], self._blocks[term.false_label])

        elif isinstance(term, IRUnreachable):
            b.unreachable()

        else:
            raise NotImplementedError(f"Unknown terminator: {type(term).__name__}")

    # ---------------------------------------------------------------- optimization

    def _optimize(self) -> str:
        mod = llvm.parse_assembly(str(self.module))
        mod.verify()

        opt = self.opts.llvm_opt
        if opt == 0:
            return str(mod)

        try:
            # New Pass Manager (llvmlite >= 0.40)
            pto = llvm.create_pipeline_tuning_options()
            pto.loop_unrolling    = opt >= 2
            pto.loop_vectorization = opt >= 2
            pto.slp_vectorization  = opt >= 2

            pb = llvm.create_pass_builder(self.target_machine, pto)
            pm = llvm.create_new_module_pass_manager()

            if opt >= 1:
                pm.add_sroa_pass()
                pm.add_instruction_combine_pass()
                pm.add_simplify_cfg_pass()
                pm.add_reassociate_pass()
            if opt >= 2:
                pm.add_global_opt_pass()
                pm.add_loop_rotate_pass()
                pm.add_loop_unroll_pass()
                # GVN removed in new pass manager, instruction combining + CSE covers it mostly
                # pm.add_memcpy_optimize_pass()
                pm.add_sccp_pass()
            if opt >= 3:
                pm.add_dead_arg_elimination_pass()
                pm.add_aggressive_dead_code_elimination_pass()
                pm.add_merge_functions_pass()

            pm.run(mod, pb)
        except Exception as exc:
            # Degrade gracefully — unoptimized IR is still correct IR
            import warnings
            warnings.warn(f"LLVM optimization failed, emitting unoptimized IR: {exc}")

        return str(mod)

    # ---------------------------------------------------------------- object / asm emission

    def emit_object(self, ir_str: str, outfile: str) -> None:
        mod = llvm.parse_assembly(ir_str)
        with open(outfile, "wb") as f:
            f.write(self.target_machine.emit_object(mod))

    def emit_asm(self, ir_str: str, outfile: str) -> None:
        mod = llvm.parse_assembly(ir_str)
        with open(outfile, "w", encoding="utf-8") as f:
            f.write(self.target_machine.emit_assembly(mod))