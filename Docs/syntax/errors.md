# Gestion des Erreurs

Cx utilise une gestion des erreurs explicite integree au systeme de types. Il n'y a pas d'exceptions ; les erreurs sont des valeurs retournees.

## Declaration d'Erreur

Une fonction peut declarer qu'elle peut echouer en ajoutant `| fail TypeErreur` a son type de retour.

```cx
func lire_donnees() -> str | fail str {
    if !pret() {
        fail "Pas pret";
    }
    return "Donnees";
}
```

## Propagation : `try`

Le mot-cle `try` permet de propager automatiquement une erreur a la fonction appelante si l'appel echoue.

```cx
func process() -> void | fail str {
    set::str d = try lire_donnees();
    print(d);
}
```

## Gestion Locale : `catch`

Le mot-cle `catch` permet d'intercepter une erreur et de fournir une valeur de substitution ou d'executer un bloc de secours.

```cx
set::str d = lire_donnees() catch err {
    print("Erreur interceptée : " + err);
    "Valeur par défaut"
};
```

Si on ne souhaite pas recuperer la valeur de l'erreur, on peut omettre le nom de la variable :

```cx
set::str d = lire_donnees() catch { "Vide" };
```

## Pourquoi ce systeme ?

- Explicite : Vous savez exactement quelle fonction peut echouer.
- Securise : Le compilateur vous oblige a traiter l'erreur (via `try` ou `catch`).
- Performance : Pas de mecanisme de "stack unwinding" couteux comme les exceptions traditionnelles.
