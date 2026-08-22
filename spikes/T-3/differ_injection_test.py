"""T-3 negative control (framing section 5.1) -- can differ.py report a failure AT ALL?

differ.py is the instrument T-3's entire headline comes from, and RECHECK-2026-08-21.md
section 5.1 records that it has never been shown able to fail.  This script pushes
deliberately wrong compilations through the REAL run_case path -- the compiler handle is
swapped, nothing else is touched -- and each injection declares IN ADVANCE the class it
must land in.

Binding rules honoured here:
  * minimum coverage: class 1 (different value), class 2 (value -> null), class 3
    (null -> value), class 4 (PY_RAISE), a NAMED refusal, an UNEXPLAINED raise
    (framing 5.1) -- plus BOTH extra refusal kinds (overflow, underflow), NULLNESS,
    UNCOMPILABLE, and one non-injected AGREE sanity case.
  * if ANY injection is scored as agreement, this script exits 2 and prints REFUSING
    TO REPORT -- hard stop 1 of framing section 8.  No output may be quoted.
  * it runs once PER extra_float_digits setting (env AUTOSQL_EFD), because it doubles
    as proof the new setting plumbing is live on this exact path (framing 5.2 item 3).

--pre-fix skips the XPR01 guard-refusal injection: before step zero the runtime has no
named refusal to provoke (that is the point of step zero).  The pre-fix control still
covers all four wrong-answer classes, a 22003 named refusal, and an unexplained raise.

Usage:  AUTOSQL_SPIKE_DSN=... AUTOSQL_EFD=1 python differ_injection_test.py [--pre-fix]
"""
import os
import sys

sys.dont_write_bytecode = True
FUZZ = "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/analysis/fuzz"
sys.path.insert(0, FUZZ)
os.chdir(FUZZ)   # differ's sibling imports expect this

import differ                      # noqa: E402
from differ import run_case        # noqa: E402

Uncompilable = differ.xcompile.Uncompilable
Compiled = differ.xcompile.Compiled

PRE_FIX = "--pre-fix" in sys.argv

# Each: name, expr src, record, injected sql (or raises), what MUST come out.
INJECTIONS = [
    dict(id="N1", cls="class 1 (different value)",
         src="1 + 2", rec={}, sql="to_jsonb(999::float8)",
         expect_verdict="DIVERGE",
         check=lambda o: o.get("sql_value") in ("999", "999.0") and o.get("python") == "3.0"),
    dict(id="N2", cls="class 2 (value -> null)",
         src="10 - 7", rec={}, sql="NULL::jsonb",
         expect_verdict="DIVERGE",
         check=lambda o: o.get("sql_typeof") == "SQL NULL" and o.get("python") == "3.0"),
    # NOTE: every src below is UNIQUE on purpose -- the injector is keyed by AST repr,
    # and the first version of this control reused "1 + 1"/"1 + 2"/"$.zzz" across
    # injections, so later entries silently overwrote earlier ones.  The control caught
    # its own defect on its first run (out/negctl_prefix.txt); fixed 2026-08-22.
    dict(id="N3", cls="class 3 (null -> value)",
         src="$.zzz", rec={}, sql="to_jsonb(7::float8)",
         expect_verdict="DIVERGE",
         check=lambda o: o.get("python") == "None" and o.get("sql_value") in ("7", "7.0")),
    dict(id="N4", cls="class 4 (PY_RAISE: Python raises, SQL returns a value)",
         src="round($.a, $.b)", rec={"a": 1.5, "b": 400}, sql="to_jsonb(1::float8)",
         expect_verdict="PY_RAISE",
         check=lambda o: "OverflowError" in str(o.get("python_raised"))),
    dict(id="N5", cls="NAMED refusal -- the step-zero guard (SQLSTATE XPR01)",
         src="2 + 2", rec={}, sql="to_jsonb(xpr.f8('1e309'::jsonb))",
         expect_verdict="SQL_REFUSAL", expect_kind="guard",
         skip=PRE_FIX, skip_why="pre-fix runtime has no named refusal yet"),
    dict(id="N6", cls="NAMED refusal -- float8 overflow (22003)",
         src="3 + 3", rec={}, sql="to_jsonb(1e308::float8 * 10::float8)",
         expect_verdict="SQL_REFUSAL", expect_kind="overflow"),
    dict(id="N7", cls="NAMED refusal -- float8 underflow (22003), counted separately",
         src="4 + 4", rec={}, sql="to_jsonb(1e-300::float8 * 1e-300::float8)",
         expect_verdict="SQL_REFUSAL", expect_kind="underflow"),
    dict(id="N8", cls="UNEXPLAINED raise -- must NOT be scored as a refusal",
         src="5 + 5", rec={}, sql="to_jsonb(xpr.no_such_function(1::int))",
         expect_verdict="SQL_RAISE",
         check=lambda o: o.get("refusal_kind") is None),
    dict(id="N9", cls="UNCOMPILABLE (honest gap, never a pass)",
         src="6 + 6", rec={}, raises="INJECTED: deliberate refusal to compile",
         expect_verdict="UNCOMPILABLE"),
    dict(id="N10", cls="NULLNESS (jsonb 'null' where Python has None)",
         src="$.yyy", rec={}, sql="'null'::jsonb",
         expect_verdict="NULLNESS"),
]

_real = differ.xcompile.compile_ast
_by_src = {}


def injecting(ast, *, column="data", ctx_param="ctx"):
    inj = _by_src.get(repr(ast))
    if inj is not None:
        inj["_fired"] = inj.get("_fired", 0) + 1
        if "raises" in inj:
            raise Uncompilable(inj["raises"])
        return Compiled(sql=inj["sql"], params={})
    return _real(ast, column=column, ctx_param=ctx_param)


def main():
    print("=== T-3 negative control: differ.py under deliberate injection ===")
    print("mode: %s" % ("PRE-FIX (no XPR01 yet)" if PRE_FIX else "POST-FIX (full)"))
    active = [i for i in INJECTIONS if not i.get("skip")]
    for inj in active:
        _by_src[repr(differ.expr.parse(inj["src"]))] = inj

    differ.xcompile.compile_ast = injecting
    failures, agreements = [], []
    try:
        for inj in INJECTIONS:
            if inj.get("skip"):
                print("  %-4s SKIPPED (%s)" % (inj["id"], inj["skip_why"]))
                continue
            o = run_case(inj["src"], inj["rec"], None)
            got = o["verdict"]
            ok = got == inj["expect_verdict"]
            if ok and "expect_kind" in inj:
                ok = o.get("refusal_kind") == inj["expect_kind"]
            if ok and "check" in inj:
                ok = bool(inj["check"](o))
            if ok and inj.get("_fired", 0) != 1:
                ok = False
            print("  %-4s %-58s expected %-12s got %-12s kind=%-12s %s"
                  % (inj["id"], inj["cls"][:58], inj["expect_verdict"], got,
                     str(o.get("refusal_kind")), "OK" if ok else "MISMATCH"))
            if not ok:
                failures.append(inj["id"])
            if got == "AGREE":
                agreements.append(inj["id"])
    finally:
        differ.xcompile.compile_ast = _real

    # sanity: the non-injected path still agrees (proves the swap was surgical)
    o = run_case("1 + 2", {}, None)
    print("  SANE non-injected '1 + 2'                                   -> %s (must be AGREE)"
          % o["verdict"])
    if o["verdict"] != "AGREE":
        failures.append("SANE")

    print()
    print("  extra_float_digits requested=%s  session read-back=%s"
          % (differ.EFD, differ.EFD_READBACK))
    if differ.EFD_READBACK != differ.EFD:
        failures.append("EFD")

    if agreements:
        print("\nRESULT: AN INJECTION WAS SCORED AS AGREEMENT: %s" % agreements)
        print("REFUSING TO REPORT.  Hard stop 1 (framing section 8).  Nothing from this")
        print("rig may be quoted until the instrument is fixed and this control restarts.")
        return 2
    if failures:
        print("\nRESULT: control FAILED (wrong class) for: %s -- nothing may be quoted." % failures)
        return 1
    print("\nRESULT: every injected failure landed in its declared class.  The rig can fail.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
