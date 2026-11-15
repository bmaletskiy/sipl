"""Typed AST for SIPL (abstract syntax: parentheses are not represented)."""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field, fields
from typing import Any, Iterator


@dataclass(frozen=True)
class SourceSpan:
    """Range [start, end) in the source text; lines and columns are 1-based."""

    start: int
    end: int
    start_line: int
    start_column: int
    end_line: int
    end_column: int

    def to_dict(self) -> dict[str, dict[str, int]]:
        return {
            "start": {"line": self.start_line, "column": self.start_column, "offset": self.start},
            "end": {"line": self.end_line, "column": self.end_column, "offset": self.end},
        }


NO_SPAN = SourceSpan(0, 0, 1, 1, 1, 1)


class SourceMap:
    """Converts character offsets of a source text to SourceSpan (1-based lines and columns)."""

    def __init__(self, text: str):
        self._starts = [0] + [m.end() for m in re.finditer("\n", text)]

    def _locate(self, offset: int) -> tuple[int, int]:
        line = bisect.bisect_right(self._starts, offset)
        return line, offset - self._starts[line - 1] + 1

    def span(self, start: int, end: int) -> SourceSpan:
        return SourceSpan(start, end, *self._locate(start), *self._locate(end))


def span_between(first: SourceSpan, last: SourceSpan) -> SourceSpan:
    return SourceSpan(first.start, last.end, first.start_line, first.start_column,
                      last.end_line, last.end_column)


@dataclass(frozen=True)
class Node:
    # Spans are ignored by ==, so trees can be compared structurally.
    span: SourceSpan = field(default=NO_SPAN, compare=False, repr=False, kw_only=True)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"type": type(self).__name__, "span": self.span.to_dict()}
        for f in fields(self):
            if f.name != "span":
                value = getattr(self, f.name)
                data[f.name] = value.to_dict() if isinstance(value, Node) else value
        return data


# Arithmetic expressions
@dataclass(frozen=True)
class Num(Node):
    value: int


@dataclass(frozen=True)
class Var(Node):
    name: str


@dataclass(frozen=True)
class BinOp(Node):
    op: str  # "+", "-" or "*"
    left: Aexp
    right: Aexp


# Conditions
@dataclass(frozen=True)
class Compare(Node):
    op: str  # "=" or ">"
    left: Aexp
    right: Aexp


@dataclass(frozen=True)
class Or(Node):
    left: Bexp
    right: Bexp


@dataclass(frozen=True)
class Not(Node):
    operand: Bexp


# Statements
@dataclass(frozen=True)
class Assign(Node):
    target: Var
    expr: Aexp


@dataclass(frozen=True)
class Seq(Node):
    first: Stm
    second: Stm


@dataclass(frozen=True)
class If(Node):
    cond: Bexp
    then: Stm
    orelse: Stm


@dataclass(frozen=True)
class While(Node):
    cond: Bexp
    body: Stm


@dataclass(frozen=True)
class Block(Node):
    body: Stm


@dataclass(frozen=True)
class Skip(Node):
    pass


@dataclass(frozen=True)
class Program(Node):
    body: Stm


Aexp = Num | Var | BinOp
Bexp = Compare | Or | Not
Stm = Assign | Seq | If | While | Block | Skip


def children(node: Node) -> Iterator[Node]:
    for f in fields(node):
        value = getattr(node, f.name)
        if isinstance(value, Node):
            yield value


def walk(node: Node) -> Iterator[Node]:
    """Pre-order traversal of the tree rooted at `node`."""
    yield node
    for child in children(node):
        yield from walk(child)


def dump(node: Node) -> str:
    """Indented text rendering of a tree: node types and their non-node fields."""
    lines, stack = [], [(node, 0)]
    while stack:
        current, depth = stack.pop()
        scalars = " ".join(
            f"{f.name}={getattr(current, f.name)!r}" for f in fields(current)
            if f.name != "span" and not isinstance(getattr(current, f.name), Node))
        lines.append("  " * depth + type(current).__name__ + (f" {scalars}" if scalars else ""))
        stack.extend((child, depth + 1) for child in reversed(list(children(current))))
    return "\n".join(lines)
