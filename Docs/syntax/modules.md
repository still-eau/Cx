# Modules et imports

---

## Declaration de module

Chaque fichier `.cx` appartient a un module declare en premiere ligne.

```cx
module math;
module main;
```

---

## Inclure un module (Imports)

L'inclusion de modules se fait via la directive `@include:`. Le langage utilise une syntaxe explicite permettant de savoir au premier coup d'œil la nature de ce qui est importé.

```cx
@include:std/io;      // Inclut tout le module (utilisable via io::...)
@include:std/mem;
@include:./player;
```

### Alias

```cx
@include:std/io as terminal;
@include:./net as network;

terminal::print("connected");
network::connect("localhost");
```

### Inclusion sélective et typée

Lors d'une inclusion sélective, l'élément peut être explicitement marqué avec `()` si c'est une fonction. Les types, objets ou constantes n'ont pas de parenthèses. Cela rend la lecture des dépendances beaucoup plus claire.

```cx
@include:std/io/print();         // C'est une fonction !
@include:std/io/read_line();     // C'est une fonction !
@include:std/io/File;            // C'est un type ou un objet ou un fichier entier

// Utilisation directe
print("hello");
```

On peut également grouper plusieurs éléments pour éviter la répétition du chemin :

```cx
@include:std/io/{ print(), read_line(), File };
```

---

## Visibilite

Par defaut, toute declaration est privee au module.
Utiliser `pub` pour l'exporter.

```cx
pub func add(set::int a, set::int b) -> int {
    return a + b;
}

pub obj Config {
    pub set::str  host = "localhost";
    pub set::uint port = 8080;
        set::str  secret;    // private field
}
```

---

## Point d'entree

```cx
module main;

func main() -> void {
    print("hello world");
}
```

Avec code de retour :

```cx
func main() -> int {
    return 0;
}
```

---

## Compilation conditionnelle

```cx
@when(target == "linux") {
    func get_pid() -> int { return native_getpid(); }
}

@when(debug) {
    func dump_state() -> void { print("state dump..."); }
}
```

| Condition  | Valeurs possibles |
|------------|-------------------|
| `target`   | `"linux"`, `"windows"`, `"macos"`, `"bare"` |
| `arch`     | `"x86_64"`, `"aarch64"`, `"riscv64"`, `"wasm32"` |
| `debug`    | `true` / `false` |
| `optimize` | `"none"`, `"speed"`, `"size"` |
