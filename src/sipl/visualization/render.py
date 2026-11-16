"""Renderers of a parse tree: text, JSON-ready dict, DOT and SVG.

Every node carries its source span, so each rendering links nodes to fragments of the program.
"""
from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any

from sipl.visualization.parse_tree import ParseNode, ParseTree


def _position(node: ParseNode) -> str:
    s = node.span
    return f"{s.start_line}:{s.start_column}-{s.end_line}:{s.end_column}"


def _fragment(tree: ParseTree, node: ParseNode, limit: int) -> str:
    text = " ".join(tree.fragment(node).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def to_text(tree: ParseTree) -> str:
    """Indented tree; each line shows the source position, then the check of the course workbook."""
    lines, stack = [], [(tree.root, 0)]
    while stack:
        node, depth = stack.pop()
        pad = "  " * depth
        if node.is_terminal:
            lines.append(f"{pad}{node.number}: {node.symbol}  [{_position(node)}]")
        else:
            lines.append(f"{pad}{node.symbol}  [{_position(node)}]  {_fragment(tree, node, 40)}")
        stack.extend((child, depth + 1) for child in reversed(node.children))
    return "\n".join([*lines, "", f"terminals: {tree.numbered_leaves()}"])


def to_dict(tree: ParseTree) -> dict[str, Any]:
    def convert(node: ParseNode) -> dict[str, Any]:
        data: dict[str, Any] = {"symbol": node.symbol,
                                "kind": "terminal" if node.is_terminal else "nonterminal",
                                "span": node.span.to_dict()}
        if node.is_terminal:
            data["number"] = node.number
        else:
            data["children"] = [convert(child) for child in node.children]
        return data

    return convert(tree.root)


def _dot_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def to_dot(tree: ParseTree) -> str:
    lines = ["digraph parse_tree {", '  graph [ordering=out, bgcolor="white"];',
             '  node [shape=plaintext, fontname="DejaVu Serif"];',
             '  edge [arrowhead=vee, arrowsize=0.5, color="#555555"];']
    edges, stack, count = [], [(tree.root, None)], 0
    while stack:
        node, parent = stack.pop()
        ident, count = count, count + 1
        tooltip = _dot_escape(f"{_position(node)}: {_fragment(tree, node, 60)}")
        if node.is_terminal:
            label = (f'<<FONT COLOR="#c0392b" POINT-SIZE="10">{node.number}</FONT><BR/>'
                     f"{html.escape(node.symbol)}>")
        else:
            label = f'"{_dot_escape(node.symbol)}"'
        lines.append(f'  n{ident} [label={label}, tooltip="{tooltip}"];')
        if parent is not None:
            edges.append(f"  n{parent} -> n{ident};")
        stack.extend((child, ident) for child in reversed(node.children))
    return "\n".join([*lines, *edges, "}"])


_CHAR_WIDTH, _PADDING, _LEVEL_GAP, _MARGIN, _TOP = 8.0, 16.0, 60.0, 24.0, 20.0


@dataclass(frozen=True)
class _Box:
    node: ParseNode
    x: float  # center
    y: float  # text baseline
    width: float
    parent: int | None  # index of the parent box


def _layout(tree: ParseTree) -> tuple[list[_Box], float, float]:
    """Boxes in pre-order; boxes of one level never overlap. Returns the boxes, width and height."""
    nodes: list[ParseNode] = []
    depth: list[int] = []
    parent: list[int | None] = []
    stack: list[tuple[ParseNode, int, int | None]] = [(tree.root, 0, None)]
    while stack:
        node, d, p = stack.pop()
        nodes.append(node)
        depth.append(d)
        parent.append(p)
        stack.extend((child, d + 1, len(nodes) - 1) for child in reversed(node.children))
    kids: list[list[int]] = [[] for _ in nodes]
    for index, p in enumerate(parent):
        if p is not None:
            kids[p].append(index)

    own = [len(node.symbol) * _CHAR_WIDTH + _PADDING for node in nodes]
    subtree = [0.0] * len(nodes)  # width reserved for the whole subtree
    for i in reversed(range(len(nodes))):
        subtree[i] = max(own[i], sum(subtree[k] for k in kids[i]))
    left = [0.0] * len(nodes)
    for i in range(len(nodes)):
        start = left[i] + (subtree[i] - sum(subtree[k] for k in kids[i])) / 2
        for k in kids[i]:
            left[k], start = start, start + subtree[k]
    center = [0.0] * len(nodes)
    for i in reversed(range(len(nodes))):
        if kids[i]:
            middle = (center[kids[i][0]] + center[kids[i][-1]]) / 2
            center[i] = min(max(middle, left[i] + own[i] / 2), left[i] + subtree[i] - own[i] / 2)
        else:
            center[i] = left[i] + subtree[i] / 2

    boxes = [_Box(nodes[i], _MARGIN + center[i], _MARGIN + _TOP + depth[i] * _LEVEL_GAP, own[i], parent[i])
             for i in range(len(nodes))]
    return boxes, subtree[0] + 2 * _MARGIN, 2 * _MARGIN + _TOP + max(depth) * _LEVEL_GAP + 8


_STYLE = """text{font-family:'DejaVu Serif',serif;font-size:13px;text-anchor:middle}
.t{font-family:'DejaVu Sans Mono',monospace;fill:#0b3d91}
.num{font-size:10px;fill:#c0392b}
line{stroke:#555;stroke-width:.8}
.node:hover .nt,.node:hover .t{font-weight:bold}"""


def to_svg(tree: ParseTree) -> str:
    """Standalone SVG. Every node is a <g class="node ..."> with data-* attributes holding its source
    span (offsets, lines, columns) and a <title> tooltip with the source fragment."""
    boxes, width, height = _layout(tree)
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
           f'width="{width:.0f}" height="{height:.0f}">',
           f"<style>{_STYLE}</style>",
           '<defs><marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" '
           'markerHeight="6" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#555"/></marker></defs>',
           '<rect width="100%" height="100%" fill="#ffffff"/>', '<g class="edges">']
    for box in boxes:
        if box.parent is not None:
            above = boxes[box.parent]
            top = box.y - (24 if box.node.is_terminal else 16)
            out.append(f'<line x1="{above.x:.1f}" y1="{above.y + 6:.1f}" x2="{box.x:.1f}" '
                       f'y2="{top:.1f}" marker-end="url(#arrow)"/>')
    out += ["</g>", '<g class="nodes">']
    for box in boxes:
        node, s = box.node, box.node.span
        kind = "terminal" if node.is_terminal else "nonterminal"
        title = html.escape(f"{_position(node)}: {_fragment(tree, node, 60)}")
        text = html.escape(node.symbol)
        if node.is_terminal:
            body = (f'<text class="num" x="{box.x:.1f}" y="{box.y - 11:.1f}">{node.number}</text>'
                    f'<text class="t" x="{box.x:.1f}" y="{box.y:.1f}">{text}</text>')
        else:
            body = f'<text class="nt" x="{box.x:.1f}" y="{box.y:.1f}">{text}</text>'
        out.append(f'<g class="node {kind}" data-start="{s.start}" data-end="{s.end}" '
                   f'data-line="{s.start_line}" data-column="{s.start_column}" '
                   f'data-end-line="{s.end_line}" data-end-column="{s.end_column}">'
                   f"<title>{title}</title>{body}</g>")
    return "\n".join([*out, "</g>", "</svg>"])
