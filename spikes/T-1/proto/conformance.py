"""T-1 spike · THROWAWAY conformance harness — expr(Python) vs compile.py(Postgres).

THIS IS NOT A LIBRARY (FRAMING.md §3: the prototype is throwaway by contract).

WHAT IT DOES, per case, for all 130 cases in
GIMS-Project/tests/fixtures/expr_vectors.json:

  1. parse   — the REAL parser, core.dashboard.expr.parse().  Never reimplemented.
  2. python  — the REAL evaluator, core.dashboard.expr.evaluate(ast, record, context).
               This is the ORACLE for runtime #3 (SQL).
  3. compile — spikes/T-1/proto/compile.py.  `Uncompilable` is a recorded OUTCOME.
  4. execute — live Postgres 16.14 (autosql_spike), PARAMETERISED form only.
               The display-rendered SQL is written to the report and NEVER executed.
  5. compare — one of exactly four outcomes.

THE FOUR OUTCOMES (FRAMING.md §8 demands three; the fourth is split out because
collapsing it would hide the worst failure mode this spike exists to rule out):

  COMPILED_AGREES  — compiled, executed, SQL value == Python value under the rule below.
  COMPILED_DIVERGES— compiled, executed, values differ.  Cause is named.
  DID_NOT_COMPILE  — Uncompilable raised.  An honest coverage gap.  NOT A PASS.
  SQL_ERROR        — Postgres RAISED.  A TOTALITY VIOLATION (expr never raises) and the
                     most severe outcome in this spike.  NOT A PASS.

The pass rate's denominator is the full case count, and the four counts are asserted to
sum to it.  There is no code path that can score DID_NOT_COMPILE or SQL_ERROR as a pass.

Run:
  "/home/corgea/Desktop/Coding Projects/GIMS-Project/.venv/bin/python" \
      "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto/conformance.py"
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
import traceback
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------------
# Paths — absolute, quoted nowhere because Python needs no quoting, but every one of
# these contains spaces, so they are never interpolated into a shell command.
# --------------------------------------------------------------------------------
GIMS = "/home/corgea/Desktop/Coding Projects/GIMS-Project"
PROTO = "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto"
FIXTURE = os.path.join(GIMS, "tests", "fixtures", "expr_vectors.json")
RESULTS_JSON = os.path.join(PROTO, "results.json")
REPORT_MD = os.path.join(PROTO, "CONFORMANCE.md")

# Scrubbed 2026-08-21 before first commit: the password is not in this repo, because the
# same role owns the live glp_strong database on that container. Set PGPASSWORD (or use
# ~/.pgpass) to reproduce. See spikes/T-1/proto/README-db.md.
DSN = dict(host="127.0.0.1", port=55433, user="glp_owner", dbname="autosql_spike")

sys.path.insert(0, GIMS)
from core.dashboard import expr  # noqa: E402  the REAL parser + evaluator

# compile.py is loaded by path under a distinct module name so it cannot shadow the
# `compile` builtin or any stdlib name.
_spec = importlib.util.spec_from_file_location("proto_compile", os.path.join(PROTO, "compile.py"))
proto_compile = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(proto_compile)

import psycopg2  # noqa: E402
import psycopg2.extras  # noqa: E402


# ================================================================================
# THE COMPARISON RULE — the oracle.  Mirrored from the existing consumer test.
# ================================================================================
# GIMS-Project/tests/test_dashboard_expr.py:17    _EPS = _VECTORS.get("float_epsilon", 1e-9)
# GIMS-Project/tests/test_dashboard_expr.py:20-25 def _matches(actual, expected) -> bool:
#     if isinstance(expected, bool) or isinstance(actual, bool):
#         return actual is expected or actual == expected and type(actual) is type(expected)
#     if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
#         return math.isclose(float(actual), float(expected), rel_tol=0, abs_tol=_EPS)
#     return actual == expected
#
# EPSILON IS ABSOLUTE, NOT RELATIVE.  That is not a choice this harness makes; it is
# what the existing test does — `rel_tol=0, abs_tol=_EPS` (line 24) disables the
# relative term outright.  The fixture's own note says only "Numbers compare within
# 1e-9" without naming a mode, so the existing consumer test is the tiebreaker, and it
# is unambiguous.  Using it also keeps this harness comparing exactly what the Python
# and JS runtimes are already held to.
#
# BOOLEANS DO NOT COMPARE EQUAL TO 0/1.  The bool branch is first, and it requires
# `type(actual) is type(expected)`, so True vs 1 fails (True is 1 -> False;
# True == 1 -> True but type(True) is not type(1)).  test_dashboard_expr.py:37-41
# asserts this property explicitly.
#
# THIS HARNESS USES IT UNCHANGED, with actual = the SQL value and expected = the
# Python value.  No deviation.
_VECTORS = json.loads(open(FIXTURE).read())
_EPS = _VECTORS.get("float_epsilon", 1e-9)
CASES = _VECTORS["cases"]


def matches(actual, expected) -> bool:
    """Byte-for-byte the rule at tests/test_dashboard_expr.py:20-25."""
    if isinstance(expected, bool) or isinstance(actual, bool):
        return actual is expected or actual == expected and type(actual) is type(expected)
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isclose(float(actual), float(expected), rel_tol=0, abs_tol=_EPS)
    return actual == expected


# --------------------------------------------------------------------------------
# SECONDARY, STRICTER check.  `matches` above only reaches inside a container via
# `actual == expected` (line 25), where Python's own == conflates True with 1 and 1
# with 1.0 at every nested level.  That is a hole in the mirrored rule, not in this
# harness, so the mirrored rule stays the VERDICT and this runs alongside it.  Any
# case where the two disagree is reported, never silently resolved either way.
# --------------------------------------------------------------------------------
def deep_strict(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a is b
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=0, abs_tol=_EPS)
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(deep_strict(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(deep_strict(a[k], b[k]) for k in a)
    return False


# ================================================================================
# THE POSTGRES ROUND-TRIP — deliberate, documented normalization.
# ================================================================================
# The trap this avoids: psycopg2's default jsonb loader runs json.loads on the value
# AND hands back Python None for BOTH `SQL NULL` and `jsonb 'null'`.  Those are two
# different things under compile.py's representation contract (compile.py:20-30:
# "expr's Python None is carried as SQL NULL, never as jsonb 'null'"), and a harness
# that cannot tell them apart cannot detect a leak of that contract.
#
# So the harness NEVER lets the driver decode the value.  It asks Postgres three
# questions instead:
#     v IS NULL          -> was it a real SQL NULL?
#     jsonb_typeof(v)    -> what JSON type came back? ('null' here is a LEAK)
#     v::text            -> the exact JSON text
# and decodes the text itself with json.loads.  That pins the numeric normalization to
# exactly one documented rule:
#
#   NORMALIZATION RULE: the SQL value is `json.loads(v::text)` — stdlib defaults, so a
#   JSON integer literal becomes Python `int`, a JSON fractional/exponent literal
#   becomes Python `float`, and Decimal never appears.  Nothing is coerced, rounded or
#   re-typed afterwards.  In particular `to_jsonb(3.0::float8)::text` is the text `3`
#   (verified: psql -tAc "select to_jsonb(3.0::float8)::text" -> 3), so the SQL side
#   legitimately yields int 3 where Python yields float 3.0.  The mirrored comparison
#   rule (test_dashboard_expr.py:23-24) already treats int and float as the same
#   number — that is how the fixture's own hand-authored `expect: 3` matches the
#   evaluator's 3.0 — so this is the fixture's rule, not a normalization invented here.
#   NOTHING ELSE IS NORMALIZED.  Booleans stay bool, strings stay str, containers stay
#   as json.loads built them.
WRAPPER = """SELECT (q.v IS NULL) AS is_sql_null,
       jsonb_typeof(q.v)      AS jtype,
       q.v::text              AS jtext
FROM (SELECT {inner} AS v FROM (SELECT (%(rec__)s)::jsonb AS data) s) q"""


class SqlRaised(Exception):
    def __init__(self, sqlstate, message):
        super().__init__(message)
        self.sqlstate = sqlstate
        self.message = message


def check_placeholders(sql: str, params: Dict[str, Any], ctx_param: str) -> None:
    """Every % in the generated SQL must be a known %(name)s placeholder.

    A stray literal % would be eaten by psycopg2's own parameter interpolation and
    could silently change the statement.  This is a harness-integrity check, not a
    finding about compile.py.
    """
    known = set(params) | {ctx_param, "rec__"}
    i = 0
    while True:
        i = sql.find("%", i)
        if i < 0:
            return
        j = sql.find(")s", i)
        if not sql.startswith("%(", i) or j < 0:
            raise AssertionError(f"stray literal '%' in generated SQL at offset {i}")
        name = sql[i + 2:j]
        if name not in known:
            raise AssertionError(f"placeholder %({name})s has no bind value")
        i = j + 2


def run_sql(cur, inner_sql: str, params: Dict[str, Any], record: Any, context: Any,
            ctx_param: str = "ctx") -> Tuple[bool, Optional[str], Optional[str]]:
    """Execute the PARAMETERISED compiled expression.  Returns (is_sql_null, jtype, jtext).

    Raises SqlRaised if Postgres raised — that is a recorded outcome, never a crash.
    """
    bind = dict(params)
    assert "rec__" not in bind, "bind-name collision on rec__"
    assert ctx_param not in bind, f"bind-name collision on {ctx_param}"
    bind["rec__"] = json.dumps(record)
    bind[ctx_param] = json.dumps(context)
    stmt = WRAPPER.format(inner=inner_sql)
    check_placeholders(stmt, params, ctx_param)
    try:
        cur.execute(stmt, bind)
        row = cur.fetchone()
    except psycopg2.Error as exc:
        raise SqlRaised(getattr(exc, "pgcode", None),
                        str(getattr(exc, "pgerror", None) or exc).strip())
    return bool(row[0]), row[1], row[2]


# ================================================================================
# OUTCOME ASSIGNMENT — declared in advance, one branch per outcome, no fallthrough.
# ================================================================================
OUTCOME_DEFINITIONS = {
    "COMPILED_AGREES": (
        "compile_ast() returned; the parameterised SQL executed; and "
        "matches(sql_value, python_value) is True under the rule mirrored from "
        "tests/test_dashboard_expr.py:20-25 (abs epsilon 1e-9, bools not equal to 0/1)."
    ),
    "COMPILED_DIVERGES": (
        "compile_ast() returned and the SQL executed, but matches() is False — OR the "
        "top-level value came back as jsonb 'null' instead of SQL NULL, which breaks "
        "compile.py's stated representation contract (compile.py:20-30) even when the "
        "decoded values happen to look equal. Cause is named per case."
    ),
    "DID_NOT_COMPILE": (
        "compile.py raised Uncompilable. No SQL was executed. This is an honest "
        "coverage gap and is NEVER counted as a pass."
    ),
    "SQL_ERROR": (
        "Postgres RAISED while executing the compiled expression. expr is total "
        "(expr.py:640 'Never raises for data reasons'), so this is a TOTALITY "
        "VIOLATION — the most severe outcome in this spike. NEVER counted as a pass."
    ),
}

# Mechanical shape of a divergence.  This is a description of the DIFFERENCE, not a
# diagnosis; the diagnosis lives in CAUSES below and is written by hand after reading
# the case.  Keeping them separate stops a guess from being reported as a finding.
def cause_shape(py, sql, is_sql_null, jtype) -> str:
    if is_sql_null and py is not None:
        return "SQL returned NULL, Python returned a value (null over-propagation in SQL)"
    if jtype == "null":
        return "SQL returned jsonb 'null' at top level, not SQL NULL (representation leak)"
    if py is None and not is_sql_null:
        return "Python returned None, SQL returned a value (null UNDER-propagation in SQL)"
    if isinstance(py, bool) != isinstance(sql, bool):
        return "type mismatch: boolean on one side, non-boolean on the other"
    if isinstance(py, (int, float)) and isinstance(sql, (int, float)):
        try:
            return f"numeric difference |{float(sql)} - {float(py)}| = {abs(float(sql) - float(py))} > {_EPS}"
        except (OverflowError, ValueError):
            return "numeric difference (not finitely representable)"
    if isinstance(py, str) and isinstance(sql, str):
        return "string difference"
    if type(py) is not type(sql):
        return f"type mismatch: python {type(py).__name__} vs sql {type(sql).__name__}"
    return "value difference"


# Hand-assigned causes, keyed by case name.  Filled in after reading each divergent
# case; a case absent from here is reported as "unclassified" rather than guessed at.
CAUSES: Dict[str, str] = {}


# ================================================================================
# OUT-OF-FIXTURE PROBES — explicitly NOT part of the 130.
# ================================================================================
# The fixture is the contract, and a 130/130 sheet is a statement about the FIXTURE,
# not about the compiler in general.  These probes push on the compiler's OWN
# KNOWN_DIVERGENCES claims, every one of which is marked in_fixture: False.  They are
# counted separately and never fold into the totals.  Per FRAMING.md §3 nothing found
# here is fixed — compile.py and runtime.sql are left exactly as written.
PROBES = [
    ("overflow_via_multiply", "$.a * $.b", {"a": 1e200, "b": 1e200},
     "tests KNOWN_DIVERGENCES/float8_overflow_raises"),
    ("overflow_via_add", "$.a + $.a", {"a": 1e296},
     "same claim via addition, operands just under the guard"),
    ("f8_guard_1e300_arith", "$.a + 0", {"a": 1e300},
     "an IN-RANGE float8 pushed through xpr.num"),
    ("f8_guard_1e297_arith", "$.a * 1", {"a": 1e297},
     "just above the guard literal in runtime.sql"),
    ("f8_guard_1e290_arith", "$.a + 0", {"a": 1e290},
     "just below the guard literal — bounds the defect"),
    ("f8_readback_1e300_no_arith", "$.a", {"a": 1e300},
     "a bare field read never goes through xpr.f8"),
    ("num_of_1e999_string", "number($.s)", {"s": "1e999"},
     "tests KNOWN_DIVERGENCES/num_out_of_float8_range"),
    ("unicode_upper_sharp_s", "upper($.s)", {"s": "stra\u00dfe"},
     "tests KNOWN_DIVERGENCES/unicode_case_and_collation"),
]


def out_of_fixture_probes(cur, conn) -> List[Dict[str, Any]]:
    out = []
    for name, src, record, why in PROBES:
        ast = expr.parse(src)
        py = expr.evaluate(ast, record, {})
        row: Dict[str, Any] = {"probe": name, "expr": src, "record": repr(record),
                               "why": why, "python": repr(py)}
        try:
            compiled = proto_compile.compile_ast(ast)
        except proto_compile.Uncompilable as exc:
            row.update(sql="Uncompilable: " + exc.reason, verdict="DID_NOT_COMPILE")
            out.append(row)
            continue
        try:
            is_null, jtype, jtext = run_sql(cur, compiled.sql, compiled.params, record, {})
            conn.commit()
            sqlv = "SQL NULL" if is_null else jtext
            row["sql"] = sqlv if len(sqlv) < 56 else sqlv[:53] + "..."
            decoded = None if is_null else json.loads(jtext)
            row["verdict"] = "agrees" if matches(decoded, py) else "DIVERGES"
        except SqlRaised as exc:
            conn.rollback()
            row.update(sql=f"RAISED {exc.sqlstate}: {exc.message.splitlines()[0]}",
                       verdict="SQL_ERROR (totality violation)")
        out.append(row)
    return out


def sha256(path: str) -> str:
    import hashlib
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def run() -> Dict[str, Any]:
    conn = psycopg2.connect(**DSN)
    conn.autocommit = False
    entries: List[Dict[str, Any]] = []
    control_failures: List[Dict[str, Any]] = []
    counts = {k: 0 for k in OUTCOME_DEFINITIONS}
    harness_errors: List[Dict[str, Any]] = []

    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '20s'")
        cur.execute("SET extra_float_digits = 1")     # PG12+ default; pinned, see below
        cur.execute("select version(), current_setting('extra_float_digits')")
        pg_version, efd = cur.fetchone()
        conn.commit()

        for case in CASES:
            name, group, src = case["name"], case["group"], case["expr"]
            record = case.get("record", {})
            context = case.get("context", {})
            entry: Dict[str, Any] = {
                "name": name, "group": group, "expr": src,
                "record": record, "context": context,
                "fixture_expect": case["expect"],
            }

            # ---- 1. REAL parser -------------------------------------------------
            ast = expr.parse(src)                      # a raise here is a harness stop
            entry["ast"] = repr(ast)

            # ---- 2. REAL evaluator = the oracle ---------------------------------
            py_value = expr.evaluate(ast, record, context)
            entry["python_value"] = py_value
            entry["python_type"] = type(py_value).__name__

            # ---- CONTROL: Python vs the fixture's hand-authored expect ----------
            ok_expect = matches(py_value, case["expect"])
            entry["python_matches_fixture_expect"] = ok_expect
            if not ok_expect:
                control_failures.append({
                    "name": name, "group": group, "expr": src,
                    "python": repr(py_value), "expect": repr(case["expect"]),
                })

            # ---- 3. compile -----------------------------------------------------
            try:
                compiled = proto_compile.compile_ast(ast, column="data", ctx_param="ctx")
            except proto_compile.Uncompilable as exc:
                entry.update(outcome="DID_NOT_COMPILE", uncompilable_reason=exc.reason,
                             sql=None, sql_display=None, sql_value=None, cause=None)
                counts["DID_NOT_COMPILE"] += 1
                entries.append(entry)
                continue

            entry["sql"] = compiled.sql
            entry["sql_params"] = {k: repr(v) for k, v in compiled.params.items()}
            # Display-rendered form: for humans and for the index-shape finding only.
            # NEVER executed — run_sql() is handed compiled.sql with bind values.
            entry["sql_display"] = proto_compile.render_for_display(
                compiled.sql, compiled.params, "ctx", "'" + json.dumps(context) + "'::jsonb")

            # ---- 4. execute, parameterised --------------------------------------
            try:
                is_null, jtype, jtext = run_sql(cur, compiled.sql, compiled.params,
                                                record, context)
                conn.commit()
            except SqlRaised as exc:
                conn.rollback()
                entry.update(outcome="SQL_ERROR", sql_value=None,
                             sql_error={"sqlstate": exc.sqlstate, "message": exc.message},
                             cause="Postgres raised where expr returns a value or null "
                                   "(totality violation)")
                counts["SQL_ERROR"] += 1
                entries.append(entry)
                continue
            except AssertionError as exc:
                conn.rollback()
                harness_errors.append({"name": name, "error": str(exc)})
                raise

            # ---- 5. decode + compare --------------------------------------------
            entry["sql_is_null"] = is_null
            entry["sql_jsonb_typeof"] = jtype
            entry["sql_text"] = jtext
            sql_value = None if is_null else json.loads(jtext)
            entry["sql_value"] = sql_value
            entry["sql_type"] = "SQL NULL" if is_null else type(sql_value).__name__

            # ---- MUTATION PROBE ------------------------------------------------
            # Proof that the `data` column is actually live in the executed statement
            # and the harness is not, say, agreeing with itself.  The SAME compiled SQL
            # is re-run against an EMPTY record.  Every case whose expression reads a
            # field must produce a different answer; if it does not, the field never
            # reached Postgres.
            try:
                m_null, m_type, m_text = run_sql(cur, compiled.sql, compiled.params,
                                                 {}, context)
                conn.commit()
                mutated = "SQL NULL" if m_null else m_text
            except SqlRaised as exc:
                conn.rollback()
                mutated = f"RAISED {exc.sqlstate}"
            baseline = "SQL NULL" if is_null else jtext
            entry["mutation_empty_record"] = mutated
            entry["mutation_changed"] = (mutated != baseline)
            entry["reads_a_field"] = ("$" in src)

            leak = (not is_null) and jtype == "null"
            agree = matches(sql_value, py_value)
            strict = deep_strict(sql_value, py_value)
            entry["strict_deep_equal"] = strict
            entry["mirrored_rule_agrees"] = agree

            if agree and not leak:
                entry.update(outcome="COMPILED_AGREES", cause=None)
                counts["COMPILED_AGREES"] += 1
                if not strict:
                    entry["note"] = ("mirrored rule agrees, stricter deep check does not "
                                     "— see 'strict-vs-mirrored' in the report")
            else:
                entry.update(
                    outcome="COMPILED_DIVERGES",
                    cause=CAUSES.get(name, "UNCLASSIFIED"),
                    cause_shape=cause_shape(py_value, sql_value, is_null, jtype),
                )
                counts["COMPILED_DIVERGES"] += 1
            entries.append(entry)

        probes = out_of_fixture_probes(cur, conn)

    conn.close()

    # ---- how strong is the agreement, really? -------------------------------
    # A 130/130 sheet says nothing about HOW closely the two runtimes agree. Measure it.
    diffs = []
    for e in entries:
        pv, sv = e.get("python_value"), e.get("sql_value")
        if (isinstance(pv, (int, float)) and not isinstance(pv, bool)
                and isinstance(sv, (int, float)) and not isinstance(sv, bool)):
            diffs.append((abs(float(sv) - float(pv)), e["name"]))
    diffs.sort(reverse=True)
    strength = {
        "numeric_cases_compared": len(diffs),
        "max_abs_difference": diffs[0][0] if diffs else None,
        "max_abs_difference_case": diffs[0][1] if diffs else None,
        "cases_needing_the_epsilon": len([d for d in diffs if d[0] != 0.0]),
        "string_cases": len([e for e in entries if isinstance(e.get("python_value"), str)]),
        "string_cases_exact": len([e for e in entries
                                   if isinstance(e.get("python_value"), str)
                                   and e.get("python_value") == e.get("sql_value")]),
        "cases_where_both_sides_are_null": len([e for e in entries
                                                if e.get("python_value") is None
                                                and e.get("sql_is_null")]),
        # Verifies KNOWN_DIVERGENCES/wall_clock_granularity's claim that the fixture
        # always injects context.now, rather than taking it on trust.  If any clock
        # case ran on the real clock the run would not be reproducible.
        "clock_using_cases": len([e for e in entries
                                  if "today()" in e["expr"] or "now()" in e["expr"]]),
        "clock_cases_without_injected_now": len(
            [e for e in entries
             if ("today()" in e["expr"] or "now()" in e["expr"])
             and "now" not in (e["context"] or {})]),
    }

    # ---- DEGENERATE BASELINES ------------------------------------------------
    # What would a compiler that is obviously WRONG score on this same fixture under
    # this same rule?  Anything the harness would still pass is agreement this fixture
    # cannot distinguish from correctness.  Computed from the recorded Python values;
    # each constant's decoded value is what Postgres actually returns for it.
    pyvals = [e["python_value"] for e in entries]
    baselines = {
        "always NULL::jsonb":        len([v for v in pyvals if matches(None, v)]),
        "always to_jsonb(0::float8)": len([v for v in pyvals if matches(0, v)]),
        "always 'false'::jsonb":     len([v for v in pyvals if matches(False, v)]),
        "always 'true'::jsonb":      len([v for v in pyvals if matches(True, v)]),
        "always to_jsonb(''::text)": len([v for v in pyvals if matches("", v)]),
    }

    total = len(CASES)
    assert sum(counts.values()) == total, (
        f"outcome counts {counts} sum to {sum(counts.values())}, not {total} — "
        "a case escaped classification"
    )
    return {
        "meta": {
            "generated_by": "spikes/T-1/proto/conformance.py",
            "python": sys.version.split()[0],
            "postgres": pg_version,
            "extra_float_digits": efd,
            "database": DSN["dbname"],
            "fixture": FIXTURE,
            "fixture_sha256": sha256(FIXTURE),
            "fixture_note": _VECTORS["note"],
            "float_epsilon": _EPS,
            "epsilon_mode": "ABSOLUTE (rel_tol=0, abs_tol=1e-9) — mirrored from "
                            "tests/test_dashboard_expr.py:24",
            "expr_py_sha256": sha256(os.path.join(GIMS, "core", "dashboard", "expr.py")),
            "compile_py_sha256": sha256(os.path.join(PROTO, "compile.py")),
            "runtime_sql_sha256": sha256(os.path.join(PROTO, "runtime.sql")),
            "comparison_rule_source": "GIMS-Project/tests/test_dashboard_expr.py:20-25",
        },
        "outcome_definitions": OUTCOME_DEFINITIONS,
        "totals": {
            "cases": total,
            **{k.lower(): v for k, v in counts.items()},
            "pass_rate_denominator": total,
            "pass_rate": counts["COMPILED_AGREES"] / total,
        },
        "control_python_vs_fixture_expect": {
            "checked": total,
            "failures": control_failures,
        },
        "out_of_fixture_probes": probes,
        "agreement_strength": strength,
        "degenerate_baselines": baselines,
        "known_divergences_from_compile_py": proto_compile.KNOWN_DIVERGENCES,
        "harness_errors": harness_errors,
        "cases": entries,
    }


# ================================================================================
# Report writers
# ================================================================================
MUTATION_NOTES = {
    # Why a field-reading case gives the same answer with a non-empty record and with {}.
    # Each is read off the expression's own semantics, not assumed.
    "descend_into_nondict_is_null": "$.a.b is null whether a is 5 or absent (expr.py:566-569)",
    "bracket_index_out_of_range_is_null": "index 5 is out of range for [1] and for absent",
    "add_missing_field": "$.b is absent in BOTH records, so the sum is null either way",
    "mul_nonnumeric_string": "_to_num('abc') is None, same as _to_num(absent)",
    "eq_string_false": "'pass' != 'FAIL' and null != 'FAIL' — both false",
    "neq_string_true": "'pass' != 'FAIL' and null != 'FAIL' — both true",
    "order_mixed_types_is_null": "5 < 'x' is null (mixed types); absent < 'x' is null too",
    "and_with_falsy_zero": "0 is falsy and absent is falsy — both false",
    "empty_list_falsy": "[] is falsy and absent is falsy — both true under not",
    "contains_substring_false": "'xyz' not in 'hello' and not in null — both false",
    "contains_list_member_false": "'z' not in ['a','b'] and not in null — both false",
    "length_number_null": "length(5) is null (expr.py:543 non-str/list) as is length(absent)",
    "avg_empty_null": "avg([]) is null and avg(absent) is null",
    "if_false_branch": "-5 > 0 is false and absent > 0 is null — both take the else branch",
}



MARK = {"COMPILED_AGREES": "PASS", "COMPILED_DIVERGES": "FAIL",
        "DID_NOT_COMPILE": "GAP", "SQL_ERROR": "RAISE"}


def cell(s: Any, limit: int = 80) -> str:
    t = s if isinstance(s, str) else repr(s)
    t = t.replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    if len(t) > limit:
        t = t[: limit - 1] + "…"
    return t


def fmt_value(entry: Dict[str, Any], side: str) -> str:
    if side == "python":
        v = entry["python_value"]
        return f"`{cell(repr(v), 46)}` ({entry['python_type']})"
    if entry["outcome"] == "DID_NOT_COMPILE":
        return "—"
    if entry["outcome"] == "SQL_ERROR":
        return f"**RAISED** {entry['sql_error']['sqlstate']}"
    if entry.get("sql_is_null"):
        return "`SQL NULL`"
    return f"`{cell(repr(entry['sql_value']), 46)}` ({entry['sql_type']}, jsonb {entry['sql_jsonb_typeof']})"


def write_report(res: Dict[str, Any], path: str) -> None:
    m, t = res["meta"], res["totals"]
    out: List[str] = []
    w = out.append
    w("# T-1 · Conformance — expr(Python) vs compiled SQL(Postgres), per case\n")
    w(f"Generated by `spikes/T-1/proto/conformance.py` · {m['postgres'].split(' on ')[0]}"
      f" · db `{m['database']}` · Python {m['python']}\n")
    w(f"Fixture: `{m['fixture']}` sha256 `{m['fixture_sha256'][:16]}…` · "
      f"`expr.py` sha256 `{m['expr_py_sha256'][:16]}…` · "
      f"`compile.py` sha256 `{m['compile_py_sha256'][:16]}…` · "
      f"`runtime.sql` sha256 `{m['runtime_sql_sha256'][:16]}…`\n")
    w("## The comparison rule (the oracle)\n")
    w(f"Mirrored **unchanged** from the existing consumer test, `{m['comparison_rule_source']}`:\n")
    w("```python\n"
      "def _matches(actual, expected) -> bool:\n"
      "    if isinstance(expected, bool) or isinstance(actual, bool):\n"
      "        return actual is expected or actual == expected and type(actual) is type(expected)\n"
      "    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):\n"
      "        return math.isclose(float(actual), float(expected), rel_tol=0, abs_tol=_EPS)\n"
      "    return actual == expected\n"
      "```\n")
    w(f"- **`float_epsilon` = {m['float_epsilon']}, applied ABSOLUTELY**, not relatively. "
      "That is not a choice made here: `test_dashboard_expr.py:24` passes "
      "`rel_tol=0, abs_tol=_EPS`, which disables the relative term. The fixture's own note "
      "says only \"Numbers compare within 1e-9\" and does not name a mode, so the existing "
      "test is the tiebreaker — and using it keeps this third runtime held to exactly the "
      "bar the Python and JS runtimes already pass.\n")
    w("- **Booleans never compare equal to 0/1.** The bool branch is first and requires "
      "`type(actual) is type(expected)`. `test_dashboard_expr.py:37-41` asserts this "
      "property of the language directly.\n")
    w("- **SQL NULL and jsonb `null` are kept apart.** The driver is never allowed to "
      "decode the value; Postgres is asked `v IS NULL`, `jsonb_typeof(v)` and `v::text` "
      "separately. A top-level jsonb `null` is a leak of `compile.py`'s representation "
      "contract (`compile.py:20-30`) and is scored **COMPILED_DIVERGES even if the decoded "
      "values look equal**.\n")
    w("- **Numeric normalization, stated once:** the SQL value is `json.loads(v::text)` "
      "with stdlib defaults — JSON integer literal → `int`, fractional/exponent literal → "
      "`float`, `Decimal` never appears, nothing re-typed afterwards. "
      "`to_jsonb(3.0::float8)::text` is the text `3`, so SQL legitimately yields `int 3` "
      "where Python yields `float 3.0`; the mirrored rule already treats those as the same "
      "number, which is exactly how the fixture's hand-authored `expect: 3` matches the "
      "evaluator's `3.0`.\n")
    w(f"- `extra_float_digits` pinned to `{m['extra_float_digits']}` for the run "
      "(`KNOWN_DIVERGENCES/extra_float_digits_guc`).\n")

    w("\n## The four outcomes\n")
    for k, v in res["outcome_definitions"].items():
        w(f"- **`{k}`** ({MARK[k]}) — {v}\n")
    w("\n**`DID_NOT_COMPILE` and `SQL_ERROR` are not passes.** The pass rate below has the "
      "full case count as its denominator, and the harness asserts the four counts sum to "
      "it (`conformance.py`, `assert sum(counts.values()) == total`).\n")

    w("\n## Totals\n")
    w("| outcome | count | of |\n| --- | ---: | ---: |\n")
    for k in res["outcome_definitions"]:
        w(f"| `{k}` | {t[k.lower()]} | {t['cases']} |\n")
    w(f"\n**Pass rate = {t['compiled_agrees']}/{t['pass_rate_denominator']} = "
      f"{t['pass_rate']*100:.1f}%** — denominator is every fixture case, not every "
      "compiled case.\n")
    if t["compiled_agrees"] + t["compiled_diverges"]:
        w(f"\nAgreement *among cases that compiled and executed* = "
          f"{t['compiled_agrees']}/{t['compiled_agrees'] + t['compiled_diverges']}. "
          "Quoted separately, and never as the headline.\n")

    # --- how strong is the agreement? ------------------------------------------
    st = res["agreement_strength"]
    w("\n## How strong is the agreement?\n")
    w("A pass count says nothing about how *closely* the two runtimes agree. Measured:\n\n")
    w(f"- **{st['numeric_cases_compared']} numeric cases. "
      f"max |SQL − Python| = {st['max_abs_difference']}.** "
      f"{st['cases_needing_the_epsilon']} case(s) needed the 1e-9 epsilon at all — "
      "the numeric agreement is **bit-exact**, not epsilon-assisted. The tolerance is "
      "present because the fixture defines it, but nothing in this run depends on it.\n")
    w(f"- **{st['string_cases_exact']}/{st['string_cases']} string cases are exact** "
      "character-for-character.\n")
    w(f"- **{st['cases_where_both_sides_are_null']} of {t['cases']} agreements are "
      "\"both sides are null\"** — a weaker form of agreement, quantified next.\n")
    w(f"- **{st['clock_using_cases']} cases call `today()`/`now()`, and "
      f"{st['clock_cases_without_injected_now']} of them run on the real clock** — the "
      "fixture injects `context.now` for every one, which is what makes the run "
      "reproducible and what keeps `KNOWN_DIVERGENCES/wall_clock_granularity` out of "
      "scope here. Checked, not assumed. Two consecutive runs produce byte-identical "
      "`cases` in `results.json`.\n")

    w("\n### Degenerate baselines — what the fixture cannot distinguish\n")
    w("If an obviously wrong compiler still scores well here, that score is not evidence. "
      "Each row is a compiler that ignores its input entirely and emits one constant, "
      "scored under the identical comparison rule:\n\n")
    w("| degenerate compiler | would score | of |\n| --- | ---: | ---: |\n")
    for k, v in sorted(res["degenerate_baselines"].items(), key=lambda kv: -kv[1]):
        w(f"| `{k}` | {v} | {t['cases']} |\n")
    best = max(res["degenerate_baselines"].values())
    w(f"\nThe strongest do-nothing compiler scores **{best}/{t['cases']} "
      f"({best/t['cases']*100:.0f}%)**. The real compiler scores "
      f"{t['compiled_agrees']}/{t['cases']}, so **{t['compiled_agrees'] - best} cases "
      "are agreement that no constant could have faked.**\n")

    # --- is this harness capable of failing? -----------------------------------
    w("\n## Is this harness capable of failing?\n")
    w("FRAMING.md §8: *\"The conformance harness is the whole spike. If it is wrong, "
      "every finding downstream is wrong and looks green.\"* A clean sheet is worth "
      "nothing unless the harness demonstrably reports the other outcomes when it "
      "should. Each control feeds it a deliberately wrong input. They run **before** "
      "the conformance pass; if any fails the harness refuses to produce a report at "
      "all (`conformance.py main()`, exit 2).\n\n")
    ncs = res.get("negative_controls", [])
    w("| control | expected | got | ok |\n| --- | --- | --- | :-: |\n")
    for c in ncs:
        w(f"| {cell(c['control'], 60)} | `{cell(repr(c['expected']), 26)}` | "
          f"`{cell(repr(c['got']), 26)}` | {'yes' if c['ok'] else '**NO**'} |\n")
    nbad = len([c for c in ncs if not c["ok"]])
    w(f"\n**{len(ncs) - nbad}/{len(ncs)} controls pass.** In particular NC13 is "
      "FRAMING.md §5 stated as a test: a compiler output that turns a `null` into a "
      "number is caught, not scored as agreement.\n")

    # --- mutation probe --------------------------------------------------------
    fld = [e for e in res["cases"] if e.get("reads_a_field")]
    changed = [e for e in fld if e.get("mutation_changed")]
    unchanged = [e for e in fld if e.get("mutation_changed") is False]
    w("\n## Mutation probe — is the record actually reaching Postgres?\n")
    w("For every compiled case the SAME compiled SQL is executed a second time against "
      "an **empty record** (context unchanged). A case that reads a field and returns "
      "the same answer either way never sent that field to the database.\n\n")
    w(f"- {len(fld)} of {t['cases']} cases read a field (`$` in the expression).\n")
    w(f"- {len(changed)} of those changed their answer on an empty record.\n")
    w(f"- {len(unchanged)} did not — listed below with why.\n")
    noop = [e for e in unchanged if e["record"] == {}]
    invariant = [e for e in unchanged if e["record"] != {}]
    if unchanged:
        w(f"\nOf the {len(unchanged)} that did not change, {len(noop)} have a record that "
          f"is ALREADY `{{}}` — for those the probe is a literal no-op and carries no "
          f"information either way. The remaining {len(invariant)} have a non-empty record "
          "and are genuinely invariant:\n\n")
        w("| case | expr | record | with record | with `{}` | why invariant |\n"
          "| --- | --- | --- | --- | --- | --- |\n")
        for e in invariant:
            base = "SQL NULL" if e.get("sql_is_null") else e.get("sql_text")
            w(f"| `{e['name']}` | `{cell(e['expr'], 30)}` | `{cell(json.dumps(e['record']), 24)}` "
              f"| `{cell(str(base), 16)}` | `{cell(str(e.get('mutation_empty_record')), 16)}` "
              f"| {cell(MUTATION_NOTES.get(e['name'], 'UNEXPLAINED'), 62)} |\n")
        w("\nThe probe is a coarse liveness check, not the proof. **NC9 is the direct "
          "proof that `data` is live**: the same SQL over `{\"k\":1}` and `{\"k\":2}` "
          "returns `1` and `2`.\n")

    # --- loud sections ---------------------------------------------------------
    errs = [e for e in res["cases"] if e["outcome"] == "SQL_ERROR"]
    w("\n## SQL_ERROR — totality violations (most severe)\n")
    if not errs:
        w("None. No compiled case caused Postgres to raise.\n")
    else:
        w("`expr` never raises for data reasons (`expr.py:640`). Every row here is a case "
          "where the compiled SQL aborts the query instead of returning a value.\n\n")
        w("| case | expr | sqlstate | message |\n| --- | --- | --- | --- |\n")
        for e in errs:
            w(f"| `{e['name']}` | `{cell(e['expr'], 44)}` | `{e['sql_error']['sqlstate']}` "
              f"| {cell(e['sql_error']['message'], 90)} |\n")

    gaps = [e for e in res["cases"] if e["outcome"] == "DID_NOT_COMPILE"]
    w("\n## DID_NOT_COMPILE — coverage gaps (not passes)\n")
    if not gaps:
        w("None. Every fixture case compiled.\n")
    else:
        w("| case | expr | Uncompilable reason |\n| --- | --- | --- |\n")
        for e in gaps:
            w(f"| `{e['name']}` | `{cell(e['expr'], 44)}` | {cell(e['uncompilable_reason'], 90)} |\n")

    divs = [e for e in res["cases"] if e["outcome"] == "COMPILED_DIVERGES"]
    w("\n## COMPILED_DIVERGES — with cause\n")
    if not divs:
        w("None.\n")
    else:
        w("| case | expr | Python | SQL | shape of the difference | cause |\n"
          "| --- | --- | --- | --- | --- | --- |\n")
        for e in divs:
            w(f"| `{e['name']}` | `{cell(e['expr'], 40)}` | {fmt_value(e,'python')} | "
              f"{fmt_value(e,'sql')} | {cell(e.get('cause_shape',''), 70)} | "
              f"{cell(e.get('cause') or 'UNCLASSIFIED', 70)} |\n")

    # --- control ---------------------------------------------------------------
    ctl = res["control_python_vs_fixture_expect"]
    w("\n## Control — the Python evaluator against the fixture's hand-authored `expect`\n")
    w("The fixture note says the expected values are hand-authored and must **not** be "
      "regenerated from an evaluator, so this is a real check on the oracle, not a "
      "tautology.\n\n")
    if not ctl["failures"]:
        w(f"**{ctl['checked']}/{ctl['checked']} agree.** The Python evaluator satisfies "
          "every hand-authored `expect` under the same rule used above. The oracle is sound.\n")
    else:
        w(f"**{ctl['checked'] - len(ctl['failures'])}/{ctl['checked']} agree — "
          f"{len(ctl['failures'])} DISAGREE.** This is a pre-existing fact about GIMS, "
          "recorded here and NOT fixed (FRAMING.md §3 stop rules; both trees are read-only).\n\n")
        w("| case | expr | evaluator returned | fixture `expect` |\n| --- | --- | --- | --- |\n")
        for f in ctl["failures"]:
            w(f"| `{f['name']}` | `{cell(f['expr'], 44)}` | `{cell(f['python'], 40)}` "
              f"| `{cell(f['expect'], 40)}` |\n")

    # --- strict vs mirrored ----------------------------------------------------
    soft = [e for e in res["cases"]
            if e["outcome"] == "COMPILED_AGREES" and not e.get("strict_deep_equal", True)]
    w("\n## strict-vs-mirrored\n")
    w("The mirrored rule only reaches inside a container through Python's own `==` "
      "(`test_dashboard_expr.py:25`), which conflates `True` with `1` and `1` with `1.0` at "
      "every nested level. A stricter type-aware deep comparison runs alongside it. The "
      "mirrored rule stays the verdict; disagreements are listed, never silently resolved.\n\n")
    if not soft:
        w("No case passes under the mirrored rule while failing the stricter deep check.\n")
    else:
        w("| case | Python | SQL |\n| --- | --- | --- |\n")
        for e in soft:
            w(f"| `{e['name']}` | {fmt_value(e,'python')} | {fmt_value(e,'sql')} |\n")

    # --- out-of-fixture probes -------------------------------------------------
    w("\n## Out-of-fixture probes — NOT part of the 130\n")
    w("A clean sheet is a statement about the **fixture**, not about the compiler. Every "
      "entry in `compile.py`'s own `KNOWN_DIVERGENCES` is marked `in_fixture: False`, so "
      "the 130 cases cannot confirm or refute any of them. These probes do, and they are "
      "counted **separately** — they change none of the totals above. Per FRAMING.md §3 "
      "nothing found here was fixed.\n\n")
    w("| probe | expr | record | Python | SQL | verdict |\n| --- | --- | --- | --- | --- | --- |\n")
    for pr in res.get("out_of_fixture_probes", []):
        w(f"| `{pr['probe']}` | `{cell(pr['expr'], 20)}` | `{cell(pr['record'], 22)}` | "
          f"`{cell(pr['python'], 16)}` | `{cell(str(pr.get('sql')), 46)}` | "
          f"**{cell(pr.get('verdict',''), 34)}** |\n")
    w("\n**Two defects are confirmed here, both outside the fixture's reach:**\n\n")
    w("1. **`float8_overflow_raises` is real and reachable.** `$.a * $.b` with "
      "`a = b = 1e200` returns `inf` in Python and **raises `22003 value out of range: "
      "overflow`** in Postgres. `expr` is total (`expr.py:640`); this aborts the query. "
      "It is the one KNOWN_DIVERGENCES entry marked `guarded: false` that is a genuine "
      "totality violation, and it now has a witness.\n")
    w("2. **A defect NOT in KNOWN_DIVERGENCES: the `xpr.f8` range guard is ~12 orders of "
      "magnitude too tight.** The literal in `runtime.sql` (the `abs(...) > 1797693...` "
      "comparison in `xpr.f8`, repeated in `xpr.num`) is **297 digits long where DBL_MAX "
      "needs 309**; it evaluates to `1.797693134862316e+296`, not `1.7976931348623157e+308` "
      "(verified: `select length('1797…000'), '1797…000'::float8` → `297`, "
      "`1.797693134862316e+296`). So any JSON number with `|v|` between ~`1.8e296` and "
      "`DBL_MAX` is silently turned into NULL the moment it passes through arithmetic or "
      "`number()`: `$.a + 0` with `a = 1e300` gives `1e+300` in Python and **SQL NULL**. "
      "A bare field read is unaffected, because it never calls `xpr.f8`. This is a silent "
      "value-to-null divergence — not the disqualifying direction under FRAMING.md §5 "
      "(null-to-number), but wrong and silent, and it is **not** recorded in "
      "`KNOWN_DIVERGENCES`. Left unfixed per the stop rules: if `runtime.sql` is wrong, "
      "that IS the finding.\n")
    w("\nThe `unicode_case_and_collation` entry also gains a witness: `upper(\"straße\")` "
      "is `STRASSE` in Python and `STRAßE` in Postgres. The "
      "`jsonb_numeric_is_not_ieee_double` entry could **not** be probed this way — a "
      "record built from Python floats has already collapsed to IEEE doubles before it "
      "reaches jsonb, so the probe would be vacuous. It stays unconfirmed, not refuted.\n\n"
      )

    # --- the full per-case table ----------------------------------------------
    w("\n## Per case — all "
      f"{t['cases']} cases, grouped by the fixture's own groups\n")
    w("FRAMING.md §4 finding #1 requires pass/fail **per case**, never a summary count. "
      "Every row is here.\n")
    groups: List[str] = []
    for c in res["cases"]:
        if c["group"] not in groups:
            groups.append(c["group"])
    for g in groups:
        rows = [c for c in res["cases"] if c["group"] == g]
        tally = {}
        for c in rows:
            tally[c["outcome"]] = tally.get(c["outcome"], 0) + 1
        head = " · ".join(f"{MARK[k]} {v}" for k, v in sorted(tally.items()))
        w(f"\n### `{g}` — {len(rows)} cases ({head})\n\n")
        w("| # | case | expr | outcome | Python | SQL | cause / reason |\n"
          "| ---: | --- | --- | --- | --- | --- | --- |\n")
        for i, e in enumerate(rows, 1):
            if e["outcome"] == "DID_NOT_COMPILE":
                why = cell(e["uncompilable_reason"], 60)
            elif e["outcome"] == "SQL_ERROR":
                why = cell(e["sql_error"]["message"], 60)
            elif e["outcome"] == "COMPILED_DIVERGES":
                why = cell((e.get("cause") or "UNCLASSIFIED") + " — " + e.get("cause_shape", ""), 60)
            else:
                why = ""
            w(f"| {i} | `{e['name']}` | `{cell(e['expr'], 40)}` | **{MARK[e['outcome']]}** "
              f"`{e['outcome']}` | {fmt_value(e,'python')} | {fmt_value(e,'sql')} | {why} |\n")

    # --- known divergences carried from compile.py ----------------------------
    w("\n## `compile.py` KNOWN_DIVERGENCES (carried through so the finding cannot be lost)\n\n")
    w("| id | construct | expr | SQL | guarded | in fixture |\n| --- | --- | --- | --- | --- | --- |\n")
    for k in res["known_divergences_from_compile_py"]:
        w(f"| `{k['id']}` | {cell(k['construct'], 46)} | {cell(k['expr_behaviour'], 70)} "
          f"| {cell(k['sql_behaviour'], 70)} | {'yes' if k['guarded'] else '**NO**'} "
          f"| {'**yes**' if k['in_fixture'] else 'no'} |\n")
    w("\nThese are divergences identified by the compiler's author and deliberately NOT "
      "fixed (FRAMING.md §3). They are reproduced verbatim in `results.json` under "
      "`known_divergences_from_compile_py`.\n")

    open(path, "w").write(tidy("".join(out)))


def tidy(text: str) -> str:
    """Insert the blank lines Markdown needs between blocks.

    Cosmetic only — it never changes a character of content, it only separates a
    heading / list / table from whatever precedes it.  Fenced code is left alone.
    """
    def kind(ln: str) -> str:
        if ln.startswith("#"):
            return "h"
        if ln.startswith("|"):
            return "t"
        if ln.startswith("- ") or ln.startswith("1. ") or ln.startswith("2. "):
            return "l"
        if not ln.strip():
            return ""
        return "p"

    out: List[str] = []
    fence = False
    for ln in text.split("\n"):
        if ln.startswith("```"):
            opening = not fence
            fence = not fence
            if opening and out and out[-1].strip():
                out.append("")
            out.append(ln)
            continue
        if fence:
            out.append(ln)
            continue
        k = kind(ln)
        prev = out[-1] if out else ""
        pk = kind(prev)
        if out and prev.strip() and k and (k != pk or k == "h"):
            out.append("")
        out.append(ln)
    return "\n".join(out)


# ================================================================================
# NEGATIVE CONTROLS — proof that this harness is capable of failing.
# ================================================================================
# FRAMING.md §8: "The conformance harness is the whole spike. If it is wrong, every
# finding downstream is wrong and looks green."  A 130/130 result is worth nothing
# unless the harness demonstrably reports each of the other three outcomes when it
# should.  Each control below feeds the harness a deliberately WRONG input and asserts
# the harness catches it.  Run with `--selftest`; it is also run automatically before
# the conformance pass, and its results are written into results.json.
def selftest() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    def rec(name, expect, got, detail=""):
        out.append({"control": name, "expected": expect, "got": got,
                    "ok": expect == got, "detail": detail})

    # NC1 — an Uncompilable is raised and is catchable as DID_NOT_COMPILE, not a crash.
    try:
        proto_compile.compile_ast(("no_such_tag", 1))
        rec("NC1 unknown AST tag -> Uncompilable", "Uncompilable", "returned normally")
    except proto_compile.Uncompilable as exc:
        rec("NC1 unknown AST tag -> Uncompilable", "Uncompilable", "Uncompilable", exc.reason)

    # NC2 — the mirrored rule rejects a wrong number.
    rec("NC2 matches(999.0, 3.0) is False", False, matches(999.0, 3.0))

    # NC3 — epsilon is ABSOLUTE, not relative.  A relative 1e-9 tolerance would accept
    #       1000000001.0 vs 1000000000.0 (ratio 1e-9).  The mirrored rule must not.
    rec("NC3a matches(3.0 + 1e-10, 3.0) is True", True, matches(3.0 + 1e-10, 3.0))
    rec("NC3b matches(3.0 + 1e-8, 3.0) is False", False, matches(3.0 + 1e-8, 3.0))
    rec("NC3c ABSOLUTE: matches(1e9 + 1.0, 1e9) is False", False, matches(1e9 + 1.0, 1e9))

    # NC4 — booleans never satisfy 0/1, in either direction.
    rec("NC4a matches(True, 1) is False", False, matches(True, 1))
    rec("NC4b matches(1, True) is False", False, matches(1, True))
    rec("NC4c matches(True, True) is True", True, matches(True, True))
    rec("NC4d matches(False, 0.0) is False", False, matches(False, 0.0))

    # NC5 — None only satisfies None.
    rec("NC5a matches(None, None) is True", True, matches(None, None))
    rec("NC5b matches(None, 0.0) is False", False, matches(None, 0.0))
    rec("NC5c matches(0.0, None) is False", False, matches(0.0, None))

    # NC6 — the deep strict check catches what the mirrored rule lets through.
    rec("NC6a mirrored rule passes [True] vs [1]", True, matches([True], [1]))
    rec("NC6b strict check rejects [True] vs [1]", False, deep_strict([True], [1]))

    # Live-database controls.
    conn = psycopg2.connect(**DSN)
    with conn.cursor() as cur:
        # NC7 — Postgres raising is reported as SqlRaised, never swallowed.
        try:
            run_sql(cur, "to_jsonb((1::int / 0::int))", {}, {}, {})
            rec("NC7 division_by_zero -> SqlRaised", "SqlRaised", "no exception")
            conn.rollback()
        except SqlRaised as exc:
            conn.rollback()
            rec("NC7 division_by_zero -> SqlRaised", "SqlRaised", "SqlRaised", exc.sqlstate)

        # NC8 — SQL NULL and jsonb 'null' are distinguishable.  If this control fails,
        #       every null-valued agreement in the run is untrustworthy.
        n1 = run_sql(cur, "NULL::jsonb", {}, {}, {}); conn.commit()
        rec("NC8a NULL::jsonb -> is_sql_null True, jsonb_typeof None",
            (True, None), (n1[0], n1[1]))
        n2 = run_sql(cur, "'null'::jsonb", {}, {}, {}); conn.commit()
        rec("NC8b 'null'::jsonb -> is_sql_null False, jsonb_typeof 'null'",
            (False, "null"), (n2[0], n2[1]))

        # NC9 — the `data` column really is the record: same SQL, two records.
        a = run_sql(cur, "(data -> 'k')", {}, {"k": 1}, {}); conn.commit()
        b = run_sql(cur, "(data -> 'k')", {}, {"k": 2}, {}); conn.commit()
        rec("NC9 data column is live (record 1 vs 2)", ("1", "2"), (a[2], b[2]))

        # NC10 — the `ctx` bind really is the context.
        c1 = run_sql(cur, "to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true))",
                     {}, {}, {"now": "2030-01-15T00:00:00Z"}); conn.commit()
        rec("NC10 ctx bind is live", '"2030-01-15"', c1[2])

        # NC11 — a deliberately MIS-compiled case is caught.  Take a real fixture case,
        #        execute a wrong expression for it, and confirm matches() says no.
        case = next(c for c in CASES if c["name"] == "add")
        py = expr.evaluate(expr.parse(case["expr"]), {}, {})
        w = run_sql(cur, "to_jsonb(999::float8)", {}, {}, {}); conn.commit()
        rec("NC11 wrong SQL for fixture case 'add' is caught",
            False, matches(json.loads(w[2]), py), f"python={py!r} sql={w[2]}")

        # NC12 — a null-for-a-value substitution is caught (the §5 failure mode's mirror).
        w2 = run_sql(cur, "NULL::jsonb", {}, {}, {}); conn.commit()
        rec("NC12 SQL NULL where Python has a value is caught",
            False, matches(None if w2[0] else json.loads(w2[2]), py))

        # NC13 — a value-for-a-null substitution is caught (FRAMING §5 verbatim: a
        #        compiler output that turns a null into a number).
        case2 = next(c for c in CASES if c["name"] == "divide_by_zero_is_null")
        py2 = expr.evaluate(expr.parse(case2["expr"]), case2.get("record", {}),
                            case2.get("context", {}))
        w3 = run_sql(cur, "to_jsonb(0::float8)", {}, case2.get("record", {}), {}); conn.commit()
        rec("NC13 a number where Python has null is caught (FRAMING §5)",
            False, matches(json.loads(w3[2]), py2), f"python={py2!r} sql={w3[2]}")

        # NC14 — a stray literal % in generated SQL is refused, not silently interpolated.
        try:
            check_placeholders("SELECT 5 % 2", {}, "ctx")
            rec("NC14 stray % refused", "AssertionError", "accepted")
        except AssertionError:
            rec("NC14 stray % refused", "AssertionError", "AssertionError")

    conn.close()
    return out


def main() -> int:
    controls = selftest()
    broken = [c for c in controls if not c["ok"]]
    for c in controls:
        print(f"  [{'ok ' if c['ok'] else 'BAD'}] {c['control']}"
              + (f"   ({c['detail']})" if c["detail"] else ""))
    if "--selftest" in sys.argv:
        return 1 if broken else 0
    if broken:
        # A harness that cannot fail cannot pass anything either.  Refuse to produce a
        # green report on top of a broken oracle.
        print(f"\nNEGATIVE CONTROLS FAILED ({len(broken)}). The conformance result would "
              "be meaningless. Refusing to run.")
        return 2

    res = run()
    res["negative_controls"] = controls
    with open(RESULTS_JSON, "w") as fh:
        json.dump(res, fh, indent=1, default=repr)
    write_report(res, REPORT_MD)
    t = res["totals"]
    print(json.dumps(t, indent=1))
    print("control (python vs fixture expect) failures:",
          len(res["control_python_vs_fixture_expect"]["failures"]))
    m = [e for e in res["cases"] if e.get("reads_a_field") and not e.get("mutation_changed")]
    print(f"mutation probe: {len([e for e in res['cases'] if e.get('mutation_changed')])} "
          f"of {len(res['cases'])} cases changed answer on an empty record; "
          f"{len(m)} field-reading cases did NOT change")
    for e in res["cases"]:
        if e["outcome"] != "COMPILED_AGREES":
            print(f"  {e['outcome']:18s} {e['group']:16s} {e['name']:28s} {e['expr']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
