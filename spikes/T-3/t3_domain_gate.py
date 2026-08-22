"""T-3 input-domain gate (framing section 5.3) -- both halves, with printed witnesses.

Half one: the class-4 emptiness demonstration.  All eight catalogued Python raise sites
need constructs outside the subset; the fuzz batteries verify that mechanically per
expression.  Here the remaining obligations run: infinity composed from PERMITTED
arithmetic with confirmation nothing downstream raises in Python, and the adversarial
raw-JSON probes that hunt for an UNCATALOGUED raise site.

Half two: every magnitude row of the 5.3 table gets a direct witness case here, in
py mode where a Python float can carry it and in RAW mode (JSON text -> ::jsonb; the
shape of a row written by anything that is not this Python process) where it cannot.
Rows the batteries already reached are re-witnessed so this table stands alone.

Usage: AUTOSQL_SPIKE_DSN=... AUTOSQL_EFD=<1|0|-3> python t3_domain_gate.py
"""
import json
import sys

sys.dont_write_bytecode = True
FUZZ = "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/analysis/fuzz"
sys.path.insert(0, FUZZ)
import os
os.chdir(FUZZ)

import differ                    # noqa: E402
from differ import run_case      # noqa: E402


def rc(src, rec=None, ctx=None, mode="py", raw=None, note=""):
    o = run_case(src, rec, ctx, mode=mode, raw=raw, note=note)
    tag = o["verdict"]
    kind = o.get("refusal_kind")
    print("  [%s%s] %-34s %s" % (tag, ":" + kind if kind else "", src,
                                 ("rec=" + json.dumps(rec, ensure_ascii=False)[:60]) if mode == "py"
                                 else ("raw=" + str(raw)[:60])))
    print("      py=%s%s  sql=%s%s" % (
        o.get("python"),
        " RAISED " + str(o["python_raised"]) if o.get("python_raised") else "",
        o.get("sql_value") if o.get("sql_value") is not None else "None",
        " RAISED " + str(o["sql_raised"]) if o.get("sql_raised") else ""))
    return o


def main():
    print("=== T-3 domain gate  (efd requested=%s) ===" % differ.EFD)

    print("\n-- HALF ONE (a): infinity composed from permitted arithmetic; Python must not raise --")
    o1 = rc("$.a * $.b", {"a": 1e200, "b": 1e200})
    o2 = rc("abs(($.a * $.b))", {"a": 1e200, "b": 1e200})
    o3 = rc("(($.a * $.b) > 0)", {"a": 1e200, "b": 1e200})
    o4 = rc("min(($.a * $.b), 1)", {"a": 1e200, "b": 1e200})
    o5 = rc("if(($.a * $.b), 1, 2)", {"a": 1e200, "b": 1e200})
    py_raises = [o for o in (o1, o2, o3, o4, o5) if o.get("python_raised")]
    print("  => Python raised in %d of 5 composed-infinity cases%s" % (
        len(py_raises), " -- NO ninth raise site on this path" if not py_raises else
        " -- NINTH RAISE SITE, see below"))

    print("\n-- HALF ONE (b): hunting an uncatalogued raise site in RAW JSON (non-Python writers) --")
    huge_int = "1" + "0" * 400          # a full-digit JSON integer; Python json keeps it int
    rc("$.a == 1", mode="raw", raw='{"a": %s}' % huge_int,
       note="Python _eq -> float(10**400) ...")
    rc("$.a > 1", mode="raw", raw='{"a": %s}' % huge_int)
    rc("$.a != 3", mode="raw", raw='{"a": %s}' % huge_int)
    rc("count($.a)", mode="raw", raw='{"a": %s}' % huge_int)

    print("\n-- HALF TWO: the 5.3 magnitude rows, one direct witness each --")
    print("row: old guard boundary, both sides (py mode)")
    rc("$.a + 0", {"a": 1.79769313486231551e296})
    rc("$.a + 0", {"a": 1.79769313486231587e296})
    print("row: real limit, below and AT (py mode)")
    rc("$.a + 0", {"a": 1.7976931348623155e308})
    rc("$.a + 0", {"a": 1.7976931348623157e308})
    print("row: real limit, ABOVE (raw mode only -- no Python float can carry it)")
    rc("$.a + 0", mode="raw", raw='{"a": 1e309}')
    rc("$.a", mode="raw", raw='{"a": 1e309}', note="bare read, no xpr function involved")
    rc("$.a > 1", mode="raw", raw='{"a": 1e309}', note="the pushdown-predicate path")
    rc("abs($.a)", mode="raw", raw='{"a": 1e400}')
    print("row: infinity composed by arithmetic -- half one (a) above")
    print("row: subnormals (py mode, then raw where Python underflows at parse)")
    rc("$.a + 0", {"a": 5e-324})
    rc("$.a + 0", {"a": 1e-320})
    rc("$.a + 0", mode="raw", raw='{"a": 1e-400}', note="Python json -> 0.0; jsonb keeps 1e-400")
    rc("if($.a, 1, 2)", mode="raw", raw='{"a": 1e-400}', note="framing 5.3: xpr.truthy vs Python falsy")
    rc("$.a == 0", mode="raw", raw='{"a": 1e-400}')
    print("row: 2**53 boundary (py mode, then raw exact-integer text)")
    rc("$.a + 0", {"a": 2.0 ** 53})
    rc("$.a + 0", {"a": 2.0 ** 53 + 2})
    rc("$.a == 9007199254740992", mode="raw", raw='{"a": 9007199254740993}',
       note="Python float() collapses ...993 to ...992; jsonb numeric keeps it exact")
    print("row: 0.0 and -0.0 (py mode)")
    rc("$.a + 0", {"a": 0.0})
    rc("$.a + 0", {"a": -0.0})
    rc("$.a == 0", {"a": -0.0})
    rc("if($.a, 1, 2)", {"a": -0.0})
    print("row: numeric strings that coerce (py mode; D.6's tolerant-coercion class)")
    rc("$.a + 0", {"a": " 7 "})
    rc("$.a + 0", {"a": "1e3"})
    rc("$.a + 0", {"a": "１２３"}, note="full-width digits: Python \\d matches, SQL [0-9] does not")
    rc("max($.a, 1)", {"a": "١٢٣"}, note="Arabic-Indic digits, same gate")

    print("\n  extra_float_digits read-back: %s" % differ.EFD_READBACK)


if __name__ == "__main__":
    main()
