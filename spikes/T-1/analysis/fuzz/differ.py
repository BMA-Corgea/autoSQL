"""T-1 spike / semantic-faithfulness seat -- THROWAWAY differential driver.

One job: given (expr source, record, context), get the Python answer and the
Postgres answer for the SAME expression and say whether they agree, using the
comparison rule mirrored UNCHANGED from
GIMS-Project/tests/test_dashboard_expr.py:20-25.

Nothing here is a library.  It imports the REAL parser/evaluator
(GIMS-Project@995cc59 core/dashboard/expr.py) and the spike compiler
(spikes/T-1/proto/compile.py); it never reimplements either.

Two ingestion modes, because they are NOT the same experiment:
  mode="py"  -- the record is a Python object, sent through psycopg2 as jsonb
                (this is what api/storage_aws.py PgRecordStore does: Jsonb(record),
                i.e. json.dumps of Python objects; every number has ALREADY
                collapsed to an IEEE double before it reaches the column).
  mode="raw" -- the record is raw JSON *text*, cast ::jsonb in SQL, and Python
                gets json.loads(text).  This is the shape of any row written by
                something that is not this Python process (ETL, migration, psql,
                another service).  It is the only mode that can exercise jsonb's
                `numeric` storage against Python's `float` parse.
"""
from __future__ import annotations
import os

import json
import math
import sys
import traceback

sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/GIMS-Project")
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto")

from core.dashboard import expr            # noqa: E402  the REAL evaluator
import compile as xcompile                 # noqa: E402  the spike compiler

import psycopg2                            # noqa: E402

# Connection string for the spike's scratch database.
# Set AUTOSQL_SPIKE_DSN to reproduce, e.g.
#   export AUTOSQL_SPIKE_DSN="host=127.0.0.1 port=55434 user=glp_owner password=<throwaway> dbname=autosql_spike"
# The password is deliberately NOT in this repo: the same role owns the live glp_strong
# database on that container. Scrubbed 2026-08-21 before first commit.
DSN = os.environ.get("AUTOSQL_SPIKE_DSN")
if not DSN:
    raise SystemExit(
        "AUTOSQL_SPIKE_DSN is not set, and there is no default. The only default that ever\n"
        "  existed pointed at port 55433 - the live glp-strong-db container, which holds real\n"
        "  data owned by the same role. Point it at a THROWAWAY Postgres instead.\n"
        "  See spikes/T-1/proto/REGENERATE-CORPUS.md."
    )
if "port=55433" in DSN:
    raise SystemExit(
        "Refusing to run against port 55433 - that is the live glp-strong-db container.\n"
        "  Use a throwaway one. See spikes/T-1/proto/REGENERATE-CORPUS.md."
    )

# T-3 (2026-08-22, spec EXPERIMENTS.md 1.4 item 1 / framing C3): the float-digit setting is
# an ARGUMENT now, not a pin.  Q10 requires the correctness run at all three values, and this
# file's old hard-coded `SET extra_float_digits = 1` would have run all three "settings" at 1.
EFD = os.environ.get("AUTOSQL_EFD", "1")
if EFD not in ("1", "0", "-3"):
    raise SystemExit(
        "AUTOSQL_EFD must be one of 1, 0, -3 (Q10's three settings); got %r" % EFD
    )
EFD_READBACK = None   # filled on first connect; batteries record it beside their counts

_EPS = 1e-9   # expr_vectors.json float_epsilon

# The SQLSTATE the step-zero runtime raises for its NAMED out-of-float8-range refusal
# (the GA-4 ruling: raise loudly instead of returning NULL).  Anything arriving with this
# code is xpr.f8/xpr.num refusing on purpose.
GUARD_REFUSAL_SQLSTATE = "XPR01"


def refusal_kind(pgcode, message):
    """framing 4.5/C4: a refusal must be IDENTIFIABLE.  Returns the named kind for a
    deliberate refusal, or None for an unexplained raise (which stays a defect)."""
    if pgcode == GUARD_REFUSAL_SQLSTATE:
        return "guard"                       # xpr.f8/xpr.num named refusal (step zero)
    if pgcode == "22003":
        m = (message or "").lower()
        if "underflow" in m:
            return "underflow"               # counted separately per framing 4.7
        if "overflow" in m:
            return "overflow"
        return "out_of_range"                # e.g. float8 input parse of a subnormal-below-min
    return None


def matches(actual, expected) -> bool:
    """Mirrored UNCHANGED from tests/test_dashboard_expr.py:20-25."""
    if isinstance(expected, bool) or isinstance(actual, bool):
        return actual is expected or actual == expected and type(actual) is type(expected)
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isclose(float(actual), float(expected), rel_tol=0, abs_tol=_EPS)
    return actual == expected


_conn = None


def conn():
    global _conn, EFD_READBACK
    if _conn is None:
        _conn = psycopg2.connect(DSN)
        _conn.autocommit = True
        with _conn.cursor() as cur:
            cur.execute("SET statement_timeout = '20s'")      # same value conformance.py uses
            cur.execute("SET extra_float_digits = %s", (int(EFD),))   # was pinned to 1; see EFD
            cur.execute("select current_setting('extra_float_digits')")
            EFD_READBACK = cur.fetchone()[0]
        if EFD_READBACK != EFD:
            raise SystemExit(
                "positive-control failure: requested extra_float_digits=%s, session says %s"
                % (EFD, EFD_READBACK))
    return _conn


class Outcome(dict):
    pass


def run_case(src, record=None, ctx=None, mode="py", raw=None, note=""):
    """Return an Outcome describing Python vs Postgres for one expression.

    verdict is one of:
      AGREE            both produced a value and matches() is True
      DIVERGE          both produced a value and matches() is False
      SQL_REFUSAL      Postgres raised a NAMED, deliberate refusal where Python
                       returned (T-3 split, framing C4/R7: SQLSTATE XPR01 = the
                       step-zero guard, or 22003 overflow/underflow/out-of-range;
                       out["refusal_kind"] says which).  Allowed by the GA-4
                       ruling; counted, never a pass and never a fail.
      SQL_RAISE        Postgres raised something UNNAMED where Python returned --
                       an unexplained raise, still a defect line
      PY_RAISE         Python raised where Postgres returned  (expr is not total!)
      BOTH_RAISE       both raised (reported on the refusal line -- neither side
                       produced an answer, so nothing can be wrong)
      UNCOMPILABLE     compile.py refused (an honest gap, never a pass)
      NULLNESS         values decode equal but one side is SQL NULL and the other
                       jsonb 'null' -- a leak of the representation contract
    """
    out = Outcome(expr=src, mode=mode, note=note,
                  record=record if mode == "py" else raw, ctx=ctx)

    # ---- Python side -----------------------------------------------------
    try:
        ast = expr.parse(src)
    except Exception as e:                       # a syntax error is not our subject
        out.update(verdict="PARSE_ERROR", py_error=repr(e))
        return out

    py_record = record if mode == "py" else json.loads(raw)
    out["py_record_decoded"] = repr(py_record) if mode == "raw" else None
    try:
        py = expr.evaluate(ast, py_record, ctx or {})
        py_raised = None
    except Exception as e:
        py, py_raised = None, f"{type(e).__name__}: {e}"
    out["python"] = repr(py) if py_raised is None else None
    out["python_raised"] = py_raised

    # ---- compile ---------------------------------------------------------
    try:
        c = xcompile.compile_ast(ast)
    except xcompile.Uncompilable as e:
        out.update(verdict="UNCOMPILABLE", uncompilable=e.reason)
        return out
    out["sql"] = c.sql

    params = dict(c.params)
    params["ctx"] = json.dumps(ctx or {})
    params["rec"] = json.dumps(record) if mode == "py" else raw

    q = ("SELECT (v IS NULL) AS is_sql_null, jsonb_typeof(v) AS jt, v::text AS vt "
         "FROM (SELECT " + c.sql + " AS v "
         "FROM (SELECT (%(rec)s)::jsonb AS data) t) q")
    try:
        with conn().cursor() as cur:
            cur.execute(q, params)
            is_null, jt, vt = cur.fetchone()
        sql_raised = None
    except psycopg2.Error as e:
        is_null = jt = vt = None
        sql_raised = f"{e.pgcode} {str(e).strip().splitlines()[0]}"
        out["sqlstate"] = e.pgcode
        out["refusal_kind"] = refusal_kind(e.pgcode, str(e))
    out["sql_raised"] = sql_raised
    out["efd"] = EFD_READBACK

    if sql_raised is None:
        sql_val = None if (is_null or jt == "null") else json.loads(vt)
        if isinstance(sql_val, int) and not isinstance(sql_val, bool):
            # jsonb keeps `numeric`; a JSON integer literal decodes to a Python int
            # that may not be representable as a float at all.
            try:
                float(sql_val)
            except OverflowError:
                out["sql_int_unrepresentable"] = True
        out["sql"] = c.sql
        out["sql_text"] = vt
        out["sql_typeof"] = "SQL NULL" if is_null else jt
        out["sql_value"] = repr(sql_val)
    else:
        sql_val = None
        out["sql_typeof"] = None
        out["sql_value"] = None

    # ---- verdict ---------------------------------------------------------
    if py_raised and sql_raised:
        out["verdict"] = "BOTH_RAISE"
    elif py_raised:
        out["verdict"] = "PY_RAISE"          # expr claims to be total; it is not
    elif sql_raised:
        # T-3 split (framing C4, ruling R7): a NAMED refusal is the GA-4 ruling's intended
        # behaviour and must not be scored with genuine defects; an unexplained raise stays
        # SQL_RAISE and stays a defect.  Under T-1's framing every raise was one class.
        out["verdict"] = ("SQL_REFUSAL" if out.get("refusal_kind") else "SQL_RAISE")
    elif py is None and jt == "null":
        out["verdict"] = "NULLNESS"
    else:
        try:
            agree = matches(sql_val, py)
        except (OverflowError, ValueError, TypeError) as e:
            # The SQL value cannot even be brought into Python's value space.
            out["compare_error"] = f"{type(e).__name__}: {e}"
            agree = False
        out["verdict"] = "AGREE" if agree else "DIVERGE"
    return out


def show(o, verbose=False):
    tag = o["verdict"]
    line = f"[{tag:12s}] {o['expr']!r}"
    if o.get("record") is not None:
        line += f"  rec={o['record']!r}"
    if o.get("ctx"):
        line += f"  ctx={o['ctx']!r}"
    print(line)
    if tag not in ("AGREE",) or verbose:
        print(f"               py  = {o.get('python')}"
              f"{'  RAISED ' + o['python_raised'] if o.get('python_raised') else ''}")
        print(f"               sql = {o.get('sql_value')}"
              f"  ({o.get('sql_typeof')})"
              f"{'  RAISED ' + o['sql_raised'] if o.get('sql_raised') else ''}")
        if o.get("uncompilable"):
            print(f"               uncompilable: {o['uncompilable']}")
        if verbose and o.get("sql"):
            print(f"               SQL: {o['sql']}")
    return o
