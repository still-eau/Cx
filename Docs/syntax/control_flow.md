# Flux de controle

Trois constructions. C'est tout.

---

## `if` / `else`

Pas de parentheses. Accolades obligatoires.

```cx
if x > 0 {
    print("positive");
} else if x < 0 {
    print("negative");
} else {
    print("zero");
}
```

`if` peut etre une expression. Les deux branches doivent avoir le meme type.

```cx
set::str label = if score > 50 { "pass" } else { "fail" };
```

---

## `for` : la seule boucle

`for` couvre tous les cas de boucle.

### Plage numerique

```cx
for i in 0..9   { print(i); }    // [0, 9] inclus
for i in 0..<10 { print(i); }    // [0, 10[ exclusif
```

### Iteration sur un tableau

```cx
for item in inventory { print(item); }

for i, item in inventory { print(i, "->", item); }    // avec indice
```

### Boucle infinie

```cx
for {
    set::int key = read_key();
    if key == KEY_QUIT { break; }
    handle(key);
}
```

### Boucle conditionnelle

```cx
for health > 0 {
    health -= take_hit();
}
```

### `break` et `continue`

```cx
for i in 0..<100 {
    if i == 50    { break;    }
    if i % 2 == 0 { continue; }
    print(i);
}
```

Etiquettes pour les boucles imbriquees :

```cx
outer: for i in 0..<10 {
    for j in 0..<10 {
        if i + j == 15 { break outer; }
    }
}
```

---

## `match`

Correspondance de motif. L'exhaustivite est verifiee a la compilation.

```cx
match direction {
    Direction::North => { move(0,  1); }
    Direction::South => { move(0, -1); }
    Direction::East  => { move( 1, 0); }
    Direction::West  => { move(-1, 0); }
}
```

Avec capture des donnees d'un enum :

```cx
match result {
    Result::Ok   { value }  => { use(value);   }
    Result::Fail { reason } => { print(reason); }
}
```

Joker et gardes :

```cx
match code {
    0             => { print("ok");       }
    1 | 2         => { print("warning");  }
    n if n >= 100 => { print("critical"); }
    _             => { print("unknown");  }
}
```

`match` comme expression :

```cx
set::str label = match code {
    0 => "ok",
    1 => "warning",
    _ => "unknown",
};
```
