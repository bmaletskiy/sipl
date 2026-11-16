# Command-line interface

```
sipl parse FILE [--json]                          print the AST
sipl check FILE [--json]                          check the syntax
sipl term  FILE [--json]                          print the semantic term (course notation)
sipl run   FILE [--var NAME=INT]... [--max-steps N] [--json]    run, print the final state
sipl trace FILE [--var NAME=INT]... [--max-steps N] [--json]    run, print the execution trace
sipl tree  FILE [--format text|json|dot|svg] [--output FILE]    draw the parse tree
```

`FILE` is a SIPL source file (UTF-8) or `-` for standard input. `python -m sipl ...` works the same.
`--var` / `-v` sets the initial value of a variable and can be repeated; `--max-steps` limits the number of
steps (default 1 000 000).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | syntax error in the program |
| 2 | command-line usage error (unknown command, bad `--var`, bad `--max-steps`, missing file argument) |
| 3 | runtime error (`UndefinedVariableError`, `StepLimitExceeded`); also `trace` when the trace ends with `Failed` |
| 4 | input error: the file cannot be read or is not valid UTF-8, or the `--output` file cannot be written |

## Human output

Results go to standard output. Diagnostics go to standard error in the form
`FILE:LINE:COLUMN: error: MESSAGE` (`<stdin>` for standard input; input errors have no position).

```
$ sipl run examples/power.sipl --var X=5 --var Y=2
R = 25
X = 5
Y = 0
```

## JSON output (`--json`)

Standard output is exactly one JSON object. Every object has `version` (currently `1`) and `status`
(`"ok"` or `"error"`); the exit code is the same as in human mode.

| Command | Success (`status: "ok"`) |
|---|---|
| `check` | `{"version":1,"status":"ok"}` |
| `parse` | `{"version":1,"status":"ok","ast":{...}}` |
| `term` | `{"version":1,"status":"ok","notation":"ASR(1) · ...","term":{...}}`, see [semantics.md](semantics.md) |
| `run` | `{"version":1,"status":"ok","state":{"X":5,...},"steps":8}` |
| `trace` | `{"version":1,"status":"ok","events":[...]}` |
| `tree --format json` | `{"version":1,"status":"ok","tree":{...}}`, see [visualization.md](visualization.md) |

An AST node is `{"type":"Assign","span":{...},<fields>}`, where each field is a number, a string or a nested
node. Node types: `Program`, `Seq`, `Assign`, `If`, `While`, `Block`, `Skip`, `Var`, `Num`, `BinOp`,
`Compare`, `Or`, `Not`. Spans have the form of the [trace format](trace-format.md); events are described there too.

Errors (any command) have this shape:

```json
{"version":1,"status":"error",
 "error":{"type":"SiplSyntaxError","message":"unexpected ';', expected '(', number, variable",
          "span":{"start":{"line":2,"column":8,"offset":13},"end":{"line":2,"column":9,"offset":14}},
          "expected":["'('","number","variable"]}}
```

| `error.type` | Exit code | Extra fields |
|---|---|---|
| `SiplSyntaxError` | 1 | `span`, `expected` |
| `UndefinedVariableError` | 3 | `span` |
| `StepLimitExceeded` | 3 | `span` |
| `NestingTooDeep` | 3 | none (`parse --json`, `term` or `tree --format json` of a program with about a thousand nested statements) |
| `InputError` | 4 | none |
| `OutputError` | 4 | none (`tree --output` cannot write the file) |

`trace --json` is the exception for runtime errors: it still prints all events, with `status: "error"`
and a final `Failed` event, and exits with 3.

## Notes

- If the reader of standard output closes the pipe (for example `sipl trace ... | head`), the command stops
  quietly with exit code 0.
- `tree` writes text, DOT or SVG as plain text, not JSON; with `--format json` errors are JSON like in the other commands.
- Usage errors are reported by the argument parser on standard error and are never JSON.
