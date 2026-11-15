"""CORE-03: execution semantics, state handling, explicit errors and the step limit."""
from pathlib import Path

import pytest

from sipl import State, ast, parse, run
from sipl.interpreter import Interpreter, StepLimitExceeded, UndefinedVariableError

EXAMPLES = Path(__file__).parent.parent / "examples"


def execute(source: str, **initial: int) -> dict[str, int]:
    return dict(run(parse(f"begin {source} end"), initial))


def example(name: str, **initial: int) -> dict[str, int]:
    return dict(run(parse((EXAMPLES / name).read_text(encoding="utf-8")), initial))


def test_gcd_example_from_the_course():
    assert example("gcd.sipl", M=8, N=16) == {"M": 8, "N": 8}
    assert example("gcd.sipl", M=12, N=18) == {"M": 6, "N": 6}


def test_power_example_matches_the_course_trace():
    assert example("power.sipl", X=5, Y=2) == {"X": 5, "Y": 0, "R": 25}
    assert example("power.sipl", X=7, Y=0)["R"] == 1


def test_multiply_example():
    assert example("multiply.sipl", X=3, Y=4) == {"X": 0, "Y": 4, "R": 12}


def test_assignment_uses_the_old_state_and_creates_variables():
    assert execute("x := x + 1", x=1) == {"x": 2}
    assert execute("y := 5") == {"y": 5}


def test_sequence_runs_left_to_right():
    assert execute("x := 1; y := x + 1; x := y * 10") == {"x": 20, "y": 2}


def test_arithmetic_precedence_and_negative_numbers():
    assert execute("x := 2 + 3 * 4; y := 10 - 3 - 2; z := -5 * -2") == {"x": 14, "y": 5, "z": 10}


@pytest.mark.parametrize("cond, expected", [
    ("1 = 1", 1), ("1 = 2", 0), ("2 > 1", 1), ("1 > 2", 0), ("1 > 1", 0),
    ("¬1 = 2", 1), ("¬2 > 1", 0), ("1 = 2 ∨ 2 > 1", 1), ("1 = 2 ∨ 1 > 2", 0),
    ("¬(1 = 2 ∨ 1 > 2)", 1),
])
def test_conditions(cond, expected):
    assert execute(f"if {cond} then r := 1 else r := 0") == {"r": expected}


def test_if_runs_only_the_chosen_branch():
    assert execute("if x > 0 then a := 1 else b := 1", x=1) == {"x": 1, "a": 1}
    assert execute("if x > 0 then a := 1 else b := 1", x=0) == {"x": 0, "b": 1}


def test_while_runs_zero_or_more_times():
    assert execute("while x > 0 do x := x - 1", x=0) == {"x": 0}
    assert execute("while x > 0 do x := x - 1", x=3) == {"x": 0}


def test_block_and_skip():
    assert execute("begin skip end; begin x := 1; y := 2 end") == {"x": 1, "y": 2}


def test_initial_state_is_not_modified():
    initial = State({"x": 1})
    final = run(parse("begin x := 2 end"), initial)
    assert dict(initial) == {"x": 1} and dict(final) == {"x": 2}


def test_run_accepts_a_bare_statement():
    assert dict(run(parse("begin x := 1 end").body)) == {"x": 1}


def test_undefined_variable_reports_name_and_position():
    with pytest.raises(UndefinedVariableError) as info:
        run(parse("begin\n  x := y + 1\nend"))
    err = info.value
    assert err.name == "y" and (err.span.start_line, err.span.start_column) == (2, 8)
    assert "'y'" in str(err)


def test_undefined_variable_in_condition_and_strict_or():
    with pytest.raises(UndefinedVariableError):
        execute("while u > 0 do skip")
    with pytest.raises(UndefinedVariableError):
        execute("if 1 = 1 ∨ u = 0 then skip else skip")


def test_infinite_loop_is_stopped_by_the_step_limit():
    with pytest.raises(StepLimitExceeded) as info:
        run(parse("begin while 1 = 1 do x := 0 end"), {"x": 1}, max_steps=100)
    err = info.value
    assert err.limit == 100 and dict(err.state) == {"x": 0}
    assert (err.span.start_line, err.span.start_column) == (1, 7)


def test_step_limit_counts_assignments_skips_and_condition_checks():
    program = parse("begin x := 1; skip; if x = 1 then skip else skip; while x > 0 do x := x - 1 end")
    interpreter = Interpreter()
    interpreter.execute(program.body, State())
    # x := 1, skip, if, skip (then-branch), while (true), x := x - 1, while (false)
    assert interpreter.steps == 7
    with pytest.raises(StepLimitExceeded):
        run(parse("begin x := 1 end"), max_steps=0)
    run(parse("begin x := 1 end"), max_steps=1)


def test_long_programs_do_not_hit_the_recursion_limit():
    source = "begin x := 0" + "; x := x + 1" * 3000 + " end"
    assert run(parse(source))["x"] == 3000


def test_right_nested_sequence_in_a_hand_built_ast():
    one, two = ast.Assign(ast.Var("x"), ast.Num(1)), ast.Assign(ast.Var("x"), ast.Num(2))
    assert dict(run(ast.Seq(two, ast.Seq(one, two)))) == {"x": 2}
    assert dict(run(ast.Seq(ast.Seq(two, one), two))) == {"x": 2}


def test_non_nodes_are_rejected_explicitly():
    for bad in (object(), ast.Num(1)):
        with pytest.raises(TypeError):
            Interpreter().execute(bad, State())
    with pytest.raises(TypeError):
        Interpreter().aexp(ast.Skip(), State())
    with pytest.raises(TypeError):
        Interpreter().bexp(ast.Num(1), State())


def test_state_overlay_and_mapping_behaviour():
    state = State({"x": 1, "y": 2})
    assert dict(state.overlay({"y": 5, "z": 7})) == {"x": 1, "y": 5, "z": 7}
    assert dict(state) == {"x": 1, "y": 2}
    assert len(state) == 2 and list(state) == ["x", "y"] and state["x"] == 1
    assert state == {"x": 1, "y": 2} and "x" in state and "q" not in state
    assert repr(State({"x": 1})) == "State({'x': 1})"


@pytest.mark.parametrize("bad", ["5", 1.5, None, True])
def test_state_rejects_non_integer_values(bad):
    with pytest.raises(TypeError):
        State({"x": bad})
