"""Cx recursive-descent parser — handwritten, zero external dependencies.

Grammar coverage
----------------
  - Module declaration and import directives
  - All declaration kinds: func, obj, enum, alias, set/const, arr
  - Generics (<T, U>) and where-clauses
  - Full expression grammar with 14-level precedence climbing
  - all statement kinds: if/else, for (4 variants), match, return, …
  - Lambda expressions  |x, y| expr
  - try / catch error handling
  - @unsafe blocks and @when conditional compilation
  - Attribute annotations: @inline, @noreturn, @extern, @unsafe

Error strategy
--------------
  - Hard errors raise ParseError immediately (unrecoverable syntax).
  - The caller wraps parsing in a try/except to collect errors via the
    ErrorReporter; abort_if_errors() exits after the full parse phase.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from .lexer import TK, Token, Lexer
from .ast   import *
from ..utils.source_loc import Loc
from ..utils.errors     import ErrorReporter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ASSIGN_OPS: frozenset[TK] = frozenset({
    TK.EQ, TK.PLUS_EQ, TK.MINUS_EQ, TK.STAR_EQ, TK.SLASH_EQ,
    TK.PERCENT_EQ, TK.STARSTAR_EQ, TK.AMP_EQ, TK.PIPE_EQ,
    TK.CARET_EQ, TK.LSHIFT_EQ, TK.RSHIFT_EQ,
})

# Binary operator precedence (higher = tighter).
# Assignments are NOT in this table — they are handled at statement level.
_PREC: dict[TK, int] = {
    TK.PIPE_PIPE:  1,
    TK.AMP_AMP:    2,
    TK.PIPE:       3,
    TK.CARET:      4,
    TK.AMP:        5,
    TK.EQ_EQ:      6,  TK.BANG_EQ: 6,
    TK.LT:         6,  TK.GT:      6,  TK.LT_EQ: 6, TK.GT_EQ: 6,
    TK.LSHIFT:     7,  TK.RSHIFT:  7,  TK.RSHIFT_LOGIC: 7,
    TK.PLUS:       8,  TK.MINUS:   8,
    TK.STAR:       9,  TK.SLASH:   9,  TK.PERCENT: 9,
    TK.STARSTAR:  10,                  # right-associative
}

_RIGHT_ASSOC: frozenset[TK] = frozenset({TK.STARSTAR})

_UNARY_OPS: frozenset[TK] = frozenset({
    TK.MINUS, TK.BANG, TK.TILDE, TK.STAR, TK.AMP,
})

_PRIM_TYPES: frozenset[TK] = frozenset({
    TK.KW_INT, TK.KW_UINT, TK.KW_FLT, TK.KW_DBL,
    TK.KW_CHAR, TK.KW_STR, TK.KW_BOOL, TK.KW_VOID,
})

_PRIM_NAME: dict[TK, str] = {
    TK.KW_INT:  "int",  TK.KW_UINT: "uint", TK.KW_FLT:  "flt",
    TK.KW_DBL:  "dbl",  TK.KW_CHAR: "char", TK.KW_STR:  "str",
    TK.KW_BOOL: "bool", TK.KW_VOID: "void",
}

_TYPE_MODS: frozenset[TK] = frozenset({
    TK.KW_LONG, TK.KW_SHORT, TK.KW_PTR, TK.KW_OPT,
})

_MOD_NAME: dict[TK, str] = {
    TK.KW_LONG: "long", TK.KW_SHORT: "short",
    TK.KW_PTR:  "ptr",  TK.KW_OPT:   "opt",
}

# Tokens that can begin a statement
_STMT_SYNC: frozenset[TK] = frozenset({
    TK.SET, TK.CONST, TK.FUNC, TK.OBJ, TK.ENUM, TK.ALIAS, TK.ARR,
    TK.IF, TK.FOR, TK.MATCH, TK.RETURN, TK.BREAK, TK.CONTINUE,
    TK.FAIL, TK.AT_UNSAFE, TK.AT_WHEN,
    TK.LBRACE, TK.SEMICOLON, TK.RBRACE, TK.EOF,
})


class ParseError(Exception):
    """Raised on unrecoverable syntax error."""
    def __init__(self, msg: str, loc: Loc) -> None:
        super().__init__(f"{loc}: {msg}")
        self.loc = loc


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class Parser:
    """Hand-written recursive-descent parser for the Cx language.

    Usage::

        tokens  = Lexer(source).tokenize()
        program = Parser(tokens, filename, source).parse()
    """

    __slots__ = ("_toks", "_pos", "_filename", "_source", "_reporter")

    def __init__(
        self,
        tokens:   List[Token],
        filename: str,
        source:   str,
        reporter: Optional[ErrorReporter] = None,
    ) -> None:
        self._toks    = tokens
        self._pos     = 0
        self._filename = filename
        self._source   = source
        self._reporter = reporter or ErrorReporter(filename, source)

    # ================================================================
    # Public API
    # ================================================================

    def parse(self) -> Program:
        loc     = self._loc()
        mod     = self._parse_module_decl()
        imports = self._parse_imports()
        items   = self._parse_items()
        self._expect(TK.EOF)
        return Program(loc, self._filename, mod, imports, items)

    # ================================================================
    # Internal helpers
    # ================================================================

    def _loc(self) -> Loc:
        t = self._toks[self._pos]
        return Loc(self._filename, t.line, t.col, getattr(t, 'length', 1))

    def _peek(self, offset: int = 0) -> Token:
        i = self._pos + offset
        return self._toks[min(i, len(self._toks) - 1)]

    def _check(self, *kinds: TK) -> bool:
        return self._toks[self._pos].kind in kinds

    def _advance(self) -> Token:
        tok = self._toks[self._pos]
        if tok.kind is not TK.EOF:
            self._pos += 1
        return tok

    def _match(self, *kinds: TK) -> Optional[Token]:
        if self._toks[self._pos].kind in kinds:
            return self._advance()
        return None

    def _expect(self, kind: TK, msg: str = "") -> Token:
        tok = self._toks[self._pos]
        if tok.kind is not kind:
            desc = msg or f"expected '{kind.name}', got '{tok.value!r}'"
            raise ParseError(desc, self._loc())
        return self._advance()

    def _expect_ident(self, msg: str = "expected identifier") -> str:
        tok = self._toks[self._pos]
        if tok.kind is not TK.IDENT:
            raise ParseError(msg, self._loc())
        self._advance()
        return tok.value

    # ================================================================
    # Module and imports
    # ================================================================

    def _parse_module_decl(self) -> Optional[ModuleDecl]:
        if not self._check(TK.MODULE):
            return None
        loc = self._loc()
        self._advance()
        name = self._expect_ident("expected module name")
        self._expect(TK.SEMICOLON, "expected ';' after module declaration")
        return ModuleDecl(loc, name)

    def _parse_imports(self) -> List[ImportDirective]:
        imports: List[ImportDirective] = []
        while self._check(TK.AT_IMPORT, TK.AT_INCLUDE):
            imports.append(self._parse_import())
        return imports

    def _parse_import(self) -> ImportDirective:
        """@import:path  |  @import:path as alias  |  @import:path/{a(), B}"""
        loc = self._loc()
        self._advance()   # consume @import / @include
        self._expect(TK.COLON, "expected ':' after @import")

        # Parse path segments separated by '/'
        path_parts: List[str] = []
        
        while True:
            seg = ""
            if self._match(TK.DOT_DOT):
                seg = ".."
            elif self._match(TK.DOT):
                seg = "."
            elif self._check(TK.IDENT):
                seg = self._advance().value
            else:
                raise ParseError("expected path segment (ident, . or ..)", self._loc())
                
            # suffix '()' marks a function
            if self._check(TK.LPAREN):
                self._advance()
                self._expect(TK.RPAREN)
                seg += "()"
            
            path_parts.append(seg)
            
            if self._match(TK.SLASH):
                # selective group: { a(), B }
                if self._check(TK.LBRACE):
                    selective = self._parse_import_group()
                    full_path = "/".join(path_parts)
                    return ImportDirective(loc, full_path, None, selective)
                continue
            else:
                break

        # trailing '()' on the last segment was already processed when checking TK.LPAREN

        full_path = "/".join(path_parts)

        alias: Optional[str] = None
        if self._match(TK.IN):   # 'as' is lexed as IDENT "as"
            # 'as' is not a keyword, it's a bare ident
            alias = self._expect_ident("expected alias name after 'as'")
        elif self._check(TK.IDENT) and self._toks[self._pos].value == "as":
            self._advance()
            alias = self._expect_ident("expected alias name after 'as'")

        self._expect(TK.SEMICOLON, "expected ';' after import")
        return ImportDirective(loc, full_path, alias)

    def _parse_import_group(self) -> List[str]:
        """{ print(), read_line(), File }"""
        self._expect(TK.LBRACE)
        items: List[str] = []
        while not self._check(TK.RBRACE, TK.EOF):
            name = self._expect_ident("expected symbol name in import group")
            if self._check(TK.LPAREN):
                self._advance()
                self._expect(TK.RPAREN)
                items.append(name + "()")
            else:
                items.append(name)
            if not self._match(TK.COMMA):
                break
        self._expect(TK.RBRACE)
        return items

    # ================================================================
    # Top-level items
    # ================================================================

    def _parse_items(self) -> List[Item]:
        items: List[Item] = []
        while not self._check(TK.EOF):
            item = self._parse_item()
            if item is not None:
                items.append(item)
        return items

    def _parse_item(self) -> Optional[Item]:
        loc    = self._loc()
        is_pub = False

        # attribute list before the declaration
        attrs:      List[str]     = []
        extern_sym: Optional[str] = None
        
        while True:
            if self._match(TK.PUB):
                is_pub = True
            elif self._check(TK.AT_INLINE, TK.AT_NORETURN, TK.AT_EXTERN,
                             TK.AT_UNSAFE, TK.AT_WHEN):
                tok = self._advance()
                if tok.kind is TK.AT_INLINE:
                    attrs.append("inline")
                elif tok.kind is TK.AT_NORETURN:
                    attrs.append("noreturn")
                elif tok.kind is TK.AT_UNSAFE:
                    attrs.append("unsafe")
                elif tok.kind is TK.AT_EXTERN:
                    self._expect(TK.LPAREN)
                    extern_sym = self._expect(TK.STRING).value
                    self._expect(TK.RPAREN)
                    attrs.append("extern")
                elif tok.kind is TK.AT_WHEN:
                    cond = self._parse_when_cond()
                    body_items = self._parse_brace_items()
                    return None
            else:
                break

        if self._check(TK.FUNC):
            return self._parse_func(loc, is_pub, attrs, extern_sym)
        if self._check(TK.OBJ):
            return self._parse_obj(loc, is_pub)
        if self._check(TK.ENUM):
            return self._parse_enum(loc, is_pub)
        if self._check(TK.ALIAS):
            return self._parse_alias(loc, is_pub)
        if self._check(TK.SET, TK.CONST):
            return self._parse_var_item(loc, is_pub)
        if self._check(TK.ARR):
            return self._parse_arr_item(loc, is_pub)
        # Skip unknown token with an error
        tok = self._advance()
        self._reporter.error(f"unexpected top-level token '{tok.value}'",
                                Loc(self._filename, tok.line, tok.col, getattr(tok, 'length', 1)))
        return None

    def _parse_brace_items(self) -> List[Item]:
        self._expect(TK.LBRACE)
        items: List[Item] = []
        while not self._check(TK.RBRACE, TK.EOF):
            it = self._parse_item()
            if it:
                items.append(it)
        self._expect(TK.RBRACE)
        return items

    # ================================================================
    # Function declaration
    # ================================================================

    def _parse_func(
        self,
        loc:        Loc,
        is_pub:     bool,
        attrs:      List[str],
        extern_sym: Optional[str],
    ) -> FuncDecl:
        self._expect(TK.FUNC)
        name        = self._expect_ident("expected function name")
        type_params = self._parse_type_params()
        params      = self._parse_param_list()
        ret_type, fail_type = self._parse_return_type()
        where_cls   = self._parse_where()

        if self._check(TK.SEMICOLON):   # forward / extern declaration
            self._advance()
            body = None
        else:
            body = self._parse_block()

        return FuncDecl(
            loc, is_pub, name, type_params, params,
            ret_type, fail_type, body, attrs, extern_sym, where_cls,
        )

    def _parse_type_params(self) -> List[str]:
        """<T, U, …>  — empty list if absent."""
        if not self._check(TK.LT):
            return []
        self._advance()
        params: List[str] = []
        while not self._check(TK.GT, TK.EOF):
            params.append(self._expect_ident("expected type parameter"))
            if not self._match(TK.COMMA):
                break
        self._expect(TK.GT)
        return params

    def _parse_param_list(self) -> List[ParamDecl]:
        self._expect(TK.LPAREN)
        params: List[ParamDecl] = []
        while not self._check(TK.RPAREN, TK.EOF):
            params.append(self._parse_param())
            if not self._match(TK.COMMA):
                break
        self._expect(TK.RPAREN)
        return params

    def _parse_param(self) -> ParamDecl:
        loc = self._loc()
        qual, ty = self._parse_qualifier_type()
        name = self._expect_ident("expected parameter name")
        default: Optional[Expr] = None
        if self._match(TK.EQ):
            default = self._parse_expr()
        return ParamDecl(loc, qual, ty, name, default)

    def _parse_return_type(self) -> Tuple[Optional[TypeNode], Optional[TypeNode]]:
        """-> T  or  -> T | fail E  or nothing (void)."""
        if not self._match(TK.ARROW):
            return None, None
        ret = self._parse_type()
        fail_type: Optional[TypeNode] = None
        if self._check(TK.PIPE):
            # look ahead for 'fail'
            if self._peek(1).kind is TK.FAIL:
                self._advance()   # |
                self._advance()   # fail
                fail_type = self._parse_type()
        return ret, fail_type

    def _parse_where(self) -> List[WhereClause]:
        if not self._check(TK.WHERE):
            return []
        self._advance()
        clauses: List[WhereClause] = []
        while True:
            loc   = self._loc()
            tparam = self._expect_ident("expected type parameter in where")
            self._expect(TK.COLON, "expected ':' in where clause")
            constraint = self._expect_ident("expected constraint name")
            clauses.append(WhereClause(loc, tparam, constraint))
            if not self._match(TK.COMMA):
                break
        return clauses

    # ================================================================
    # Obj declaration
    # ================================================================

    def _parse_obj(self, loc: Loc, is_pub: bool) -> ObjDecl:
        self._expect(TK.OBJ)
        name        = self._expect_ident("expected struct name")
        type_params = self._parse_type_params()
        self._expect(TK.LBRACE)
        fields:  List[FieldDecl] = []
        methods: List[FuncDecl]  = []
        while not self._check(TK.RBRACE, TK.EOF):
            loc_f = self._loc()
            fld_pub = False
            attrs = []
            extern_sym = None

            while True:
                if self._match(TK.PUB):
                    fld_pub = True
                elif self._check(TK.AT_INLINE, TK.AT_NORETURN, TK.AT_EXTERN, TK.AT_UNSAFE):
                    tok = self._advance()
                    if tok.kind is TK.AT_INLINE: attrs.append("inline")
                    elif tok.kind is TK.AT_NORETURN: attrs.append("noreturn")
                    elif tok.kind is TK.AT_UNSAFE: attrs.append("unsafe")
                    elif tok.kind is TK.AT_EXTERN:
                        self._expect(TK.LPAREN)
                        extern_sym = self._expect(TK.STRING).value
                        self._expect(TK.RPAREN)
                        attrs.append("extern")
                else:
                    break

            if self._check(TK.FUNC):
                m = self._parse_func(loc_f, fld_pub, attrs, extern_sym)
                methods.append(m)
            else:
                f = self._parse_field_decl(fld_pub)
                fields.append(f)
        self._expect(TK.RBRACE)
        return ObjDecl(loc, is_pub, name, type_params, fields, methods)

    def _parse_field_decl(self, is_pub: bool, expect_semi: bool = True) -> FieldDecl:
        loc       = self._loc()
        qual, ty  = self._parse_qualifier_type()
        name      = self._expect_ident("expected field name")
        default: Optional[Expr] = None
        if self._match(TK.EQ):
            default = self._parse_expr()
        
        if expect_semi:
            self._expect(TK.SEMICOLON)
        else:
            self._match(TK.SEMICOLON)
            
        return FieldDecl(loc, qual, ty, name, default, is_pub)

    # ================================================================
    # Enum declaration
    # ================================================================

    def _parse_enum(self, loc: Loc, is_pub: bool) -> EnumDecl:
        self._expect(TK.ENUM)
        name        = self._expect_ident("expected enum name")
        type_params = self._parse_type_params()
        self._expect(TK.LBRACE)
        variants: List[EnumVariant] = []
        while not self._check(TK.RBRACE, TK.EOF):
            variants.append(self._parse_enum_variant())
            self._match(TK.COMMA)   # optional trailing comma
        self._expect(TK.RBRACE)
        return EnumDecl(loc, is_pub, name, type_params, variants)

    def _parse_enum_variant(self) -> EnumVariant:
        loc    = self._loc()
        vname  = self._expect_ident("expected variant name")
        fields: List[FieldDecl] = []
        if self._check(TK.LBRACE):
            self._advance()
            while not self._check(TK.RBRACE, TK.EOF):
                fields.append(self._parse_field_decl(False, expect_semi=False))
                self._match(TK.COMMA, TK.SEMICOLON)   # Optional separator
            self._expect(TK.RBRACE)
        return EnumVariant(loc, vname, fields)

    # ================================================================
    # Alias
    # ================================================================

    def _parse_alias(self, loc: Loc, is_pub: bool) -> AliasDecl:
        self._expect(TK.ALIAS)
        name = self._expect_ident("expected alias name")
        self._expect(TK.EQ)
        ty   = self._parse_type()
        self._expect(TK.SEMICOLON)
        return AliasDecl(loc, is_pub, name, ty)

    # ================================================================
    # Variable / constant declaration  (set / const)
    # ================================================================

    def _parse_var_item(self, loc: Loc, is_pub: bool) -> VarDecl:
        return self._parse_var_decl(loc, is_pub)

    def _parse_var_decl(self, loc: Optional[Loc] = None, is_pub: bool = False) -> VarDecl:
        loc = loc or self._loc()
        qual_tok = self._advance()            # SET or CONST
        qual     = qual_tok.value             # "set" | "const"
        self._expect(TK.COLON_COLON)
        ty = self._parse_type()

        # name list
        names: List[str] = []
        inits: List[Optional[Expr]] = []

        first_name = self._expect_ident("expected variable name")
        names.append(first_name)

        first_init: Optional[Expr] = None
        if self._match(TK.EQ):
            first_init = self._parse_expr()
        inits.append(first_init)

        while self._match(TK.COMMA):
            # could be  name = expr  or just  name
            if self._check(TK.IDENT) and self._peek(1).kind == TK.EQ:
                n = self._expect_ident()
                self._expect(TK.EQ)
                e = self._parse_expr()
                names.append(n)
                inits.append(e)
            elif self._check(TK.IDENT):
                names.append(self._expect_ident())
                inits.append(None)
            else:
                break

        self._expect(TK.SEMICOLON)
        return VarDecl(loc, is_pub, qual, ty, names, inits)

    # ================================================================
    # Array declaration  arr::T|N| name = (v1, v2, …);
    # ================================================================

    def _parse_arr_item(self, loc: Loc, is_pub: bool) -> ArrDecl:
        self._expect(TK.ARR)
        self._expect(TK.COLON_COLON)
        elem_ty = self._parse_type()
        self._expect(TK.PIPE)
        cap_tok = self._expect(TK.INT, "expected array capacity")
        cap = int(cap_tok.value.replace("_", ""))
        self._expect(TK.PIPE)
        name = self._expect_ident("expected array name")

        elements: List[Expr] = []
        if self._match(TK.EQ):
            self._expect(TK.LPAREN)
            while not self._check(TK.RPAREN, TK.EOF):
                elements.append(self._parse_expr())
                if not self._match(TK.COMMA):
                    break
            self._expect(TK.RPAREN)

        self._expect(TK.SEMICOLON)
        return ArrDecl(loc, is_pub, elem_ty, cap, name, elements)

    # ================================================================
    # Types
    # ================================================================

    def _parse_qualifier_type(self) -> Tuple[str, TypeNode]:
        """Parse  set::T  or  const::T  (qualifier + type)."""
        if self._check(TK.SET, TK.CONST):
            qual = self._advance().value
        else:
            qual = "set"
        self._expect(TK.COLON_COLON, "expected '::' after qualifier")
        ty = self._parse_type()
        return qual, ty

    def _parse_type(self) -> TypeNode:
        """Parse a complete type expression including optional modifiers."""
        loc  = self._loc()
        base = self._parse_base_type(loc)
        # Append [modifier] suffixes
        mods: List[str] = []
        while self._check(TK.LBRACKET):
            self._advance()
            if self._check(*_TYPE_MODS):
                mods.append(_MOD_NAME[self._advance().kind])
            else:
                raise ParseError("expected type modifier: long, short, ptr, opt",
                                  self._loc())
            self._expect(TK.RBRACKET)
        if mods:
            return ModifiedType(loc, base, mods)
        return base

    def _parse_base_type(self, loc: Loc) -> TypeNode:
        # Inferred type: _
        if self._check(TK.IDENT) and self._toks[self._pos].value == "_":
            self._advance()
            return InferType(loc)
        # Primitive types
        if self._check(*_PRIM_TYPES):
            name = _PRIM_NAME[self._advance().kind]
            return PrimType(loc, name)
        # func type
        if self._check(TK.FUNC):
            return self._parse_func_type(loc)
        # User-defined name or generic
        if self._check(TK.IDENT):
            name = self._advance().value
            if self._check(TK.LT):
                args = self._parse_type_args()
                return GenericType(loc, name, args)
            return NamedType(loc, name)
        # Tuple: (T1, T2)
        if self._check(TK.LPAREN):
            return self._parse_tuple_type(loc)
        raise ParseError(f"expected type, got '{self._toks[self._pos].value}'",
                          self._loc())

    def _parse_func_type(self, loc: Loc) -> FuncType:
        self._advance()   # 'func'
        self._expect(TK.LPAREN)
        params: List[TypeNode] = []
        while not self._check(TK.RPAREN, TK.EOF):
            params.append(self._parse_type())
            if not self._match(TK.COMMA):
                break
        self._expect(TK.RPAREN)
        self._expect(TK.ARROW)
        ret = self._parse_type()
        return FuncType(loc, params, ret)

    def _parse_tuple_type(self, loc: Loc) -> TupleType:
        self._expect(TK.LPAREN)
        elems: List[TypeNode] = []
        while not self._check(TK.RPAREN, TK.EOF):
            elems.append(self._parse_type())
            if not self._match(TK.COMMA):
                break
        self._expect(TK.RPAREN)
        return TupleType(loc, elems)

    def _parse_type_args(self) -> List[TypeNode]:
        """<T1, T2, …>"""
        self._expect(TK.LT)
        args: List[TypeNode] = []
        while not self._check(TK.GT, TK.EOF):
            args.append(self._parse_type())
            if not self._match(TK.COMMA):
                break
        self._expect(TK.GT)
        return args

    # ================================================================
    # Statements
    # ================================================================

    def _parse_block(self) -> Block:
        loc = self._loc()
        self._expect(TK.LBRACE)
        stmts: List[Stmt] = []
        while not self._check(TK.RBRACE, TK.EOF):
            try:
                s = self._parse_stmt()
                if s is not None:
                    stmts.append(s)
            except ParseError as e:
                self._reporter.error(str(e), e.loc)
                self._sync()
        self._expect(TK.RBRACE)
        return Block(loc, stmts)

    def _sync(self) -> None:
        """Panic-mode error recovery: skip tokens until a safe restart point."""
        while not self._check(*_STMT_SYNC):
            self._advance()
        if self._check(TK.SEMICOLON):
            self._advance()

    def _parse_stmt(self) -> Optional[Stmt]:
        loc = self._loc()

        # Labelled for-loop:  label: for ...
        if self._check(TK.IDENT) and self._peek(1).kind is TK.COLON \
                and self._peek(2).kind is TK.FOR:
            label = self._advance().value
            self._advance()   # ':'
            return self._parse_for(loc, label)

        if self._check(TK.SET, TK.CONST):
            return VarDeclStmt(loc, self._parse_var_decl())
        if self._check(TK.ARR):
            return ArrDeclStmt(loc, self._parse_arr_item(loc, False))
        if self._check(TK.IF):
            return self._parse_if()
        if self._check(TK.FOR):
            return self._parse_for(loc)
        if self._check(TK.MATCH):
            return self._parse_match_stmt()
        if self._check(TK.RETURN):
            return self._parse_return()
        if self._check(TK.BREAK):
            return self._parse_break()
        if self._check(TK.CONTINUE):
            return self._parse_continue()
        if self._check(TK.FAIL):
            return self._parse_fail()
        if self._check(TK.AT_UNSAFE):
            return self._parse_unsafe()
        if self._check(TK.AT_WHEN):
            return self._parse_when_stmt()
        if self._check(TK.SEMICOLON):
            self._advance()
            return None
        if self._check(TK.LBRACE):
            b = self._parse_block()
            return ExprStmt(loc, b)        # treat bare block as ExprStmt

        # Expression statement (may be assignment or expr)
        return self._parse_expr_or_assign_stmt()

    def _parse_expr_or_assign_stmt(self) -> Stmt:
        loc  = self._loc()
        expr = self._parse_expr()

        # x++  or  x--
        if self._check(TK.PLUS_PLUS, TK.MINUS_MINUS):
            op = self._advance().value
            self._expect(TK.SEMICOLON)
            return IncrDecrStmt(loc, expr, op)

        # x = e | x += e | …
        if self._check(*_ASSIGN_OPS):
            op = self._advance().value
            val = self._parse_expr()
            self._expect(TK.SEMICOLON)
            return AssignStmt(loc, expr, op, val)

        # Semicolon is optional if followed by '}' (end of block)
        if not self._match(TK.SEMICOLON):
            if not self._check(TK.RBRACE):
                self._expect(TK.SEMICOLON)

        return ExprStmt(loc, expr)

    # ---------------------------------------------------------------- if

    def _parse_if(self) -> IfStmt:
        loc = self._loc()
        self._expect(TK.IF)
        cond      = self._parse_expr()
        then_body = self._parse_block()
        elif_branches: List[Tuple[Expr, Block]] = []
        else_body: Optional[Block] = None

        while self._check(TK.ELSE):
            self._advance()
            if self._check(TK.IF):
                self._advance()
                elif_cond = self._parse_expr()
                elif_body = self._parse_block()
                elif_branches.append((elif_cond, elif_body))
            else:
                else_body = self._parse_block()
                break

        return IfStmt(loc, cond, then_body, elif_branches, else_body)

    # ---------------------------------------------------------------- for

    def _parse_for(self, loc: Loc, label: Optional[str] = None) -> Stmt:
        self._expect(TK.FOR)

        # for { … }  → infinite loop
        if self._check(TK.LBRACE):
            body = self._parse_block()
            return ForInfiniteStmt(loc, body, label)

        # Peek for  IDENT [','] 'in'  pattern
        # e.g.  for i in  or  for i, item in
        if self._check(TK.IDENT):
            saved = self._pos
            name1 = self._advance().value
            if self._check(TK.COMMA):
                self._advance()
                if self._check(TK.IDENT):
                    name2 = self._advance().value
                    if self._check(TK.IN):
                        self._advance()
                        iterable = self._parse_expr()
                        body     = self._parse_block()
                        return ForInStmt(loc, name1, name2, iterable, body, label)
                # restore
                self._pos = saved
            elif self._check(TK.IN):
                self._advance()
                # could be range or iterable
                start = self._parse_expr_no_range()
                if self._check(TK.DOT_DOT, TK.DOT_DOT_LT):
                    inclusive = self._advance().kind is TK.DOT_DOT
                    end  = self._parse_expr()
                    body = self._parse_block()
                    rng  = RangeExpr(loc, start, end, inclusive)
                    return ForRangeStmt(loc, name1, rng, body, label)
                # plain iteration
                body = self._parse_block()
                return ForInStmt(loc, None, name1, start, body, label)
            else:
                # not 'in', restore and parse as condition
                self._pos = saved

        # for cond { … }  → conditional loop
        cond = self._parse_expr()
        body = self._parse_block()
        return ForCondStmt(loc, cond, body, label)

    # ---------------------------------------------------------------- match

    def _parse_match_stmt(self) -> MatchStmt:
        loc = self._loc()
        self._expect(TK.MATCH)
        subject = self._parse_expr()
        self._expect(TK.LBRACE)
        arms: List[MatchArm] = []
        while not self._check(TK.RBRACE, TK.EOF):
            arms.append(self._parse_match_arm())
        self._expect(TK.RBRACE)
        return MatchStmt(loc, subject, arms)

    def _parse_match_arm(self) -> MatchArm:
        loc = self._loc()
        pattern = self._parse_pattern()

        # guard:  if expr
        guard: Optional[Expr] = None
        if self._check(TK.IF):
            self._advance()
            guard = self._parse_expr()

        self._expect(TK.FAT_ARROW)

        # body is either a block or a single expression followed by a comma
        if self._check(TK.LBRACE):
            body = self._parse_block()
        else:
            expr = self._parse_expr()
            self._match(TK.COMMA)
            body = Block(loc, [ExprStmt(loc, expr)])

        return MatchArm(loc, pattern, guard, body)

    def _parse_pattern(self) -> Pattern:
        loc = self._loc()

        # Wildcard: _
        if self._check(TK.IDENT) and self._toks[self._pos].value == "_":
            self._advance()
            return WildcardPattern(loc)

        # Or-pattern chain built up below
        patterns: List[Pattern] = []
        patterns.append(self._parse_single_pattern())

        # 1 | 2 | …  (OR pattern)
        while self._check(TK.PIPE) and not self._is_lambda_start():
            self._advance()
            patterns.append(self._parse_single_pattern())

        if len(patterns) == 1:
            return patterns[0]
        return OrPattern(loc, patterns)

    def _parse_single_pattern(self) -> Pattern:
        loc = self._loc()

        # Enum pattern: Name::Variant { fields }
        if self._check(TK.IDENT) and self._peek(1).kind is TK.COLON_COLON:
            enum_name = self._advance().value
            self._advance()   # ::
            variant_name = self._expect_ident("expected variant name")
            fields: List[str] = []
            if self._check(TK.LBRACE):
                self._advance()
                while not self._check(TK.RBRACE, TK.EOF):
                    fields.append(self._expect_ident())
                    self._match(TK.COMMA)
                self._expect(TK.RBRACE)
            return EnumPattern(loc, enum_name, variant_name, fields)

        # Identifier binding (name only, no ::)
        if self._check(TK.IDENT):
            name = self._advance().value
            return IdentPattern(loc, name)

        # Literal
        lit = self._parse_primary()
        return LiteralPattern(loc, lit)

    # ---------------------------------------------------------------- return / break / continue / fail

    def _parse_return(self) -> ReturnStmt:
        loc = self._loc()
        self._advance()
        val: Optional[Expr] = None
        if not self._check(TK.SEMICOLON, TK.RBRACE):
            val = self._parse_expr()
        self._expect(TK.SEMICOLON)
        return ReturnStmt(loc, val)

    def _parse_break(self) -> BreakStmt:
        loc = self._loc()
        self._advance()
        label: Optional[str] = None
        if self._check(TK.IDENT):
            label = self._advance().value
        self._expect(TK.SEMICOLON)
        return BreakStmt(loc, label)

    def _parse_continue(self) -> ContinueStmt:
        loc = self._loc()
        self._advance()
        label: Optional[str] = None
        if self._check(TK.IDENT):
            label = self._advance().value
        self._expect(TK.SEMICOLON)
        return ContinueStmt(loc, label)

    def _parse_fail(self) -> FailStmt:
        loc = self._loc()
        self._advance()
        val: Optional[Expr] = None
        if not self._check(TK.SEMICOLON):
            val = self._parse_expr()
        self._expect(TK.SEMICOLON)
        return FailStmt(loc, val)

    # ---------------------------------------------------------------- @unsafe / @when

    def _parse_unsafe(self) -> UnsafeBlock:
        loc = self._loc()
        self._advance()
        body = self._parse_block()
        return UnsafeBlock(loc, body)

    def _parse_when_cond(self) -> Expr:
        self._expect(TK.LPAREN)
        cond = self._parse_expr()
        self._expect(TK.RPAREN)
        return cond

    def _parse_when_stmt(self) -> WhenBlock:
        loc = self._loc()
        self._advance()   # @when
        cond = self._parse_when_cond()
        body = self._parse_block()
        return WhenBlock(loc, cond, body)

    # ================================================================
    # Expressions — precedence climbing
    # ================================================================

    def _parse_expr(self) -> Expr:
        return self._parse_binary(0)

    def _parse_expr_no_range(self) -> Expr:
        """Parse an expression that does not consume '..' or '..<'."""
        return self._parse_binary(0, stop_at_range=True)

    def _parse_binary(self, min_prec: int, stop_at_range: bool = False) -> Expr:
        loc  = self._loc()
        left = self._parse_cast_or_unary()

        while True:
            tok  = self._toks[self._pos]
            prec = _PREC.get(tok.kind)
            if prec is None or prec < min_prec:
                break
            if stop_at_range and tok.kind in (TK.DOT_DOT, TK.DOT_DOT_LT):
                break

            op = self._advance()

            # null-coalesce  ??  is right-assoc
            if op.kind is TK.QUEST_QUEST:
                right = self._parse_binary(prec)
                left  = NullCoalesceExpr(loc, left, right)
                continue

            # range operator (produces a RangeExpr, not BinaryExpr)
            if op.kind in (TK.DOT_DOT, TK.DOT_DOT_LT):
                inclusive = op.kind is TK.DOT_DOT
                right     = self._parse_binary(prec + 1)
                left      = RangeExpr(loc, left, right, inclusive)
                continue

            # right-associative
            next_min = prec if tok.kind in _RIGHT_ASSOC else prec + 1
            right    = self._parse_binary(next_min)
            left     = BinaryExpr(loc, op.value, left, right)

        # catch-expression postfix:  expr catch [err] { block }
        while self._check(TK.CATCH):
            loc = self._loc()
            self._advance()
            err_name: Optional[str] = None
            if self._check(TK.IDENT) and not self._check(TK.LBRACE):
                err_name = self._advance().value
            handler = self._parse_block()
            left    = CatchExpr(loc, left, err_name, handler)

        return left

    # ---------------------------------------------------------------- unary / prefix

    def _parse_cast_or_unary(self) -> Expr:
        loc = self._loc()

        # try expr
        if self._check(TK.NEW):
            self._advance()
            ty = self._parse_type()
            self._expect(TK.LPAREN)
            args = []
            while not self._check(TK.RPAREN, TK.EOF):
                args.append(self._parse_expr())
                self._match(TK.COMMA)
            self._expect(TK.RPAREN)
            return NewExpr(loc, ty, args)

        if self._check(TK.TRY):
            self._advance()
            inner = self._parse_cast_or_unary()
            return TryExpr(loc, inner)

        # cast(T, val)
        if self._check(TK.CAST):
            self._advance()
            self._expect(TK.LPAREN)
            ty  = self._parse_type()
            self._expect(TK.COMMA)
            val = self._parse_expr()
            self._expect(TK.RPAREN)
            return CastExpr(loc, ty, val)

        # transmute(T, val)
        if self._check(TK.TRANSMUTE):
            self._advance()
            self._expect(TK.LPAREN)
            ty  = self._parse_type()
            self._expect(TK.COMMA)
            val = self._parse_expr()
            self._expect(TK.RPAREN)
            return TransmuteExpr(loc, ty, val)

        # sizeof(T)
        if self._check(TK.SIZEOF):
            self._advance()
            self._expect(TK.LPAREN)
            ty = self._parse_type()
            self._expect(TK.RPAREN)
            return SizeofExpr(loc, ty)

        # alignof(T)
        if self._check(TK.ALIGNOF):
            self._advance()
            self._expect(TK.LPAREN)
            ty = self._parse_type()
            self._expect(TK.RPAREN)
            return AlignofExpr(loc, ty)

        # alloc(T, n)
        if self._check(TK.ALLOC):
            self._advance()
            self._expect(TK.LPAREN)
            ty = self._parse_type()
            self._expect(TK.COMMA)
            n  = self._parse_expr()
            self._expect(TK.RPAREN)
            return AllocExpr(loc, ty, n)

        # free(ptr)
        if self._check(TK.FREE):
            self._advance()
            self._expect(TK.LPAREN)
            ptr = self._parse_expr()
            self._expect(TK.RPAREN)
            return FreeExpr(loc, ptr)

        # memcpy(dst, src, n)
        if self._check(TK.MEMCPY):
            self._advance()
            self._expect(TK.LPAREN)
            dst = self._parse_expr(); self._expect(TK.COMMA)
            src = self._parse_expr(); self._expect(TK.COMMA)
            n   = self._parse_expr()
            self._expect(TK.RPAREN)
            return MemcpyExpr(loc, dst, src, n)

        # memset(dst, val, n)
        if self._check(TK.MEMSET):
            self._advance()
            self._expect(TK.LPAREN)
            dst = self._parse_expr(); self._expect(TK.COMMA)
            val = self._parse_expr(); self._expect(TK.COMMA)
            n   = self._parse_expr()
            self._expect(TK.RPAREN)
            return MemsetExpr(loc, dst, src, n)

        # prefix unary: - ! ~ * &
        if self._check(*_UNARY_OPS):
            op      = self._advance().value
            operand = self._parse_cast_or_unary()
            return UnaryExpr(loc, op, operand)

        return self._parse_postfix()

    # ---------------------------------------------------------------- postfix / primary

    def _parse_postfix(self) -> Expr:
        expr = self._parse_primary()
        while True:
            loc = self._loc()
            # method call: expr.name(...)  or  field: expr.name
            if self._check(TK.DOT):
                self._advance()
                field = self._expect_ident("expected field or method name")
                if self._check(TK.LPAREN):
                    type_args, args = self._parse_call_args()
                    expr = MethodCallExpr(loc, expr, field, type_args, args)
                else:
                    expr = FieldExpr(loc, expr, field)
                continue
            # optional chain: expr?.field
            if self._check(TK.QUEST_DOT):
                self._advance()
                field = self._expect_ident("expected field name after '?.'")
                expr  = OptChainExpr(loc, expr, field)
                continue
            # function call: expr(args)
            if self._check(TK.LPAREN):
                type_args, args = self._parse_call_args()
                expr = CallExpr(loc, expr, type_args, args)
                continue
            # index: expr[idx]
            if self._check(TK.LBRACKET) and not self._is_type_modifier():
                self._advance()
                idx  = self._parse_expr()
                self._expect(TK.RBRACKET)
                expr = IndexExpr(loc, expr, idx)
                continue
            break
        return expr

    def _is_type_modifier(self) -> bool:
        """Return True if the '[' starts a type modifier like [ptr], not an index."""
        if not self._check(TK.LBRACKET):
            return False
        return self._peek(1).kind in _TYPE_MODS

    def _parse_call_args(self) -> Tuple[List[TypeNode], List[Expr]]:
        """Parse optional <T> type args followed by (arg, …)."""
        type_args: List[TypeNode] = []
        self._expect(TK.LPAREN)
        args: List[Expr] = []
        while not self._check(TK.RPAREN, TK.EOF):
            args.append(self._parse_expr())
            if not self._match(TK.COMMA):
                break
        self._expect(TK.RPAREN)
        return type_args, args

    def _parse_primary(self) -> Expr:
        loc = self._loc()
        tok = self._toks[self._pos]

        # Integer literal
        if tok.kind is TK.INT:
            self._advance()
            raw = tok.value
            val = int(raw.replace("_", ""), 0)
            return IntLit(loc, raw, val)

        # Float literal
        if tok.kind is TK.FLOAT:
            self._advance()
            raw = tok.value.replace("_", "")
            return FloatLit(loc, tok.value, float(raw))

        # String literal
        if tok.kind is TK.STRING:
            self._advance()
            return StringLit(loc, tok.value)

        # Char literal
        if tok.kind is TK.CHAR:
            self._advance()
            return CharLit(loc, tok.value)

        # Boolean literals
        if tok.kind is TK.TRUE:
            self._advance()
            return BoolLit(loc, True)
        if tok.kind is TK.FALSE:
            self._advance()
            return BoolLit(loc, False)

        # Null
        if tok.kind is TK.NULL:
            self._advance()
            return NullLit(loc)

        # self keyword
        if tok.kind is TK.SELF:
            self._advance()
            return IdentExpr(loc, "self")

        # Lambda:  |x, y| expr  or  || expr
        if tok.kind is TK.PIPE:
            return self._parse_lambda(loc)

        # if-expression
        if tok.kind is TK.IF:
            return self._parse_if_expr(loc)

        # match-expression
        if tok.kind is TK.MATCH:
            return self._parse_match_expr(loc)

        # Parenthesised expression or tuple
        if tok.kind is TK.LPAREN:
            return self._parse_paren_or_tuple(loc)

        # Identifier: may be  Name::Variant  or  Name { fields }  or bare
        if tok.kind is TK.IDENT:
            name = self._advance().value
            # path:  Name::Variant  or  Module::sym
            if self._check(TK.COLON_COLON):
                return self._parse_path_or_enum(loc, name)
            # struct literal:  Name { field = val, … }
            if self._check(TK.LBRACE) and self._is_struct_literal():
                return self._parse_struct_literal(loc, name)
            return IdentExpr(loc, name)

        raise ParseError(
            f"unexpected token '{tok.value}' in expression",
            self._loc(),
        )

    # ---------------------------------------------------------------- helpers

    def _is_lambda_start(self) -> bool:
        """Peek ahead to detect  | ident, ident | expr  or  | | expr."""
        if not self._check(TK.PIPE):
            return False
        i = self._pos + 1
        n = len(self._toks)
        # empty params: ||
        if i < n and self._toks[i].kind is TK.PIPE:
            return True
        # one or more ident params followed by |
        while i < n and self._toks[i].kind is TK.IDENT:
            i += 1
            if i < n and self._toks[i].kind is TK.PIPE:
                return True
            if i < n and self._toks[i].kind is TK.COMMA:
                i += 1
                continue
            break
        return False

    def _is_struct_literal(self) -> bool:
        """Peek past '{' to check if it looks like a struct literal (name = value)."""
        i = self._pos + 1   # skip '{'
        n = len(self._toks)
        if i >= n:
            return False
        if self._toks[i].kind is TK.RBRACE:
            return False
        # field_name = ...
        return (i < n and self._toks[i].kind is TK.IDENT
                and i + 1 < n and self._toks[i + 1].kind is TK.EQ)

    def _parse_lambda(self, loc: Loc) -> LambdaExpr:
        self._advance()   # consume first '|'
        params: List[str] = []
        while not self._check(TK.PIPE, TK.EOF):
            params.append(self._expect_ident("expected lambda parameter name"))
            self._match(TK.COMMA)
        self._expect(TK.PIPE)
        body = self._parse_expr()
        return LambdaExpr(loc, params, body)

    def _parse_if_expr(self, loc: Loc) -> IfExpr:
        self._advance()   # 'if'
        cond = self._parse_expr()
        then = self._parse_block()
        self._expect(TK.ELSE)
        else_ = self._parse_block()
        # Wrap blocks in a single-expression if they hold exactly one ExprStmt
        def _unwrap(b: Block) -> Expr:
            if len(b.stmts) == 1 and isinstance(b.stmts[0], ExprStmt):
                return b.stmts[0].expr
            return b  # type: ignore[return-value]
        return IfExpr(loc, cond, _unwrap(then), _unwrap(else_))

    def _parse_match_expr(self, loc: Loc) -> MatchExpr:
        self._advance()   # 'match'
        subject = self._parse_expr()
        self._expect(TK.LBRACE)
        arms: List[MatchArm] = []
        while not self._check(TK.RBRACE, TK.EOF):
            arms.append(self._parse_match_arm())
        self._expect(TK.RBRACE)
        return MatchExpr(loc, subject, arms)

    def _parse_paren_or_tuple(self, loc: Loc) -> Expr:
        self._advance()   # '('
        if self._check(TK.RPAREN):
            self._advance()
            return TupleExpr(loc, [])
        first = self._parse_expr()
        if self._check(TK.RPAREN):
            self._advance()
            return first  # just (expr)
        # Tuple: (a, b, …)
        elems = [first]
        while self._match(TK.COMMA):
            if self._check(TK.RPAREN):
                break
            elems.append(self._parse_expr())
        self._expect(TK.RPAREN)
        return TupleExpr(loc, elems)

    def _parse_path_or_enum(self, loc: Loc, first: str) -> Expr:
        """first::name  or  first::Variant { … }"""
        self._advance()   # '::'
        second = self._expect_ident("expected name after '::'")

        # Enum variant with fields:  Enum::Variant { field = val }
        if self._check(TK.LBRACE) and self._is_struct_literal():
            fields = self._parse_struct_fields()
            return EnumVariantExpr(loc, first, second, fields)

        # Plain enum variant or module path
        return PathExpr(loc, [first, second])

    def _parse_struct_literal(self, loc: Loc, name: str) -> StructLiteral:
        fields = self._parse_struct_fields()
        return StructLiteral(loc, name, fields)

    def _parse_struct_fields(self) -> List[Tuple[str, Expr]]:
        self._expect(TK.LBRACE)
        fields: List[Tuple[str, Expr]] = []
        while not self._check(TK.RBRACE, TK.EOF):
            fname = self._expect_ident("expected field name")
            self._expect(TK.EQ)
            fval  = self._parse_expr()
            fields.append((fname, fval))
            if not self._match(TK.COMMA):
                break
        self._expect(TK.RBRACE)
        return fields
