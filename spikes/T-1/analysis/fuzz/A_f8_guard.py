"""T-1 fuzz seat, battery A -- the xpr.f8 range guard.

runtime.sql:33 (repeated verbatim at :51 inside xpr.num) intends to hold DBL_MAX
but the literal is 297 digits where DBL_MAX needs 309.  It therefore evaluates to
1.797693134862316e+296, not 1.7976931348623157e+308.

A1 measures the literal.  A2 maps every compiled construct that routes a JSON
number through xpr.f8.  A3 bisects the exact boundary against the live database.
"""
import math
import sys

sys.path.insert(0, '.')
import differ
from differ import run_case

LIT = "1" + "7976931348623157" + "0" * (297 - 17)

print("=== A1. the guard literal, measured ===")
with differ.conn().cursor() as cur:
    cur.execute("SELECT length(%(l)s), (%(l)s)::float8", {"l": LIT})
    n, v = cur.fetchone()
print("    digits in the literal : %d" % n)
print("    its float8 value      : %r" % v)
print("    DBL_MAX               : %r  (309 digits)" % 1.7976931348623157e308)
print()

print("=== A2. blast radius at a = 1e300 (an ordinary finite double) ===")
V = 1e300
CASES = [
    ("$.a + 0", {"a": V}, "arithmetic  (compile.py _t_bin -> xpr.num -> xpr.f8)"),
    ("$.a * 1", {"a": V}, "arithmetic"),
    ("- $.a", {"a": V}, "unary minus"),
    ("number($.a)", {"a": V}, "number()"),
    ("abs($.a)", {"a": V}, "abs()"),
    ("floor($.a)", {"a": V}, "floor()"),
    ("round($.a)", {"a": V}, "round()"),
    ("string($.a)", {"a": V}, "string()  (xpr.str -> xpr.f8 -> ecma_num)"),
    ("concat($.a)", {"a": V}, "concat()  -- yields '' , not the number"),
    ("$.a < 1e301", {"a": V}, "ORDER COMPARISON -- the pushdown-predicate path"),
    ("$.a > 1", {"a": V}, "ORDER COMPARISON"),
    ("$.a >= $.a", {"a": V}, "ORDER COMPARISON, both sides"),
    ("sum($.l)", {"l": [V, 1]}, "sum()  -- yields 1, a WRONG NUMBER not a null"),
    ("max($.l)", {"l": [V, 1]}, "max()  -- yields 1"),
    ("avg($.l)", {"l": [V, 1]}, "avg()  -- yields 1"),
    ("count($.l)", {"l": [V, 1]}, "count() -- does NOT use f8"),
    ("$.a", {"a": V}, "bare field read -- does NOT use f8"),
    ("$.a == 1e300", {"a": V}, "equality -- jsonb IS NOT DISTINCT FROM, no f8"),
    ("contains($.s, $.a)", {"s": "x1e+300x", "a": V}, "contains() -> xpr.str -> f8"),
    ("if($.a, 1, 2)", {"a": V}, "truthy -- uses ::numeric, not f8"),
]
n = 0
for src, rec, note in CASES:
    o = run_case(src, rec, None, note=note)
    flag = "" if o["verdict"] == "AGREE" else "  <<<"
    print("   %-12s %-22s py=%-18s sql=%-18s %s%s" % (
        "<" + o["verdict"] + ">", src, o.get("python"), o.get("sql_value"), note, flag))
    if o["verdict"] != "AGREE":
        n += 1
print("\n   %d of %d paths diverge at a = 1e300" % (n, len(CASES)))
print()

print("=== A3. exact boundary, bisected on the live database ===")


def ok(v):
    return run_case("number($.a)", {"a": v})["verdict"] == "AGREE"


lo, hi = 1.0, 1.7976931348623157e308
assert ok(lo) and not ok(hi)
for _ in range(200):
    mid = math.sqrt(lo) * math.sqrt(hi) if hi / lo > 1e10 else (lo + hi) / 2
    if mid == lo or mid == hi:
        break
    if ok(mid):
        lo = mid
    else:
        hi = mid
print("    largest magnitude that still round-trips : %.17e" % lo)
print("    smallest magnitude that is CORRUPTED     : %.17e" % hi)
print("    negative side at -1e300                  : %s" %
      ("AGREE" if ok(-1e300) else "DIVERGES too"))
print("    every finite double with |v| >= %.6e is mishandled -- about 12 of the" % hi)
print("    float8 exponent's 632 decades.")
