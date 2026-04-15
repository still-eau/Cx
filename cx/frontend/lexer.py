# Cx language lexer -- handwritten, no external dependencies

from __future__ import annotations
from enum import Enum, auto
from dataclasses import dataclass
from typing import List


# ---------------------------------------------------------------------------
# Token kinds
# ---------------------------------------------------------------------------

class TK(Enum):
    # Literals
    INT    = auto()
    FLOAT  = auto()
    STRING = auto()
    CHAR   = auto()
    TRUE   = auto()
    FALSE  = auto()
    NULL   = auto()

    # Identifier (and the wildcard '_' for type inference)
    IDENT  = auto()

    # Declaration keywords
    SET      = auto()
    CONST    = auto()
    FUNC     = auto()
    OBJ      = auto()
    ARR      = auto()
    ENUM     = auto()
    ALIAS    = auto()
    MODULE   = auto()
    PUB      = auto()
    SELF     = auto()

    # Control flow keywords
    IF       = auto()
    ELSE     = auto()
    FOR      = auto()
    IN       = auto()
    MATCH    = auto()
    BREAK    = auto()
    CONTINUE = auto()
    RETURN   = auto()
    NEW      = auto()

    # Error handling keywords
    FAIL  = auto()
    TRY   = auto()
    CATCH = auto()

    # Generics constraint keyword
    WHERE = auto()

    # Primitive type keywords
    KW_INT  = auto()
    KW_UINT = auto()
    KW_FLT  = auto()
    KW_DBL  = auto()
    KW_CHAR = auto()
    KW_STR  = auto()
    KW_BOOL = auto()
    KW_VOID = auto()

    # Type modifier keywords (appear inside [...] after a type)
    KW_LONG  = auto()
    KW_SHORT = auto()
    KW_PTR   = auto()
    KW_OPT   = auto()

    # Memory / intrinsic builtins
    ALLOC     = auto()
    FREE      = auto()
    SIZEOF    = auto()
    ALIGNOF   = auto()
    MEMCPY    = auto()
    MEMSET    = auto()
    CAST      = auto()
    TRANSMUTE = auto()

    # Compiler directives (@ prefix)
    AT_IMPORT   = auto()   # @import  (used in source files)
    AT_INCLUDE  = auto()   # @include (alias, used in docs)
    AT_INLINE   = auto()
    AT_NORETURN = auto()
    AT_EXTERN   = auto()
    AT_UNSAFE   = auto()
    AT_WHEN     = auto()

    # Arithmetic operators
    PLUS     = auto()   # +
    MINUS    = auto()   # -
    STAR     = auto()   # *
    SLASH    = auto()   # /
    PERCENT  = auto()   # %
    STARSTAR = auto()   # **

    # Compound-assignment operators
    PLUS_EQ     = auto()   # +=
    MINUS_EQ    = auto()   # -=
    STAR_EQ     = auto()   # *=
    SLASH_EQ    = auto()   # /=
    PERCENT_EQ  = auto()   # %=
    STARSTAR_EQ = auto()   # **=
    AMP_EQ      = auto()   # &=
    PIPE_EQ     = auto()   # |=
    CARET_EQ    = auto()   # ^=
    LSHIFT_EQ   = auto()   # <<=
    RSHIFT_EQ   = auto()   # >>=

    # Increment / decrement (statement-level only, not expressions)
    PLUS_PLUS   = auto()   # ++
    MINUS_MINUS = auto()   # --

    # Comparison operators
    EQ_EQ   = auto()   # ==
    BANG_EQ = auto()   # !=
    LT      = auto()   # <
    GT      = auto()   # >
    LT_EQ   = auto()   # <=
    GT_EQ   = auto()   # >=

    # Logical operators
    AMP_AMP   = auto()   # &&
    PIPE_PIPE = auto()   # ||
    BANG      = auto()   # !

    # Bitwise operators
    AMP          = auto()   # &
    PIPE         = auto()   # |  (also used as arr capacity delimiter and lambda param)
    CARET        = auto()   # ^
    TILDE        = auto()   # ~
    LSHIFT       = auto()   # <<
    RSHIFT       = auto()   # >>
    RSHIFT_LOGIC = auto()   # >>>  (unsigned right shift)
    RSHIFT_LOGIC_EQ = auto() # >>>=

    # Nullable / optional operators
    QUEST_QUEST = auto()   # ??  (null coalescing)
    QUEST_DOT   = auto()   # ?.  (optional chaining)

    # Arrow operators
    ARROW     = auto()   # ->  (return type)
    FAT_ARROW = auto()   # =>  (match arm)

    # Plain assignment
    EQ = auto()   # =

    # Range operators
    DOT_DOT    = auto()   # ..   (inclusive range)
    DOT_DOT_LT = auto()   # ..<  (exclusive range)

    # Scope / path separator
    COLON_COLON = auto()   # ::

    # Punctuation
    LPAREN    = auto()   # (
    RPAREN    = auto()   # )
    LBRACE    = auto()   # {
    RBRACE    = auto()   # }
    LBRACKET  = auto()   # [
    RBRACKET  = auto()   # ]
    SEMICOLON = auto()   # ;
    COLON     = auto()   # :
    COMMA     = auto()   # ,
    DOT       = auto()   # .

    # Sentinel
    EOF = auto()


# ---------------------------------------------------------------------------
# Lookup tables  (built once at import time)
# ---------------------------------------------------------------------------

# All reserved words mapped to their token kind
_KEYWORDS: dict[str, TK] = {
    "set": TK.SET,       "const": TK.CONST,   "func": TK.FUNC,
    "obj": TK.OBJ,       "arr": TK.ARR,        "enum": TK.ENUM,
    "alias": TK.ALIAS,   "module": TK.MODULE,  "pub": TK.PUB,
    "self": TK.SELF,
    "if": TK.IF,         "else": TK.ELSE,      "for": TK.FOR,
    "in": TK.IN,         "match": TK.MATCH,    "break": TK.BREAK,
    "continue": TK.CONTINUE,                   "return": TK.RETURN,
    "new": TK.NEW,
    "fail": TK.FAIL,     "try": TK.TRY,        "catch": TK.CATCH,
    "where": TK.WHERE,
    "true": TK.TRUE,     "false": TK.FALSE,    "null": TK.NULL,
    # Primitive types
    "int": TK.KW_INT,    "uint": TK.KW_UINT,   "flt": TK.KW_FLT,
    "dbl": TK.KW_DBL,    "char": TK.KW_CHAR,   "str": TK.KW_STR,
    "bool": TK.KW_BOOL,  "void": TK.KW_VOID,
    # Type modifiers (used inside [...])
    "long": TK.KW_LONG,  "short": TK.KW_SHORT,
    "ptr": TK.KW_PTR,    "opt": TK.KW_OPT,
    # Memory builtins
    "alloc": TK.ALLOC,       "free": TK.FREE,
    "sizeof": TK.SIZEOF,     "alignof": TK.ALIGNOF,
    "memcpy": TK.MEMCPY,     "memset": TK.MEMSET,
    "cast": TK.CAST,         "transmute": TK.TRANSMUTE,
}

# Directive names that follow '@'
_DIRECTIVES: dict[str, TK] = {
    "import":   TK.AT_IMPORT,    # used in actual .cx source files
    "include":  TK.AT_INCLUDE,   # documented alias
    "inline":   TK.AT_INLINE,
    "noreturn": TK.AT_NORETURN,
    "extern":   TK.AT_EXTERN,
    "unsafe":   TK.AT_UNSAFE,
    "when":     TK.AT_WHEN,
}

# Two-character operator table (checked AFTER three-char tokens)
_TWO_CHAR: dict[str, TK] = {
    "::": TK.COLON_COLON,
    "->": TK.ARROW,
    "=>": TK.FAT_ARROW,
    "..": TK.DOT_DOT,
    "**": TK.STARSTAR,
    "++": TK.PLUS_PLUS,
    "--": TK.MINUS_MINUS,
    "==": TK.EQ_EQ,
    "!=": TK.BANG_EQ,
    "<=": TK.LT_EQ,
    ">=": TK.GT_EQ,
    "&&": TK.AMP_AMP,
    "||": TK.PIPE_PIPE,
    "<<": TK.LSHIFT,
    ">>": TK.RSHIFT,
    "??": TK.QUEST_QUEST,
    "?.": TK.QUEST_DOT,
    "+=": TK.PLUS_EQ,
    "-=": TK.MINUS_EQ,
    "*=": TK.STAR_EQ,
    "/=": TK.SLASH_EQ,
    "%=": TK.PERCENT_EQ,
    "&=": TK.AMP_EQ,
    "|=": TK.PIPE_EQ,
    "^=": TK.CARET_EQ,
}

# Single-character token table (checked last)
_ONE_CHAR: dict[str, TK] = {
    "(": TK.LPAREN,   ")": TK.RPAREN,
    "{": TK.LBRACE,   "}": TK.RBRACE,
    "[": TK.LBRACKET, "]": TK.RBRACKET,
    ";": TK.SEMICOLON, ":": TK.COLON,
    ",": TK.COMMA,    ".": TK.DOT,
    "+": TK.PLUS,     "-": TK.MINUS,
    "*": TK.STAR,     "/": TK.SLASH,
    "%": TK.PERCENT,  "=": TK.EQ,
    "<": TK.LT,       ">": TK.GT,
    "&": TK.AMP,      "|": TK.PIPE,
    "^": TK.CARET,    "~": TK.TILDE,
    "!": TK.BANG,
}

# Character sets for fast membership tests (frozenset beats 'in str' for long sets)
_IDENT_START = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")
_IDENT_CONT  = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789")
_DEC_DIGITS  = frozenset("0123456789_")
_HEX_DIGITS  = frozenset("0123456789abcdefABCDEF_")
_BIN_DIGITS  = frozenset("01_")
_OCT_DIGITS  = frozenset("01234567_")

_ESCAPE_TABLE: dict[str, str] = {
    "n": "\n", "t": "\t", "r": "\r",
    "\\": "\\", '"': '"', "'": "'", "0": "\0",
}


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Token:
    kind:   TK
    value:  str
    line:   int
    col:    int
    length: int = 1

    def __repr__(self) -> str:
        return f"Token({self.kind.name}, {self.value!r}, {self.line}:{self.col}, len={self.length})"


class LexError(Exception):
    def __init__(self, msg: str, line: int, col: int) -> None:
        super().__init__(f"lex error at {line}:{col} -- {msg}")
        self.line = line
        self.col  = col


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------

class Lexer:
    """Single-pass, hand-written lexer for the Cx language.

    Usage:
        tokens = Lexer(source_code).tokenize()

    The lexer is also iterable:
        for tok in Lexer(source_code): ...
    """

    __slots__ = ("_src", "_pos", "_line", "_col", "_len")

    def __init__(self, source: str) -> None:
        self._src  = source
        self._len  = len(source)
        self._pos  = 0
        self._line = 1
        self._col  = 1

    # -- public API ----------------------------------------------------------

    def tokenize(self) -> List[Token]:
        """Consume the entire source and return all tokens including EOF."""
        tokens: List[Token] = []
        while True:
            tok = self._next()
            tokens.append(tok)
            if tok.kind is TK.EOF:
                break
        return tokens

    def __iter__(self):
        return self

    def __next__(self) -> Token:
        tok = self._next()
        if tok.kind is TK.EOF:
            raise StopIteration
        return tok

    # -- internal: character access ------------------------------------------

    def _peek(self, offset: int = 0) -> str:
        i = self._pos + offset
        return self._src[i] if i < self._len else ""

    def _advance(self) -> str:
        ch = self._src[self._pos]
        self._pos += 1
        if ch == "\n":
            self._line += 1
            self._col = 1
        else:
            self._col += 1
        return ch

    # -- internal: whitespace and comments -----------------------------------

    def _skip(self) -> None:
        """Skip whitespace, line comments (//) and block comments (/* */)."""
        src = self._src
        while self._pos < self._len:
            ch = src[self._pos]

            if ch in " \t\r\n":
                self._advance()

            elif ch == "/" and self._pos + 1 < self._len:
                nxt = src[self._pos + 1]
                if nxt == "/":
                    while self._pos < self._len and src[self._pos] != "\n":
                        self._advance()
                elif nxt == "*":
                    line, col = self._line, self._col
                    self._advance(); self._advance()  # consume /*
                    while self._pos < self._len:
                        if src[self._pos] == "*" and self._pos + 1 < self._len and src[self._pos + 1] == "/":
                            self._advance(); self._advance()  # consume */
                            break
                        self._advance()
                    else:
                        raise LexError("unterminated block comment", line, col)
                else:
                    break
            else:
                break

    # -- internal: token construction ----------------------------------------

    def _make(self, kind: TK, value: str, line: int, col: int, length: int = -1) -> Token:
        if length == -1:
            length = len(value)
        return Token(kind, value, line, col, length)

    # -- internal: main dispatch ---------------------------------------------

    def _next(self) -> Token:
        self._skip()
        if self._pos >= self._len:
            return self._make(TK.EOF, "", self._line, self._col)

        line = self._line
        col  = self._col
        ch   = self._src[self._pos]

        if ch in _IDENT_START:
            return self._lex_ident(line, col)
        if ch.isdigit():
            return self._lex_number(line, col)
        if ch == '"':
            return self._lex_string(line, col)
        if ch == "'":
            return self._lex_char(line, col)
        if ch == "@":
            return self._lex_directive(line, col)
        return self._lex_symbol(line, col)

    # -- internal: identifiers and keywords ----------------------------------

    def _lex_ident(self, line: int, col: int) -> Token:
        # Fast path: bypass _advance() since identifiers contain no newlines
        start = self._pos
        src   = self._src
        while self._pos < self._len and src[self._pos] in _IDENT_CONT:
            self._pos += 1
        word = src[start:self._pos]
        self._col += len(word)
        return self._make(_KEYWORDS.get(word, TK.IDENT), word, line, col)

    # -- internal: numeric literals ------------------------------------------

    def _lex_number(self, line: int, col: int) -> Token:
        """Lex decimal, 0x hex, 0b binary, 0o octal and float literals.
        Underscore '_' is allowed as a visual separator inside any literal.
        """
        start    = self._pos
        src      = self._src
        is_float = False

        # Detect base prefix
        if src[self._pos] == "0" and self._pos + 1 < self._len:
            p = src[self._pos + 1].lower()
            if p == "x":
                self._pos += 2
                self._scan_set(_HEX_DIGITS)
            elif p == "b":
                self._pos += 2
                self._scan_set(_BIN_DIGITS)
            elif p == "o":
                self._pos += 2
                self._scan_set(_OCT_DIGITS)
            else:
                self._scan_set(_DEC_DIGITS)
        else:
            self._scan_set(_DEC_DIGITS)

        # Fractional part: accept '.' only when NOT followed by '.' or '<'
        # (those are range operators, not decimal points)
        if (self._pos < self._len
                and src[self._pos] == "."
                and (self._pos + 1 >= self._len or src[self._pos + 1] not in (".", "<"))):
            is_float = True
            self._pos += 1  # consume '.'
            self._scan_set(_DEC_DIGITS)

        # Scientific notation exponent
        if self._pos < self._len and src[self._pos].lower() == "e":
            is_float = True
            self._pos += 1
            if self._pos < self._len and src[self._pos] in "+-":
                self._pos += 1
            self._scan_set(_DEC_DIGITS)

        raw = src[start:self._pos]
        self._col += len(raw)  # no newlines inside a numeric literal
        return self._make(TK.FLOAT if is_float else TK.INT, raw, line, col)

    def _scan_set(self, allowed: frozenset) -> None:
        src = self._src
        while self._pos < self._len and src[self._pos] in allowed:
            self._pos += 1

    # -- internal: string and char literals ----------------------------------

    def _lex_string(self, line: int, col: int) -> Token:
        start_pos = self._pos
        self._advance()  # opening "
        parts: List[str] = []
        while True:
            if self._pos >= self._len:
                raise LexError("unterminated string literal", line, col)
            ch = self._src[self._pos]
            if ch == '"':
                self._advance()
                break
            if ch == "\\":
                parts.append(self._lex_escape(line, col))
            else:
                parts.append(self._advance())
        return self._make(TK.STRING, "".join(parts), line, col, self._pos - start_pos)

    def _lex_char(self, line: int, col: int) -> Token:
        start_pos = self._pos
        self._advance()  # opening '
        if self._pos >= self._len:
            raise LexError("unterminated char literal", line, col)
        if self._src[self._pos] == "\\":
            val = self._lex_escape(line, col)
        else:
            val = self._advance()
        if self._pos >= self._len or self._src[self._pos] != "'":
            raise LexError("char literal must contain exactly one character", line, col)
        self._advance()  # closing '
        return self._make(TK.CHAR, val, line, col, self._pos - start_pos)

    def _lex_escape(self, line: int, col: int) -> str:
        self._advance()  # backslash
        if self._pos >= self._len:
            raise LexError("unterminated escape sequence", line, col)
        ec = self._advance()
        if ec not in _ESCAPE_TABLE:
            raise LexError(f"unknown escape sequence '\\{ec}'", line, col)
        return _ESCAPE_TABLE[ec]

    # -- internal: compiler directives (@name) --------------------------------

    def _lex_directive(self, line: int, col: int) -> Token:
        self._advance()  # consume '@' -- _advance() already increments _col
        start = self._pos
        src   = self._src
        while self._pos < self._len and (src[self._pos].isalnum() or src[self._pos] == "_"):
            self._pos += 1
        name = src[start:self._pos]
        self._col += len(name)  # '@' was handled above by _advance()
        kind = _DIRECTIVES.get(name)
        if kind is None:
            raise LexError(f"unknown directive '@{name}'", line, col)
        return self._make(kind, "@" + name, line, col)

    # -- internal: operators and punctuation ---------------------------------

    def _lex_symbol(self, line: int, col: int) -> Token:
        a = self._peek(0)
        b = self._peek(1)
        c = self._peek(2)

        d = self._peek(3)

        # --- Four-character tokens ---
        if a == ">" and b == ">" and c == ">" and d == "=":
            self._advance(); self._advance(); self._advance(); self._advance()
            return self._make(TK.RSHIFT_LOGIC_EQ, ">>>=", line, col)

        # --- Three-character tokens (must be checked before two-char) ---

        # >>> unsigned right shift
        if a == ">" and b == ">" and c == ">":
            self._advance(); self._advance(); self._advance()
            return self._make(TK.RSHIFT_LOGIC, ">>>", line, col)

        # **= exponentiation-assign
        if a == "*" and b == "*" and c == "=":
            self._advance(); self._advance(); self._advance()
            return self._make(TK.STARSTAR_EQ, "**=", line, col)

        # <<= left-shift-assign
        if a == "<" and b == "<" and c == "=":
            self._advance(); self._advance(); self._advance()
            return self._make(TK.LSHIFT_EQ, "<<=", line, col)

        # >>= right-shift-assign
        if a == ">" and b == ">" and c == "=":
            self._advance(); self._advance(); self._advance()
            return self._make(TK.RSHIFT_EQ, ">>=", line, col)

        # ..< exclusive range (must come before '..' two-char check)
        if a == "." and b == "." and c == "<":
            self._advance(); self._advance(); self._advance()
            return self._make(TK.DOT_DOT_LT, "..<", line, col)

        # --- Two-character tokens ---
        two = a + b
        if two in _TWO_CHAR:
            self._advance(); self._advance()
            return self._make(_TWO_CHAR[two], two, line, col)

        # --- Single-character tokens ---
        if a in _ONE_CHAR:
            self._advance()
            return self._make(_ONE_CHAR[a], a, line, col)

        raise LexError(f"unexpected character {a!r}", line, col)