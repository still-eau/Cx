"""Cx Compiler Runtime — Standalone LLVM Module.

This module provides the implementations for compiler-internal functions
like __cx_print_str, __cx_malloc, etc. By keeping them in a separate 
module, we can link them once to the final executable instead of 
injecting them into every single user module.
"""

from __future__ import annotations
import llvmlite.ir as ll

def get_runtime_module(triple: str, data_layout: str, os_name: str = "nt") -> ll.Module:
    """Generates a standalone LLVM module containing the Cx runtime."""
    mod = ll.Module(name="cx_runtime")
    mod.triple = triple
    mod.data_layout = data_layout

    _i8  = ll.IntType(8)
    _i32 = ll.IntType(32)
    _i64 = ll.IntType(64)
    _ptr = _i8.as_pointer()
    _str_struct_ty = ll.LiteralStructType([_ptr, _i64])

    if os_name == "nt":
        _define_win32_runtime(mod, _str_struct_ty)
    else:
        _define_posix_runtime(mod, _str_struct_ty)

    return mod

# =============================================================================
# WINDOWS (WIN32) RUNTIME
# =============================================================================

def _define_win32_runtime(mod: ll.Module, str_ty: ll.Type):
    _i8  = ll.IntType(8)
    _i32 = ll.IntType(32)
    _i64 = ll.IntType(64)
    _ptr = _i8.as_pointer()

    # Win32 Externals
    get_std_h = ll.Function(mod, ll.FunctionType(_ptr, [_i32]), name="GetStdHandle")
    write_file = ll.Function(
        mod,
        ll.FunctionType(_i32, [_ptr, _ptr, _i32, _i32.as_pointer(), _ptr]),
        name="WriteFile"
    )
    get_heap = ll.Function(mod, ll.FunctionType(_ptr, []), name="GetProcessHeap")
    heap_alloc = ll.Function(mod, ll.FunctionType(_ptr, [_ptr, _i32, _i64]), name="HeapAlloc")
    heap_free = ll.Function(mod, ll.FunctionType(_i32, [_ptr, _i32, _ptr]), name="HeapFree")
    wsprintf = ll.Function(mod, ll.FunctionType(_i32, [_ptr, _ptr], var_arg=True), name="wsprintfA")

    _impl_win32_print_str(mod, str_ty, get_std_h, write_file)
    _impl_win32_print_int(mod, get_std_h, write_file, wsprintf)
    _impl_win32_malloc(mod, get_heap, heap_alloc)
    _impl_win32_free(mod, get_heap, heap_free)

def _impl_win32_print_str(mod, str_ty, get_std_h, write_file):
    _i8, _i32, _ptr = ll.IntType(8), ll.IntType(32), ll.IntType(8).as_pointer()
    fn = ll.Function(mod, ll.FunctionType(ll.VoidType(), [str_ty]), name="__cx_print_str")
    builder = ll.IRBuilder(fn.append_basic_block("entry"))
    
    h_out = builder.call(get_std_h, [_i32(-11)]) # STD_OUTPUT_HANDLE
    arg_s = fn.args[0]
    p_data = builder.extract_value(arg_s, 0)
    u_len  = builder.extract_value(arg_s, 1)
    u_len32 = builder.trunc(u_len, _i32)
    
    written = builder.alloca(_i32)
    builder.call(write_file, [h_out, p_data, u_len32, written, ll.Constant(_ptr, None)])
    
    nl_ptr = builder.alloca(_i8)
    builder.store(_i8(10), nl_ptr)
    builder.call(write_file, [h_out, nl_ptr, _i32(1), written, ll.Constant(_ptr, None)])
    builder.ret_void()

def _impl_win32_print_int(mod, get_std_h, write_file, wsprintf):
    _i8, _i32, _ptr = ll.IntType(8), ll.IntType(32), ll.IntType(8).as_pointer()
    fn = ll.Function(mod, ll.FunctionType(ll.VoidType(), [_i32]), name="__cx_print_int")
    builder = ll.IRBuilder(fn.append_basic_block("entry"))
    
    fmt = _get_or_create_fmt(mod, ".str_fmt_int", "%d\0")
    fmt_ptr = builder.bitcast(fmt, _ptr)
    buf = builder.alloca(ll.ArrayType(_i8, 32))
    buf_ptr = builder.bitcast(buf, _ptr)
    
    n_chars = builder.call(wsprintf, [buf_ptr, fmt_ptr, fn.args[0]])
    h_out = builder.call(get_std_h, [_i32(-11)])
    written = builder.alloca(_i32)
    builder.call(write_file, [h_out, buf_ptr, n_chars, written, ll.Constant(_ptr, None)])
    
    nl_ptr = builder.alloca(_i8)
    builder.store(_i8(10), nl_ptr)
    builder.call(write_file, [h_out, nl_ptr, _i32(1), written, ll.Constant(_ptr, None)])
    builder.ret_void()

def _impl_win32_malloc(mod, get_heap, heap_alloc):
    _i32, _i64, _ptr = ll.IntType(32), ll.IntType(64), ll.IntType(8).as_pointer()
    fn = ll.Function(mod, ll.FunctionType(_ptr, [_i64]), name="__cx_malloc")
    builder = ll.IRBuilder(fn.append_basic_block("entry"))
    h_heap = builder.call(get_heap, [])
    # HEAP_ZERO_MEMORY = 0x08
    res = builder.call(heap_alloc, [h_heap, _i32(8), fn.args[0]])
    builder.ret(res)

def _impl_win32_free(mod, get_heap, heap_free):
    _i32, _ptr = ll.IntType(32), ll.IntType(8).as_pointer()
    fn = ll.Function(mod, ll.FunctionType(ll.VoidType(), [_ptr]), name="__cx_free")
    builder = ll.IRBuilder(fn.append_basic_block("entry"))
    h_heap = builder.call(get_heap, [])
    builder.call(heap_free, [h_heap, _i32(0), fn.args[0]])
    builder.ret_void()

# =============================================================================
# POSIX (LIBC) RUNTIME
# =============================================================================

def _define_posix_runtime(mod: ll.Module, str_ty: ll.Type):
    _i8, _i32, _i64, _ptr = ll.IntType(8), ll.IntType(32), ll.IntType(64), ll.IntType(8).as_pointer()
    
    # libc Externals
    # ssize_t write(int fd, const void *buf, size_t count);
    write_fn = ll.Function(mod, ll.FunctionType(_i64, [_i32, _ptr, _i64]), name="write")
    # void *malloc(size_t size);
    malloc_fn = ll.Function(mod, ll.FunctionType(_ptr, [_i64]), name="malloc")
    # void free(void *ptr);
    free_fn = ll.Function(mod, ll.FunctionType(ll.VoidType(), [_ptr]), name="free")
    # int sprintf(char *str, const char *format, ...);
    sprintf_fn = ll.Function(mod, ll.FunctionType(_i32, [_ptr, _ptr], var_arg=True), name="sprintf")

    _impl_posix_print_str(mod, str_ty, write_fn)
    _impl_posix_print_int(mod, write_fn, sprintf_fn)
    _impl_posix_malloc(mod, malloc_fn)
    _impl_posix_free(mod, free_fn)

def _impl_posix_print_str(mod, str_ty, write_fn):
    _i8, _i32, _i64, _ptr = ll.IntType(8), ll.IntType(32), ll.IntType(64), ll.IntType(8).as_pointer()
    fn = ll.Function(mod, ll.FunctionType(ll.VoidType(), [str_ty]), name="__cx_print_str")
    builder = ll.IRBuilder(fn.append_basic_block("entry"))
    
    # Extract {ptr, len}
    arg_s = fn.args[0]
    p_data = builder.extract_value(arg_s, 0)
    u_len  = builder.extract_value(arg_s, 1)
    
    # write(1, p_data, u_len)
    builder.call(write_fn, [_i32(1), p_data, u_len])
    
    # write(1, "\n", 1)
    nl_ptr = builder.alloca(_i8)
    builder.store(_i8(10), nl_ptr)
    builder.call(write_fn, [_i32(1), nl_ptr, _i64(1)])
    
    builder.ret_void()

def _impl_posix_print_int(mod, write_fn, sprintf_fn):
    _i8, _i32, _i64, _ptr = ll.IntType(8), ll.IntType(32), ll.IntType(64), ll.IntType(8).as_pointer()
    fn = ll.Function(mod, ll.FunctionType(ll.VoidType(), [_i32]), name="__cx_print_int")
    builder = ll.IRBuilder(fn.append_basic_block("entry"))
    
    fmt = _get_or_create_fmt(mod, ".str_fmt_int", "%d\0")
    fmt_ptr = builder.bitcast(fmt, _ptr)
    buf = builder.alloca(ll.ArrayType(_i8, 32))
    buf_ptr = builder.bitcast(buf, _ptr)
    
    # n = sprintf(buf, "%d", value)
    n_chars = builder.call(sprintf_fn, [buf_ptr, fmt_ptr, fn.args[0]])
    n_chars64 = builder.sext(n_chars, _i64)
    
    # write(1, buf, n)
    builder.call(write_fn, [_i32(1), buf_ptr, n_chars64])
    
    # write(1, "\n", 1)
    nl_ptr = builder.alloca(_i8)
    builder.store(_i8(10), nl_ptr)
    builder.call(write_fn, [_i32(1), nl_ptr, _i64(1)])
    
    builder.ret_void()

def _impl_posix_malloc(mod, malloc_fn):
    _i64 = ll.IntType(64)
    _ptr = ll.IntType(8).as_pointer()
    fn = ll.Function(mod, ll.FunctionType(_ptr, [_i64]), name="__cx_malloc")
    builder = ll.IRBuilder(fn.append_basic_block("entry"))
    res = builder.call(malloc_fn, [fn.args[0]])
    builder.ret(res)

def _impl_posix_free(mod, free_fn):
    _ptr = ll.IntType(8).as_pointer()
    fn = ll.Function(mod, ll.FunctionType(ll.VoidType(), [_ptr]), name="__cx_free")
    builder = ll.IRBuilder(fn.append_basic_block("entry"))
    builder.call(free_fn, [fn.args[0]])
    builder.ret_void()

# =============================================================================
# HELPERS
# =============================================================================

def _get_or_create_fmt(mod: ll.Module, name: str, value: str) -> ll.GlobalVariable:
    if name in mod.globals:
        return mod.globals[name]
    _i8 = ll.IntType(8)
    fmt = ll.GlobalVariable(mod, ll.ArrayType(_i8, len(value)), name=name)
    fmt.initializer = ll.Constant(ll.ArrayType(_i8, len(value)), bytearray(value, "utf-8"))
    fmt.linkage = "internal"
    return fmt
