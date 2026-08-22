"""T-1 battery B2 -- producer for B2_overflow.txt, written by T-3 (2026-08-22).

The output existed in the record with no producer (EXPERIMENTS.md 1.4 item 5).
Overflow AND underflow probes, corrected: pre-fix the mistyped guard clamped
operands to ~1.8e296 so + - and sum() could not overflow; post-fix the operands
come through whole, and every overflow/underflow is a NAMED 22003 refusal.
Underflow is counted separately (framing 4.7): it needs a product below the
smallest double, not a value near DBL_MAX, and nobody has measured its rate.

Usage: AUTOSQL_SPIKE_DSN=... AUTOSQL_EFD=<1|0|-3> python B2_overflow.py
"""
import sys

sys.path.insert(0, '.')
import differ
from differ import run_case, show

CASES = [
    ("$.a * $.b", {"a": 1e150, "b": 1e160}, "multiply: smallest realistic overflow"),
    ("$.a / $.b", {"a": 1e150, "b": 1e-160}, "divide"),
    ("$.qty * $.price", {"qty": 1e200, "price": 1e200}, "the shape a real dashboard writes"),
    ("($.a + $.b)", {"a": 1.7976931348623157e308, "b": 1.7976931348623157e308},
     "ADDITION overflow -- impossible pre-fix, possible now that operands come through"),
    ("- ($.a + $.a)", {"a": 1.7976931348623157e308}, "negated addition overflow"),
    ("max($.l) * 10", {"l": [1.7976931348623157e308, 1]}, "aggregate feeding overflow"),
    ("$.a * $.a", {"a": 1e-200}, "multiply UNDERflow"),
    ("$.a / $.b", {"a": 1e-300, "b": 1e100}, "divide underflow"),
    ("$.a * 0", {"a": 1e-320}, "subnormal * 0 -- exact zero, no underflow raise"),
    ("$.a + $.a", {"a": 5e-324}, "smallest subnormal doubled -- exact, fine"),
    ("$.a * $.b", {"a": 2e-162, "b": 2e-162}, "underflow just past the subnormal floor"),
    ("if(($.a * $.a), 1, 2)", {"a": 1e-200}, "underflow inside a FILTER-shaped truthy"),
    ("count($.l)", {"l": [1e300, 1e-300]}, "count never touches f8 -- control"),
]


def main():
    print("=== B2. overflow and underflow, post-step-zero (efd=%s) ===" % differ.EFD)
    kinds = {}
    for src, rec, note in CASES:
        o = run_case(src, rec, None, note=note)
        k = o.get("refusal_kind")
        kinds[k] = kinds.get(k, 0) + 1
        print("   <%s%s>  %s" % (o["verdict"], ":" + k if k else "", note))
        show(o)
    print()
    print("refusal kinds histogram: %s" % kinds)
    print("extra_float_digits read-back: %s" % differ.EFD_READBACK)


if __name__ == "__main__":
    main()
