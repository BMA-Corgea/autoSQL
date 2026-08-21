"""T-1 fuzz seat, battery B -- float8 overflow AND underflow.

expr.py:640 -- "Never raises for data reasons".  Postgres float8 arithmetic raises
22003 on BOTH overflow and underflow, and a raise aborts the entire query: one bad
row takes the dashboard down for every row.

compile.py KNOWN_DIVERGENCES/float8_overflow_raises records overflow with
guarded:false.  UNDERFLOW is not recorded anywhere.

Note the interaction with battery A: the (buggy) xpr.f8 guard clamps every operand
to <= 1.7976931348623157e296, which accidentally makes `+`, `-` and `sum` unable to
overflow today.  Fixing the guard REMOVES that accident.  The direct-SQL probes at
the bottom show what `+` and `sum` do once the operands are real.
"""
import sys

sys.path.insert(0, '.')
import differ
from differ import run_case

CASES = [
    ("$.a * $.b", {"a": 1e150, "b": 1e160}, "multiply overflow"),
    ("$.qty * $.price", {"qty": 1e200, "price": 1e200}, "the shape a real dashboard writes"),
    ("$.a / $.b", {"a": 1e150, "b": 1e-160}, "divide overflow"),
    ("sum($.l) * sum($.l)", {"l": [1e200]}, "sum then multiply"),
    ("$.a * $.a", {"a": 1e-200}, "multiply UNDERFLOW -- Python 0.0, Postgres RAISES"),
    ("$.a / $.b", {"a": 1e-300, "b": 1e100}, "divide UNDERFLOW"),
    ("round($.a, 20)", {"a": 1.7e296}, "round(): x*10^nd overflows inside xpr.round"),
    ("round($.a, -350)", {"a": 1.0}, "round(x,-350): 10^-350 underflows"),
    ("round($.a, -2)", {"a": 5e-324}, "round(subnormal, -2): scaled underflows"),
    ("$.a + $.a", {"a": 1.5e295}, "add -- cannot overflow while the f8 guard is wrong"),
    ("sum($.l)", {"l": [1.5e295, 1.5e295]}, "sum -- likewise"),
    ("$.a * 0", {"a": 1e-320}, "subnormal * 0 -- control, must not raise"),
    ("days_between($.d, $.e)", {"d": "2024-01-01", "e": "2024-01-02"}, "control"),
]

print("=== B. overflow / underflow through the compiler ===")
raises = 0
for src, rec, note in CASES:
    o = run_case(src, rec, None, note=note)
    flag = "" if o["verdict"] == "AGREE" else "  <<<"
    print("   %-14s %-22s %s%s" % ("<" + o["verdict"] + ">", src, note, flag))
    if o["verdict"] != "AGREE":
        print("                  py=%s%s" % (
            o.get("python"),
            "  RAISED " + str(o.get("python_raised")) if o.get("python_raised") else ""))
        print("                  sql=%s%s" % (
            o.get("sql_value"),
            "  RAISED " + str(o.get("sql_raised")) if o.get("sql_raised") else ""))
    if o["verdict"] in ("SQL_RAISE", "BOTH_RAISE"):
        raises += 1
print("\n   %d of %d probes made Postgres raise\n" % (raises, len(CASES)))

print("=== B2. direct SQL: what + and sum do once the operand guard is correct ===")
for q in ("select 1e308::float8 + 1e308::float8",
          "select sum(v) from (values(1e308::float8),(1e308::float8)) s(v)",
          "select 1e-300::float8 * 1e-300::float8",
          "select 10::float8 ^ 400::float8",
          "select 10::float8 ^ (-350)::float8"):
    try:
        with differ.conn().cursor() as cur:
            cur.execute(q)
            r = repr(cur.fetchone()[0])
    except Exception as e:
        r = "RAISED " + str(e).splitlines()[0]
    print("   %-64s => %s" % (q, r))
