"""Execution events: the data model shared by trace, CLI, debugger and visualizers.

Events are emitted around every `assign`, `skip`, `if` and `while` statement
(`;` and `begin ... end` are structure only and produce no events of their own).
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

from sipl.ast import SourceSpan
from sipl.interpreter.state import State


@dataclass(frozen=True)
class Event:
    step: int  # interpreter step counter when the event was emitted
    span: SourceSpan  # source fragment the event refers to

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"event": type(self).__name__, "step": self.step,
                                "span": self.span.to_dict()}
        for f in fields(self):
            if f.name not in ("step", "span"):
                value = getattr(self, f.name)
                data[f.name] = dict(value) if isinstance(value, State) else value
        return data


@dataclass(frozen=True)
class BeforeStatement(Event):
    statement: str  # "assign", "skip", "if" or "while"
    state: State  # state before the statement


@dataclass(frozen=True)
class AfterStatement(Event):
    statement: str
    state: State  # state after the statement


@dataclass(frozen=True)
class VariableChanged(Event):
    name: str
    old: int | None  # None if the variable was undefined
    new: int


@dataclass(frozen=True)
class ConditionEvaluated(Event):
    statement: str  # "if" or "while"; span is the condition itself
    value: bool
    state: State


@dataclass(frozen=True)
class Finished(Event):
    state: State  # final state; span is the whole program


@dataclass(frozen=True)
class Failed(Event):
    error: str  # class name, e.g. "UndefinedVariableError"
    message: str  # span is the failing fragment
