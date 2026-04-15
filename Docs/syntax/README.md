# Reference du Langage Cx

Cx est un langage de programmation systeme moderne concu pour la performance, la clarite et la simplicite. Il combine une syntaxe expressive avec un controle precis sur la memoire et les ressources.

## Principes Directeurs

- Simplicite : Un nombre minimal de concepts puissants.
- Securite : Gestion explicite des erreurs et blocs unsafe delimites.
- Performance : Compilation native via LLVM sans garbage collector.

## Table des Matieres

### Fondations
- [Variables et Constantes](./variables.md) : `set`, `const`, inference de type.
- [Types Primitifs](./types.md) : `int`, `uint`, `flt`, `dbl`, `char`, `str`, `bool`.
- [Operateurs](./operators.md) : Arithmetique, comparaison, logique, morsure.

### Structures de Donnees
- [Objets (structs)](./types.md#objets) : `obj`, champs et methodes.
- [Enums](./types.md#enums) : Variants avec donnees et pattern matching.
- [Tableaux](./types.md#tableaux) : `arr`, types fixes et slices.

### Comportement et Logique
- [Fonctions](./functions.md) : `func`, lambdas, parametres nommes.
- [Flux de Controle](./control_flow.md) : `if`, `for`, `match`.
- [Gestion des Erreurs](./errors.md) : `try`, `catch`, `fail`.

### Systeme et Metaprogrammation
- [Modules et Visibilite](./modules.md) : `module`, `@import`, `pub`.
- [Generics](./generics.md) : Parametrisation de type et clauses `where`.
- [Memoire et Unsafe](./memory.md) : `alloc`, `free`, pointeurs, `@unsafe`.
- [Attributs et Directives](./attributes.md) : `@extern`, `@inline`, `@when`.
