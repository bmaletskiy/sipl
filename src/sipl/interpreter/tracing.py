"""Trace: the complete event log of one execution, serializable to JSON."""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sipl import ast
from sipl.interpreter.core import DEFAULT_MAX_STEPS, run
from sipl.interpreter.errors import SiplRuntimeError
from sipl.interpreter.events import Event, Failed, Finished
from sipl.interpreter.state import State

TRACE_FORMAT_VERSION = 1


@dataclass(frozen=True)
class Trace:
    events: tuple[Event, ...]  # always ends with Finished or Failed

    @property
    def final_state(self) -> State | None:
        last = self.events[-1]
        return last.state if isinstance(last, Finished) else None

    @property
    def failure(self) -> Failed | None:
        last = self.events[-1]
        return last if isinstance(last, Failed) else None

    def to_dict(self) -> dict[str, Any]:
        return {"version": TRACE_FORMAT_VERSION, "events": [e.to_dict() for e in self.events]}

    def to_json(self, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


def trace(program: ast.Program | ast.Stm, initial: Mapping[str, int] | None = None, *,
          max_steps: int = DEFAULT_MAX_STEPS) -> Trace:
    """Run a program and return its trace; runtime errors end the trace with a Failed event."""
    events: list[Event] = []
    try:
        run(program, initial, max_steps=max_steps, observer=events.append)
    except SiplRuntimeError:
        pass  # already recorded as the final Failed event
    return Trace(tuple(events))
