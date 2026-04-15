# Types de Donnees

Cx propose des types primitifs simples et des constructions composites puissantes pour organiser vos donnees.

## Modificateurs de Type

Les types de base peuvent etre modifies pour preciser leur taille ou leur comportement. Les modificateurs se placent entre crochets `[]` apres le type.

| Modificateur | Description |
|--------------|-------------|
| `[long]`     | Etend la taille (ex: `int[long]` est un entier 64-bits) |
| `[short]`    | Reduit la taille (ex: `int[short]` est un entier 16-bits) |
| `[ptr]`      | Definit un pointeur vers le type |
| `[opt]`      | Indique que la valeur peut etre `null` |

```cx
set::int[long] large_value = 1234567890;
set::int[ptr]  p_val = null;
```

## Objets : `obj`

Les objets regroupent des donnees (champs) et des comportements (methodes).

```cx
obj Entity {
    set::str name;
    set::int health = 100;

    func is_alive() -> bool {
        return self.health > 0;
    }
}
```

- `self` : Refere a l'instance actuelle a l'interieur d'une methode.
- L'initialisation se fait via une syntaxe de bloc : `Entity { name = "Hero" }`.

## Tableaux : `arr`

Les tableaux ont une taille fixe connue a la compilation.

```cx
arr::int|4| scores = (10, 20, 30, 40);
```

- Syntaxe : `arr::Type|Capacite|`.
- Initialisation : `(val1, val2, ...)`.
- Acces : `scores[0]`, `scores.len`.

## Enumerations : `enum`

Les enums permettent de definir une somme de types. Chaque variante peut optionnellement contenir des champs.

```cx
enum Status {
    Active,
    Inactive,
    Error { set::str code; }
}
```

- Les enums sont parfaits pour le pattern matching (voir [Flux de Controle](./control_flow.md)).

## Alias : `alias`

Permet de creer un nouveau nom pour un type existant.

```cx
alias UserId = uint;
set::UserId id = 101;
```