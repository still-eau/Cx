"""Script de désinstallation du compilateur Cx.

Lance l'assistant de désinstallation Windows (msiexec)
pour le package MSI installé par build_msi.py.
"""

import os
import sys
import subprocess

UUID = "{A123B456-C789-0123-D456-E789F0123456}"

def uninstall():
    print("========================================")
    print("Désinstallation du compilateur Cx...")
    print("========================================")
    print("Ouverture de l'assistant Windows...")
    
    # msiexec /x uuid déclenche la désinstallation standard via l'UI Windows
    try:
        subprocess.run(["msiexec", "/x", UUID], check=True)
        print("Désinstallation terminée (ou annulée par l'utilisateur).")
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de la désinstallation : {e}")
        sys.exit(1)
    except FileNotFoundError:
        print("msiexec.exe introuvable. Système non supporté ?")
        sys.exit(1)

if __name__ == "__main__":
    uninstall()
