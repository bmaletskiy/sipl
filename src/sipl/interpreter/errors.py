"""Explicit runtime errors; every error carries the source span of the failing node."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sipl.ast import SourceSpan

if TYPE_CHECKING:
    from sipl.interpreter.state import State


class SiplRuntimeError(Exception):
    def __init__(self, message: str, span: SourceSpan):
        super().__init__(f"line {span.start_line}, column {span.start_column}: {message}")
        self.message = message
        self.span = span


class UndefinedVariableError(SiplRuntimeError):
    """A variable is read before it was assigned (the course semantics is undefined here)."""

    def __init__(self, name: str, span: SourceSpan):
        super().__init__(f"variable '{name}' is not defined", span)
        self.name = name


class StepLimitExceeded(SiplRuntimeError):
    """Execution did not finish within the step limit (possible infinite loop)."""

    def __init__(self, limit: int, span: SourceSpan, state: State):
        super().__init__(f"step limit of {limit} exceeded (possible infinite loop)", span)
        self.limit = limit
        self.state = state
