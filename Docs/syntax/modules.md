# Modules et imports

---

## Declaration de module

Chaque fichier `.cx` appartient a un module declare en premiere ligne.

```cx
module math;
module main;
```

---

L'inclusion de modules se fait via la directive `@import:` (ou son alias `@include:`). Le langage utilise une syntaxe explicite et épurée utilisant des chemins relatifs sans guillemets.

```cx
@import:std/io;        // Inclut tout le module (utilisable via io::...)
@import:std/mem;
@import:../../lib/net; // Chemin relatif sans guillemets
@import:./player;
```

### Alias

```cx
@import:std/io as terminal;
@import:./net as network;

terminal::print("connected");
network::connect("localhost");
```

### Inclusion sélective et typée

Lors d'une inclusion sélective, l'élément peut être explicitement marqué avec `()` si c'est une fonction. Les types, objets ou constantes n'ont pas de parenthèses. Cela rend la lecture des dépendances beaucoup plus claire.

```cx
```cx
@import:std/io/print();         // C'est une fonction !
@import:std/io/read_line();     // C'est une fonction !
@import:std/io/File;            // C'est un type ou un objet

// Utilisation directe
print("hello");
```

On peut également grouper plusieurs éléments pour éviter la répétition du chemin :

```cx
@import:std/io/{ print(), read_line(), File };
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
