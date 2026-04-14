"""System linker invocation using Clang or GCC.

In v0.1 we rely on the host system's C compiler (Clang preferably, or gcc)
to link the LLVM-generated object file with the C standard library.
"""

from __future__ import annotations

import os
import subprocess
from typing import List

from ..config import CompileOptions
from ..utils.logger import CompileLogger
from ..utils.errors import CxError


class RelocatableLinker:
    def __init__(self, opts: CompileOptions, logger: CompileLogger):
        self.opts = opts
        self.logger = logger
        self.cc = self._find_cc()

    def _find_cc(self) -> str:
        # Prefer clang, fallback to gcc
        for cc in ("clang", "gcc", "ld"):
            try:
                # Just check if it's in PATH
                subprocess.run([cc, "--version"], capture_output=True, check=True)
                return cc
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        raise CxError("System CC (clang/gcc) not found in PATH for linking.")

    def link(self, input_obj: str, output_exe: str) -> None:
        self.logger.phase("link", f"using {self.cc}")
        
        args: List[str] = [self.cc, input_obj, "-o", output_exe]
        
        # Adding m for math library (used by standard double operations) on Linux/mac
        if os.name != 'nt':
            args.append("-lm")
        try:
            res = subprocess.run(args, capture_output=True, text=True, check=True)
            if res.stderr and self.opts.verbose:
                self.logger.info(res.stderr)
        except subprocess.CalledProcessError as e:
            self.logger.warn(f"Linker failed with code {e.returncode}")
            err_msg = e.stderr or ""
            
            # Gestion amicale de l'erreur classique sous Windows (LLVM standalone vs MSVC)
            if os.name == 'nt' and ("msvc-not-found" in err_msg or "program not executable" in err_msg):
                raise CxError(
                    "Impossible de lier l'exécutable sous Windows.\n\n"
                    "Explication :\n"
                    "Bien que Clang soit installé, LLVM sur Windows ne fournit pas la bibliothèque standard C (libc) "
                    "ni les outils de linkage de base. Clang a besoin du SDK Windows et des librairies Microsoft.\n\n"
                    "Solution :\n"
                    "Installez 'Visual Studio Build Tools' (la charge de travail 'Développement Desktop en C++'),\n"
                    "OU installez MinGW-w64 via MSYS2 et utilisez GCC.\n\n"
                    f"Détail technique (Clang):\n{err_msg.strip()}"
                )
            
            raise CxError(f"Linking error:\n{err_msg}")
