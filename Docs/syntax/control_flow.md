# Flux de Controle

Cx propose des structures de controle epurees et puissantes.

## `if` / `else`

Les parentheses sont optionnelles, mais les accolades sont obligatoires.

```cx
if score >= 90 {
    print("A");
} else if score >= 80 {
    print("B");
} else {
    print("F");
}
```

`if` peut egalement etre utilise comme une expression :

```cx
set::str resultat = if x > 0 { "positif" } else { "negatif" };
```

## `for` : La Boucle Unique

La boucle `for` est polyvalente et remplace toutes les autres formes de boucles.

### Iteration sur une plage (Range)
```cx
for i in 0..10 { ... }     // 0 a 10 inclus
for i in 0..<10 { ... }    // 0 a 9 (10 exclu)
```

### Iteration sur une collection
```cx
for element in liste { ... }
for index, element in liste { ... }
```

### Boucle conditionnelle (While)
```cx
for x < 100 {
    x += 1;
}
```

### Boucle infinie
```cx
for {
    if fini() { break; }
}
```

## `match` : Pattern Matching

`match` permet de comparer une valeur a une serie de motifs. Il doit etre exhaustif.

```cx
match direction {
    North => print("Haut"),
    South => print("Bas"),
    _     => print("Autre"), // Joker
}
```

`match` supporte egalement l'extraction de donnees des enums :

```cx
match status {
    Active          => print("Ok"),
    Error { code }  => print("Erreur: " + code),
}
```

## Labels et Sauts

On peut nommer une boucle avec un label pour l'interrompre specifiquement depuis une boucle imbriquee.

```cx
externe: for i in 0..10 {
    for j in 0..10 {
        if i * j > 50 { break externe; }
    }
}
```
