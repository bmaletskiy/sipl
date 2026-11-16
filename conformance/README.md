# SIPL conformance suite

A language-neutral test suite for SIPL (the course language): programs together with the expected AST,
the expected final state, or the expected error. It does not depend on this repository's implementation:
any implementation that provides the small command-line contract below can be checked with it.

```
python conformance/run.py                          # tests `python -m sipl` (this repository)
python conformance/run.py --command "./my-sipl"    # tests another implementation
python conformance/run.py --suite ast -v           # one suite, list passing cases too
```

The runner needs only Python 3.10+ and the standard library. It prints `FAIL suite/case` with the reason
for every failing case and `N passed, M failed` at the end; the exit code is 0 if all cases pass, 1 otherwise.

## Layout

| File in `cases/` | Contents |
|---|---|
| `ast.json` | the expected abstract syntax tree: priorities, associativity, the effect of `;` and `begin ... end` |
| `syntax_errors.json` | programs that must be rejected, with the position of the first offending token |
| `semantics.json` | the final state of programs that finish normally (including the examples of the course book) |
| `runtime_errors.json` | undefined variables and the step limit |

## Case format

Each file is `{"suite": ..., "description": ..., "cases": [...]}`. A case is an object:

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | unique within the suite |
| `description` | yes | what the case checks |
| `source` | yes | the complete program text, including the outer `begin ... end` |
| `initial` | no | initial state: `{"X": 5, "Y": 2}` (integers); default is the empty state |
| `max_steps` | no | step limit passed to the implementation |
| `expect` | yes | the expectation, see below |

`expect` has `ast` and/or `state`, or `error`:

```json
{"expect": {"ast": "(Program (Assign x (+ a (* b c))))"}}
{"expect": {"state": {"M": 8, "N": 8}}}
{"expect": {"error": {"type": "SiplSyntaxError", "line": 1, "column": 15}}}
```

- `ast`: the tree in the notation below; whitespace is not significant.
- `state`: the exact final state: the same variables and values, no more and no less.
- `error`: `type` is `SiplSyntaxError`, `UndefinedVariableError` or `StepLimitExceeded`. `line` and `column`
  are optional; when given, they are the 1-based position of the first offending character or token
  (for a runtime error: the variable that cannot be read). They are omitted where implementations could
  reasonably differ, for example for an error at the end of the input.

## AST notation

Every node is written as an S-expression; `Var` and `Num` are written as the bare name or number.

| Node | Notation | JSON fields |
|---|---|---|
| program | `(Program S)` | `body` |
| `begin S end` | `(Block S)` | `body` |
| `S1 ; S2` | `(Seq S1 S2)` | `first`, `second` |
| `x := a` | `(Assign x a)` | `target` (a `Var` node), `expr` |
| `if b then S1 else S2` | `(If b S1 S2)` | `cond`, `then`, `orelse` |
| `while b do S` | `(While b S)` | `cond`, `body` |
| `skip` | `(Skip)` | none |
| variable | `x` | `name` |
| number | `-12` | `value` |
| `a1 + a2`, `a1 - a2`, `a1 * a2` | `(+ a1 a2)`, `(- a1 a2)`, `(* a1 a2)` | `op`, `left`, `right` (type `BinOp`) |
| `a1 = a2`, `a1 > a2` | `(= a1 a2)`, `(> a1 a2)` | `op`, `left`, `right` (type `Compare`) |
| `b1 ∨ b2` | `(or b1 b2)` | `left`, `right` (type `Or`) |
| `¬b` | `(not b)` | `operand` (type `Not`) |

This is abstract syntax: parentheses are not nodes. Binary operations are left-associative, and the priorities
are, from the highest: `*`; `+ -`; `= >`; `¬`; `∨`; then the statements, where `;` binds loosest.

## What an implementation must provide

Two commands, with the program on standard input (`-`), and one JSON object on standard output:

```
<command> parse - --json
<command> run   - --json [--var NAME=INT]... [--max-steps N]
```

| Result | Output |
|---|---|
| `parse`, success | `{"status": "ok", "ast": <node>}`; a node is `{"type": ..., <fields of the table>}` |
| `run`, success | `{"status": "ok", "state": {"X": 5, ...}}` |
| any failure | `{"status": "error", "error": {"type": ..., "span": {"start": {"line": L, "column": C}}}}` |

Other fields (spans of nodes, step counts, messages) are allowed and ignored. Cases with an `ast` expectation
use `parse`; cases with `state` or `error` use `run` (a syntax error is reported by `run` as well).
`--var` sets an initial variable; `--max-steps` is the step limit.

This repository's `sipl parse|run ... --json` is one such implementation (see `docs/cli.md`).

## Not tested

Message texts, exit codes, the number of steps, node spans, integers beyond 64 bits, and the exact step at
which a limit is hit: the course does not define them. Cases that need a step limit use infinite loops.

## Adding cases

Derive the expectation from the course definition (the BNF, the priorities and the semantics), never by copying
the output of an implementation. Keep names unique and give every case a description.
