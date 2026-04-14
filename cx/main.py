"""Cx compiler CLI entry point.

Orchestrates the entire compilation pipeline:
Lex -> Parse -> Semantic Check -> AST Opt -> IR Gen -> LLVM Opt -> Link
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

# On insère le dossier parent dans le sys.path explicitemment
# pour éviter les erreurs d'import quand la CLI est lancée comme exécutable gelé.
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

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="cx",
    help="Cx Programming Language Compiler (LLVM backend)",
    no_args_is_help=True,
    add_completion=False,
)

console = Console(stderr=True)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def _run_pipeline(opts: CompileOptions, logger: CompileLogger, check_only: bool = False, ast_only: bool = False) -> None:
    # 0. Read file
    if not os.path.exists(opts.source_file):
        console.print(f"[bold red]error[/bold red]: file not found: {opts.source_file}")
        sys.exit(1)
        
    with open(opts.source_file, "r", encoding="utf-8") as f:
        source_code = f.read()
        
    reporter = ErrorReporter(opts.source_file, source_code)
    
    try:
        # 1. Lex
        logger.phase("lex")
        lexer = Lexer(source_code)
        tokens = lexer.tokenize()
        
        # 2. Parse
        logger.phase("parse")
        parser = Parser(tokens, opts.source_file, source_code, reporter=reporter)
        program = parser.parse()
        reporter.abort_if_errors()

        if ast_only:
            from rich.pretty import pprint
            pprint(program)
            logger.done("AST dumped.")
            return
        
        # 3. Semantic Analysis
        logger.phase("check")
        checker = TypeChecker(reporter)
        checker.check(program)
        reporter.abort_if_errors()

        if check_only:
            logger.done("Syntax and types are correct.")
            return
        
        # 4. AST Optimization
        logger.phase("opt")
        pm = build_pipeline(opts.llvm_opt, logger)
        pm.run(program)
        
        # 5. HIR Generation
        logger.phase("hir")
        ir_builder = IRBuilder(name=Path(opts.source_file).stem)
        hir_mod = ir_builder.build(program)
        
        # 6. LLVM Codegen & Optimization
        logger.phase("codegen", f"level O{opts.llvm_opt}")
        codegen = LLVMCodegen(opts, module_name=Path(opts.source_file).stem)
        llvm_ir_str = codegen.lower(hir_mod)

        out_ext = opts.derived_output()

        if opts.emit == EmitKind.IR:
            dst = out_ext + ".ll"
            with open(dst, "w", encoding="utf-8") as f:
                f.write(llvm_ir_str)
            logger.done(dst)
            return

        if opts.emit == EmitKind.ASM:
            dst = out_ext + ".s"
            codegen.emit_asm(llvm_ir_str, dst)
            logger.done(dst)
            return
            
        # Emit object file (temporary if building executable)
        obj_file = out_ext + ".o" if opts.emit == EmitKind.OBJ else tempfile.mktemp(suffix=".o")
        codegen.emit_object(llvm_ir_str, obj_file)
        
        if opts.emit == EmitKind.OBJ:
            logger.done(obj_file)
            return
            
        # 7. Link to executable
        linker = RelocatableLinker(opts, logger)
        exe_file = out_ext + (".exe" if os.name == "nt" else "")
        linker.link(obj_file, exe_file)
        
        # Cleanup temp obj
        if os.path.exists(obj_file):
            os.remove(obj_file)

        logger.done(exe_file)
        
        # 8. Run generated binary
        if opts.run_after:
            console.print(f"[dim]Running {exe_file}...[/dim]\n")
            os.system(os.path.abspath(exe_file))
            
    except CxError as e:
        if e.loc:
            reporter.error(str(e), e.loc)
            reporter.abort_if_errors()
        else:
            console.print(f"[bold red]Compiler Error[/bold red]: {e}")
            sys.exit(1)


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------

@app.command()
def build(
    source_file: str = typer.Argument(..., help="Main .cx file to compile"),
    output: str      = typer.Option("", "-o", "--output", help="Output file name"),
    opt_level: str   = typer.Option("O2", "-O", help="Optimization level (O0, O1, O2, O3, Os)"),
    emit: str        = typer.Option("exe", "--emit", help="Emit kind: exe, obj, asm, ir"),
    verbose: bool    = typer.Option(False, "-v", "--verbose", help="Show timings and phase info"),
) -> None:
    """Compile a Cx source file."""
    opts = CompileOptions(
        source_file=source_file,
        output=output,
        opt_level=CompileOptions.from_opt_string(opt_level),
        emit=EmitKind(emit.lower()),
        verbose=verbose,
    )
    logger = CompileLogger(verbose)
    _run_pipeline(opts, logger)


@app.command()
def run(
    source_file: str = typer.Argument(..., help="Main .cx file to compile and run"),
    opt_level: str   = typer.Option("O2", "-O", help="Optimization level"),
    verbose: bool    = typer.Option(False, "-v", "--verbose", help="Show compilation phases"),
) -> None:
    """Compile and immediately execute a Cx source file."""
    opts = CompileOptions(
        source_file=source_file,
        opt_level=CompileOptions.from_opt_string(opt_level),
        emit=EmitKind.EXE,
        verbose=verbose,
        run_after=True,
    )
    logger = CompileLogger(verbose)
    _run_pipeline(opts, logger)


@app.command()
def check(
    source_file: str = typer.Argument(..., help="Main .cx file to check (no codegen)"),
    verbose: bool    = typer.Option(False, "-v", "--verbose", help="Show phases info"),
) -> None:
    """Check a Cx source file for errors without compiling it."""
    opts = CompileOptions(
        source_file=source_file,
        emit=EmitKind.IR, # dummy
        verbose=verbose,
    )
    logger = CompileLogger(verbose)
    _run_pipeline(opts, logger, check_only=True)


@app.command()
def ast(
    source_file: str = typer.Argument(..., help="Main .cx file to dump AST for"),
    verbose: bool    = typer.Option(False, "-v", "--verbose", help="Show phases info"),
) -> None:
    """Parse a Cx source file and print its Abstract Syntax Tree."""
    opts = CompileOptions(
        source_file=source_file,
        emit=EmitKind.IR, # dummy
        verbose=verbose,
    )
    logger = CompileLogger(verbose)
    _run_pipeline(opts, logger, ast_only=True)


@app.command()
def version() -> None:
    """Print the compiler version."""
    try:
        from cx.__version__ import __version__
    except ImportError:
        __version__ = "unknown"
    console.print(f"Cx Compiler [bold cyan]v{__version__}[/bold cyan]")


@app.command()
def init(
    name: str = typer.Argument(..., help="Name of the project to initialize"),
) -> None:
    """Initialize a new Cx project directory with a default template."""
    project_dir = Path(name)
    if project_dir.exists():
        console.print(f"[bold red]error[/bold red]: directory '{name}' already exists.")
        sys.exit(1)
        
    try:
        project_dir.mkdir()
        src_dir = project_dir / "src"
        src_dir.mkdir()
        
        main_file = src_dir / "main.cx"
        main_file.write_text('// The entry point to your program\nfunc main() {\n    // Your code here\n}\n', encoding="utf-8")
        
        gitignore = project_dir / ".gitignore"
        gitignore.write_text("/build/\n*.o\n*.exe\n*.ll\n*.s\n", encoding="utf-8")
        
        console.print(f"[bold green]Created[/bold green] application '{name}'")
    except Exception as e:
        console.print(f"[bold red]error[/bold red]: failed to create project: {e}")
        sys.exit(1)


if __name__ == "__main__":
    app()
