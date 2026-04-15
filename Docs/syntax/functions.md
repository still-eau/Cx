# Fonctions et Lambdas

Les fonctions sont les unites de base de la logique en Cx. Elles sont flexibles, supportent les parametres par defaut et peuvent echouer de maniere explicite.

## Declaration

```cx
func nom(qual::Type param = defaut) -> ReturnType {
    // corps
}
```

```cx
func addition(set::int a, set::int b) -> int {
    return a + b;
}
```

## Valeurs de Retour

- `-> void` : La fonction ne retourne rien (optionnel).
- `-> (T1, T2)` : Retourne un tuple de valeurs.
- `-> T | fail E` : La fonction peut soit retourner un succes (`T`), soit echouer avec une erreur (`E`).

```cx
func diviser(set::int a, set::int b) -> (int, int) {
    return (a / b, a % b);
}
```

## Parametres par Defaut

Les fonctions peuvent avoir des valeurs de parametre par defaut, ce qui les rend optionnelles lors de l'appel.

```cx
func saluer(set::str message = "Bonjour") -> void {
    print(message);
}
```

## Fonctions de Premiere Classe

Les fonctions peuvent etre stockees dans des variables et passees comme arguments.

```cx
set::func(int, int) -> int operation = addition;
```

## Lambdas

Syntaxe legere pour les fonctions anonymes : `|params| expression`.

```cx
set::func(int) -> int multiplier = |x| x * 2;
```

## Gestion des Erreurs

Cx utilise un systeme explicite pour les fonctions pouvant echouer.

- `fail valeur` : Interrompt la fonction et retourne une erreur.
- `try appel()` : Propage l'erreur a l'appelant.
- `appel() catch err { ... }` : Gere l'erreur localement.

```cx
func lire_fichier(set::str path) -> str | fail str {
    if !existe(path) {
        fail "Fichier introuvable";
    }
    return contenu(path);
}
```