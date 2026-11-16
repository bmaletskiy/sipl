"""Construction of the semantic term of a program: the rules sem_P, sem_S, sem_A, sem_B of the course.

Each case names the course rule it implements. The rules NS_A_Par and NS_B_Par need no code: the AST has
no parentheses.
"""
from __future__ import annotations

from sipl import ast
from sipl.semantics import terms

_ARITHMETIC = {"+": "add", "-": "sub", "*": "mult"}
_COMPARISON = {"=": "eq", ">": "gr"}


def sem_s(stm: ast.Node) -> terms.Term:
    match stm:
        case ast.Assign(target, expr):  # NS_Stm_As
            return terms.Assign(target.name, sem_a(expr))
        case ast.Seq(first, second):  # NS_Stm_Seq
            return terms.Compose(sem_s(first), sem_s(second))
        case ast.If(cond, then, orelse):  # NS_Stm_If
            return terms.If(sem_b(cond), sem_s(then), sem_s(orelse))
        case ast.While(cond, body):  # NS_Stm_Wh
            return terms.While(sem_b(cond), sem_s(body))
        case ast.Block(body):  # NS_Stm_BE: (sem_S(S)), the parentheses are only notation
            return sem_s(body)
        case ast.Skip():  # NS_Stm_skip
            return terms.Identity()
    raise TypeError(f"not a statement: {stm!r}")


def sem_a(exp: ast.Node) -> terms.Term:
    match exp:
        case ast.Num(value):  # NS_A_Num
            return terms.Const(value)
        case ast.Var(name):  # NS_A_Var
            return terms.Deref(name)
        case ast.BinOp(op, left, right):  # NS_A_Add, NS_A_Sub, NS_A_Mult
            return terms.Super(_ARITHMETIC[op], (sem_a(left), sem_a(right)))
    raise TypeError(f"not an arithmetic expression: {exp!r}")


def sem_b(cond: ast.Node) -> terms.Term:
    match cond:
        case ast.Compare(op, left, right):  # NS_B_eq, NS_B_gr
            return terms.Super(_COMPARISON[op], (sem_a(left), sem_a(right)))
        case ast.Or(left, right):  # NS_B_or
            return terms.Super("or", (sem_b(left), sem_b(right)))
        case ast.Not(operand):  # NS_B_neg
            return terms.Super("neg", (sem_b(operand),))
    raise TypeError(f"not a condition: {cond!r}")


def semantic_term(program: ast.Program | ast.Stm) -> terms.Term:
    """sem_P: the semantic term of a program (NS_Prog), or of a single statement."""
    return sem_s(program.body if isinstance(program, ast.Program) else program)
