# Variables

Deux qualificateurs. C'est tout.

| Qualificateur | Signification |
|---------------|---------------|
| `set`         | Variable mutable |
| `const`       | Constante, jamais modifiable |

```cx
set::int   x = 42;
const::str NAME = "Cx";
```

---

## Types primitifs

| Type   | Description |
|--------|-------------|
| `int`  | Entier signe (taille native : 32 ou 64 bits selon la plateforme) |
| `uint` | Entier non signe |
| `flt`  | Virgule flottante simple precision |
| `dbl`  | Virgule flottante double precision |
| `char` | Caractere UTF-8 |
| `str`  | Chaine de caracteres (pointeur + longueur) |
| `bool` | `true` ou `false` |
| `null` | Absence de valeur |
| `void` | Aucune valeur (type de retour uniquement) |

---

## Modificateurs de type

S'ajoutent apres le type entre crochets.

| Modificateur | Description |
|--------------|-------------|
| `[long]`     | Version etendue : `int[long]` fait toujours 64 bits |
| `[short]`    | Version reduite : `int[short]` fait toujours 16 bits |
| `[ptr]`      | Pointeur brut vers une valeur |
| `[opt]`      | Peut etre `null` |

```cx
set::int[long]    large   = 20_000_000_000;
set::int[short]   small   = 12;
set::int[ptr]     p       = &x;
set::int[opt]     maybe   = null;
set::int[ptr][opt] nullable = null;    // pointeur qui peut etre null
```

---

## Inference de type

`_` laisse le compilateur deduire le type.

```cx
set::_ result = compute();
const::_ MAX  = 255;
```

---

## Zero-initialisation

Sans valeur, toute variable est zero-initialisee.

```cx
set::int   count;    // 0
set::flt   ratio;    // 0.0
set::bool  flag;     // false
set::int[ptr] ptr;   // null pointer
```

---

## Plusieurs declarations

```cx
set::int a = 1, b = 2, c = 3;
set::int x, y, z = 0;    // tous a zero
```