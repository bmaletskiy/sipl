# Semantic terms

`sipl term` builds the **semantic term** of a program: the expression of the program algebra A_SIPL that
denotes the function the program computes. This is what practical work 2 of the workbook does by hand; here
the AST is translated recursively by the rules `sem_P`, `sem_S`, `sem_A`, `sem_B` of the course.

```
$ sipl term examples/power.sipl
ASR(1) · WH(S²(gr, Y⇒, 0), ASR(S²(mult, R⇒, X⇒)) · ASY(S²(sub, Y⇒, 1)))
```

## Notation

| Term | Meaning |
|---|---|
| `5`, `-1` | constant function |
| `x⇒` | dereference: the value of variable `x` in the state |
| `S²(add, f, g)`, `S¹(neg, f)` | superposition of a basic function (`add`, `sub`, `mult`, `eq`, `gr`, `or`, `neg`) |
| `ASx(f)` | assignment to `x` of the value of `f` |
| `f · g` | sequence: first `f`, then `g` |
| `IF(b, f, g)` | conditional |
| `WH(b, f)` | loop |
| `id` | identity (`skip`) |

`f · g · h` means `(f · g) · h`. A sequence on the right is written with parentheses, `f · (g · h)`: it comes from
a `begin ... end` block, as in the rule NS_Stm_BE.

## Rules

| AST node | Term | Course rule |
|---|---|---|
| `Program` | the term of its body | NS_Prog |
| `Assign x := a` | `ASx(sem_A(a))` | NS_Stm_As |
| `Seq S1 ; S2` | `sem_S(S1) · sem_S(S2)` | NS_Stm_Seq |
| `If` | `IF(sem_B(b), sem_S(S1), sem_S(S2))` | NS_Stm_If |
| `While` | `WH(sem_B(b), sem_S(S))` | NS_Stm_Wh |
| `Block` | the term of its body | NS_Stm_BE |
| `Skip` | `id` | NS_Stm_skip |
| `Num n`, `Var x` | `n`, `x⇒` | NS_A_Num, NS_A_Var |
| `BinOp +`, `-`, `*` | `S²(add\|sub\|mult, ...)` | NS_A_Add, NS_A_Sub, NS_A_Mult |
| `Compare =`, `>` | `S²(eq\|gr, ...)` | NS_B_eq, NS_B_gr |
| `Or`, `Not` | `S²(or, ...)`, `S¹(neg, ...)` | NS_B_or, NS_B_neg |

The rules NS_A_Par and NS_B_Par need no code: the AST has no parentheses.

## How it is checked

- **Course examples.** The term of `examples/gcd.sipl` equals the term in Example 1.3 of the course book, and
  the term of `examples/power.sipl` equals the one in practical work 2 of the workbook.
- **Meaning.** The tests evaluate the terms with the composition formulas of the course (AF_S, AF_AS, AF_SEQ,
  AF_IF, AF_WH, AF_DNM, AF_ID) on the 26 programs of the conformance suite (`conformance/cases/semantics.json`);
  the result must be the expected final state.
- Deliberately broken builders (wrong operator, wrong comparison, swapped sequence) are detected.

## JSON

`sipl term FILE --json` prints `{"version":1,"status":"ok","notation":"...","term":{...}}`. A term is
`{"type": ..., <fields>}`:

| `type` | Fields |
|---|---|
| `Const` | `value` |
| `Deref` | `name` |
| `Super` | `op`, `args` (a list of one or two terms) |
| `Assign` | `name`, `expr` |
| `Compose` | `first`, `second` |
| `If` | `cond`, `then`, `orelse` |
| `While` | `cond`, `body` |
| `Identity` | none |

## Python

```python
from sipl import parse, semantic_term

term = semantic_term(parse(source))
print(term)             # the notation above
print(term.to_dict())   # the JSON form
```

## Limits

A program with about a thousand statements in a row is too deep for the recursive construction. `sipl term`
reports it as `NestingTooDeep` (exit code 3).
