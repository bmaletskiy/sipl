"""Semantic terms of the program algebra A_SIPL, printed in the notation of the course.

    constant 5        variable dereference x⇒        superposition S²(add, f, g), S¹(neg, f)
    assignment ASx(f) sequence f · g                 IF(b, f, g)   WH(b, f)   id
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

_SUPERSCRIPT = {1: "¹", 2: "²"}


@dataclass(frozen=True)
class Term:
    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"type": type(self).__name__}
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, Term):
                value = value.to_dict()
            elif isinstance(value, tuple):
                value = [item.to_dict() for item in value]
            data[f.name] = value
        return data


@dataclass(frozen=True)
class Const(Term):
    value: int

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class Deref(Term):
    name: str

    def __str__(self) -> str:
        return f"{self.name}⇒"


@dataclass(frozen=True)
class Super(Term):
    op: str  # add, sub, mult, eq, gr, or, neg
    args: tuple[Term, ...]  # one argument (neg) or two

    def __str__(self) -> str:
        return f"S{_SUPERSCRIPT[len(self.args)]}({self.op}, {', '.join(map(str, self.args))})"


@dataclass(frozen=True)
class Assign(Term):
    name: str
    expr: Term

    def __str__(self) -> str:
        return f"AS{self.name}({self.expr})"


@dataclass(frozen=True)
class Compose(Term):
    first: Term
    second: Term

    def __str__(self) -> str:
        # f · g · h is (f · g) · h; a sequence on the right comes from `begin ... end` and keeps its parentheses
        right = f"({self.second})" if isinstance(self.second, Compose) else str(self.second)
        return f"{self.first} · {right}"


@dataclass(frozen=True)
class If(Term):
    cond: Term
    then: Term
    orelse: Term

    def __str__(self) -> str:
        return f"IF({self.cond}, {self.then}, {self.orelse})"


@dataclass(frozen=True)
class While(Term):
    cond: Term
    body: Term

    def __str__(self) -> str:
        return f"WH({self.cond}, {self.body})"


@dataclass(frozen=True)
class Identity(Term):
    def __str__(self) -> str:
        return "id"
