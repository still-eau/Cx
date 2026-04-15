# Directives et Attributs

Les directives commencent par `@` et fournissent des instructions speciales au compilateur.

## Attributs de Fonction

Ces attributs modifient la generation de code ou l'analyse statique d'une fonction.

| Attribut | Description |
|----------|-------------|
| `@inline` | Suggere au compilateur d'integrer le code de la fonction directement. |
| `@noreturn` | Indique que la fonction ne rend jamais le contrôle (ex: panic, exit). |
| `@extern("nom")` | Lie la fonction a un symbole externe (souvent en C). Pas de corps autorise. |
| `@unsafe` | Autorise les operations non securisees dans tout le corps de la fonction. |

```cx
@extern("puts")
func c_puts(set::str s) -> int;

@inline
func multiplier(set::int x) -> int {
    return x * 2;
}
```

## Directives Speciales

### `@unsafe { ... }`

Le mot-cle `@unsafe` peut egalement etre utilise pour marquer un bloc de code specifique au sein d'une fonction comme non securise.

```cx
func bidouille() -> void {
    @unsafe {
        // Arithmetique de pointeurs autorisee ici
    }
}
```

### `@when(condition) { ... }`

Permet de realiser une compilation conditionnelle selon la cible ou l'environnement.

```cx
@when(target == "linux") {
    // Code specifique Linux
}
```

### `@import`

Utilise pour importer des modules (voir [Modules](./modules.md)).
