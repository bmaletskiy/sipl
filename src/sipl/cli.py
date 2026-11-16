"""Command-line interface: sipl parse | check | run | trace."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import errno
from pathlib import Path
from typing import Any

from sipl import ast
from sipl.interpreter import (DEFAULT_MAX_STEPS, AfterStatement, BeforeStatement,
                              ConditionEvaluated, Failed, Finished, Interpreter, SiplRuntimeError,
                              State, VariableChanged, trace)
from sipl.interpreter.events import Event
from sipl.parser import SiplSyntaxError, parse
from sipl.semantics import semantic_term
from sipl.visualization import build_parse_tree, to_dict, to_dot, to_svg, to_text

EXIT_OK, EXIT_SYNTAX, EXIT_USAGE, EXIT_RUNTIME, EXIT_INPUT = 0, 1, 2, 3, 4
JSON_VERSION = 1

_EPILOG = """exit codes:
  0  success
  1  syntax error in the program
  2  command-line usage error
  3  runtime error (undefined variable, step limit exceeded)
  4  input error (the file cannot be read, or the output file cannot be written)

With --json, standard output is one JSON object with "version" and "status"
("ok" or "error"); see docs/cli.md for the schema."""


class _InputError(Exception):
    pass


def _assignment(text: str) -> tuple[str, int]:
    match = re.fullmatch(r"([A-Za-z_][A-Za-z_0-9]*)=(-?[0-9]+)", text)
    if not match:
        raise argparse.ArgumentTypeError(f"expected NAME=INTEGER, got {text!r}")
    return match[1], int(match[2])


def _positive_int(text: str) -> int:
    value = int(text) if re.fullmatch(r"[0-9]+", text) else 0
    if value < 1:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {text!r}")
    return value


def _read(path: str) -> str:
    try:
        return sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        reason = exc.strerror if isinstance(exc, OSError) and exc.strerror else str(exc)
        raise _InputError(f"cannot read '{path}': {reason}") from None


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _wants_json(args: argparse.Namespace) -> bool:
    return getattr(args, "json", False) or getattr(args, "format", None) == "json"


def _fail(args, kind: str, message: str, code: int, span: ast.SourceSpan | None = None,
          **extra: Any) -> int:
    if _wants_json(args):
        error: dict[str, Any] = {"type": kind, "message": message}
        if span:
            error["span"] = span.to_dict()
        _print_json({"version": JSON_VERSION, "status": "error", "error": {**error, **extra}})
    else:
        name = "<stdin>" if args.file == "-" else args.file
        where = f"{name}:{span.start_line}:{span.start_column}: " if span else ""
        print(f"{where}error: {message}", file=sys.stderr)
    return code


def _format_state(state: State) -> str:
    return "{" + ", ".join(f"{name}={value}" for name, value in sorted(state.items())) + "}"


def _format_event(event: Event) -> str:
    where = f"{event.span.start_line}:{event.span.start_column}"
    match event:
        case BeforeStatement():
            return f"[{event.step}] {where} before {event.statement}"
        case AfterStatement():
            return f"[{event.step}] {where} after {event.statement} {_format_state(event.state)}"
        case VariableChanged():
            old = "undefined" if event.old is None else event.old
            return f"[{event.step}] {where} {event.name}: {old} -> {event.new}"
        case ConditionEvaluated():
            return f"[{event.step}] {where} {event.statement} condition = {str(event.value).lower()}"
        case Finished():
            return f"finished after {event.step} steps {_format_state(event.state)}"
        case Failed():
            return f"failed at {where}: {event.error}: {event.message}"
    raise TypeError(f"unknown event: {event!r}")


def _cmd_parse(args, program: ast.Program) -> int:
    if not args.json:
        print(ast.dump(program))
        return EXIT_OK
    try:
        _print_json({"version": JSON_VERSION, "status": "ok", "ast": program.to_dict()})
    except RecursionError:
        return _fail(args, "NestingTooDeep",
                     "the AST is too deeply nested to be written as JSON", EXIT_RUNTIME)
    return EXIT_OK


def _cmd_check(args, program: ast.Program) -> int:
    if args.json:
        _print_json({"version": JSON_VERSION, "status": "ok"})
    else:
        print("OK")
    return EXIT_OK


def _cmd_term(args, program: ast.Program) -> int:
    try:
        term = semantic_term(program)
        if args.json:
            _print_json({"version": JSON_VERSION, "status": "ok", "notation": str(term),
                         "term": term.to_dict()})
        else:
            print(term)
    except RecursionError:
        return _fail(args, "NestingTooDeep",
                     "the semantic term is too deeply nested to be printed", EXIT_RUNTIME)
    return EXIT_OK


def _cmd_run(args, program: ast.Program) -> int:
    interpreter = Interpreter(args.max_steps)
    try:
        final = interpreter.run(program, State(dict(args.var)))
    except SiplRuntimeError as err:
        return _fail(args, type(err).__name__, err.message, EXIT_RUNTIME, err.span)
    if args.json:
        _print_json({"version": JSON_VERSION, "status": "ok", "state": dict(final),
                     "steps": interpreter.steps})
    else:
        for name, value in sorted(final.items()):
            print(f"{name} = {value}")
    return EXIT_OK


def _cmd_trace(args, program: ast.Program) -> int:
    result = trace(program, dict(args.var), max_steps=args.max_steps)
    failed = result.failure is not None
    if args.json:
        _print_json({"version": JSON_VERSION, "status": "error" if failed else "ok",
                     "events": result.to_dict()["events"]})
    else:
        for event in result.events:
            print(_format_event(event))
    return EXIT_RUNTIME if failed else EXIT_OK


def _format_tree(tree, fmt: str) -> str:
    if fmt == "json":
        return json.dumps({"version": JSON_VERSION, "status": "ok", "tree": to_dict(tree)},
                          ensure_ascii=False, separators=(",", ":"))
    return {"text": to_text, "dot": to_dot, "svg": to_svg}[fmt](tree)


def _cmd_tree(args, program: ast.Program) -> int:
    try:
        output = _format_tree(build_parse_tree(args.source), args.format)
    except RecursionError:
        return _fail(args, "NestingTooDeep",
                     "the parse tree is too deeply nested to be drawn", EXIT_RUNTIME)
    if not args.output:
        print(output)
        return EXIT_OK
    try:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    except OSError as exc:
        return _fail(args, "OutputError", f"cannot write '{args.output}': {exc.strerror or exc}",
                     EXIT_INPUT)
    return EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sipl", description="SIPL Language Toolkit", epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True, metavar="{parse,check,term,run,trace,tree}")
    for name, handler, help_text, executes in [
        ("parse", _cmd_parse, "print the AST", False),
        ("check", _cmd_check, "check the syntax", False),
        ("term", _cmd_term, "print the semantic term in the notation of the course", False),
        ("run", _cmd_run, "run the program and print the final state", True),
        ("trace", _cmd_trace, "run the program and print the execution trace", True),
    ]:
        sub = commands.add_parser(name, help=help_text, description=help_text)
        sub.add_argument("file", help="SIPL source file, or - for standard input")
        sub.add_argument("--json", action="store_true", help="machine-readable JSON output")
        if executes:
            sub.add_argument("--var", "-v", action="append", default=[], type=_assignment,
                             metavar="NAME=INT", help="initial value of a variable (repeatable)")
            sub.add_argument("--max-steps", type=_positive_int, default=DEFAULT_MAX_STEPS,
                             metavar="N", help=f"step limit (default {DEFAULT_MAX_STEPS})")
        sub.set_defaults(handler=handler)
    tree = commands.add_parser("tree", help="draw the parse tree (text, JSON, DOT or SVG)",
                               description="Draw the parse tree of the program in the notation of "
                                           "the course BNF; every node is linked to its source fragment.")
    tree.add_argument("file", help="SIPL source file, or - for standard input")
    tree.add_argument("--format", choices=("text", "json", "dot", "svg"), default="text",
                      help="output format (default: text)")
    tree.add_argument("--output", "-o", metavar="FILE", help="write to FILE instead of standard output")
    tree.set_defaults(handler=_cmd_tree)
    return parser


def _use_utf8() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")


def _execute(args: argparse.Namespace) -> int:
    try:
        args.source = _read(args.file)
        program = parse(args.source)
    except _InputError as err:
        return _fail(args, "InputError", str(err), EXIT_INPUT)
    except SiplSyntaxError as err:
        return _fail(args, "SiplSyntaxError", err.message, EXIT_SYNTAX, err.span,
                     expected=list(err.expected))
    return args.handler(args, program)



def main(argv: list[str] | None = None) -> int:
    _use_utf8()
    args = _build_parser().parse_args(argv)
    try:
        return _execute(args)
    except OSError as exc:
        if not (
            isinstance(exc, BrokenPipeError)
            or (os.name == "nt" and exc.errno == errno.EINVAL)
        ):
            raise

        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return EXIT_OK
