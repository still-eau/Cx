"""Script de construction du fichier d'installation (.msi) du compilateur Cx.

Ce script utilise `cx_Freeze` pour transformer le code Python en
exécutable natif (cx.exe), puis génère un installeur Windows (.msi).

Prérequis :
    pip install cx_Freeze pillow

Utilisation :
    python scripts/build_msi.py bdist_msi
"""

import sys
import os
from pathlib import Path

# On va essayer de convertir le logo .png en .ico (si Pillow est installé)
# afin d'avoir une belle icône pour notre exécutable et l'installeur.
try:
    from PIL import Image
    def prepare_assets():
        root = Path(__file__).resolve().parent.parent
        png_path = root / "assets" / "logo.cx.png"
        ico_path = root / "assets" / "logo.ico"
        if png_path.exists() and not ico_path.exists():
            img = Image.open(png_path)
            img.save(ico_path, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (32, 32)])
            print(f"[+] Icône générée: {ico_path}")
        return str(ico_path) if ico_path.exists() else None
except ImportError:
    def prepare_assets():
        print("[-] Pillow n'est pas installé, le logo PNG ne sera pas converti en ICO.")
        return None

try:
    from cx_Freeze import setup, Executable
except ImportError:
    print("Erreur: cx_Freeze n'est pas installé.")
    print("Installez-le avec : pip install cx_Freeze")
    sys.exit(1)


# -- Configuration des chemins ------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
MAIN_SCRIPT = ROOT_DIR / "cx" / "main.py"
icon_path = prepare_assets()

# -- Options cx_Freeze -------------------------------------------------------
build_exe_options = {
    # On ajoute nos packages vitaux
    "packages": ["typer", "rich", "llvmlite"],
    "excludes": ["tkinter", "unittest"], # Allège le binaire final
    "include_files": [],
}

# Configuration spécifiques pour créer un installeur MSI
# "ProgramFilesFolder" permet d'installer dans C:\Program Files\StilauSuite\Cx
bdist_msi_options = {
    "upgrade_code": "{A123B456-C789-0123-D456-E789F0123456}",  # Garder le même pour les mises à jour
    "add_to_path": True,       # Modifie la variable PATH de Windows !
    "initial_target_dir": r"[ProgramFilesFolder]\StilauSuite\Cx",
    "summary_data": {
        "author": "Stilau",
        "comments": "The Cx Programming Language Compiler",
        "keywords": "compiler, cx, llvm",
    }
}

# Définition de l'exécutable
executables = [
    Executable(
        script=str(MAIN_SCRIPT),
        target_name="cx.exe",
        base=None,  # "Console" base (affiche le terminal), pas "Win32GUI"
        icon=icon_path, # Utilise le joli logo
        shortcut_name="Cx Compiler",
        shortcut_dir="ProgramMenuFolder"
    )
]

# -- Lancement du setup ------------------------------------------------------
setup(
    name="Cx Compiler",
    version="0.1.0",
    description="Le compilateur natif ultra-optimisé pour le langage Cx",
    author="Stilau",
    options={
        "build_exe": build_exe_options,
        "bdist_msi": bdist_msi_options,
    },
    executables=executables
)
