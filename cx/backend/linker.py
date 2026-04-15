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
        # Prefer clang, fallback to gcc/cc/ld
        candidates = ["clang", "gcc", "cc", "ld"]
        if os.name == "nt":
            candidates.insert(0, "clang.exe")
            candidates.extend(["gcc.exe", "lld-link.exe"])
            
        for cc in candidates:
            try:
                # Just check if it's in PATH
                subprocess.run([cc, "--version" if "link" not in cc else "/?"], 
                               capture_output=True, check=True, text=True, shell=(os.name == 'nt'))
                return cc
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        raise CxError("System Linker (clang/gcc) not found in PATH for linking. Please install LLVM or GCC.")

    def link(self, input_objs: List[str], output_exe: str) -> None:
        """Links multiple object files into a single executable."""
        self.logger.phase("link", f"using {self.cc}")
        
        args: List[str] = [self.cc]
        args.extend(input_objs)
        args.extend(["-o", output_exe])
        
        # OS-specific library linking
        if os.name == 'nt':
            # On Windows, we need standard system libs for Win32 API calls (kernel32, user32)
            # We also explicitly tell clang to use the msvc environment if possible
            args.extend(["-lkernel32", "-luser32"])
            if "clang" in self.cc:
                # Helps finding MSVC libs if they are in standard paths
                args.append("-Xlinker")
                args.append("/subsystem:console")
        else:
            # On Linux/Posix, we need libc and libm
            # -no-pie is often needed for simple binaries depending on the distro
            args.extend(["-lc", "-lm", "-no-pie"])

        try:
            res = subprocess.run(args, capture_output=True, check=True, text=True)
            if res.stderr and self.opts.verbose:
                self.logger.info(res.stderr)
        except subprocess.CalledProcessError as e:
            self.logger.warn(f"Linker failed with code {e.returncode}")
            err_msg = e.stderr if e.stderr else ""
            
            # Special handling for Windows linking errors (common in standard LLVM installs)
            if os.name == 'nt' and ("msvc-not-found" in err_msg or "program not executable" in err_msg):
                raise CxError(
                    "Linker Error: Cannot link the executable on Windows.\n\n"
                    "Background:\n"
                    "Clang on Windows requires the Microsoft Visual C++ (MSVC) runtime and SDK libraries "
                    "to produce functional executables.\n\n"
                    "Solution:\n"
                    "- Install 'Visual Studio Build Tools' (Desktop development with C++)\n"
                    "- OR use MinGW-w64/GCC as an alternative linker."
                )
            
            raise CxError(f"Linking error:\n{err_msg}")
