# Memoire et pointeurs

Par defaut Cx est sur. Les pointeurs bruts et l'arithmetique memoire requierent `@unsafe`.

---

## Pointeurs

Le modificateur `[ptr]` transforme un type en pointeur brut.

```cx
set::int       x = 42;
set::int[ptr]  p = &x;      // address of x
set::int       v = *p;      // read through pointer
*p = 99;                    // write through pointer
```

Un `[ptr]` peut etre null. Pour le rendre explicite, combiner avec `[opt]` :

```cx
set::int[ptr][opt] p = null;

if p != null {
    print(*p);
}
```

---

## Allocation sur le tas

```cx
set::int[ptr] buffer = alloc(int, 64);    // 64 ints, zero-initialized
buffer[0] = 1;
buffer[1] = 2;
free(buffer);                             // must be called exactly once
```

> Chaque `alloc` doit avoir exactement un `free`. Un double-free est un comportement indefini.

---

## Zone @unsafe

L'arithmetique de pointeur est interdite en dehors d'un bloc `@unsafe`.

```cx
@unsafe {
    set::int[ptr] p = alloc(int, 16);
    set::int[ptr] q = p + 4;     // advance by 4 elements
    *q = 0xAB;
    free(p);
}
```

`@unsafe` debloque aussi `cast` sur des pointeurs et `transmute`.

---

## `cast` : conversion de type

```cx
set::int  n = 300;
set::uint u = cast(uint, n);    // numeric cast

// Pointer reinterpretation (requires @unsafe)
@unsafe {
    set::int[ptr] raw = alloc(int, 4);
    set::flt[ptr] fp  = cast(flt[ptr], raw);    // same bits, different type
    free(raw);
}
```

> Les conversions numeriques tronquent silencieusement, elles ne paniquent pas.

---

## `transmute` : reinterpretation de bits

Memes bits, type different, taille identique. Toujours dans `@unsafe`.

```cx
@unsafe {
    set::uint bits = 0x3F800000;
    set::flt  one  = transmute(flt, bits);    // == 1.0
}
```

---

## Intrinsiques memoire

| Fonction                  | Description |
|---------------------------|-------------|
| `alloc(T, n) -> T[ptr]`   | Alloue n elements de type T sur le tas |
| `free(ptr)`               | Libere une allocation |
| `sizeof(T) -> uint`       | Taille du type T en octets |
| `alignof(T) -> uint`      | Alignement du type T en octets |
| `memcpy(dst, src, n)`     | Copie n octets de src vers dst |
| `memset(dst, val, n)`     | Remplit n octets avec val |
| `cast(T, val)`            | Convertit val en type T |
| `transmute(T, val)`       | Reinterprete les bits de val en T |

---

## Lien avec du code C

```cx
@extern("malloc")
func c_malloc(set::uint size) -> int[ptr];

@extern("free")
func c_free(set::int[ptr] p) -> void;
```
