#!/usr/bin/env python3
"""SIPL conformance runner.

Checks any SIPL implementation that provides the command-line contract described in README.md.
Only the standard library is used, so the runner does not depend on the implementation under test.

    python conformance/run.py                       # tests `python -m sipl`
    python conformance/run.py --command "./my-sipl"  # tests another implementation
    python conformance/run.py --suite ast -v
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Callable, TextIO

CASES_DIR = Path(__file__).parent / "cases"

# An executor runs the implementation: (command-line arguments, standard input) -> standard output.
Executor = Callable[[list[str], str], str]


def load_suites(names: list[str] | None = None) -> dict[str, list[dict]]:
    suites = {}
    for path in sorted(CASES_DIR.glob("*.json")):
        if not names or path.stem in names:
            suites[path.stem] = json.loads(path.read_text(encoding="utf-8"))["cases"]
    return suites


def to_sexpr(node: dict) -> str:
    """Render a JSON AST node in the notation used by the cases (see README.md)."""
    kind = node["type"]
    match kind:
        case "Var":
            return node["name"]
        case "Num":
            return str(node["value"])
        case "Skip":
            return "(Skip)"
        case "Program" | "Block":
            return f"({kind} {to_sexpr(node['body'])})"
        case "Seq":
            return f"(Seq {to_sexpr(node['first'])} {to_sexpr(node['second'])})"
        case "Assign":
            return f"(Assign {node['target']['name']} {to_sexpr(node['expr'])})"
        case "If":
            return (f"(If {to_sexpr(node['cond'])} {to_sexpr(node['then'])} "
                    f"{to_sexpr(node['orelse'])})")
        case "While":
            return f"(While {to_sexpr(node['cond'])} {to_sexpr(node['body'])})"
        case "BinOp" | "Compare":
            return f"({node['op']} {to_sexpr(node['left'])} {to_sexpr(node['right'])})"
        case "Or":
            return f"(or {to_sexpr(node['left'])} {to_sexpr(node['right'])})"
        case "Not":
            return f"(not {to_sexpr(node['operand'])})"
    raise ValueError(f"unknown node type {kind!r}")


def _call(execute: Executor, args: list[str], source: str) -> dict:
    output = execute(args, source)
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        raise ValueError(f"output of `{' '.join(args)}` is not valid JSON: {output[:60]!r}") from None
    if not isinstance(data, dict):
        raise ValueError(f"output of `{' '.join(args)}` is not a JSON object")
    return data


def _check_ast(case: dict, execute: Executor) -> list[str]:
    data = _call(execute, ["parse", "-", "--json"], case["source"])
    if data.get("status") != "ok":
        return [f"parse failed: {data.get('error')}"]
    try:
        actual = to_sexpr(data["ast"])
    except (KeyError, TypeError, ValueError) as exc:
        return [f"unsupported AST: {exc!r}"]
    expected = " ".join(case["expect"]["ast"].split())
    return [] if actual == expected else [f"AST: expected {expected}, got {actual}"]


def _check_run(case: dict, execute: Executor) -> list[str]:
    args = ["run", "-", "--json"]
    for name, value in case.get("initial", {}).items():
        args += ["--var", f"{name}={value}"]
    if "max_steps" in case:
        args += ["--max-steps", str(case["max_steps"])]
    data = _call(execute, args, case["source"])
    expect = case["expect"]
    if "state" in expect:
        if data.get("status") != "ok":
            return [f"run failed: {data.get('error')}"]
        actual = data.get("state")
        return [] if actual == expect["state"] else [f"state: expected {expect['state']}, got {actual}"]
    wanted = expect["error"]
    if data.get("status") != "error":
        return [f"expected {wanted['type']}, but the run succeeded with state {data.get('state')}"]
    error = data.get("error", {})
    failures = []
    if error.get("type") != wanted["type"]:
        failures.append(f"error type: expected {wanted['type']}, got {error.get('type')}")
    start = error.get("span", {}).get("start", {})
    for key in ("line", "column"):
        if key in wanted and start.get(key) != wanted[key]:
            failures.append(f"error {key}: expected {wanted[key]}, got {start.get(key)}")
    return failures


def run_case(case: dict, execute: Executor) -> list[str]:
    """Run one case; return the list of failure messages (empty if the case passes)."""
    failures = []
    try:
        if "ast" in case["expect"]:
            failures += _check_ast(case, execute)
        if "state" in case["expect"] or "error" in case["expect"]:
            failures += _check_run(case, execute)
    except ValueError as exc:
        failures.append(str(exc))
    return failures


def run_suites(suites: dict[str, list[dict]], execute: Executor, verbose: bool = False,
               out: TextIO = sys.stdout) -> int:
    passed = failed = 0
    for suite, cases in suites.items():
        for case in cases:
            failures = run_case(case, execute)
            if failures:
                failed += 1
                print(f"FAIL {suite}/{case['name']}", file=out)
                for message in failures:
                    print(f"     {message}", file=out)
            else:
                passed += 1
                if verbose:
                    print(f"PASS {suite}/{case['name']}", file=out)
    print(f"{passed} passed, {failed} failed", file=out)
    return 0 if failed == 0 else 1


def subprocess_executor(command: list[str]) -> Executor:
    def execute(args: list[str], stdin: str) -> str:
        result = subprocess.run([*command, *args], input=stdin, capture_output=True, text=True,
                                encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
        return result.stdout
    return execute


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the SIPL conformance suite.")
    parser.add_argument("--command", help="command that starts the implementation "
                        "(default: this Python with `-m sipl`)")
    parser.add_argument("--suite", action="append", metavar="NAME",
                        help="run only this suite (a file in cases/, without .json); repeatable")
    parser.add_argument("-v", "--verbose", action="store_true", help="also list passing cases")
    args = parser.parse_args(argv)
    suites = load_suites(args.suite)
    if not suites:
        parser.error("no such suite")
    command = (shlex.split(args.command, posix=os.name != "nt") if args.command
               else [sys.executable, "-m", "sipl"])
    return run_suites(suites, subprocess_executor(command), args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
