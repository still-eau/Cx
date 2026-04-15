# Modules et Importations

Cx utilise un systeme de modules simple et explicite pour organiser le code et gerer les dependances.

## Declaration de Module

Chaque fichier Cx commence par une declaration de module. Par convention, le module `main` est le point d'entree du programme.

```cx
module math;
```

## Importations : `@import`

Les dependances sont declarees a l'aide de la directive `@import:`.

- `@import:chemin/vers/module;` : Importe tout le module.
- `@import:chemin/vers/module as alias;` : Importe avec un alias.
- `@import:chemin/vers/module/{element1, element2};` : Importation selective.

```cx
@import:std/io;
@import:std/mem as memory;
@import:./utils/{ helper(), CONSTANTE };
```

Dans les importations selectives, les fonctions sont suffixees par `()` pour plus de clarte.

## Visibilite : `pub`

Par defaut, tout ce qui est declare dans un module est prive. Pour rendre une fonction, un objet ou une variable accessible depuis un autre module, utilisez le mot-cle `pub`.

```cx
pub func addition(set::int a, set::int b) -> int {
    return a + b;
}

pub obj Config {
    pub set::str host = "localhost";
    set::str secret = "top-secret"; // Prive
}
```

## Compilation Conditionnelle : `@when`

Permet d'inclure du code selon la plateforme ou des options de compilation.

```cx
@when(target == "windows") {
    // Code specifique Windows
}
```
Options communes : `target`, `arch`, `debug`, `optimize`.
