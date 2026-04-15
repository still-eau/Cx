# Generiques

Les generiques permettent d'ecrire du code reutilisable en parametrant les types.

## Fonctions Generiques

```cx
func id<T>(set::T valeur) -> T {
    return valeur;
}
```

- Syntaxe : `<T, U, ...>` apres le nom de la fonction.
- L'inference de type permet souvent d'appeler la fonction sans specifier explicitement le type.

## Objets et Enums Generiques

```cx
obj Boite<T> {
    set::T contenu;
}

enum Resultat<T, E> {
    Succes { set::T valeur; },
    Erreur { set::E info; }
}
```

## Clauses `where`

Les clauses `where` imposent des contraintes sur les types generiques afin de garantir qu'ils supportent certaines operations.

```cx
func comparer<T>(set::T a, set::T b) -> bool where T: Ord {
    return a > b;
}
```

### Contraintes Courantes

| Contrainte | Description |
|------------|-------------|
| `Numeric`  | Types numeriques (`int`, `flt`, etc.) |
| `Eq`       | Supporte l'egalite (`==`, `!=`) |
| `Ord`       | Supporte la comparaison (`<`, `>`, `<=`, `>=`) |

Si aucune contrainte n'est specifiee, seules les operations de base (copie, affectation) sont autorisees sur le type `T`.
