"""T-98: xpr.time_of_day is GIMS's time_of_day, case by case.

time_of_day(t, zone) (GIMS T-98, GA-68 Q6) is the time a wall clock in a NAMED zone shows at the
instant t, as whole seconds since that clock's midnight; null for a bare date, an unreadable t,
an unlisted zone, or a clock date outside years 1..9999. Every case below is held to GIMS's own
evaluator (demo/vendor/expr.py, or the tree AUTOSQL_GIMS_TREE names): the SQL value must EQUAL
it, NULL where it is None.

The zone reaches SQL only as one of the evaluator's TIME_ZONES (the compiler emits the call only
for such a literal), so every zone here is a listed one. What each zone's clock says comes from
each engine's own time-zone data; where those disagree (picks/zones.py checks it before a pick
runs), the cases avoid the dates involved.

Database tests: AUTOSQL_RUNTIME_DSN, as in test_runtime.py.  They SKIP without it.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DSN = os.environ.get("AUTOSQL_RUNTIME_DSN")
if DSN and "port=55433" in DSN:
    raise SystemExit("refusing to run against port 55433 — that is the live database")
needs_db = pytest.mark.skipif(not DSN, reason="set AUTOSQL_RUNTIME_DSN to a throwaway Postgres")

GIMS_TREE = os.environ.get("AUTOSQL_GIMS_TREE")
if GIMS_TREE:
    sys.path.insert(0, GIMS_TREE)
    from core.dashboard import expr as GIMS  # noqa: E402
else:
    _spec = importlib.util.spec_from_file_location("t98_gims_expr", ROOT / "demo" / "vendor" / "expr.py")
    GIMS = importlib.util.module_from_spec(_spec)
    sys.modules["t98_gims_expr"] = GIMS
    _spec.loader.exec_module(GIMS)

_AST = GIMS.parse("time_of_day($.t, $.z)")


def _python(t, zone):
    record = {"z": zone} if t is _MISSING else {"t": t, "z": zone}
    return GIMS.evaluate(_AST, record, {})


_MISSING = object()

#: Zones with every kind of clock: whole hours, half and three-quarter hours, the furthest
#: ahead and behind, a fixed offset whose name runs backwards, a 30-minute daylight saving
#: change (Lord Howe), daylight saving at midnight (Santiago), and the southern hemisphere.
ZONES = ["UTC", "America/Denver", "America/New_York", "Asia/Kolkata", "Asia/Kathmandu",
         "Pacific/Kiritimati", "Pacific/Pago_Pago", "Etc/GMT+12", "Etc/GMT-14", "Australia/Lord_Howe",
         "Pacific/Chatham", "America/Santiago", "Europe/London", "Australia/Adelaide",
         "America/St_Johns", "Asia/Tehran", "Pacific/Apia", "America/Phoenix", "Asia/Dhaka"]


def _every_half_hour(day_start: str, hours: int):
    from datetime import datetime, timedelta, timezone
    t0 = datetime.fromisoformat(day_start).replace(tzinfo=timezone.utc)
    return [(t0 + timedelta(minutes=30 * i)).strftime("%Y-%m-%dT%H:%M:%SZ") for i in range(hours * 2)]


#: Instants around both of Denver's 2026 changes, every half hour, plus a second either side.
DST_INSTANTS = (_every_half_hour("2026-03-07T12:00:00", 36) + _every_half_hour("2026-10-31T12:00:00", 36)
                + ["2026-03-08T08:59:59Z", "2026-03-08T09:00:00Z", "2026-11-01T07:59:59Z",
                   "2026-11-01T08:00:00Z", "2026-11-01T07:30:00Z", "2026-11-01T08:30:00Z"])

#: Every text form GIMS's date reader takes or refuses, and every JSON kind that is no time.
FORMS = [
    "2026-08-20T17:00:00Z", "2026-08-20T16:59:59Z", "2026-08-20T16:59:59.9Z",
    "2026-08-20T16:59:59.999999Z", "2026-08-20T23:00:00+05:30", "2026-08-20T23:00:00-0545",
    "2026-08-20 14:30", "2026-08-20T14:30", "2026-08-20T14:30:15", "2026-08-20",
    "2026-08-20T24:00:00Z", "2026-08-20T23:60:00Z", "2026-02-30T12:00:00Z", "2024-02-29T12:00:00Z",
    "1900-02-29T12:00:00Z", "0000-06-01T12:00:00Z", " 2026-08-20T17:00:00Z ",
    " 2026-08-20T17:00:00Z　", "２０２６-08-20T17:00:00Z",
    "٢٠٢٦-08-20T17:00:00Z", "2026-08-20t17:00:00z", "", "teatime",
    "1800-01-01T12:00:00Z", "1883-11-18T19:00:00Z", "1970-01-01T00:00:00Z", "2000-01-01T00:00:00Z",
    "0001-01-01T00:00:00Z", "0001-01-01T12:00:00Z", "0001-01-01T00:00:00+14:00",
    "9999-12-31T09:00:00Z", "9999-12-31T23:00:00Z", "9999-12-31T23:59:59-14:00",
    "9999-12-31T23:00:00-12:00", "9999-12-31T23:59:59Z", "0001-01-01T00:00:00-12:00",
    1755730800000, 0, 1.5, True, False, None, _MISSING, [], ["2026-08-20T17:00:00Z"],
    {"t": "2026-08-20T17:00:00Z"},
]


def _sql(conn, cases):
    """One statement: xpr.time_of_day over each (t, zone). A missing t is SQL NULL (what the
    compiler delivers for a missing field); a JSON null is the jsonb 'null'."""
    payload = [[None if t is _MISSING else t, t is _MISSING, z] for t, z in cases]
    q = ("SELECT xpr.time_of_day(CASE WHEN (x ->> 1)::boolean THEN NULL ELSE x -> 0 END, x ->> 2) "
         "FROM jsonb_array_elements(%s::jsonb) WITH ORDINALITY AS a(x, n) ORDER BY n")
    import psycopg
    try:
        return [r[0] for r in conn.execute(q, (json.dumps(payload),)).fetchall()]
    except psycopg.errors.UndefinedFunction:
        pytest.fail("this runtime has no xpr.time_of_day(jsonb, text): GIMS's time_of_day has no SQL form")


@pytest.fixture(scope="module")
def conn():
    import psycopg
    sys.path.insert(0, str(ROOT / "runtime"))
    import this_runtime
    with psycopg.connect(DSN, autocommit=True) as cx:
        this_runtime.install(cx)       # the runtime under test, never what a database happens to hold
        yield cx


def _disagreements(conn, cases):
    got = _sql(conn, cases)
    bad = []
    for (t, z), s in zip(cases, got):
        p = _python(t, z)
        if not (p == s and (p is None) == (s is None)):
            bad.append(f"time_of_day({'<missing>' if t is _MISSING else t!r}, {z!r}): GIMS {p!r}, SQL {s!r}")
    return bad


def test_the_battery_uses_only_listed_zones():
    """The compiler emits xpr.time_of_day only for a listed zone; an unlisted one is GIMS's
    null and never reaches SQL (whose own data may well know it: Alpine's Postgres still
    carries US/Mountain and Asia/Calcutta, which Ubuntu 24.04's Python no longer lists)."""
    assert set(ZONES) <= GIMS.TIME_ZONES, sorted(set(ZONES) - GIMS.TIME_ZONES)


def test_the_battery_reaches_both_answers():
    """A battery that only ever compared NULL with None would prove nothing."""
    vals = [_python(t, z) for t in FORMS for z in ZONES]
    assert sum(v is None for v in vals) > 100 and sum(v is not None for v in vals) > 100
    assert {_python(t, "America/Denver") for t in DST_INSTANTS} >= {7200.0, 3600.0, 5400.0, 10800.0}


@needs_db
def test_every_form_in_every_kind_of_zone(conn):
    bad = _disagreements(conn, [(t, z) for t in FORMS for z in ZONES])
    assert not bad, f"{len(bad)} disagreements:\n" + "\n".join(bad[:20])


@needs_db
def test_across_the_clock_changes(conn):
    bad = _disagreements(conn, [(t, z) for t in DST_INSTANTS for z in ZONES])
    assert not bad, f"{len(bad)} disagreements:\n" + "\n".join(bad[:20])


# Every listed zone: compiler/tests/test_compile_time_of_day.py, where each runs behind the zone guard
# (a zone whose two clock databases disagree is refused there, by name, before any row is read).


# ── T-98: does a database run THIS tree's runtime? (the suite says so at its start) ──

@needs_db
def test_a_database_running_this_runtime_is_said_to(conn):
    """this_runtime.install ran in the fixture: every function the file declares is there, as written."""
    import this_runtime
    got = this_runtime.compare(conn, this_runtime.RUNTIME_SQL.read_text())
    assert got["state"] == "same" and got["functions"] == 27, got


@needs_db
def test_a_database_running_another_runtime_is_named_function_by_function(conn):
    import this_runtime
    sql = this_runtime.RUNTIME_SQL.read_text()
    try:
        conn.execute("CREATE OR REPLACE FUNCTION xpr.div(a float8, b float8) RETURNS float8 "
                     "LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT a / nullif(b, 0) $$")
        conn.execute("DROP FUNCTION xpr.time_of_day(jsonb, text)")
        conn.execute("CREATE FUNCTION xpr.stray() RETURNS int LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT 1 $$")
        got = this_runtime.compare(conn, sql)
        assert got["state"] == "differs"
        assert (got["differ"], got["missing"], got["extra"]) == (["xpr.div"], ["xpr.time_of_day"], ["xpr.stray"]), got
        words = this_runtime.words(got, "demo/vendor/runtime.sql")
        assert "differs: xpr.div" in words and "missing: xpr.time_of_day" in words and "extra: xpr.stray" in words
    finally:
        this_runtime.install(conn)
