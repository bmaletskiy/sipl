"""SIPL parser: source text -> typed AST (own nodes, not Lark trees)."""
from __future__ import annotations

import re

from lark import Lark, Token, Transformer, v_args
from lark.exceptions import UnexpectedCharacters, UnexpectedInput, UnexpectedToken

from sipl import ast

_PARSER = Lark.open_from_package(
    "sipl", "grammar/sipl.lark", parser="lalr", start="program", propagate_positions=True
)

_TERMINAL_NAMES = {
    "VAR": "variable",
    "NUMBER": "number",
    "ADD": "'+' or '-'",
    "MUL": "'*'",
    "CMP": "'=' or '>'",
    "$END": "end of input",
}


class SiplSyntaxError(Exception):
    """Syntax error with the exact position of the offending text."""

    def __init__(self, message: str, span: ast.SourceSpan, expected: tuple[str, ...]):
        super().__init__(f"line {span.start_line}, column {span.start_column}: {message}")
        self.message = message
        self.span = span
        self.expected = expected

    @property
    def line(self) -> int:
        return self.span.start_line

    @property
    def column(self) -> int:
        return self.span.start_column


@v_args(meta=True)
class _Builder(Transformer):
    def __init__(self, source: ast.SourceMap):
        super().__init__()
        self._src = source

    def _tok(self, tok: Token) -> ast.SourceSpan:
        return self._src.span(tok.start_pos, tok.end_pos)

    def _meta(self, meta) -> ast.SourceSpan:
        return self._src.span(meta.start_pos, meta.end_pos)

    def program(self, meta, items):
        return ast.Program(items[0], span=self._meta(meta))

    def seq(self, meta, items):
        node = items[0]
        for nxt in items[1:]:
            node = ast.Seq(node, nxt, span=ast.span_between(node.span, nxt.span))
        return node

    def assign(self, meta, items):
        name, expr = items
        target = ast.Var(name.value, span=self._tok(name))
        return ast.Assign(target, expr, span=ast.span_between(target.span, expr.span))

    def if_stmt(self, meta, items):
        return ast.If(*items, span=self._meta(meta))

    def while_stmt(self, meta, items):
        return ast.While(*items, span=self._meta(meta))

    def block(self, meta, items):
        return ast.Block(items[0], span=self._meta(meta))

    def skip(self, meta, items):
        return ast.Skip(span=self._meta(meta))

    def or_(self, meta, items):
        left, right = items
        return ast.Or(left, right, span=ast.span_between(left.span, right.span))

    def not_(self, meta, items):
        return ast.Not(items[0], span=self._meta(meta))

    def compare(self, meta, items):
        left, op, right = items
        return ast.Compare(op.value, left, right, span=ast.span_between(left.span, right.span))

    def binop(self, meta, items):
        left, op, right = items
        return ast.BinOp(op.value, left, right, span=ast.span_between(left.span, right.span))

    def num(self, meta, items):
        return ast.Num(int(items[0].value), span=self._tok(items[0]))

    def var(self, meta, items):
        return ast.Var(items[0].value, span=self._tok(items[0]))


def _describe(terminal: str) -> str:
    if terminal in _TERMINAL_NAMES:
        return _TERMINAL_NAMES[terminal]
    return f"'{_PARSER.get_terminal(terminal).pattern.value}'"


def _syntax_error(text: str, exc: UnexpectedInput) -> SiplSyntaxError:
    source = ast.SourceMap(text)
    if isinstance(exc, UnexpectedToken):
        expected = exc.accepts or exc.expected
        if exc.token.type == "$END":
            span, found = source.span(len(text), len(text)), "end of input"
        else:
            span = source.span(exc.token.start_pos, exc.token.end_pos)
            found = f"'{exc.token.value}'"
    else:
        assert isinstance(exc, UnexpectedCharacters)
        expected = exc.allowed
        word = re.compile(r"\w+|.", re.S).match(text, exc.pos_in_stream).group()
        span = source.span(exc.pos_in_stream, exc.pos_in_stream + len(word))
        found = f"'{word}'"
    names = tuple(sorted({_describe(t) for t in expected}))
    return SiplSyntaxError(f"unexpected {found}, expected {', '.join(names)}", span, names)


def parse(text: str) -> ast.Program:
    """Parse a SIPL program; raise SiplSyntaxError with a precise position on failure."""
    try:
        tree = _PARSER.parse(text)
    except UnexpectedInput as exc:
        raise _syntax_error(text, exc) from None
    return _Builder(ast.SourceMap(text)).transform(tree)
