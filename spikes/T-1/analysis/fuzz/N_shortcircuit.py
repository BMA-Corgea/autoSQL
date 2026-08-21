"""T-1 fuzz seat, battery N -- evaluation ORDER.

expr.py:596-598:
    ("and") -> _truthy(left) and _truthy(right)
    ("or")  -> _truthy(left) or  _truthy(right)
Python's `and`/`or` SHORT-CIRCUIT, so the right operand is never evaluated when
the left already decides the answer.

compile.py:252-256 emits `to_jsonb(xpr.truthy(L) AND xpr.truthy(R))`.  SQL's AND
is NOT specified to short-circuit -- Postgres may evaluate either side first, and
the planner is free to reorder.  Since expr is total this cannot change a VALUE,
but Postgres is not total: an operand that raises is skipped by Python and
evaluated by Postgres.

`if()` compiles to CASE (compile.py:338-339), which Postgres DOES evaluate lazily;
that one is tested here as the control.
"""
import sys

sys.path.insert(0, '.')
from differ import run_case

BOOM_MUL = "($.big * $.big)"          # float8 overflow -> Postgres raises
BOOM_UF = "($.tiny * $.tiny)"         # float8 underflow -> Postgres raises
BOOM_IDX = "$.l[3000000000]"          # index literal beyond int4 -> Postgres raises
REC = {"big": 1e200, "tiny": 1e-200, "l": [1, 2, 3], "f": False, "t": True}

CASES = [
    ('false and %s' % BOOM_MUL, "left is false: Python never touches the right"),
    ('$.f and %s' % BOOM_MUL, "same, via a field"),
    ('true or %s' % BOOM_MUL, "left is true: Python never touches the right"),
    ('$.t or %s' % BOOM_MUL, "same, via a field"),
    ('false and %s' % BOOM_UF, "underflow on the skipped side"),
    ('false and %s' % BOOM_IDX, "int4 index overflow on the skipped side"),
    ('if(false, %s, 0)' % BOOM_MUL, "CONTROL: if() compiles to CASE, which IS lazy"),
    ('if(true, 0, %s)' % BOOM_MUL, "CONTROL: the untaken else-branch"),
    ('coalesce($.t, %s)' % BOOM_MUL, "COALESCE: SQL skips it, Python evaluates it (both total)"),
    ('not (false and %s)' % BOOM_MUL, "nested under not()"),
    ('(false and %s) or true' % BOOM_MUL, "nested under or()"),
]

print("=== N. short-circuit vs eager evaluation ===")
print()
n = 0
for src, note in CASES:
    o = run_case(src, REC)
    star = "" if o["verdict"] == "AGREE" else "   <<<"
    print("   %-14s %-46s %s%s" % ("<" + o["verdict"] + ">", src, note, star))
    if o["verdict"] != "AGREE":
        n += 1
        print("                  py=%s   sql=%s%s" % (
            o.get("python"), o.get("sql_value"),
            "  RAISED " + str(o.get("sql_raised")) if o.get("sql_raised") else ""))
print()
print("%d of %d evaluation-order probes diverge" % (n, len(CASES)))
