"""CORE-01: the grammar accepts the course language and rejects everything else."""
from pathlib import Path

import pytest

from sipl import SiplSyntaxError, parse

EXAMPLES = Path(__file__).parent.parent / "examples"

VALID = [
    "begin skip end",
    "begin x := 1 end",
    "begin x := -1 end",
    "begin x := (a + b) * c end",
    "begin x := a - b - c end",
    "begin F1 := K_2 end",
    "begin x := 1; y := 2; z := 3 end",
    "begin begin skip end end",
    "begin if x > 0 then y := 1 else y := 2 end",
    "begin if a > b then skip else skip; x := 1 end",
    "begin while x > 0 do x := x - 1 end",
    "begin while ¬x = y ∨ z > 0 do skip end",
    "begin if (a > b) ∨ (c = d) then skip else skip end",
    "begin while x > 0 do begin x := x - 1; y := y + 1 end end",
    "begin\n\tx := 1;\r\n  y := 2\nend",
    "begin iffy := ends end",
]

INVALID = [
    "",
    "x := 1 end",
    "begin x := 1",
    "begin x := 1; end",
    "begin x := 1;; y := 2 end",
    "begin begin end end",
    "begin if x > 0 then skip end",
    "begin while x > 0 skip end",
    "begin x := end",
    "begin x := while end",
    "begin while := 1 end",
    "begin 1 := x end",
    "begin x = 1 end",
    "begin while x do skip end",
    "begin x := (1 + 2 end",
    "begin x := a / b end",
    "begin x := 1 # end",
    "begin skip end skip",
    "BEGIN skip END",
]


@pytest.mark.parametrize("source", VALID)
def test_valid_program_is_accepted(source):
    parse(source)


@pytest.mark.parametrize("source", INVALID)
def test_invalid_program_is_rejected(source):
    with pytest.raises(SiplSyntaxError):
        parse(source)


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.sipl")), ids=lambda p: p.name)
def test_examples_are_accepted(path):
    parse(path.read_text(encoding="utf-8"))


def test_test_sets_are_large_enough():
    assert len(VALID) >= 10 and len(INVALID) >= 10
