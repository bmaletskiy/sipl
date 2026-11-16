"""CORE-04: event model and trace (programmatic and JSON)."""
import json
from pathlib import Path

import pytest

from sipl import parse, run, trace
from sipl.interpreter import (AfterStatement, BeforeStatement, ConditionEvaluated, Failed,
                              Finished, VariableChanged)

EXAMPLES = Path(__file__).parent.parent / "examples"


def names(t):
    return [type(e).__name__ for e in t.events]


def traced(source, initial=None, **kwargs):
    return trace(parse(f"begin {source} end"), initial, **kwargs)


def test_sequence_of_assignments():
    t = traced("x := 1; y := x + 1")
    assert names(t) == ["BeforeStatement", "VariableChanged", "AfterStatement"] * 2 + ["Finished"]
    changes = [e for e in t.events if isinstance(e, VariableChanged)]
    assert [(c.name, c.old, c.new) for c in changes] == [("x", None, 1), ("y", None, 2)]
    assert [e.step for e in t.events] == [1, 1, 1, 2, 2, 2, 2]
    assert dict(t.final_state) == {"x": 1, "y": 2} and t.failure is None


def test_variable_change_reports_the_old_value():
    t = traced("x := x + 1", {"x": 5})
    change = next(e for e in t.events if isinstance(e, VariableChanged))
    assert (change.old, change.new) == (5, 6)


def test_while_event_order_and_condition_values():
    source = "x := 2; while x > 0 do x := x - 1"
    t = traced(source)
    assert names(t) == (
        ["BeforeStatement", "VariableChanged", "AfterStatement"]
        + ["BeforeStatement", "ConditionEvaluated"]
        + ["BeforeStatement", "VariableChanged", "AfterStatement", "ConditionEvaluated"]
        + ["BeforeStatement", "VariableChanged", "AfterStatement", "ConditionEvaluated"]
        + ["AfterStatement", "Finished"]
    )
    conditions = [e for e in t.events if isinstance(e, ConditionEvaluated)]
    assert [c.value for c in conditions] == [True, True, False]
    assert {c.statement for c in conditions} == {"while"}
    assert t.events[-1].step == 6


def test_condition_span_points_to_the_condition_text():
    program_text = "begin x := 1; if x > 0 then skip else skip end"
    t = trace(parse(program_text))
    cond = next(e for e in t.events if isinstance(e, ConditionEvaluated))
    assert program_text[cond.span.start:cond.span.end] == "x > 0"
    assert cond.statement == "if" and cond.value is True


def test_if_and_skip_events():
    t = traced("if 1 = 2 then x := 1 else skip")
    assert names(t) == ["BeforeStatement", "ConditionEvaluated", "BeforeStatement",
                        "AfterStatement", "AfterStatement", "Finished"]
    assert [e.statement for e in t.events if isinstance(e, BeforeStatement)] == ["if", "skip"]


def test_before_and_after_are_properly_nested_and_states_are_snapshots():
    for name, initial in [("gcd.sipl", {"M": 12, "N": 18}), ("power.sipl", {"X": 2, "Y": 3}),
                          ("multiply.sipl", {"X": 2, "Y": 3})]:
        t = trace(parse((EXAMPLES / name).read_text(encoding="utf-8")), initial)
        stack = []
        for e in t.events:
            if isinstance(e, BeforeStatement):
                stack.append(e)
            elif isinstance(e, AfterStatement):
                assert stack.pop().span == e.span
        assert not stack and isinstance(t.events[-1], Finished)
    firsts = [e for e in t.events if isinstance(e, AfterStatement)][:2]
    assert dict(firsts[0].state) != dict(firsts[1].state)


def test_runtime_error_ends_the_trace_with_failed_instead_of_raising():
    t = traced("x := y + 1")
    last = t.events[-1]
    assert isinstance(last, Failed) and t.failure is last and t.final_state is None
    assert last.error == "UndefinedVariableError" and "'y'" in last.message
    assert (last.span.start_line, last.span.start_column) == (1, 12)


def test_step_limit_ends_the_trace_with_failed():
    t = traced("while 1 = 1 do skip", max_steps=10)
    assert t.failure.error == "StepLimitExceeded" and len(t.events) < 100


def test_observer_receives_events_and_run_still_raises():
    seen = []
    run(parse("begin x := 1 end"), observer=seen.append)
    assert [type(e).__name__ for e in seen] == [
        "BeforeStatement", "VariableChanged", "AfterStatement", "Finished"]
    seen.clear()
    with pytest.raises(Exception):
        run(parse("begin x := y end"), observer=seen.append)
    assert isinstance(seen[-1], Failed)


def test_json_format_is_stable():
    t = traced("x := 1")
    data = json.loads(t.to_json())
    assert data["version"] == 1
    before, change, after, finished = data["events"]
    assert before == {"event": "BeforeStatement", "step": 1,
                      "span": {"start": {"line": 1, "column": 7, "offset": 6},
                               "end": {"line": 1, "column": 13, "offset": 12}},
                      "statement": "assign", "state": {}}
    assert change["event"] == "VariableChanged"
    assert (change["name"], change["old"], change["new"]) == ("x", None, 1)
    assert after["state"] == {"x": 1} and finished["state"] == {"x": 1}


def test_json_of_failed_trace_and_indent():
    t = traced("x := y")
    data = json.loads(t.to_json(indent=2))
    assert data["events"][-1]["event"] == "Failed"
    assert data["events"][-1]["error"] == "UndefinedVariableError"
    assert "\n  " in t.to_json(indent=2)
