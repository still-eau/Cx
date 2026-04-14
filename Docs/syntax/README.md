# Cx

Cx est un langage bas niveau a syntaxe moderne.

Son objectif : **peu de concepts, tout est possible**.

---

## Les concepts du langage

Cx n'a que ces elements :

| Categorie     | Ce qu'il y a |
|---------------|--------------|
| Variables     | `set`, `const` |
| Types         | `int` `uint` `flt` `dbl` `char` `str` `bool` `null` `void` |
| Modificateurs | `[long]` `[short]` `[ptr]` `[opt]` |
| Donnees       | `obj`, `arr`, `enum` |
| Comportement  | `func`, `self` |
| Controle      | `if`, `for`, `match`, `break`, `continue` |
| Erreurs       | `fail`, `catch`, `try` |
| Modules       | `module`, `@import`, `pub` |
| Memoire       | `alloc`, `free`, `cast`, `sizeof`, `@unsafe` |
| Attributs     | `@inline`, `@extern`, `@noreturn`, `@unsafe` |

**C'est tout.**

`vec`, `map`, `string_builder`, les algorithmes, les structures de donnees : tout ca c'est de la bibliotheque standard, pas du langage.

---

## Fichiers de reference

- [variables.md](./variables.md) : `set` et `const`
- [types.md](./types.md) : types primitifs, `obj`, `arr`, `enum`
- [functions.md](./functions.md) : `func`, `self`, erreurs
- [control_flow.md](./control_flow.md) : `if`, `for`, `match`
- [memory.md](./memory.md) : pointeurs, allocation, `@unsafe`
- [operators.md](./operators.md) : operateurs
- [modules.md](syntax/modules.md) : `@import`, `module`, `pub`
