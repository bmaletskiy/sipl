"""SEM-01: semantic terms built from the AST, checked against the course and by evaluation."""
import json
import operator
import re
from pathlib import Path

import pytest

from sipl import ast, parse, semantic_term
from sipl.cli import main
from sipl.semantics import (Assign, Compose, Const, Deref, Identity, If, Super, While, sem_a, sem_b,
                            sem_s)

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"


def term_of(source: str) -> str:
    return str(semantic_term(parse(f"begin {source} end")))


def squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def example_term(name: str) -> str:
    return str(semantic_term(parse((EXAMPLES / name).read_text(encoding="utf-8"))))


# Golden terms taken from the course materials

def test_gcd_term_matches_example_1_3_of_the_course_book():
    book = "WH(S¹(neg, S²(eq, M⇒, N⇒)), IF(S²(gr, M⇒, N⇒), ASM( S²(sub, M⇒, N⇒)), ASN( S²(sub, N⇒, M⇒))))"
    assert squash(example_term("gcd.sipl")) == squash(book)


def test_power_term_matches_practical_work_2_of_the_workbook():
    workbook = "ASR(1) · WH(S²(gr, Y⇒, 0), ASR(S²(mult, R⇒, X⇒)) · ASY(S²(sub, Y⇒, 1)))"
    assert squash(example_term("power.sipl")) == squash(workbook)
    assert example_term("power.sipl") == workbook


def test_multiply_term_derived_by_hand():
    assert example_term("multiply.sipl") == (
        "ASR(0) · WH(S²(gr, X⇒, 0), ASR(S²(add, R⇒, Y⇒)) · ASX(S²(sub, X⇒, 1)))")


def test_every_operator_in_one_program():
    source = ("x := 1 + 2 * 3 - 4; if ¬x = 0 ∨ x > 5 then skip else y := (x - 1) * 2; "
              "while x > 0 do begin x := x - 1; y := y + x end")
    assert term_of(source) == (
        "ASx(S²(sub, S²(add, 1, S²(mult, 2, 3)), 4)) · "
        "IF(S²(or, S¹(neg, S²(eq, x⇒, 0)), S²(gr, x⇒, 5)), id, ASy(S²(mult, S²(sub, x⇒, 1), 2))) · "
        "WH(S²(gr, x⇒, 0), ASx(S²(sub, x⇒, 1)) · ASy(S²(add, y⇒, x⇒)))")


def test_notation_details():
    assert term_of("skip") == "id"
    assert term_of("x := -1") == "ASx(-1)"
    assert term_of("x := (a + b) * c") == "ASx(S²(mult, S²(add, a⇒, b⇒), c⇒))"
    assert term_of("x := a - b - c") == "ASx(S²(sub, S²(sub, a⇒, b⇒), c⇒))"
    assert term_of("begin x := 1 end") == "ASx(1)"
    assert term_of("x := 1; y := 2; z := 3") == "ASx(1) · ASy(2) · ASz(3)"


def test_a_block_on_the_right_keeps_its_parentheses():
    assert term_of("x := 1; begin y := 2; z := 3 end") == "ASx(1) · (ASy(2) · ASz(3))"


# The rules one by one

@pytest.mark.parametrize("op, name", [("+", "add"), ("-", "sub"), ("*", "mult")])
def test_arithmetic_rules(op, name):
    node = ast.BinOp(op, ast.Num(2), ast.Var("x"))
    assert sem_a(node) == Super(name, (Const(2), Deref("x")))


@pytest.mark.parametrize("op, name", [("=", "eq"), (">", "gr")])
def test_comparison_rules(op, name):
    assert sem_b(ast.Compare(op, ast.Var("x"), ast.Num(0))) == Super(name, (Deref("x"), Const(0)))


def test_boolean_rules():
    cmp = ast.Compare("=", ast.Var("x"), ast.Num(0))
    assert sem_b(ast.Not(cmp)) == Super("neg", (sem_b(cmp),))
    assert sem_b(ast.Or(cmp, cmp)) == Super("or", (sem_b(cmp), sem_b(cmp)))


def test_statement_rules():
    skip, assign = ast.Skip(), ast.Assign(ast.Var("x"), ast.Num(1))
    cond = ast.Compare(">", ast.Var("x"), ast.Num(0))
    assert sem_s(skip) == Identity()
    assert sem_s(assign) == Assign("x", Const(1))
    assert sem_s(ast.Seq(skip, assign)) == Compose(Identity(), Assign("x", Const(1)))
    assert sem_s(ast.If(cond, skip, assign)) == If(sem_b(cond), Identity(), Assign("x", Const(1)))
    assert sem_s(ast.While(cond, assign)) == While(sem_b(cond), Assign("x", Const(1)))
    assert sem_s(ast.Block(assign)) == Assign("x", Const(1))


def test_program_and_bare_statement_are_accepted():
    program = parse("begin x := 1 end")
    assert semantic_term(program) == semantic_term(program.body) == Assign("x", Const(1))


def test_wrong_node_kinds_are_rejected_explicitly():
    with pytest.raises(TypeError):
        sem_s(ast.Num(1))
    with pytest.raises(TypeError):
        sem_a(ast.Skip())
    with pytest.raises(TypeError):
        sem_b(ast.Num(1))


def test_json_form():
    assert semantic_term(parse("begin x := 1 + y end")).to_dict() == {
        "type": "Assign", "name": "x",
        "expr": {"type": "Super", "op": "add",
                 "args": [{"type": "Const", "value": 1}, {"type": "Deref", "name": "y"}]}}
    assert Identity().to_dict() == {"type": "Identity"}


# Evaluation of the terms with the composition formulas of the course (AF_S, AF_AS, AF_SEQ, AF_IF,
# AF_WH, AF_DNM, AF_ID) agrees with the expected final states: the terms mean what the programs mean.

OPERATIONS = {"add": operator.add, "sub": operator.sub, "mult": operator.mul, "eq": operator.eq,
              "gr": operator.gt, "or": lambda a, b: a or b, "neg": operator.not_}


def apply(term, state):
    match term:
        case Const(value):
            return value
        case Deref(name):
            return state[name]
        case Super(op, args):
            return OPERATIONS[op](*(apply(arg, state) for arg in args))
        case Assign(name, expr):
            return {**state, name: apply(expr, state)}
        case Compose(first, second):
            return apply(second, apply(first, state))
        case If(cond, then, orelse):
            return apply(then if apply(cond, state) else orelse, state)
        case While(cond, body):
            while apply(cond, state):
                state = apply(body, state)
            return state
        case Identity():
            return state


SEMANTICS = json.loads((ROOT / "conformance" / "cases" / "semantics.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", SEMANTICS, ids=[case["name"] for case in SEMANTICS])
def test_term_evaluates_to_the_expected_state(case):
    term = semantic_term(parse(case["source"]))
    assert apply(term, case.get("initial", {})) == case["expect"]["state"]


# Command line

def cli(capsys, *args):
    code = main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_cli_prints_the_notation(capsys):
    code, out, _ = cli(capsys, "term", str(EXAMPLES / "power.sipl"))
    assert (code, out) == (0, example_term("power.sipl") + "\n")


def test_cli_json(capsys):
    code, out, _ = cli(capsys, "term", str(EXAMPLES / "gcd.sipl"), "--json")
    data = json.loads(out)
    assert code == 0 and data["version"] == 1 and data["status"] == "ok"
    assert data["notation"] == example_term("gcd.sipl") and data["term"]["type"] == "While"


def test_cli_syntax_error(capsys, tmp_path):
    path = tmp_path / "bad.sipl"
    path.write_text("begin x := ; end", encoding="utf-8")
    code, out, err = cli(capsys, "term", str(path))
    assert code == 1 and out == "" and f"{path}:1:12: error:" in err


def test_cli_too_deep_program_is_reported(capsys, tmp_path):
    path = tmp_path / "long.sipl"
    path.write_text("begin x := 0" + "; x := x + 1" * 3000 + " end", encoding="utf-8")
    code, out, _ = cli(capsys, "term", str(path), "--json")
    assert code == 3 and json.loads(out)["error"]["type"] == "NestingTooDeep"
