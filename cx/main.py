"""Cx Compiler CLI entry point.

Orchestrates the entire compilation pipeline:
Lex -> Parse -> Semantic Check -> AST Opt -> IR Gen -> LLVM Opt -> Link
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console

# Ensure we can find the 'cx' package regardless of how we are called.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cx.config import CompileOptions, OptLevel, EmitKind
from cx.utils.logger import CompileLogger
from cx.utils.errors import ErrorReporter, CxError
from cx.frontend.lexer import Lexer
from cx.frontend.parser import Parser
from cx.middleend.semantic.type_checker import TypeChecker
from cx.middleend.optimizer.pass_manager import build_pipeline
from cx.middleend.ir.builder import IRBuilder
from cx.backend.llvm_codegen import LLVMCodegen
from cx.backend.linker import RelocatableLinker
from cx.backend import runtime

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

app     = typer.Typer(name="cx", help="Cx Programming Language Compiler", no_args_is_help=True)
console = Console(stderr=True)


# ---------------------------------------------------------------------------
# Compile Session
# ---------------------------------------------------------------------------

class CompileSession:
    """Orchestrates the lifecycle of a compilation task with robust resource management."""

    def __init__(self, opts: CompileOptions, logger: CompileLogger):
        self.opts     = opts
        self.logger   = logger
        self.reporter = None

    def run(self, check_only: bool = False, ast_only: bool = False) -> None:
        """Executes the compilation pipeline."""
        src_path = Path(self.opts.source_file)
        if not src_path.exists():
            console.print(f"[bold red]error[/bold red]: file not found: {src_path}")
            sys.exit(1)

        source_code = src_path.read_text(encoding="utf-8")
        self.reporter = ErrorReporter(str(src_path), source_code)

        try:
            # 1. Frontend: Lexing & Parsing
            self.logger.phase("parse")
            lexer  = Lexer(source_code)
            parser = Parser(lexer.tokenize(), str(src_path), source_code, reporter=self.reporter)
            program = parser.parse()
            self.reporter.abort_if_errors()

            if ast_only:
                from rich.pretty import pprint
                pprint(program)
                return

            # 2. Middle-end: Semantic Analysis
            self.logger.phase("check")
            checker = TypeChecker(self.reporter)
            checker.check(program)
            self.reporter.abort_if_errors()

            if check_only:
                self.logger.done("Syntax and types are correct.")
                return

            # 3. Middle-end: Optimization & IR Generation
            self.logger.phase("opt")
            pm = build_pipeline(self.opts.llvm_opt, self.logger)
            pm.run(program)

            self.logger.phase("hir")
            ir_builder = IRBuilder(name=src_path.stem)
            hir_mod    = ir_builder.build(program)

            # 4. Backend: LLVM Codegen
            self.logger.phase("codegen", f"O{self.opts.llvm_opt}")
            codegen = LLVMCodegen(self.opts, module_name=src_path.stem)
            llvm_ir = codegen.lower(hir_mod)

            # 5. Output Emission
            self._emit_output(codegen, llvm_ir)

        except CxError as e:
            if e.loc:
                self.reporter.error(str(e), e.loc)
                self.reporter.abort_if_errors()
            else:
                console.print(f"[bold red]Compiler Error[/bold red]: {e}")
                sys.exit(1)

    def _emit_output(self, codegen: LLVMCodegen, llvm_ir: str) -> None:
        """Handles the final emission of IR, ASM, OBJ, or EXE."""
        out_base = self.opts.derived_output()

        # Handle text-based emissions
        if self.opts.emit == EmitKind.IR:
            dst = out_base + ".ll"
            Path(dst).write_text(llvm_ir, encoding="utf-8")
            self.logger.done(dst)
            return

        if self.opts.emit == EmitKind.ASM:
            dst = out_base + ".s"
            codegen.emit_asm(llvm_ir, dst)
            self.logger.done(dst)
            return

        # Handle binary emissions via object files
        with tempfile.TemporaryDirectory(prefix="cx_build_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            
            # 1. Compile User Code to Object
            user_obj = tmp_path / "user.o"
            codegen.emit_object(llvm_ir, str(user_obj))

            if self.opts.emit == EmitKind.OBJ:
                final_obj = out_base + ".o"
                import shutil
                shutil.copy(user_obj, final_obj)
                self.logger.done(final_obj)
                return

            # 2. Compile Modular Runtime to Object
            self.logger.phase("runtime", "building modular standard library")
            os_name = "nt" if os.name == "nt" else "posix"
            rt_mod = runtime.get_runtime_module(codegen.module.triple, codegen.module.data_layout, os_name=os_name)
            rt_obj = tmp_path / "runtime.o"
            codegen.emit_object(str(rt_mod), str(rt_obj))

            # 3. Link Executable
            exe_file = out_base + (".exe" if os.name == "nt" else "")
            linker = RelocatableLinker(self.opts, self.logger)
            linker.link([str(user_obj), str(rt_obj)], exe_file)
            
            self.logger.done(exe_file)

            if self.opts.run_after:
                self._run_binary(exe_file)

    def _run_binary(self, path: str) -> None:
        """Executes the produced binary."""
        full_path = str(Path(path).absolute())
        console.print(f"[dim]Executing {path}...[/dim]\n")
        # Use subprocess.call to ensure it waits for the process to finish
        import subprocess
        subprocess.call([full_path])


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------

@app.command()
def build(
    source_file: str = typer.Argument(..., help="Main .cx file to compile"),
    output: str      = typer.Option("", "-o", "--output", help="Output filename"),
    opt_level: str   = typer.Option("O2", "-O", help="Opt level (O0, O1, O2, O3, Os)"),
    emit: str        = typer.Option("exe", "--emit", help="Emit kind: exe, obj, asm, ir"),
    verbose: bool    = typer.Option(False, "-v", "--verbose", help="Show timings and phase info"),
) -> None:
    """Compile a Cx source file into an executable or intermediate format."""
    opts = CompileOptions(
        source_file=source_file,
        output=output,
        opt_level=CompileOptions.from_opt_string(opt_level),
        emit=EmitKind(emit.lower()),
        verbose=verbose,
    )
    Session = CompileSession(opts, CompileLogger(verbose))
    Session.run()

@app.command()
def run(
    source_file: str = typer.Argument(..., help="Source file to compile and run"),
    opt_level: str   = typer.Option("O2", "-O", help="Optimization level"),
    verbose: bool    = typer.Option(False, "-v", "--verbose"),
) -> None:
    """Compile and immediately execute a Cx source file."""
    opts = CompileOptions(
        source_file=source_file,
        opt_level=CompileOptions.from_opt_string(opt_level),
        emit=EmitKind.EXE,
        verbose=verbose,
        run_after=True,
    )
    Session = CompileSession(opts, CompileLogger(verbose))
    Session.run()

@app.command()
def check(source_file: str = typer.Argument(...), verbose: bool = typer.Option(False, "-v")) -> None:
    """Check a source file for errors without code generation."""
    opts = CompileOptions(source_file=source_file, verbose=verbose)
    Session = CompileSession(opts, CompileLogger(verbose))
    Session.run(check_only=True)

@app.command()
def version() -> None:
    """Print the compiler version."""
    from cx.__version__ import __version__
    console.print(f"Cx Compiler [bold cyan]v{__version__}[/bold cyan]")

@app.command()
def init(name: str = typer.Argument(..., help="New project name")) -> None:
    """Initialize a new Cx project template."""
    project_dir = Path(name)
    if project_dir.exists():
        console.print(f"[bold red]error[/bold red]: directory '{name}' already exists.")
        sys.exit(1)
        
    project_dir.mkdir()
    (project_dir / "src").mkdir()
    (project_dir / "src" / "main.cx").write_text('func main() {\n    print("Hello, Cx!");\n}\n')
    (project_dir / ".gitignore").write_text("/build/\n*.o\n*.exe\n*.ll\n*.s\n")
    console.print(f"[bold green]Initialized[/bold green] project '{name}'")

if __name__ == "__main__":
    app()
