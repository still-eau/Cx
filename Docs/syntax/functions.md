# Fonctions

Une seule facon de declarer une fonction.

```cx
func <name>(<params>) -> <return_type> {
    <body>
}
```

```cx
func add(set::int a, set::int b) -> int {
    return a + b;
}

func log(set::str message) -> void {
    print(message);
}
```

`-> void` peut etre omis si la fonction ne retourne rien.

---

## Parametres par defaut

```cx
func connect(set::str host, set::uint port = 8080) -> bool {
    ...
}

connect("localhost");          // port = 8080
connect("localhost", 3000);    // port = 3000
```

---

## Retours multiples

```cx
func divide(set::int a, set::int b) -> (int, int) {
    return (a / b, a % b);
}

set::int quotient, remainder = divide(10, 3);
```

---

## Fonctions de premiere classe

Les fonctions sont des valeurs. On les stocke et on les passe.

```cx
set::func(int, int) -> int  op = add;
set::int result = op(3, 4);

func apply(set::func(int) -> int f, set::int x) -> int {
    return f(x);
}
```

Forme courte pour une fonction anonyme a une expression :

```cx
set::func(int) -> int double = |x| x * 2;
set::func(int) -> int triple = |x| x * 3;
```

---

## Erreurs : `fail`, `try`, `catch`

Une fonction qui peut echouer le declare dans son type de retour.

```cx
func read_file(set::str path) -> str | fail str {
    if !file_exists(path) {
        fail "file not found";
    }
    return file_content(path);
}
```

Propager l'erreur vers l'appelant avec `try` :

```cx
func process() -> void | fail str {
    set::str content = try read_file("config.txt");
    print(content);
}
```

Gerer localement avec `catch` :

```cx
// Avec recuperation de l'erreur
set::str content = read_file("config.txt") catch err {
    print("error: " + err);
    ""
};

// Sans recuperer l'erreur
set::str content = read_file("config.txt") catch { "" };
```

> Il n'y a pas d'exceptions. Les erreurs sont des valeurs dans le type de retour.
> Ignorer une erreur sans `catch` est une erreur de compilation.

---

## Attributs de fonction

| Attribut         | Effet |
|------------------|-------|
| `@inline`        | Incitation a inliner l'appel |
| `@noreturn`      | La fonction ne retourne jamais |
| `@extern("sym")` | Lien vers un symbole C externe |
| `@unsafe`        | Corps autorise les operations dangereuses |

```cx
@inline
func clamp(set::int val, set::int lo, set::int hi) -> int {
    if val < lo { return lo; }
    if val > hi { return hi; }
    return val;
}

@extern("puts")
func c_puts(set::int[ptr] s) -> int;

@noreturn
func panic(set::str msg) -> void {
    print(msg);
    exit(1);
}
```