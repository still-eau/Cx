"""Générateur d'installation ultra-simple et robuste pour Cx Compiler."""

import sys
import os
import shutil
from pathlib import Path
from cx_Freeze import setup, Executable

# ---------------------------------------------------------------------------
# Nettoyage optionnel
# ---------------------------------------------------------------------------
if "--clean" in sys.argv:
    sys.argv.remove("--clean")
    for d in ["build", "dist"]:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"[+] Dossier {d} nettoyé.")

# ---------------------------------------------------------------------------
# Récupération de la version
# ---------------------------------------------------------------------------
# On lit __version__.py dynamiquement sans importer tout le package
version_dict = {}
with open("cx/__version__.py", "r", encoding="utf-8") as f:
    exec(f.read(), version_dict)
version = version_dict["__version__"]
print(f"[+] Construction du compilateur Cx v{version}")

# ---------------------------------------------------------------------------
# Gestion de l'icône
# ---------------------------------------------------------------------------
icon_path = None
if os.path.exists("assets/logo.ico"):
    icon_path = "assets/logo.ico"
elif os.path.exists("assets/logo.cx.png"):
    try:
        from PIL import Image
        img = Image.open("assets/logo.cx.png")
        img.save("assets/logo.ico", format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (32, 32)])
        icon_path = "assets/logo.ico"
        print("[+] Icône logo.ico générée avec succès.")
    except ImportError:
        print("[-] Pillow non installé, l'exécutable n'aura pas d'icône.")

# ---------------------------------------------------------------------------
# Paramètres d'exécutable (cx_Freeze)
# ---------------------------------------------------------------------------

build_exe_options = {
    # Emballe explicitement tout le package "cx", "typer" et "llvmlite"
    "packages": ["cx", "typer", "rich", "llvmlite"],
    
    # Exclusions pour alléger le fichier final
    "excludes": ["tkinter", "unittest", "email", "http", "xml", "pydoc"],
    "zip_include_packages": ["*"],
    "zip_exclude_packages": ["llvmlite"],
}

bdist_msi_options = {
    "upgrade_code": "{A123B456-C789-0123-D456-E789F0123456}",
    "add_to_path": True,
    # S'installera dans C:\Program Files\CxCompiler
    "initial_target_dir": r"[ProgramFilesFolder]\CxCompiler",
    
    # Ces infos dictent ce qui apparaît quand on clique sur le MSI (nom du produit, etc.)
    "summary_data": {
        "author": "Stilau",
        "comments": "The native compiler for the Cx Programming Language.",
        "keywords": "compiler, cx, llvm",
    },
    
    # Pour s'assurer que Windows affiche bien "Cx Compiler" si possible au lieu 
    # de chemins aléatoires dans la demande d'élévation UAC (lors de l'installation).
    "all_users": True,
}

# ---------------------------------------------------------------------------
# Déclaration de l'exécutable final "cx.exe"
# ---------------------------------------------------------------------------
executables = [
    Executable(
        script="cx/main.py",
        target_name="cx.exe",
        base=None, 
        icon=icon_path,
        shortcut_name="Cx Compiler",
        shortcut_dir="ProgramMenuFolder",
        # Force l'exécutable cx autonome à demander l'admin si nécessaire ? (Non, pas un compilo)
        # uac_admin=False
    )
]

# ---------------------------------------------------------------------------
# Lancement
# ---------------------------------------------------------------------------
setup(
    name="Cx Compiler",           # Le nom officiel qui apparaitra partout et dans l'UAC de l'installeur MSI
    version=version,
    description="Le compilateur haute performance natif pour le langage Cx.",
    author="Stilau",
    options={
        "build_exe": build_exe_options,
        "bdist_msi": bdist_msi_options,
    },
    executables=executables,
)
