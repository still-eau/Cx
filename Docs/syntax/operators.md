# Operateurs

Cx propose un ensemble complet d'operateurs pour manipuler les donnees.

## Arithmetique

| Operateur | Description |
|-----------|-------------|
| `+` | Addition |
| `-` | Soustraction |
| `*` | Multiplication |
| `/` | Division |
| `%` | Modulo |
| `**` | Exponentiation |

```cx
set::int x = 10 + 2;
set::int y = 5 ** 2; // 25
```

## Comparaison

| Operateur | Description |
|-----------|-------------|
| `==` | Egal a |
| `!=` | Different de |
| `<` | Inferieur a |
| `>` | Superieur a |
| `<=` | Inferieur ou egal a |
| `>=` | Superieur ou egal a |

## Logique

| Operateur | Description |
|-----------|-------------|
| `&&` | ET logique (court-circuit) |
| `||` | OU logique (court-circuit) |
| `!` | NON logique |

## Manipulation de Bits (Bitwise)

| Operateur | Description |
|-----------|-------------|
| `&` | ET bit a bit |
| `|` | OU bit a bit |
| `^` | XOR bit a bit |
| `~` | Complement a un |
| `<<` | Decalage a gauche |
| `>>` | Decalage a droite |
| `>>>` | Decalage a droite logique |

## Assignation

Outre l'assignation simple `=`, Cx supporte les assignations composees : `+=`, `-=`, `*=`, `/=`, `%=`, `**=`, `&=`, `|=`, `^=`, `<<=`, `>>=`, `>>>=`.

```cx
set::int x = 10;
x += 5; // x est maintenant 15
```

## Increment et Decrement

- `x++` : Incremente `x` de 1.
- `x--` : Decremente `x` de 1.

*Note : Ces operateurs sont des instructions et ne peuvent pas etre utilises au sein d'une expression.*

## Operateurs Optionnels

- `??` (Coalescence de null) : `a ?? b` retourne `a` si non null, sinon `b`.
- `?.` (Chaine optionnelle) : `a?.b` retourne `b` si `a` n'est pas null, sinon retourne `null`.

## Priorite (de haut en bas)

1. `()`, `[]`, `.`, `?.`
2. `!`, `~`, `-` (unaire), `*` (dereference), `&` (adresse)
3. `**`
4. `*`, `/`, `%`
5. `+`, `-`
6. `<<`, `>>`, `>>>`
7. `&`, `^`, `|`
8. `==`, `!=`, `<`, `>`, `<=`, `>=`
9. `&&`, `||`, `??`
10. `=` et ses variantes composees
