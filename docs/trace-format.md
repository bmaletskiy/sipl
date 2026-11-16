# Trace format (version 1)

`sipl.trace(program, initial)` returns a `Trace`; `trace.to_json()` produces:

```json
{"version": 1, "events": [ {...}, {...} ]}
```

Every event has `event` (its type), `step` (interpreter step counter when it was emitted) and
`span` (the source fragment it refers to):

```json
"span": {"start": {"line": 1, "column": 7, "offset": 6}, "end": {"line": 1, "column": 13, "offset": 12}}
```

Lines and columns are 1-based, offsets are 0-based, `end` is exclusive. The state is a JSON object
`{"variable": integer}`; a variable that is not present is undefined.

| `event` | Extra fields | Meaning |
|---|---|---|
| `BeforeStatement` | `statement`, `state` | an `assign`, `skip`, `if` or `while` statement starts; `state` is the state before it |
| `AfterStatement` | `statement`, `state` | the same statement finished; `state` is the state after it |
| `VariableChanged` | `name`, `old`, `new` | an assignment was performed; `old` is `null` if the variable was undefined |
| `ConditionEvaluated` | `statement`, `value`, `state` | the condition of an `if` or `while` was checked; `span` is the condition |
| `Finished` | `state` | normal termination; `span` is the whole program |
| `Failed` | `error`, `message` | abnormal termination (`UndefinedVariableError`, `StepLimitExceeded`); `span` is the failing fragment |

Rules:

- A trace always ends with exactly one `Finished` or `Failed` event.
- `;` and `begin ... end` produce no events.
- `BeforeStatement` / `AfterStatement` are properly nested, like brackets. For `while`, they are emitted
  once per statement, and every condition check (including the last, false one) is a
  `ConditionEvaluated` event.
- Runtime errors do not raise in `trace()`: they end the trace with `Failed`. `run(..., observer=f)`
  gives the same events to `f` and still raises the error.
