# Operateurs

---

## Arithmetique

| Operateur | Description |
|-----------|-------------|
| `+`       | Addition |
| `-`       | Soustraction |
| `*`       | Multiplication |
| `/`       | Division |
| `%`       | Modulo |
| `**`      | Exponentiation |

```cx
set::int x = 10 + 3;      // 13
set::int y = 10 % 3;      // 1
set::flt z = 2.0 ** 8.0;  // 256.0
```

---

## Assignation composee

`+=`  `-=`  `*=`  `/=`  `%=`  `**=`

```cx
x += 5;
x **= 2;
```

---

## Increment et decrement

```cx
x++;    // x = x + 1
x--;    // x = x - 1
```

> `++` et `--` sont des **instructions**, pas des expressions. `y = x++` est une erreur.

---

## Comparaison

`==`  `!=`  `<`  `>`  `<=`  `>=`

---

## Logique

`&&`  `||`  `!`

Les deux sont a court-circuit.

```cx
if alive && health > 0 { attack(); }
if done || failed      { stop();   }
```

---

## Bit a bit

| Operateur | Description |
|-----------|-------------|
| `&`       | ET bit a bit |
| `\|`      | OU bit a bit |
| `^`       | XOR bit a bit |
| `~`       | NON bit a bit |
| `<<`      | Decalage gauche |
| `>>`      | Decalage droit |
| `>>>`     | Decalage droit logique (non signe) |

```cx
set::int flags = 0b0000_1010;
flags |= 0b0001_0000;      // set a bit
flags &= ~0b0000_1010;     // clear bits
set::int hi = flags << 4;
set::int lo = flags >> 4;
```

Assignation : `&=`  `|=`  `^=`  `<<=`  `>>>=`

> `_` dans les literaux numeriques sert de separateur visuel :
> `1_000_000`, `0xFF_AA_BB_CC`, `0b0000_1010`

---

## Coalescence de null : `??`

Retourne l'operande gauche s'il n'est pas null, sinon l'operande droite.

```cx
set::int[opt] val = null;
set::int      x   = val ?? 42;    // 42
```

---

## Acces optionnel : `?.`

Court-circuite si l'operande gauche est null, retourne null.

```cx
set::Player[opt] p = find_player(id);
set::str[opt]    n = p?.name;    // null if p is null
```

---

## Priorite (haute a basse)

| Niveau | Operateurs |
|--------|------------|
| 1      | `()` `[]` `.` `?.` |
| 2      | `!` `~` `-` (unaire) `*` (deref) `&` (adresse) |
| 3      | `**` |
| 4      | `*` `/` `%` |
| 5      | `+` `-` |
| 6      | `<<` `>>` `>>>` |
| 7      | `&` |
| 8      | `^` |
| 9      | `\|` |
| 10     | `==` `!=` `<` `>` `<=` `>=` |
| 11     | `&&` |
| 12     | `\|\|` |
| 13     | `??` |
| 14     | `=` `+=` `-=` `*=` `/=` `%=` `&=` `\|=` `^=` `<<=` `>>>=` |
