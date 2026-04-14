# Cx Compiler

Le compilateur officiel pour le langage de programmation Cx.

## Dépendances

- `llvmlite` : Génération de code système via LLVM
- `lark` : Parsing et construction de l'AST
- `typer` : Création de la CLI
- `rich` : UI CLI

## Installation (Développement)

```bash
pip install -e ".[dev]"
```

## Utilisation

```bash
cx build [fichier]
```
