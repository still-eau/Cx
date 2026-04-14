# Generiques

Les generiques permettent d'ecrire une fonction ou une structure qui fonctionne pour n'importe quel type.

---

## Fonction generique

```cx
func max<T>(set::T a, set::T b) -> T {
    if a > b { return a; }
    return b;
}

set::int m = max(3, 7);       // T = int, automatically inferred
set::flt f = max(1.5, 2.5);   // T = flt
```

---

## Structure generique

```cx
obj Pair<A, B> {
    set::A first;
    set::B second;
}

set::Pair<str, int> score = Pair { first = "Stilau", second = 42 };
print(score.first);
```

---

## Enum generique

```cx
enum Option<T> {
    Some { set::T value; },
    None,
}

set::Option<int> x = Option::Some { value = 99 };

match x {
    Option::Some { value } => { print(value); }
    Option::None           => { print("none"); }
}
```

`Option<T>` est integre a la bibliotheque standard. C'est la facon idiomatique de representer une valeur optionnelle quand `[opt]` sur un primitif ne suffit pas.

---

## Contraintes : `where`

Restreindre les types acceptes pour T.

```cx
func sum<T>(set::T a, set::T b) -> T where T: Numeric {
    return a + b;
}
```

| Contrainte  | Signification |
|-------------|---------------|
| `Numeric`   | `int`, `uint`, `flt`, `dbl` |
| `Eq`        | Supporte `==` et `!=` |
| `Ord`       | Supporte `<`, `>`, `<=`, `>=` |

> Sans contrainte, le compilateur accepte n'importe quel T mais ne permet que les operations communes a tous les types (affectation, passage en argument).
