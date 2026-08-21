"""T-1 recheck · Does conformance.py's per-case loop actually EMIT a failing outcome?

WHY THIS EXISTS
---------------
FRAMING.md §8 warned that a harness which scores "did not compile" as a pass would
reproduce, inside the spike, the silent-wrong-answer failure the project exists to
prevent.  FINDINGS.md §5.9(6) then recorded, against the spike, that conformance.py's
23 negative controls never drive the per-case loop: NC11/12/13 call matches() directly
on hand-written SQL, construct no case entry and assert no `outcome`, leaving the
outcome-assignment branches at conformance.py:376-455 exercised by NOTHING.  §5.9(6)'s
own "what would establish it" is: inject a wrong compiler for one fixture case through
the real per-case loop and assert the emitted `outcome` string.

That is what this script does.

HOW IT WORKS
------------
conformance.py is NOT modified.  It is imported by path and its handle on the compiler,
`conformance.proto_compile.compile_ast`, is replaced with a wrapper that behaves exactly
like the real compiler except for a small table of named injections keyed by fixture case
name.  Everything downstream — run_sql(), the WRAPPER statement, matches(), the mutation
probe, the four outcome branches, the counts, the summing assertion and write_report() —
is the real, unmodified harness.

Each injection declares the outcome it MUST provoke.  The script then asserts on the
`outcome` string the harness actually emitted for that case, and on the counts.  It
asserts nothing about the other 126 cases beyond their staying COMPILED_AGREES.

THE FOUR INJECTIONS
-------------------
  I1  add                     -> compiles to a CONSTANT WRONG NUMBER   expect COMPILED_DIVERGES
  I2  precedence_mul_before_add -> raises Uncompilable                 expect DID_NOT_COMPILE
  I3  parens_override         -> compiles to SQL that RAISES (1/0)     expect SQL_ERROR
  I4  divide_by_zero_is_null  -> returns jsonb 'null' where Python has None,
                                 i.e. the values DECODE EQUAL but the representation
                                 contract (compile.py:20-30) is broken               expect COMPILED_DIVERGES
  I5  true_division           -> off by 1e-8, just ABOVE the 1e-9 absolute epsilon  expect COMPILED_DIVERGES
  I6  modulo_pos              -> off by 1e-10, just BELOW it                        expect COMPILED_AGREES

I4 is the interesting one: it is the only wrong-answer injection for which matches()
returns True.  It exists to test the `and not leak` half of the condition at
conformance.py:443.

I5/I6 are a near-miss pair.  I1 (999 vs 3) only shows the rig catches a gross error; a
rig could catch that and still be blind to a small one.  I5/I6 bracket the fixture's own
1e-9 ABSOLUTE tolerance from both sides through the real per-case loop.  I6 expecting
COMPILED_AGREES is not the rig being lenient — 1e-10 is inside the tolerance the fixture
defines, so agreeing is the CORRECT answer, and a rig that failed I6 would be broken in
the other direction.

Target cases were chosen so that none of their expression strings collides with an
out-of-fixture PROBE expression (fixture cases `simple` = "$.a" and `upper` =
"upper($.s)" DO collide and are deliberately not used).  Each injection asserts it fired
exactly once.

NOTHING IS WRITTEN TO proto/.  This script calls conformance.run() directly, never
main(), so proto/results.json and proto/CONFORMANCE.md are untouched.  With
--write-report DIR it renders the harness's own report writer into DIR for inspection.

USAGE
  <venv-python> conformance_injection_test.py                 # run the 4 injections
  <venv-python> conformance_injection_test.py --control       # run with NO injections
  <venv-python> conformance_injection_test.py --write-report /some/dir
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

sys.dont_write_bytecode = True

PROTO = os.path.dirname(os.path.abspath(__file__))
CONF_PATH = os.path.join(PROTO, "conformance.py")

_spec = importlib.util.spec_from_file_location("conformance_under_injection", CONF_PATH)
conf = importlib.util.module_from_spec(_spec)
sys.modules["conformance_under_injection"] = conf
_spec.loader.exec_module(conf)

Compiled = conf.proto_compile.Compiled
Uncompilable = conf.proto_compile.Uncompilable

# --------------------------------------------------------------------------------
# The injections.  `sql` is substituted for the compiler's output; `raises` makes the
# compiler refuse.  `expect` is the outcome the harness MUST emit.
# --------------------------------------------------------------------------------
INJECTIONS = {
    "add": {
        "id": "I1",
        "what": "constant wrong number (999) where Python says 3.0",
        "sql": "to_jsonb(999::float8)",
        "expect": "COMPILED_DIVERGES",
    },
    "precedence_mul_before_add": {
        "id": "I2",
        "what": "compiler refuses: raises Uncompilable",
        "raises": "INJECTED: this construct is not compilable (deliberate)",
        "expect": "DID_NOT_COMPILE",
    },
    "parens_override": {
        "id": "I3",
        "what": "SQL that raises at execution time (integer division by zero)",
        "sql": "to_jsonb((1::int / 0::int))",
        "expect": "SQL_ERROR",
    },
    "divide_by_zero_is_null": {
        "id": "I4",
        "what": "jsonb 'null' where Python has None — decodes EQUAL, breaks the "
                "SQL-NULL representation contract",
        "sql": "'null'::jsonb",
        "expect": "COMPILED_DIVERGES",
    },
    "true_division": {
        "id": "I5",
        "what": "3.50000001 where Python says 3.5 — off by 1e-8, just ABOVE the "
                "1e-9 absolute epsilon",
        "sql": "to_jsonb(3.50000001::float8)",
        "expect": "COMPILED_DIVERGES",
    },
    "modulo_pos": {
        "id": "I6",
        "what": "1.0000000001 where Python says 1.0 — off by 1e-10, just BELOW the "
                "1e-9 absolute epsilon. Agreeing here is CORRECT, not lenient.",
        "sql": "to_jsonb(1.0000000001::float8)",
        "expect": "COMPILED_AGREES",
    },
}

# repr(ast) -> case name, so the wrapper can recognise the target from the AST alone.
_AST_INDEX = {}
for _c in conf.CASES:
    if _c["name"] in INJECTIONS:
        _AST_INDEX[repr(conf.expr.parse(_c["expr"]))] = _c["name"]

_fired = {name: 0 for name in INJECTIONS}
_real_compile_ast = conf.proto_compile.compile_ast


def injecting_compile_ast(ast, *, column="data", ctx_param="ctx"):
    name = _AST_INDEX.get(repr(ast))
    if name is not None:
        inj = INJECTIONS[name]
        _fired[name] += 1
        if "raises" in inj:
            raise Uncompilable(inj["raises"])
        return Compiled(sql=inj["sql"], params={})
    return _real_compile_ast(ast, column=column, ctx_param=ctx_param)


def stray_percent_probe() -> int:
    """The fifth path in the per-case loop: conformance.py:405-408.

    check_placeholders() raises AssertionError on a stray literal `%` in generated SQL.
    Inside run() that is caught at :405, recorded in harness_errors, and RE-RAISED at
    :408 — the run aborts rather than scoring anything.  NC14 tests check_placeholders
    as a component; nothing has ever driven this path through the loop.  This does.

    A PASS here means the harness ABORTS.  Silently scoring would be the failure.
    """
    print("STRAY-% PROBE — conformance.py:405-408, the harness-integrity abort path")
    print("  injecting SQL containing a stray literal '%' for fixture case 'add'")
    print("  REQUIRED behaviour: run() raises AssertionError and produces no result\n")

    target = "add"
    ast_repr = repr(conf.expr.parse(next(c for c in conf.CASES if c["name"] == target)["expr"]))

    def stray(ast, *, column="data", ctx_param="ctx"):
        if repr(ast) == ast_repr:
            return Compiled(sql="to_jsonb((5 % 2)::float8)", params={})
        return _real_compile_ast(ast, column=column, ctx_param=ctx_param)

    conf.proto_compile.compile_ast = stray
    try:
        res = conf.run()
    except AssertionError as exc:
        print(f"  AssertionError raised, as required: {exc}")
        print("\nRESULT: the harness aborted. It cannot score a stray-% case at all.")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"  UNEXPECTED {type(exc).__name__}: {exc}")
        return 1
    print(f"  NO EXCEPTION. totals = {res['totals']}")
    print("\nRESULT: THE HARNESS DID NOT ABORT — it scored a case whose SQL it could "
          "not verify.")
    return 1


def main() -> int:
    if "--stray-percent" in sys.argv:
        return stray_percent_probe()
    control = "--control" in sys.argv
    report_dir = None
    if "--write-report" in sys.argv:
        report_dir = sys.argv[sys.argv.index("--write-report") + 1]

    if not control:
        conf.proto_compile.compile_ast = injecting_compile_ast
        print("INJECTING into the real per-case loop:")
        for name, inj in INJECTIONS.items():
            print(f"  {inj['id']}  case {name!r}")
            print(f"      {inj['what']}")
            print(f"      MUST emit outcome = {inj['expect']}")
    else:
        print("CONTROL RUN — compile_ast is the real one, no injection.")
    print()

    res = conf.run()          # the real harness; writes nothing to disk

    totals = res["totals"]
    by_name = {e["name"]: e for e in res["cases"]}

    print("TOTALS AS EMITTED BY THE HARNESS")
    print(json.dumps(totals, indent=1))
    print()

    failures = []

    if control:
        for name, e in by_name.items():
            if e["outcome"] != "COMPILED_AGREES":
                failures.append(f"control run: {name} emitted {e['outcome']}")
        print(f"control: {totals['compiled_agrees']}/{totals['cases']} COMPILED_AGREES")
    else:
        print("PER-INJECTION — what the harness ACTUALLY emitted")
        print("-" * 74)
        for name, inj in INJECTIONS.items():
            e = by_name[name]
            got = e["outcome"]
            ok = (got == inj["expect"])
            print(f"{inj['id']}  case {name!r}")
            print(f"    expr                 {e['expr']!r}")
            print(f"    python_value         {e['python_value']!r}")
            if "sql_value" in e and e.get("sql") is not None:
                print(f"    sql (injected)       {e.get('sql')!r}")
                print(f"    sql_is_null          {e.get('sql_is_null')}")
                print(f"    sql_jsonb_typeof     {e.get('sql_jsonb_typeof')!r}")
                print(f"    sql_value            {e.get('sql_value')!r}")
                print(f"    mirrored_rule_agrees {e.get('mirrored_rule_agrees')}")
            if e.get("uncompilable_reason"):
                print(f"    uncompilable_reason  {e['uncompilable_reason']!r}")
            if e.get("sql_error"):
                print(f"    sql_error            {e['sql_error']['sqlstate']} "
                      f"{e['sql_error']['message'].splitlines()[0]!r}")
            if e.get("cause_shape"):
                print(f"    cause_shape          {e['cause_shape']!r}")
            if e.get("cause"):
                print(f"    cause                {e['cause']!r}")
            print(f"    injection fired      {_fired[name]} time(s)")
            print(f"    EXPECTED outcome     {inj['expect']}")
            print(f"    EMITTED  outcome     {got}      <-- {'OK' if ok else 'MISMATCH'}")
            print()
            if not ok:
                failures.append(f"{inj['id']} {name}: expected {inj['expect']}, emitted {got}")
            if _fired[name] != 1:
                failures.append(f"{inj['id']} {name}: injection fired {_fired[name]} times, expected 1")

        # Derived from the injection table, not hard-coded.
        expected_counts = {k: 0 for k in conf.OUTCOME_DEFINITIONS}
        for _i in INJECTIONS.values():
            expected_counts[_i["expect"]] += 1
        n_inj_agrees = expected_counts["COMPILED_AGREES"]
        expected_counts["COMPILED_AGREES"] = (
            totals["cases"] - len(INJECTIONS) + n_inj_agrees)
        got_counts = {k: totals[k.lower()] for k in expected_counts}
        print("COUNTS")
        print(f"    expected {expected_counts}")
        print(f"    emitted  {got_counts}")
        if got_counts != expected_counts:
            failures.append(f"counts: expected {expected_counts}, emitted {got_counts}")
        pr = totals["pass_rate"]
        want_pr = expected_counts["COMPILED_AGREES"] / totals["cases"]
        print(f"    pass_rate {totals['compiled_agrees']}/{totals['pass_rate_denominator']} = {pr}")
        if abs(pr - want_pr) > 1e-12:
            failures.append(f"pass_rate: expected {want_pr}, emitted {pr}")
        print()

    if report_dir:
        os.makedirs(report_dir, exist_ok=True)
        res["negative_controls"] = []
        p = os.path.join(report_dir,
                         "CONFORMANCE.control.md" if control else "CONFORMANCE.injected.md")
        conf.write_report(res, p)
        j = os.path.join(report_dir,
                         "results.control.json" if control else "results.injected.json")
        with open(j, "w") as fh:
            json.dump(res, fh, indent=1, default=repr)
        print(f"report written: {p}")
        print(f"results written: {j}")
        print()

    if failures:
        print("RESULT: THE HARNESS DID NOT BEHAVE AS REQUIRED")
        for f in failures:
            print("   " + f)
        return 1
    print("RESULT: every injected failure was emitted as the outcome it should be.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
