"""CORE-02: typed AST with source spans and precise syntax diagnostics."""
import pytest

from sipl import SiplSyntaxError, ast, parse
from sipl.ast import (Assign, BinOp, Block, Compare, If, Node, Not, Num, Or, Program, Seq,
                      Skip, Var, While)

a, b, c, d, x, y, z = (Var(n) for n in "abcdxyz")


def body(source: str):
    return parse(f"begin {source} end").body


def test_root_is_program_with_own_nodes():
    program = parse("begin skip end")
    assert program == Program(Skip())
    assert all(isinstance(node, Node) for node in ast.walk(program))
    assert all(type(node).__module__ == "sipl.ast" for node in ast.walk(program))


def test_multiplication_binds_tighter_than_addition():
    assert body("x := a + b * c") == Assign(x, BinOp("+", a, BinOp("*", b, c)))


def test_binary_operations_are_left_associative():
    assert body("x := a - b - c") == Assign(x, BinOp("-", BinOp("-", a, b), c))


def test_parentheses_change_structure_but_are_not_nodes():
    assert body("x := (a + b) * c") == Assign(x, BinOp("*", BinOp("+", a, b), c))


def test_negation_is_tighter_than_or_and_looser_than_comparison():
    stmt = body("while ¬a = b ∨ c > d do skip")
    assert stmt.cond == Or(Not(Compare("=", a, b)), Compare(">", c, d))


def test_negative_literal_and_subtraction_are_distinguished():
    assert body("x := -1") == Assign(x, Num(-1))
    assert body("x := y - 1") == Assign(x, BinOp("-", y, Num(1)))
    assert body("x := y -1") == Assign(x, BinOp("-", y, Num(1)))
    assert body("x := y - -1") == Assign(x, BinOp("-", y, Num(-1)))


def test_sequence_is_left_associative():
    assign = lambda v, n: Assign(v, Num(n))
    assert body("x := 1; y := 2; z := 3") == Seq(Seq(assign(x, 1), assign(y, 2)), assign(z, 3))


def test_else_branch_is_a_single_statement():
    stmt = body("if a > b then skip else x := 1; y := 2")
    assert stmt == Seq(If(Compare(">", a, b), Skip(), Assign(x, Num(1))), Assign(y, Num(2)))


def test_while_body_is_a_single_statement():
    stmt = body("while a > b do x := 1; y := 2")
    assert stmt == Seq(While(Compare(">", a, b), Assign(x, Num(1))), Assign(y, Num(2)))


def test_begin_end_groups_statements():
    stmt = body("while a > b do begin x := 1; y := 2 end")
    assert stmt.body == Block(Seq(Assign(x, Num(1)), Assign(y, Num(2))))


def test_keywords_are_not_identifiers_but_may_be_prefixes():
    assert body("iffy := ends") == Assign(Var("iffy"), Var("ends"))
    with pytest.raises(SiplSyntaxError):
        parse("begin while := 1 end")


SOURCE = "begin\n  x := 1;\n  y := x + 2\nend"


def test_spans_cover_exact_source_text():
    program = parse(SOURCE)
    for node in ast.walk(program):
        text = SOURCE[node.span.start:node.span.end]
        if isinstance(node, Var):
            assert text == node.name
        elif isinstance(node, Num):
            assert text == str(node.value)
        elif isinstance(node, Assign):
            assert text == {"x": "x := 1", "y": "y := x + 2"}[node.target.name]
    assert SOURCE[program.span.start:program.span.end] == SOURCE


def test_spans_have_line_and_column():
    program = parse(SOURCE)
    second = program.body.second
    assert (second.span.start_line, second.span.start_column) == (3, 3)
    assert (second.span.end_line, second.span.end_column) == (3, 13)
    assert (program.span.start_line, program.span.start_column) == (1, 1)
    assert (program.span.end_line, program.span.end_column) == (4, 4)


@pytest.mark.parametrize(
    "source, line, column, found",
    [
        ("begin\n  x := ;\nend", 2, 8, "';'"),
        ("begin skip", 1, 11, "end of input"),
        ("begin x := 1 # end", 1, 14, "'#'"),
        ("begin x := while end", 1, 12, "'while'"),
    ],
)
def test_syntax_error_position(source, line, column, found):
    with pytest.raises(SiplSyntaxError) as info:
        parse(source)
    err = info.value
    assert (err.line, err.column) == (line, column)
    assert f"unexpected {found}" in str(err)
    assert err.expected


def test_syntax_error_lists_expected_symbols():
    with pytest.raises(SiplSyntaxError) as info:
        parse("begin x := ;")
    assert set(info.value.expected) == {"'('", "number", "variable"}


def test_dump_and_to_dict():
    program = parse("begin x := 1 end")
    assert ast.dump(program) == "Program\n  Assign\n    Var name='x'\n    Num value=1"
    data = program.to_dict()
    assert data["type"] == "Program" and data["body"]["expr"] == {
        "type": "Num", "span": program.body.expr.span.to_dict(), "value": 1}
