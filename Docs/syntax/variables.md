# Variables et Constantes

En Cx, la declaration de donnees est explicite et claire.

## Declaration

On utilise deux mots-cles pour definir la mutabilite :

- `set` : Definit une variable dont la valeur peut changer.
- `const` : Definit une constante dont la valeur est fixee a l'initialisation.

La syntaxe utilise le separateur `::` entre le qualificateur et le type.

```cx
set::int   score = 0;
const::str VERSION = "1.0.0";
```

## Primitive Types

Les types de base supportes par le compilateur :

| Type   | Description |
|--------|-------------|
| `int`  | Entier signe (taille native) |
| `uint` | Entier non signe (taille native) |
| `flt`  | Flottant 32-bits (float) |
| `dbl`  | Flottant 64-bits (double) |
| `char` | Caractere (UTF-8) |
| `str`  | Chaine de caracteres |
| `bool` | Valeur booleenne (`true`, `false`) |
| `void` | Type vide (uniquement pour les retours de fonction) |

## Inference de Type

Le caractere `_` (wildcard) permet au compilateur de deduire le type a partir de la valeur d'initialisation.

```cx
set::_ x = 42;          // int
const::_ name = "Cx";   // str
```

## Initialisation par defaut

Si aucune valeur n'est fournie, la variable est initialisee a sa valeur "zero" (0, 0.0, false, null).

```cx
set::int counter;   // Initiale a 0
```

## Declarations Multiples

Il est possible de declarer plusieurs variables sur une seule ligne.

```cx
set::int x = 1, y = 2, z;
```