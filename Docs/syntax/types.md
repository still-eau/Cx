# Types

Cx a trois constructions de types composites : `obj`, `arr`, `enum`.
Tout le reste (vec, map, queue...) vient de la bibliotheque standard.

---

## Tableaux fixes : `arr`

Bloc memoire contigu de taille fixe, connue a la compilation.

```cx
arr::<type>|<capacity>| <name> = (<val1>, <val2>, ...);
```

```cx
arr::str|3| fruits = ("apple", "banana", "cherry");
arr::int|8| scores;                      // zero-initialized

set::str first  = fruits[0];
fruits[1] = "mango";
set::uint length = fruits.len;           // 3, compile-time constant
```

> Acces hors limites avec indice constant : erreur de compilation.
> Acces hors limites avec indice dynamique : panic a l'execution.

---

## Structures : `obj`

Regroupe des donnees et des fonctions qui les manipulent.

```cx
obj Player {
    set::str  name;
    set::int  health  = 100;
    set::flt  speed   = 1.0;

    func greet() -> str {
        return "I am " + self.name;
    }

    func take_damage(set::int amount) -> void {
        self.health -= amount;
    }
}
```

Instanciation :

```cx
set::Player hero = Player {
    name   = "Stilau",
    health = 100,
    speed  = 1.5,
};

hero.take_damage(30);
set::str msg = hero.greet();
```

> `self` designe l'instance courante dans une methode. Il ne se declare pas dans les parametres.

---

## Enumerations : `enum`

Ensemble ferme de variantes. Chaque variante peut porter des donnees.

```cx
enum Result {
    Ok    { set::str value; },
    Fail  { set::str reason; },
}

enum Direction { North, South, East, West }
```

Utilisation :

```cx
set::Result r = Result::Ok { value = "done" };

match r {
    Result::Ok   { value }  => { print(value);  }
    Result::Fail { reason } => { print(reason); }
}
```

L'enum est le seul mecanisme de polymorphisme en Cx.
Pas d'heritage, pas d'interfaces : juste des variantes de donnees.

---

## Alias de type

Renomme un type existant. Utile pour la clarte.

```cx
alias Id     = uint;
alias Size   = int[long];

set::Id   entity_id = 42;
set::Size file_size = 1_048_576;
```