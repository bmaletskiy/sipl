"""CORE-06: the conformance suite passes, is well-formed, and is able to fail."""
import contextlib
import importlib.util
import io
import json
import operator
import re
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest
from lark import Lark

import sipl.interpreter.core as core
import sipl.parser as parser_module
from sipl import ast
from sipl.cli import main
from sipl.interpreter import Interpreter

ROOT = Path(__file__).parent.parent
RUN = ROOT / "conformance" / "run.py"
spec = importlib.util.spec_from_file_location("conformance_run", RUN)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

SUITES = runner.load_suites()
CASES = [(suite, case) for suite, cases in SUITES.items() for case in cases]


def in_process(args, stdin):
    out = io.StringIO()
    with mock.patch("sys.stdin", io.StringIO(stdin)), contextlib.redirect_stdout(out):
        main(args)
    return out.getvalue()


def bounded(args, stdin):
    """The real implementation with a small step limit, so that diverging mutants end quickly."""
    if args[0] == "run" and "--max-steps" not in args:
        args = [*args, "--max-steps", "5000"]
    return in_process(args, stdin)


def failing_cases(executor):
    return {f"{suite}/{case['name']}" for suite, case in CASES if runner.run_case(case, executor)}


@pytest.mark.parametrize("suite, case", CASES, ids=[f"{s}/{c['name']}" for s, c in CASES])
def test_implementation_passes_the_case(suite, case):
    assert runner.run_case(case, in_process) == []


def test_suites_are_well_formed():
    assert set(SUITES) == {"ast", "syntax_errors", "semantics", "runtime_errors"}
    assert len(CASES) >= 80
    for suite, cases in SUITES.items():
        names = [case["name"] for case in cases]
        assert len(names) == len(set(names)), f"duplicate names in {suite}"
        for case in cases:
            assert set(case) <= {"name", "description", "source", "initial", "max_steps", "expect"}
            assert case["name"] and case["description"] and isinstance(case["source"], str)
            expect = case["expect"]
            assert set(expect) in ({"ast"}, {"state"}, {"error"}, {"ast", "state"})
            if "ast" in expect:
                assert expect["ast"].count("(") == expect["ast"].count(")")
            if "error" in expect:
                assert expect["error"]["type"] in {
                    "SiplSyntaxError", "UndefinedVariableError", "StepLimitExceeded"}
                assert ("line" in expect["error"]) == ("column" in expect["error"])


def test_every_ast_node_type_is_covered():
    text = " ".join(case["expect"]["ast"] for case in SUITES["ast"])
    for head in ("Program", "Block", "Seq", "Assign", "If", "While", "Skip", "or", "not",
                 "+", "-", "*", "=", ">"):
        assert f"({head}" in text, head
    assert re.search(r" -\d", text)  # a negative literal


# The suite must be able to fail: wrong implementations are detected.

def test_garbage_output_fails_every_case():
    assert len(failing_cases(lambda args, stdin: "not json")) == len(CASES)


def test_constant_answers_fail_almost_every_case():
    def constant(args, stdin):
        if args[0] == "parse":
            return json.dumps({"status": "ok", "ast": {"type": "Program", "body": {"type": "Skip"}}})
        return json.dumps({"status": "ok", "state": {}})
    assert len(failing_cases(constant)) >= len(CASES) - 2


def test_runner_reports_unsupported_ast_nodes():
    def odd(args, stdin):
        return json.dumps({"status": "ok", "ast": {"type": "Mystery"}})
    case = SUITES["ast"][0]
    assert "unsupported AST" in runner.run_case(case, odd)[0]


def backwards(stm, original=core._flatten):
    return original(stm)[::-1]


def lazy_or(self, node, state, original=Interpreter.bexp):
    if isinstance(node, ast.Or):
        return original(self, node.left, state) or original(self, node.right, state)
    return original(self, node, state)


def right_associative_grammar():
    text = (ROOT / "src" / "sipl" / "grammar" / "sipl.lark").read_text(encoding="utf-8")
    mutated = text.replace("?aexp: aexp ADD term -> binop", "?aexp: term ADD aexp -> binop")
    assert mutated != text
    return Lark(mutated, parser="lalr", start="program", propagate_positions=True)


MUTANTS = {
    "subtraction is addition": (
        lambda: mock.patch.dict(core._ARITHMETIC, {"-": operator.add}), "semantics/arithmetic"),
    "> is >=": (
        lambda: mock.patch.dict(core._COMPARISON, {">": operator.ge}), "semantics/greater-is-strict"),
    "statements run backwards": (
        lambda: mock.patch.object(core, "_flatten", backwards), "semantics/sequence-order"),
    "∨ is lazy": (lambda: mock.patch.object(Interpreter, "bexp", lazy_or), "runtime_errors/or-is-strict"),
    "operators are right-associative": (
        lambda: mock.patch.object(parser_module, "_PARSER", right_associative_grammar()),
        "ast/subtraction-left-assoc"),
}


@pytest.mark.parametrize("mutant", MUTANTS)
def test_mutants_are_detected(mutant):
    patch, detected_by = MUTANTS[mutant]
    with patch():
        failures = failing_cases(bounded)
    assert detected_by in failures


# The runner as a stand-alone program, against real processes.

def run_script(*args):
    return subprocess.run([sys.executable, str(RUN), *args], capture_output=True, text=True,
                          encoding="utf-8")


def test_runner_script_passes_with_the_default_command():
    result = run_script("--suite", "runtime_errors")
    assert result.returncode == 0 and "8 passed, 0 failed" in result.stdout


def test_runner_script_with_a_custom_command_and_verbose_output():
    result = run_script("--command", "sipl", "--suite", "syntax_errors", "-v")
    assert result.returncode == 0 and "24 passed, 0 failed" in result.stdout
    assert "PASS syntax_errors/trailing-semicolon" in result.stdout


def test_runner_script_fails_for_a_wrong_implementation():
    result = run_script("--command", f"{sys.executable} -c pass", "--suite", "runtime_errors")
    assert result.returncode == 1 and "8 failed" in result.stdout
    assert "FAIL runtime_errors/undefined-in-assignment" in result.stdout
    assert "not valid JSON" in result.stdout


def test_runner_script_rejects_an_unknown_suite():
    result = run_script("--suite", "nope")
    assert result.returncode == 2 and "no such suite" in result.stderr
