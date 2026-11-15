"""Interpreter: executes a SIPL AST over a State with a step limit."""
from __future__ import annotations

import operator
from collections.abc import Callable, Mapping

from sipl import ast
from sipl.interpreter.errors import SiplRuntimeError, StepLimitExceeded, UndefinedVariableError
from sipl.interpreter.events import (AfterStatement, BeforeStatement, ConditionEvaluated, Event,
                                     Failed, Finished, VariableChanged)
from sipl.interpreter.state import State

DEFAULT_MAX_STEPS = 1_000_000

_ARITHMETIC = {"+": operator.add, "-": operator.sub, "*": operator.mul}
_COMPARISON = {"=": operator.eq, ">": operator.gt}


def _flatten(stm: ast.Node) -> list[ast.Node]:
    """Statements of a (possibly deeply nested) sequence in execution order."""
    stack, flat = [stm], []
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Seq):
            stack += [node.second, node.first]
        else:
            flat.append(node)
    return flat


class Interpreter:
    """One step is: an assignment, a skip, an `if` condition check, or a `while` condition check.

    If an observer is given, it receives every execution event (see `events.py`) in order.
    """

    def __init__(self, max_steps: int = DEFAULT_MAX_STEPS,
                 observer: Callable[[Event], None] | None = None):
        self.max_steps = max_steps
        self.observer = observer
        self.steps = 0

    def _emit(self, event: type[Event], span: ast.SourceSpan, **data) -> None:
        if self.observer is not None:
            self.observer(event(self.steps, span, **data))

    def run(self, root: ast.Node, state: State) -> State:
        body = root.body if isinstance(root, ast.Program) else root
        try:
            final = self.execute(body, state)
        except SiplRuntimeError as err:
            self._emit(Failed, err.span, error=type(err).__name__, message=err.message)
            raise
        self._emit(Finished, root.span, state=final)
        return final

    def _tick(self, node: ast.Node, state: State) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise StepLimitExceeded(self.max_steps, node.span, state)

    def execute(self, stm: ast.Node, state: State) -> State:
        match stm:
            case ast.Assign(target, expr):
                self._tick(stm, state)
                self._emit(BeforeStatement, stm.span, statement="assign", state=state)
                value = self.aexp(expr, state)
                self._emit(VariableChanged, stm.span, name=target.name,
                           old=state.get(target.name), new=value)
                state = state.overlay({target.name: value})
                self._emit(AfterStatement, stm.span, statement="assign", state=state)
                return state
            case ast.Seq():
                for part in _flatten(stm):
                    state = self.execute(part, state)
                return state
            case ast.If(cond, then, orelse):
                self._tick(stm, state)
                self._emit(BeforeStatement, stm.span, statement="if", state=state)
                value = self.bexp(cond, state)
                self._emit(ConditionEvaluated, cond.span, statement="if", value=value, state=state)
                state = self.execute(then if value else orelse, state)
                self._emit(AfterStatement, stm.span, statement="if", state=state)
                return state
            case ast.While(cond, body):
                entered = False
                while True:
                    self._tick(stm, state)
                    if not entered:
                        self._emit(BeforeStatement, stm.span, statement="while", state=state)
                        entered = True
                    value = self.bexp(cond, state)
                    self._emit(ConditionEvaluated, cond.span, statement="while", value=value,
                               state=state)
                    if not value:
                        self._emit(AfterStatement, stm.span, statement="while", state=state)
                        return state
                    state = self.execute(body, state)
            case ast.Block(body):
                return self.execute(body, state)
            case ast.Skip():
                self._tick(stm, state)
                self._emit(BeforeStatement, stm.span, statement="skip", state=state)
                self._emit(AfterStatement, stm.span, statement="skip", state=state)
                return state
            case _:
                raise TypeError(f"not a statement: {stm!r}")

    def aexp(self, node: ast.Node, state: State) -> int:
        match node:
            case ast.Num(value):
                return value
            case ast.Var(name):
                try:
                    return state[name]
                except KeyError:
                    raise UndefinedVariableError(name, node.span) from None
            case ast.BinOp(op, left, right):
                return _ARITHMETIC[op](self.aexp(left, state), self.aexp(right, state))
            case _:
                raise TypeError(f"not an arithmetic expression: {node!r}")

    def bexp(self, node: ast.Node, state: State) -> bool:
        # Strict like the course semantics: both operands of ∨ are always evaluated.
        match node:
            case ast.Compare(op, left, right):
                return _COMPARISON[op](self.aexp(left, state), self.aexp(right, state))
            case ast.Or(left, right):
                left_value, right_value = self.bexp(left, state), self.bexp(right, state)
                return left_value or right_value
            case ast.Not(operand):
                return not self.bexp(operand, state)
            case _:
                raise TypeError(f"not a condition: {node!r}")


def run(program: ast.Program | ast.Stm, initial: Mapping[str, int] | None = None, *,
        max_steps: int = DEFAULT_MAX_STEPS,
        observer: Callable[[Event], None] | None = None) -> State:
    """Execute a program and return the final state; the initial state is not modified."""
    return Interpreter(max_steps, observer).run(program, State(initial or {}))
