"""T-1 battery A_range -- producer for A_range.txt, written by T-3 (2026-08-22).

The output file existed in the record with no script that regenerates it
(EXPERIMENTS.md 1.4 item 5).  This reproduces it: the twenty expression paths that
route (or deliberately do not route) a JSON number through xpr.f8, driven against a
record holding a = 1e300 -- an ordinary finite double.  T-3 also uses it as the
step-zero before/after: before the guard fix, 16 of 20 diverge (8 inside the
restricted subset); after it, the in-subset eight must all be AGREE (stop rule 4).

Usage: AUTOSQL_SPIKE_DSN=... AUTOSQL_EFD=<1|0|-3> python A_range.py
"""
import sys

sys.path.insert(0, '.')
import differ
from differ import run_case, show

V = 1e300
# (expr, record, note, in the 32-construct corrected subset?)
CASES = [
    ("$.a + 0",            {"a": V},                 "arithmetic  (compile.py _t_bin -> xpr.num -> xpr.f8)", True),
    ("$.a * 1",            {"a": V},                 "arithmetic", True),
    ("- $.a",              {"a": V},                 "unary minus", True),
    ("number($.a)",        {"a": V},                 "number()", False),
    ("abs($.a)",           {"a": V},                 "abs()", True),
    ("floor($.a)",         {"a": V},                 "floor()", False),
    ("round($.a)",         {"a": V},                 "round()", False),
    ("string($.a)",        {"a": V},                 "string()  (xpr.str -> xpr.f8 -> ecma_num)", False),
    ("concat($.a)",        {"a": V},                 "concat()  -- yields '' , not the number", False),
    ("$.a < 1e301",        {"a": V},                 "ORDER COMPARISON -- the pushdown-predicate path", True),
    ("$.a > 1",            {"a": V},                 "ORDER COMPARISON", True),
    ("$.a >= $.a",         {"a": V},                 "ORDER COMPARISON, both sides", True),
    ("sum($.l)",           {"l": [V, 1]},            "sum() via xpr.num", False),
    ("max($.l)",           {"l": [V, 1]},            "max()", True),
    ("avg($.l)",           {"l": [V, 1]},            "avg()", False),
    ("count($.l)",         {"l": [V, 1]},            "count() -- does NOT use f8", True),
    ("$.a",                {"a": V},                 "bare field read -- does NOT use f8", True),
    ("$.a == 1e300",       {"a": V},                 "equality -- jsonb IS NOT DISTINCT FROM, no f8", True),
    ("contains($.s, $.a)", {"s": "x1e+300x", "a": V}, "contains() -> xpr.str -> f8", False),
    ("if($.a, 1, 2)",      {"a": V},                 "truthy -- uses ::numeric not f8", True),
]


def main():
    print("=== A_range. xpr.f8 blast radius at a = 1e300 (efd=%s) ===" % differ.EFD)
    n_div = n_div_subset = 0
    for src, rec, note, in_sub in CASES:
        o = run_case(src, rec, None, note=note)
        print("   <%s>  %s  %s" % (o["verdict"], "[SUBSET]" if in_sub else "[  out ]", note))
        show(o)
        if o["verdict"] != "AGREE":
            n_div += 1
            if in_sub:
                n_div_subset += 1
    print()
    print("%d of %d f8-reachable paths diverge at a=1e300; %d of the 12 in-subset paths"
          % (n_div, len(CASES), n_div_subset))
    print("extra_float_digits read-back: %s" % differ.EFD_READBACK)


if __name__ == "__main__":
    main()
