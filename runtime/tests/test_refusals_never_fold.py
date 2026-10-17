"""T-109's round (a-chk's LOW): a raising function never fires at plan time.

Postgres folds an IMMUTABLE call whose arguments are all constants while it plans, so
``CASE WHEN random() >= 0 THEN 'ok' ELSE xpr.series_time_refused('k', 'v') END`` raised XPR06 although no row
reached the ELSE. The builder passes column arguments, so nothing was folded as used -- but only by how it is
called. Both raising functions (T-101's xpr.clock_refused, T-109's xpr.series_time_refused) are VOLATILE, and still
PARALLEL SAFE (T-52), so no future constant argument can fire one; reached, each still raises by name.

Database tests: AUTOSQL_RUNTIME_DSN, as in test_runtime.py.  They SKIP without it.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DSN = os.environ.get("AUTOSQL_RUNTIME_DSN")
if DSN and "port=55433" in DSN:
    raise SystemExit("refusing: 55433 is a live database")
needs_db = pytest.mark.skipif(not DSN, reason="set AUTOSQL_RUNTIME_DSN to a throwaway Postgres")

RAISING = {"series_time_refused": "XPR06", "clock_refused": "XPR05"}
UNREACHED = {
    "series_time_refused": "SELECT CASE WHEN random() >= 0 THEN 'ok' ELSE xpr.series_time_refused('k', 'v') END",
    "clock_refused": ("SELECT CASE WHEN random() >= 0 THEN 'ok' ELSE "
                      "xpr.clock_refused(timestamptz '2026-11-02 12:00:00+00', 'America/Edmonton')::text END"),
}


@pytest.fixture(scope="module")
def conn():
    import psycopg
    sys.path.insert(0, str(ROOT / "runtime"))
    import this_runtime
    with psycopg.connect(DSN, autocommit=True) as cx:
        this_runtime.install(cx)       # the runtime under test, never what a database happens to hold
        yield cx


@needs_db
@pytest.mark.parametrize("fn", list(RAISING))
def test_a_constant_argument_case_never_raises_when_the_else_is_not_reached(conn, fn):
    assert conn.execute(UNREACHED[fn]).fetchone()[0] == "ok"


@needs_db
@pytest.mark.parametrize("fn", list(RAISING))
def test_each_raising_function_is_volatile_and_parallel_safe(conn, fn):
    got = conn.execute("SELECT p.provolatile, p.proparallel FROM pg_proc p JOIN pg_namespace n "
                       "ON n.oid = p.pronamespace WHERE n.nspname = 'xpr' AND p.proname = %s", (fn,)).fetchall()
    assert got == [("v", "s")], got


@needs_db
def test_reached_the_series_refusal_still_raises_by_name(conn):
    import psycopg
    with pytest.raises(psycopg.Error) as e:
        conn.execute("SELECT xpr.series_time_refused(k, v) FROM (VALUES ('hb-1', '2026-08-20t10:00:00z')) AS t(k, v)")
    assert e.value.sqlstate == "XPR06"
    assert json.loads(e.value.diag.message_detail) == {"key": "hb-1", "value": "2026-08-20t10:00:00z"}


@needs_db
def test_reached_the_clock_refusal_still_raises_by_name(conn):
    import psycopg
    with pytest.raises(psycopg.Error) as e:
        conn.execute("SELECT xpr.clock_refused(t, 'America/Edmonton') "
                     "FROM (VALUES (timestamptz '2026-11-02 12:00:00+00')) AS v(t)")
    assert e.value.sqlstate == "XPR05" and "2026-11-02" in str(e.value)
