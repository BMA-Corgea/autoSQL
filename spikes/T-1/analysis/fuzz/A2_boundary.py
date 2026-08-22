"""T-1 battery A2 -- producer for A2_boundary.txt, written by T-3 (2026-08-22).

The output existed in the record with no producer (EXPERIMENTS.md 1.4 item 5).
Bisects the exact magnitude where `number($.a)` stops agreeing between the engines,
and names the verdict on the far side.  Pre-fix the boundary was the mistyped
297-digit guard (~1.7977e296, far side DIVERGE value->NULL); post-fix it must sit
at DBL_MAX itself, with the far side only reachable in raw mode (a Python float
cannot exceed DBL_MAX) where the guard now REFUSES by name.

Usage: AUTOSQL_SPIKE_DSN=... AUTOSQL_EFD=<1|0|-3> python A2_boundary.py
"""
import math
import sys

sys.path.insert(0, '.')
import differ
from differ import run_case


def verdict(v):
    return run_case("number($.a)", {"a": v})["verdict"]


def ok(v):
    return verdict(v) == "AGREE"


def main():
    print("=== A2. exact boundary of the xpr.f8 guard, by bisection (efd=%s) ===" % differ.EFD)
    lo, hi = 1.0, 1.7976931348623157e308
    if not ok(lo):
        print("1.0 itself does not agree (verdict %s) -- nothing to bisect at this setting;"
              % verdict(lo))
        print("see the fuzz batteries: at efd 0/-3 the value channel truncates everywhere.")
        return
    if ok(hi):
        print("largest magnitude that still round-trips : %.17e  (= DBL_MAX itself)" % hi)
        print("no CORRUPTED region among py-representable finite doubles at this setting.")
        o = run_case("number($.a)", None, mode="raw", raw='{"a": 1e309}')
        print("first magnitude past DBL_MAX (raw 1e309) : %s%s"
              % (o["verdict"], ":" + str(o.get("refusal_kind")) if o.get("refusal_kind") else ""))
        o = run_case("number($.a)", {"a": -1e300})
        print("negative side at -1e300                  : %s" % o["verdict"])
        return
    for _ in range(200):
        mid = math.sqrt(lo) * math.sqrt(hi) if hi / lo > 1e10 else (lo + hi) / 2
        if mid == lo or mid == hi:
            break
        if ok(mid):
            lo = mid
        else:
            hi = mid
    print("largest magnitude that still round-trips : %.17e" % lo)
    print("smallest that no longer AGREEs           : %.17e  (verdict %s)" % (hi, verdict(hi)))


if __name__ == "__main__":
    main()
