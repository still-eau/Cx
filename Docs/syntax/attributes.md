# Attributs

Les attributs modifient le comportement d'une declaration a la compilation.
Il y en a quatre.

---

## `@inline`

Incite le compilateur a inserer le code de la fonction directement a l'endroit de l'appel.

```cx
@inline
func abs(set::int x) -> int {
    return if x < 0 { -x } else { x };
}
```

---

## `@noreturn`

La fonction ne rend jamais la main. Le compilateur peut supprimer le code mort apres son appel.

```cx
@noreturn
func panic(set::str msg) -> void {
    print(msg);
    exit(1);
}

func divide(set::int a, set::int b) -> int {
    if b == 0 { panic("division by zero"); }
    return a / b;
    // le compilateur sait que panic() ne retourne pas,
    // il ne se plaint pas d'un chemin sans return
}
```

---

## `@extern`

Lie la declaration a un symbole externe (code C, assembly, OS).

```cx
@extern("puts")
func c_puts(set::int[ptr] s) -> int;

@extern("malloc")
func c_malloc(set::uint size) -> int[ptr];
```

La fonction ne doit pas avoir de corps : c'est une declaration uniquement.

---

## `@unsafe`

Autorise les operations dangereuses dans le corps de la fonction.
Equivalent a envelopper tout le corps dans un bloc `@unsafe { ... }`.

```cx
@unsafe
func raw_copy(set::int[ptr] dst, set::int[ptr] src, set::uint n) -> void {
    for i in 0..<n {
        dst[i] = src[i];
    }
}
```

Un bloc `@unsafe` peut aussi s'utiliser localement dans une fonction normale :

```cx
func example() -> void {
    set::int x = 42;

    @unsafe {
        set::int[ptr] p = &x;
        p = p + 1;     // pointer arithmetic, forbidden without @unsafe
    }
}
```
