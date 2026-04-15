# Gestion Memoire

Cx offre un contrôle total sur la mémoire, alliant sécurité par défaut et puissance pour les besoins système.

## Pointers

Le modificateur `[ptr]` indique une adresse memoire vers une valeur.

```cx
set::int x = 10;
set::int[ptr] p = &x;     // Adresse de x
set::int v = *p;          // De-referencement (lecture)
*p = 20;                  // De-referencement (ecriture)
```

## Allocation Dynamique (Tas)

Cx delegue la gestion du tas a des fonctions intrinseques explicites.

```cx
set::int[ptr] tab = alloc(int, 10);  // Alloue 10 entiers
tab[0] = 42;
free(tab);                            // Libere la memoire
```

- Chaque `alloc` doit imperativement etre libere par un `free`.
- `sizeof(Type)` et `alignof(Type)` retournent la taille et l'alignement en octets.

## Zones @unsafe

Les operations dangereuses (arithmetique de pointeurs, casts bruts) ne sont autorisees que dans un bloc ou une fonction marquee `@unsafe`.

```cx
@unsafe {
    set::int[ptr] p = alloc(int, 5);
    set::int[ptr] q = p + 2;   // Arithmetique de pointeurs possible ici
    *q = 100;
    free(p);
}
```

## Casts et Transmutes

- `cast(Type, Valeur)` : Conversion explicite de type (souvent pour les nombres).
- `transmute(Type, Valeur)` : Reinterpretation brute des bits d'un type vers un autre. Requis dans des blocs `@unsafe`.

```cx
set::flt f = 3.14;
set::uint i = cast(uint, f);

@unsafe {
    set::uint bits = transmute(uint, f); // Meme bits, type different
}
```

## Fonctions Intrinseques Memoire

| Nom | Utilite |
|-----|---------|
| `alloc(T, n)` | Alloue `n` elements de type `T` |
| `free(p)` | Libere le pointeur `p` |
| `sizeof(T)` | Taille de `T` en octets |
| `memcpy(d, s, n)` | Copie memoire |
| `memset(d, v, n)` | Remplit la memoire |
| `cast(T, v)` | Conversion de type |
| `transmute(T, v)` | Reinterpretation de bits |
