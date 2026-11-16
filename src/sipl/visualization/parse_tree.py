"""Parse tree (derivation tree) of a SIPL program in the notation of the course BNF.

Unlike the AST, the parse tree keeps every terminal (`begin`, `:=`, `;`, parentheses, ...) and the
syntactic categories of the course: <програма>, <оператор>, <вираз>, <умова>, <змінна>, <число>.
It is built from the real parser output, never drawn by hand.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from lark import Lark, Token, Tree

from sipl import ast
from sipl.parser import parse

PROGRAM, STATEMENT, ARITHMETIC, CONDITION, VARIABLE, NUMBER = (
    "<програма>", "<оператор>", "<вираз>", "<умова>", "<змінна>", "<число>")

_PARSER = Lark.open_from_package("sipl", "grammar/sipl.lark", parser="lalr", start="program",
                                 keep_all_tokens=True)

# Rules whose children correspond one-to-one to a production of the course BNF.
_SYMBOLS = {
    "program": PROGRAM,
    "if_stmt": STATEMENT, "while_stmt": STATEMENT, "block": STATEMENT, "skip": STATEMENT,
    "or_": CONDITION, "not_": CONDITION, "compare": CONDITION, "atom_cond": CONDITION,
    "binop": ARITHMETIC, "factor": ARITHMETIC,
}


@dataclass(frozen=True)
class ParseNode:
    symbol: str  # a category such as "<оператор>", or the text of a terminal
    children: tuple[ParseNode, ...]  # empty for terminals
    span: ast.SourceSpan  # the source fragment derived from this node
    number: int | None = None  # terminals only: position among all terminals, from 1

    @property
    def is_terminal(self) -> bool:
        return not self.children


@dataclass(frozen=True)
class ParseTree:
    root: ParseNode
    source: str

    def nodes(self) -> Iterator[ParseNode]:
        """All nodes in pre-order."""
        stack = [self.root]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.children))

    def leaves(self) -> Iterator[ParseNode]:
        """Terminals from left to right."""
        return (node for node in self.nodes() if node.is_terminal)

    def fragment(self, node: ParseNode) -> str:
        return self.source[node.span.start:node.span.end]

    def numbered_leaves(self) -> str:
        """The check from the course workbook: the terminals read left to right, e.g. `1 begin 2 R`."""
        return " ".join(f"{leaf.number} {leaf.symbol}" for leaf in self.leaves())


class _Converter:
    def __init__(self, source: ast.SourceMap):
        self._source = source
        self._count = 0

    def _terminal(self, token: Token) -> ParseNode:
        self._count += 1
        return ParseNode(token.value, (), self._source.span(token.start_pos, token.end_pos), self._count)

    @staticmethod
    def _node(symbol: str, children: list[ParseNode]) -> ParseNode:
        return ParseNode(symbol, tuple(children), ast.span_between(children[0].span, children[-1].span))

    def convert(self, item: Token | Tree) -> ParseNode:
        if isinstance(item, Token):
            return self._terminal(item)
        rule = str(item.data)
        if rule == "seq":  # <оператор> ::= <оператор> ; <оператор>, left-associative
            node = self.convert(item.children[0])
            for i in range(1, len(item.children), 2):
                node = self._node(STATEMENT, [node, self._terminal(item.children[i]),
                                              self.convert(item.children[i + 1])])
            return node
        if rule == "assign":
            name, assign_op, expr = item.children
            return self._node(STATEMENT, [self._node(VARIABLE, [self._terminal(name)]),
                                          self._terminal(assign_op), self.convert(expr)])
        if rule in ("num", "var"):
            layer = NUMBER if rule == "num" else VARIABLE
            return self._node(ARITHMETIC, [self._node(layer, [self._terminal(item.children[0])])])
        return self._node(_SYMBOLS[rule], [self.convert(child) for child in item.children])


def build_parse_tree(text: str) -> ParseTree:
    """Build the parse tree; raise SiplSyntaxError with a precise position for an invalid program."""
    parse(text)
    return ParseTree(_Converter(ast.SourceMap(text)).convert(_PARSER.parse(text)), text)
