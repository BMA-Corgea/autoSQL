"""T-98: compiling time_of_day(t, zone), and the zone guard every such statement carries.

GIMS's time_of_day reads a wall clock in a NAMED zone (GA-68 Q6). The compiler emits it only for
a zone written in the expression as one of the evaluator's TIME_ZONES, and wraps that zone in
xpr.zone_checked: Python's own clock for the zone (its transitions, 1800 to 2100, from the same
zoneinfo data the evaluator reads) is handed to the database, which compares it with ITS clock
for the zone once per statement and refuses (XPR05, the zone named) before any row is read if
the two differ anywhere. Two clock databases on one machine disagree today (measured 2026-10-13:
the host's tzdata 2026c and the demo container's 2026b differ on Edmonton, Yellowknife,
Casablanca and El Aaiun from this autumn, and on 105 other zones' history before 1970), so
without the guard the two engines would return different rows, both "correct".

Database tests: AUTOSQL_COMPILER_DSN, a throwaway Postgres with THIS tree's runtime installed.
They SKIP without it.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DSN = os.environ.get("AUTOSQL_COMPILER_DSN")


def _connect():
    import psycopg
    cx = psycopg.connect(DSN, autocommit=True)
    if int(cx.info.port) in (55433, 55440):
        cx.close()
        raise SystemExit("refusing: 55433 is a live database and 55440 is the shared demo's")
    return cx


needs_db = pytest.mark.skipif(not DSN, reason="set AUTOSQL_COMPILER_DSN to a throwaway Postgres with this tree's runtime")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


EXPR = _load("t98_expr", "demo/vendor/expr.py")
C = _load("t98_compile", "compiler/compile.py")
ZONES = EXPR.TIME_ZONES


def _compile(src, zones=ZONES):
    return C.compile_predicate(EXPR.parse(src), column="data", time_zones=zones)


# ---- refusals, no database ----------------------------------------------------------------------

@pytest.mark.parametrize("src, why", [
    ('time_of_day($.t, $.z) >= 0', "written in the expression"),
    ('time_of_day($.t, "Mars/Olympus") >= 0', "Mars/Olympus"),
    ('time_of_day($.t, "america/denver") >= 0', "america/denver"),
    ('time_of_day($.t, 5) >= 0', "written in the expression"),
    ('time_of_day($.t, concat("America/", "Denver")) >= 0', "written in the expression"),
])
def test_a_zone_the_compiler_is_not_sure_of_is_uncompilable(src, why):
    with pytest.raises(C.Uncompilable) as e:
        _compile(src)
    assert why in e.value.reason


def test_without_the_evaluators_zone_list_nothing_compiles():
    with pytest.raises(C.Uncompilable) as e:
        C.compile_predicate(EXPR.parse('time_of_day($.t, "UTC") >= 0'), column="data")
    assert "zone list" in e.value.reason


def test_wrong_arity_is_the_evaluators_null():
    for src in ('time_of_day($.t)', 'time_of_day($.t, "UTC", "UTC")', 'time_of_day()'):
        assert C.compile_ast(EXPR.parse(src), column="data", time_zones=ZONES).sql == "xpr.j(NULL::float8)"
        assert EXPR.evaluate(EXPR.parse(src), {"t": "2026-08-20T17:00:00Z"}) is None


# ---- Python's clock for a zone ------------------------------------------------------------------

def test_denvers_clock_in_2026():
    starts, offsets = C.zone_transitions("America/Denver")
    at = dict(zip(starts, offsets))
    assert at[1772960400] == -6 * 3600        # 2026-03-08T09:00:00Z: 2:00 MST becomes 3:00 MDT
    assert at[1793520000] == -7 * 3600        # 2026-11-01T08:00:00Z: 2:00 MDT becomes 1:00 MST
    assert starts[0] == C.ZONE_CHECK_FROM and offsets[0] == -(6 * 3600 + 59 * 60 + 56)  # local mean time
    assert starts == sorted(starts) and len(set(starts)) == len(starts)


def test_a_zone_without_changes_is_one_offset():
    assert C.zone_transitions("UTC") == ([C.ZONE_CHECK_FROM], [0])
    assert C.zone_transitions("Etc/GMT+12") == ([C.ZONE_CHECK_FROM], [-12 * 3600])


# ---- in the database ----------------------------------------------------------------------------

ROWS = ["2026-08-20T23:00:00Z", "2026-08-20T17:00:00Z", "2026-08-20T16:59:59Z",
        "2026-08-20T16:59:59.9Z", "2026-03-08T08:59:59Z", "2026-03-08T09:00:00Z",
        "2026-11-01T07:30:00Z", "2026-11-01T08:30:00Z", "2026-08-21T05:59:59Z",
        "2026-08-20T23:00:00+05:30", "2026-08-20", "teatime", None, 5, "1800-01-01T12:00:00Z",
        "0001-01-01T00:00:00Z", "9999-12-31T23:00:00Z"]

PREDICATES = ['time_of_day($.t, "{z}") >= 61200', 'time_of_day($.t, "{z}") < 61200',
              'time_of_day($.t, "{z}") == 5400', '(time_of_day($.t, "{z}") >= 79200) or (time_of_day($.t, "{z}") < 7200)',
              'not (time_of_day($.t, "{z}") >= 0)', 'time_of_day($.t, "{z}") == null']


@pytest.fixture(scope="module")
def db():
    cx = _connect()
    sys.path.insert(0, str(ROOT / "runtime"))
    import this_runtime
    this_runtime.install(cx)           # the runtime under test, never what a database happens to hold
    cx.execute("CREATE TEMP TABLE t98 (k int, data jsonb)")
    with cx.cursor() as cur:
        cur.executemany("INSERT INTO t98 VALUES (%s, %s::jsonb)",
                        [(i, json.dumps({} if t is None else {"t": t})) for i, t in enumerate(ROWS)])
    yield cx
    cx.close()


def _sql_keys(db, src, zones=ZONES):
    c = _compile(src, zones)
    params = dict(c.params, ctx="{}")
    return sorted(r[0] for r in db.execute(f"SELECT k FROM t98 WHERE {c.sql}", params).fetchall())


def _py_keys(src):
    ast = EXPR.parse(src)
    return sorted(i for i, t in enumerate(ROWS)
                  if EXPR.truthy(EXPR.evaluate(ast, {} if t is None else {"t": t})))


@needs_db
@pytest.mark.parametrize("zone", ["America/Denver", "UTC", "Asia/Kolkata", "Asia/Kathmandu",
                                  "Pacific/Kiritimati", "Etc/GMT+12", "Australia/Lord_Howe"])
def test_rows_equal_the_evaluators(db, zone):
    for p in PREDICATES:
        src = p.format(z=zone)
        assert _sql_keys(db, src) == _py_keys(src), src


@needs_db
def test_the_outcome_rows_in_denver(db):
    """5:00 PM in Denver on Aug 20 is 23:00Z; the row a second before 5 PM is not in it."""
    src = 'time_of_day($.t, "America/Denver") >= 61200'
    keys = _sql_keys(db, src)
    assert ROWS.index("2026-08-20T23:00:00Z") in keys
    assert ROWS.index("2026-08-20T16:59:59Z") not in keys     # 10:59:59 in Denver


@needs_db
def test_the_guard_runs_once_per_statement_before_the_rows(db):
    c = _compile('time_of_day($.t, "America/Denver") >= 61200')
    plan = "\n".join(r[0] for r in db.execute(f"EXPLAIN SELECT k FROM t98 WHERE {c.sql}", dict(c.params, ctx="{}")))
    assert "InitPlan" in plan, plan


@needs_db
def test_the_guard_refuses_a_zone_whose_clocks_differ(db, monkeypatch):
    """Python's clock for Denver, moved by an hour from 2026-11-01: the database's differs, so the
    statement is refused by name, with the date, and no row comes back."""
    import psycopg
    starts, offsets = C.zone_transitions("America/Denver")
    moved = [o + 3600 if s >= 1793520000 else o for s, o in zip(starts, offsets)]
    monkeypatch.setattr(C, "zone_transitions", lambda z: (starts, moved) if z == "America/Denver" else C.zone_transitions(z))
    with pytest.raises(psycopg.Error) as e:
        _sql_keys(db, 'time_of_day($.t, "America/Denver") >= 61200')
    assert e.value.sqlstate == "XPR05"
    assert "America/Denver" in str(e.value) and "2026-11-01" in str(e.value)


@needs_db
def test_the_guard_finds_a_change_pythons_clock_does_not_have(db, monkeypatch):
    """Edmonton's shape: one database has a change the other doesn't. Python's Denver clock with
    Nov 2026 and Mar 2027 removed (so it keeps MDT until Nov 2027); no change of Python's is near
    the database's Nov 1 2026, so only the daily samples can find it."""
    import psycopg
    starts, offsets = C.zone_transitions("America/Denver")
    gone = {1793520000, 1805014800}            # 2026-11-01T08:00Z, 2027-03-14T09:00Z
    assert gone <= set(starts)
    kept = [(s, o) for s, o in zip(starts, offsets) if s not in gone]
    monkeypatch.setattr(C, "zone_transitions",
                        lambda z: ([s for s, _ in kept], [o for _, o in kept]) if z == "America/Denver" else C.zone_transitions(z))
    with pytest.raises(psycopg.Error) as e:
        _sql_keys(db, 'time_of_day($.t, "America/Denver") >= 61200')
    assert e.value.sqlstate == "XPR05" and "2026-11-01" in str(e.value)


@needs_db
def test_the_guard_finds_a_change_an_hour_out_on_the_same_day(db, monkeypatch):
    """Python's Nov 1 2026 change put at 09:00Z instead of 08:00Z: both clocks agree at every noon,
    so only the probes at the change itself can find it."""
    import psycopg
    starts, offsets = C.zone_transitions("America/Denver")
    moved = [s + 3600 if s == 1793520000 else s for s in starts]
    monkeypatch.setattr(C, "zone_transitions", lambda z: (moved, offsets) if z == "America/Denver" else C.zone_transitions(z))
    with pytest.raises(psycopg.Error) as e:
        _sql_keys(db, 'time_of_day($.t, "America/Denver") >= 61200')
    assert e.value.sqlstate == "XPR05" and "2026-11-01" in str(e.value)


@needs_db
def test_the_guard_refuses_a_zone_the_database_does_not_know(db, monkeypatch):
    import psycopg
    zones = set(ZONES) | {"Mars/Olympus"}
    monkeypatch.setattr(C, "zone_transitions", lambda z: ([C.ZONE_CHECK_FROM], [0]))
    with pytest.raises(psycopg.Error) as e:
        _sql_keys(db, 'time_of_day($.t, "Mars/Olympus") >= 0', zones=zones)
    assert e.value.sqlstate == "XPR05" and "Mars/Olympus" in str(e.value)


@needs_db
def test_every_listed_zone_agrees_or_is_refused(db):
    """Every zone the evaluator lists: either the guard passes and the database's clock equals
    Python's at a spread of instants, or the guard refuses it by name. Never a third outcome."""
    import psycopg
    instants = ["1800-01-01T12:00:00Z", "1900-01-01T00:00:00Z", "1950-06-15T12:00:00Z",
                "1970-01-01T00:00:00Z", "2026-01-15T03:17:41Z", "2026-07-15T21:44:09Z",
                "2026-12-15T09:00:00Z", "2040-07-01T12:00:00Z", "2100-12-31T12:00:00Z"]
    refused, wrong = [], []
    for zone in sorted(ZONES):
        c = C.compile_ast(EXPR.parse(f'time_of_day($.t, "{zone}")'), column="x", time_zones=ZONES)
        try:
            got = [r[0] for r in db.execute(
                f"SELECT {c.sql} FROM jsonb_array_elements(%(ts)s::jsonb) WITH ORDINALITY AS a(t, n),"
                f" LATERAL (SELECT jsonb_build_object('t', a.t) AS x) b ORDER BY n",
                dict(c.params, ctx="{}", ts=json.dumps(instants))).fetchall()]
        except psycopg.Error as e:
            assert e.sqlstate == "XPR05" and zone in str(e), (zone, e.sqlstate, str(e))
            refused.append(zone)
            continue
        want = [EXPR.evaluate(EXPR.parse(f'time_of_day($.t, "{zone}")'), {"t": t}) for t in instants]
        got = [None if g is None else json.loads(g) if isinstance(g, str) else g for g in got]
        if got != want:
            wrong.append((zone, got, want))
    assert not wrong, wrong[:5]
    assert len(refused) < len(ZONES) // 2, f"refused {len(refused)}: {refused[:10]}"
    print(f"\n{len(refused)} of {len(ZONES)} zones refused by the guard on this machine: {refused}")
