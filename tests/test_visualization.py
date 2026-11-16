"""VIS-01: the parse tree and its text, JSON, DOT and SVG renderings."""
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import pytest

from sipl import SiplSyntaxError
from sipl.cli import main
from sipl.visualization import build_parse_tree, to_dict, to_dot, to_svg, to_text
from sipl.visualization.render import _layout

ROOT = Path(__file__).parent.parent
EXAMPLES = sorted((ROOT / "examples").glob("*.sipl"))
POWER = (ROOT / "examples" / "power.sipl").read_text(encoding="utf-8")


def conformance_sources():
    sources = []
    for suite in ("ast", "semantics"):
        data = json.loads((ROOT / "conformance" / "cases" / f"{suite}.json").read_text(encoding="utf-8"))
        sources += [case["source"] for case in data["cases"]]
    return sources


SOURCES = [path.read_text(encoding="utf-8") for path in EXAMPLES] + conformance_sources()


def shape(node):
    """Nested form of a tree: a terminal is its text, a nonterminal is (symbol, [children])."""
    return node.symbol if node.is_terminal else (node.symbol, [shape(c) for c in node.children])


def tree_of(source):
    return shape(build_parse_tree(f"begin {source} end").root.children[1])


def var(name):
    return ("<вираз>", [("<змінна>", [name])])


def num(value):
    return ("<вираз>", [("<число>", [value])])


def test_program_shape_follows_the_course_bnf():
    assert shape(build_parse_tree("begin x := 1 end").root) == (
        "<програма>", ["begin",
                      ("<оператор>", [("<змінна>", ["x"]), ":=", ("<вираз>", [("<число>", ["1"])])]),
                      "end"])


def test_expression_shape_reflects_priorities():
    assert tree_of("x := a + b * c")[1][2] == (
        "<вираз>", [var("a"), "+", ("<вираз>", [var("b"), "*", var("c")])])
    assert tree_of("x := a - b - c")[1][2] == (
        "<вираз>", [("<вираз>", [var("a"), "-", var("b")]), "-", var("c")])


def test_parentheses_are_terminals_of_the_parse_tree():
    assert tree_of("x := (a)")[1][2] == ("<вираз>", [("<вираз>", ["(", var("a"), ")"])])[1][0]
    cond = tree_of("while (a > b) do skip")[1][1]
    assert cond == ("<умова>", ["(", ("<умова>", [var("a"), ">", var("b")]), ")"])


def test_condition_shape_reflects_priorities():
    cond = tree_of("while ¬a = b ∨ c > d do skip")[1][1]
    assert cond == ("<умова>", [("<умова>", ["¬", ("<умова>", [var("a"), "=", var("b")])]), "∨",
                               ("<умова>", [var("c"), ">", var("d")])])


def test_sequence_is_left_nested():
    shaped = tree_of("x := 1; y := 2; z := 3")
    assert shaped[0] == "<оператор>" and shaped[1][1] == ";"
    inner = shaped[1][0]
    assert inner[0] == "<оператор>" and inner[1][1] == ";"
    assert inner[1][0][1][0] == ("<змінна>", ["x"]) and shaped[1][2][1][0] == ("<змінна>", ["z"])


def test_compound_statements():
    assert [c if isinstance(c, str) else c[0] for c in tree_of("if a > b then skip else skip")[1]] == [
        "if", "<умова>", "then", "<оператор>", "else", "<оператор>"]
    assert [c if isinstance(c, str) else c[0] for c in tree_of("while a > b do skip")[1]] == [
        "while", "<умова>", "do", "<оператор>"]
    assert tree_of("begin skip end")[1] == ["begin", ("<оператор>", ["skip"]), "end"]
    assert tree_of("skip") == ("<оператор>", ["skip"])


@pytest.mark.parametrize("source", SOURCES)
def test_terminals_spell_the_program(source):
    tree = build_parse_tree(source)
    leaves = list(tree.leaves())
    assert "".join(leaf.symbol for leaf in leaves) == re.sub(r"\s+", "", source)
    assert [leaf.number for leaf in leaves] == list(range(1, len(leaves) + 1))


@pytest.mark.parametrize("source", SOURCES)
def test_spans_link_nodes_to_source_fragments(source):
    tree = build_parse_tree(source)
    for node in tree.nodes():
        if node.is_terminal:
            assert tree.fragment(node) == node.symbol
        else:
            assert node.span.start == node.children[0].span.start
            assert node.span.end == node.children[-1].span.end
    assert tree.fragment(tree.root) == source.strip()


def test_terminal_numbering_matches_the_workbook_figure():
    assert build_parse_tree(POWER).numbered_leaves() == (
        "1 begin 2 R 3 := 4 1 5 ; 6 while 7 Y 8 > 9 0 10 do 11 begin 12 R 13 := 14 R 15 * 16 X "
        "17 ; 18 Y 19 := 20 Y 21 - 22 1 23 end 24 end")


def test_invalid_program_raises_a_syntax_error_with_position():
    with pytest.raises(SiplSyntaxError) as info:
        build_parse_tree("begin x := ; end")
    assert (info.value.line, info.value.column) == (1, 12)


def test_text_rendering():
    assert to_text(build_parse_tree("begin skip end")) == (
        "<програма>  [1:1-1:15]  begin skip end\n"
        "  1: begin  [1:1-1:6]\n"
        "  <оператор>  [1:7-1:11]  skip\n"
        "    2: skip  [1:7-1:11]\n"
        "  3: end  [1:12-1:15]\n"
        "\n"
        "terminals: 1 begin 2 skip 3 end")


def test_text_rendering_shortens_long_fragments():
    text = to_text(build_parse_tree(POWER))
    assert text.splitlines()[0].endswith("…")


def test_json_rendering():
    tree = build_parse_tree(POWER)
    data = json.loads(json.dumps(to_dict(tree)))
    assert data["symbol"] == "<програма>" and data["kind"] == "nonterminal"
    assert data["span"]["start"] == {"line": 1, "column": 1, "offset": 0}

    def count(node):
        return 1 + sum(count(child) for child in node.get("children", []))

    assert count(data) == len(list(tree.nodes()))
    first = data["children"][0]
    assert first == {"symbol": "begin", "kind": "terminal", "number": 1,
                     "span": first["span"]} and first["span"]["end"]["column"] == 6


def test_dot_rendering_structure():
    tree = build_parse_tree("begin x := a > 1 end".replace("a > 1", "a") + "")
    dot = to_dot(tree)
    nodes = len(list(tree.nodes()))
    assert dot.startswith("digraph parse_tree {") and dot.endswith("}")
    assert len(re.findall(r"^  n\d+ \[label=", dot, re.M)) == nodes
    assert len(re.findall(r"^  n\d+ -> n\d+;", dot, re.M)) == nodes - 1
    assert 'tooltip="1:7-1:13: x := a"' in dot


def test_dot_escapes_special_symbols():
    dot = to_dot(build_parse_tree("begin while ¬a > b do skip end"))
    assert "&gt;" in dot and "¬" in dot and 'label="<умова>"' in dot


@pytest.mark.skipif(shutil.which("dot") is None, reason="Graphviz is not installed")
@pytest.mark.parametrize("source", SOURCES[:6])
def test_dot_is_valid_graphviz(source):
    result = subprocess.run(["dot", "-Tsvg"], input=to_dot(build_parse_tree(source)),
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0 and "<svg" in result.stdout


SVG = "{http://www.w3.org/2000/svg}"


def test_svg_is_well_formed_and_every_node_is_linked_to_the_source():
    tree = build_parse_tree(POWER)
    root = ET.fromstring(to_svg(tree))
    assert root.tag == SVG + "svg" and root.get("viewBox")
    assert root.find(f"{SVG}rect").get("fill") == "#ffffff"
    groups = [g for g in root.iter(f"{SVG}g") if g.get("class") in ("node terminal", "node nonterminal")]
    nodes = list(tree.nodes())
    assert len(groups) == len(nodes)
    for group, node in zip(groups, nodes):
        assert (int(group.get("data-start")), int(group.get("data-end"))) == (node.span.start, node.span.end)
        assert int(group.get("data-line")) == node.span.start_line
        assert int(group.get("data-column")) == node.span.start_column
        assert group.get("class") == ("node terminal" if node.is_terminal else "node nonterminal")
        title = group.find(f"{SVG}title").text
        assert title.startswith(f"{node.span.start_line}:{node.span.start_column}-")
    texts = [g.find(f"{SVG}text[@class='t']").text for g in groups if g.get("class") == "node terminal"]
    assert texts == [leaf.symbol for leaf in tree.leaves()]
    assert len(root.findall(f".//{SVG}line")) == len(nodes) - 1


def test_svg_escapes_markup_characters():
    svg = to_svg(build_parse_tree("begin while ¬a > b do skip end"))
    assert "&lt;програма&gt;" in svg and ">&gt;</text>" in svg
    ET.fromstring(svg)


@pytest.mark.parametrize("source", SOURCES)
def test_layout_has_no_overlaps(source):
    boxes, width, height = _layout(build_parse_tree(source))
    levels = defaultdict(list)
    for box in boxes:
        levels[box.y].append(box)
        assert 0 <= box.x - box.width / 2 and box.x + box.width / 2 <= width
        assert box.y <= height
    for level in levels.values():
        level.sort(key=lambda b: b.x)
        for left, right in zip(level, level[1:]):
            assert right.x - left.x >= (left.width + right.width) / 2 - 1e-6


def test_committed_example_is_up_to_date():
    expected = to_svg(build_parse_tree(POWER))
    assert (ROOT / "docs" / "power-parse-tree.svg").read_text(encoding="utf-8").strip() == expected


# Command line

def cli(capsys, *args):
    code = main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_cli_text_is_the_default(capsys, tmp_path):
    path = tmp_path / "p.sipl"
    path.write_text("begin skip end", encoding="utf-8")
    code, out, _ = cli(capsys, "tree", str(path))
    assert code == 0 and out == to_text(build_parse_tree("begin skip end")) + "\n"


@pytest.mark.parametrize("fmt, start", [("dot", "digraph parse_tree"), ("svg", "<?xml")])
def test_cli_dot_and_svg(capsys, fmt, start):
    code, out, _ = cli(capsys, "tree", str(EXAMPLES[0]), "--format", fmt)
    assert code == 0 and out.startswith(start)


def test_cli_json_envelope(capsys):
    code, out, _ = cli(capsys, "tree", str(EXAMPLES[0]), "--format", "json")
    data = json.loads(out)
    assert code == 0 and data["version"] == 1 and data["status"] == "ok"
    assert data["tree"]["symbol"] == "<програма>"


def test_cli_writes_the_output_file(capsys, tmp_path):
    target = tmp_path / "tree.svg"
    code, out, _ = cli(capsys, "tree", str(EXAMPLES[0]), "--format", "svg", "-o", str(target))
    assert (code, out) == (0, "")
    source = EXAMPLES[0].read_text(encoding="utf-8")
    assert target.read_text(encoding="utf-8") == to_svg(build_parse_tree(source)) + "\n"


def test_cli_syntax_error_in_both_modes(capsys, tmp_path):
    path = tmp_path / "bad.sipl"
    path.write_text("begin x := ; end", encoding="utf-8")
    code, out, err = cli(capsys, "tree", str(path))
    assert code == 1 and out == "" and f"{path}:1:12: error:" in err
    code, out, _ = cli(capsys, "tree", str(path), "--format", "json")
    data = json.loads(out)
    assert code == 1 and data["status"] == "error" and data["error"]["type"] == "SiplSyntaxError"


def test_cli_output_file_error(capsys, tmp_path):
    missing = str(tmp_path / "no" / "dir" / "t.svg")
    code, _, err = cli(capsys, "tree", str(EXAMPLES[0]), "-o", missing)
    assert code == 4 and "cannot write" in err
    code, out, _ = cli(capsys, "tree", str(EXAMPLES[0]), "--format", "json", "-o", missing)
    assert code == 4 and json.loads(out)["error"]["type"] == "OutputError"


def test_cli_too_deep_json_is_reported_but_text_works(capsys, tmp_path):
    path = tmp_path / "long.sipl"
    path.write_text("begin x := 0" + "; x := x + 1" * 3000 + " end", encoding="utf-8")
    code, out, _ = cli(capsys, "tree", str(path), "--format", "json")
    assert code == 3 and json.loads(out)["error"]["type"] == "NestingTooDeep"
    code, out, _ = cli(capsys, "tree", str(path))
    assert code == 0 and out.rstrip().endswith("end")
